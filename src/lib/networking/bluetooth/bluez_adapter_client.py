import asyncio
import collections
import enum
import functools
import logging
import queue
import re
import weakref

import lib.dbus.utils as dbus_utils
import lib.exceptions
from lib.logging import conditional_logger
from lib.networking.bluetooth import bluez_config_sysfs_helper
from lib.networking.bluetooth import bluez_dbus_async_client
from lib.networking.bluetooth import gatt
from lib.networking.bluetooth.advertisements import brilliant_device_provisioning_ibeacon
from lib.networking.bluetooth.advertisements import le_advertisement
import lib.networking.bluetooth.exceptions
import lib.queueing.work_queue
import lib.time
import thrift_types.bluetooth.constants as bluetooth_consts
import thrift_types.bluetooth.ttypes as bluetooth_ttypes


try:
  from gi._error import GError as GLib_GError
  from gi.repository import GLib
except ImportError:
  import sys
  print('Failed to import dbus libraries. Bluetooth LE will not work!', file=sys.stderr)
  GLib = None
  GLib_GError = Exception


log = logging.getLogger(__name__)
throttled_log = conditional_logger.ThrottledLogger(
    log_instance=log,
    default_policy=conditional_logger.ExponentialBackoffPolicy(),
)

# NOTE: According to the Bluetooth Core Specification v5.1,
#       the applicable time ranges for the BLE advertising
#       interval is 20ms to 10.24s (0x0020 to 0x4000 ticks).
# We have choosen 100ms here: 100ms/0.625secs/tick = 160 tick
# The choice was partially guided by apple's IBeacon documentation
# which suggests a 100ms advertising interval to optimize
# between frequency and power consumption.
ADVERTISING_INTERVAL_TICKS = 160


class AdvertisementQueueItem:

  def __init__(self, priority, relative_priority, advertisement):
    self.priority = priority
    self.relative_priority = relative_priority
    self.advertisement = advertisement

  def __lt__(self, other):
    return (self.priority, self.relative_priority) < (other.priority, other.relative_priority)

  def __eq__(self, other):
    return (self.priority == other.priority and
            self.relative_priority == other.relative_priority and
            self.advertisement == other.advertisement)


class ScanPriority(enum.Enum):
  LOW = -20
  MEDIUM = -10
  DEFAULT = 0
  HIGH = 10


class ScanParameters:

  def __init__(self,
               timeout_seconds,
               force_duplicates=False,
               force_passive=False,
               priority=ScanPriority.DEFAULT,
  ):
    self.timeout_seconds = timeout_seconds
    self.force_duplicates = force_duplicates
    self.force_passive = force_passive
    self.priority = priority

  def __eq__(self, other):
    return isinstance(other, ScanParameters) and vars(self) == vars(other)

  def __repr__(self):
    return "<{} {}>".format(
        type(self).__name__,
        ", ".join("{}={!r}".format(k, v) for k, v in vars(self).items()),
    )


class BluezDBusAdapterClient:
  '''
  This class wraps the Bluez Adapter dbus API.
  It is recommended to instantiate only one instance per bluetooth device.

  It acts as the bluetooth controller for a device for the following:
    - publish/unpublish ibeacon with a specific UUID
    - scanning for ibeacons with a specific UUID
    - scanning for gatt proxy services for mesh networks
    - writing messages to mesh networks
    - getting updates from mesh networks
  '''

  DBUS_DEVICE = 'org.bluez.Device1'
  DBUS_OBJECT_PATH = '/org/bluez/hci0'
  # If there are a lot of messages in the glib queue, it might take us awhile to register an adv.
  DBUS_METHOD_TIMEOUT_SECS = 15
  DBUS_PUBLISH_RETRY_COUNT = 3

  BLUETOOTH_CONNECTION_MAX_ATTEMPTS = 5
  MESH_CONNECTION_MAX_ATTEMPTS = 5

  BRILLIANT_OUI = "7C:10:15"

  DEVICE_PURGE_INTERVAL_MS = 60 * 60 * 1000

  MAX_NEARBY_DEVICES_ALLOWED_FOR_DUPLICATES = 20

  # Minimum above which connection attempts are expected to succeed
  LIKELY_CONNECTABLE_SIGNAL_STRENGTH_THRESHOLD = 15
  # Number of consecutive "connection abort" errors after which to assume a Wi-Fi coexistence issue
  COEXISTENCE_ERROR_HEURISTIC_THRESHOLD = 20

  SCAN_WINDOW_TIMING = {
      ScanPriority.HIGH: bluez_dbus_async_client.ScanWindowTiming(window=0x12, interval=0x12),
      ScanPriority.MEDIUM: bluez_dbus_async_client.ScanWindowTiming(window=0x12, interval=0x24),
      ScanPriority.LOW: bluez_dbus_async_client.ScanWindowTiming(window=0x10, interval=0x100),
  }

  def __init__(self, loop, force_mesh_proxy_mac_address=None):
    '''
    loop: event loop
    '''

    self._loop = loop
    self._active_advertisements_to_dbus_object_map = {}
    self._system_bus = dbus_utils.get_system_bus()
    self._system_bus.default_timeout = self.DBUS_METHOD_TIMEOUT_SECS
    self.bluez_dbus_async_client = bluez_dbus_async_client.BluezDBusAsyncClient(self._loop)
    self.bluez_config_sysfs_helper = bluez_config_sysfs_helper.BluezConfigSysfsHelper(self._loop)
    self._mesh_proxy_device = None  # BluezDBusDeviceClient
    self._mesh_network_id = None  # if specified we will only attempt to connect to this network
    self._devices_disallowed = set()
    self._devices_allowed = None
    self._restart_lock = asyncio.Lock()
    self._scan_lock = asyncio.Lock()
    self._is_started = False
    self._time_ms_since_last_device_purge = lib.time.get_current_time_ms()
    self.devices = {}  # key: mac_address, value: BluezDBusDeviceClient
    self.receive_mesh_pdu_callback = lambda pdu: None

    # example device path: /org/bluez/hci0/dev_EB_34_4B_35_DF_50
    self.device_path_regex = re.compile(
        self.DBUS_OBJECT_PATH + '/dev_([0-9A-F]{2}_){5}[0-9A-F]{2}$'
    )
    self._device_interfaces_change_subscriptions = []
    self._system_bus_subscriptions = []
    self._active_scan_parameters = None
    self._bluetooth_service_restart_in_progress = False
    self._restore_adapter_task = None
    self._stop_connections_for_advertisement = False
    self.service_data_handlers = collections.defaultdict(list)
    self._advertisement_queue = queue.PriorityQueue()
    self._advertisement_work_queue = lib.queueing.work_queue.SingletonJobWorkQueue(
        process_job_func=self._process_next_advertisement,
        loop=self._loop,
        replace_existing_job=False,
        expected_exceptions=GLib_GError,
    )
    self.mesh_connection_attempts = 0
    self._aborted_connection_count = 0
    self._force_mesh_proxy_mac_address = force_mesh_proxy_mac_address

  def set_mesh_network_id(self, network_id):
    '''
    network_id: 8 bytes of public information derived from a mesh netkey
                If not None, will only connect to devices with specified network_id
    '''
    if network_id is not None and len(network_id) != 8:
      log.error("Invalid network_id: %s needs to be 8 bytes!")
    self._mesh_network_id = network_id

  def set_device_address_filters(self, disallowed_mac_addresses, allowed_mac_addresses=None):
    '''
    disallowed_mac_addresses: A set of devices to which we should not attempt to connect
                              because they are owned by other proxies
    allowed_mac_addresses: A set of devices to which to limit proxy connections. If None,
                           connections to any MAC address not explicitly disallowed.
    '''
    self._devices_disallowed = disallowed_mac_addresses
    self._devices_allowed = allowed_mac_addresses

  async def _power_on(self):
    await self.bluez_dbus_async_client.set_adapter_property("Powered", True)
    await self.bluez_dbus_async_client.set_adapter_property("Discoverable", True)
    await self.bluez_dbus_async_client.set_adapter_property("Pairable", True)

  async def _power_off(self):
    await self.bluez_dbus_async_client.set_adapter_property("Powered", False)

  async def _restart_adapter(self, restart_daemon_on_failure=True):
    try:
      await self._power_off()
      await self._power_on()
    except Exception as restart_exception:
      if restart_daemon_on_failure:
        log.warning("Failed to toggle adapter power: %r. Restarting daemon!",
                    restart_exception)
        await self._restart_bluetooth_daemon()
      else:
        raise

  async def start(self):
    log.debug("BluezDBusAdapterClient: Starting client.")
    if self._is_started:
      log.debug("BluezDBusAdapterClient: Already started.")
      return

    self._advertisement_work_queue.start()
    await self.bluez_config_sysfs_helper.set_advertising_interval(
        min_interval_tick=ADVERTISING_INTERVAL_TICKS,
        max_interval_tick=ADVERTISING_INTERVAL_TICKS,
    )
    await self.bluez_dbus_async_client.start()
    await self._subscribe_device_interfaces_change_callback()
    await self._system_bus_bluez_interface_subscribe()
    await self._restart_adapter(restart_daemon_on_failure=True)
    self._is_started = True

  async def disconnect_from_mesh_network(self):
    if not self._mesh_proxy_device:
      return

    await self.bluez_dbus_async_client.disconnect_from_device(self._mesh_proxy_device)
    self._mesh_proxy_device = None

  async def _stop_scan(self):
    async with self._scan_lock:
      await self._stop_scan_with_lock()

  async def _stop_scan_with_lock(self):
    if not self._active_scan_parameters:
      return

    self._active_scan_parameters = None
    if self._bluetooth_service_restart_in_progress:
      return

    try:
      await self.bluez_dbus_async_client.stop_discovery()
    except GLib_GError as e:
      if "No discovery started" not in str(e):
        raise

  async def shutdown(self):
    log.debug("BluezDBusAdapterClient: Shutting down.")
    self._is_started = False
    self._advertisement_work_queue.shutdown()
    await self._unsubscribe_device_interfaces_change_callback()
    await self._unregister_all_advertisements()
    await self.disconnect_from_mesh_network()
    await self._stop_scan()
    await self.bluez_dbus_async_client.shutdown()

  async def _publish_advertisement_to_dbus(self, advertisement):
    if advertisement in self._active_advertisements_to_dbus_object_map:
      return self._active_advertisements_to_dbus_object_map[advertisement]

    for i in range(self.DBUS_PUBLISH_RETRY_COUNT):
      try:
        published = await self.bluez_dbus_async_client.publish_advertisement_to_dbus(
            advertisement,
            advertisement.dbus_object_name,
        )
        return published
      except GLib_GError as e:
        # This can happen when the previous unpublish
        # has yet to complete on the DBus.
        await asyncio.sleep(1)

    raise lib.networking.bluetooth.exceptions.BluezDBusRegisterAdvertisementError(
        "Failed to publish advertisement to DBus"
    )

  async def register_advertisement(self, advertisement):
    if not advertisement:
      raise lib.exceptions.BadArgsError("An advertisement must be specified!")
    if not isinstance(advertisement, le_advertisement.LEAdvertisement):
      raise lib.networking.bluetooth.exceptions.BluezDBusRegisterAdvertisementError(
          "Unsupported advertisement packet class: {packet_type}".format(
              packet_type=type(advertisement),
          )
      )
    try:
      published_object = await self._publish_advertisement_to_dbus(advertisement)
      self._active_advertisements_to_dbus_object_map[advertisement] = published_object

      adv_options = dict(
          Timeout=GLib.Variant("u", advertisement.timeout),
      )
      await self.bluez_dbus_async_client.register_advertisement(
          advertisement.dbus_object_path,
          adv_options,
      )
    except Exception as e:
      log.warning("Encountered exception '%r' while trying to register advertisement.", e)
      await self._restart_bluetooth_daemon()
      raise

  async def enqueue_advertisement(self,
                                  advertisement,
                                  relative_index=0,
                                  priority=bluetooth_ttypes.AdvertisementPriority.LOW):
    if not advertisement:
      raise lib.exceptions.BadArgsError("An advertisement must be specified!")

    if not isinstance(advertisement, le_advertisement.LEAdvertisement):
      raise lib.networking.bluetooth.exceptions.BluezDBusAdapterError(
          "Unsupported advertisement packet class: {packet_type}".format(
              packet_type=type(advertisement),
          )
      )

    advertisement.register_adv_release_callback(self._advertisement_released)
    self._advertisement_queue.put(
        AdvertisementQueueItem(
            priority,
            relative_index,
            advertisement,
        )
    )
    self._advertisement_work_queue.add_job("")

  async def _process_next_advertisement(self, job):
    if self._bluetooth_service_restart_in_progress:
      log.debug("BluezDBusAdapterClient: Bluetooth service restart in progress. "
                "Waiting for InterfaceAdded callback to requeue.")
      return

    num_supported_instances = await self.bluez_dbus_async_client.get_adapter_property(
        "SupportedInstances"
    )
    # The adapter may support broadcasting multiple advertisements, but that currently doesn't work
    # with how we register the advertisement objects on D-Bus.
    if self._active_advertisements_to_dbus_object_map:
      log.info("BluezDBusAdapterClient: Have active advertisement(s). Waiting for release.")
      return

    if num_supported_instances < 1:
      log.error("No known active advertisements, but no slots available!")
      # TODO Does this actually happen? If so, do we need to restart BlueZ to recover?
      return

    try:
      next_advertisement_queue_item = self._advertisement_queue.get_nowait()
      if next_advertisement_queue_item:
        await self.register_advertisement(next_advertisement_queue_item.advertisement)
    except queue.Empty:
      log.debug("BluezDBusAdapterClient: No advertisement remaining.")
      return
    except GLib_GError as e:
      # We are requeueing the advertisement in _restart_bluetooth_daemon because
      # that is the central point at which any restart process will call into
      # to restart the bluetooth daemon
      log.debug("BluezDBusAdapterClient: Encountered '%r' error when registering "
               "advertisement.", e)

  async def _advertisement_released(self, advertisement):
    log.debug("BluezDBusAdapterClient: Advertisement released")
    published_object = self._active_advertisements_to_dbus_object_map.pop(advertisement, None)
    if published_object:
      await self.bluez_dbus_async_client.unpublish_advertisement_from_dbus(published_object)
    # Enqueue job to push next advertisement out
    self._advertisement_work_queue.add_job("")

  async def _restart_bluetooth_daemon(self):
    log.debug("BluezDBusAdapterClient: Requesting daemon restart.")
    if self._bluetooth_service_restart_in_progress:
      return

    self._bluetooth_service_restart_in_progress = True

    for advertisement in list(self._active_advertisements_to_dbus_object_map.keys()):
      published_object = self._active_advertisements_to_dbus_object_map.pop(advertisement, None)
      if published_object:
        # The active advertisements might have changed
        await self.bluez_dbus_async_client.unpublish_advertisement_from_dbus(published_object)
        self._advertisement_queue.put(
            AdvertisementQueueItem(
                bluetooth_ttypes.AdvertisementPriority.HIGH,
                0,
                advertisement,
            )
        )

    try:
      await self.bluez_dbus_async_client.restart_bluetooth_service()
    except GLib_GError as e:
      log.error("BluezDBusAdapterClient: Failed to restart bluetooth.service due to '%r'.", e)
      self._bluetooth_service_restart_in_progress = False

  async def unregister_advertisement(self, advertisement):
    if self._bluetooth_service_restart_in_progress:
      return

    if not advertisement:
      raise lib.exceptions.BadArgsError("An advertisement must be specified.")

    if not isinstance(advertisement, le_advertisement.LEAdvertisement):
      raise lib.networking.bluetooth.exceptions.BluezDBusAdapterError(
          "Unsupported advertisement packet class: {packet_type}.".format(
              packet_type=type(advertisement),
          )
      )

    published_object = self._active_advertisements_to_dbus_object_map.pop(advertisement, None)
    if not published_object:
      # The timeout for the advertisement triggered
      # resulting in the removal of the advertisement
      # from this set.
      return

    try:
      await self.bluez_dbus_async_client.unregister_advertisement(advertisement.dbus_object_path)
    except GLib_GError as e:
      # If the advertisement does not exists, the
      # advertisement might have already timed out.
      # Proceed with the unpublishing of the dbus
      # object from the DBus.
      if "DoesNotExist" not in str(e):
        raise

    await self.bluez_dbus_async_client.unpublish_object_from_dbus(published_object)

  async def _unregister_all_advertisements(self):
    # Iterating over a list of the keys because undergister would modify the active advert
    # to dbus object map dict
    for advertisement in list(self._active_advertisements_to_dbus_object_map.keys()):
      try:
        await self.unregister_advertisement(advertisement)
      except Exception as e:
        log.error("Error unregistering advertisement: %s", e)

  async def is_adapter_powered(self):
    powered = await self.bluez_dbus_async_client.get_adapter_property("Powered")
    return powered or False

  async def _prune_stale_brilliant_devices(self, now_ms):
    mac_addresses_to_remove = []
    for mac_address, device in self.devices.items():
      ms_since_last_updated = now_ms - device.last_updated_timestamp
      if ms_since_last_updated > self.DEVICE_PURGE_INTERVAL_MS:
        if device != self._mesh_proxy_device:
          log.info("Removing device at %s; hasn't been updated in last %sms",
                   mac_address, ms_since_last_updated)
          mac_addresses_to_remove.append(mac_address)
        else:
          log.warning("Mesh proxy device %s not updated in %s ms!",
                      mac_address, ms_since_last_updated)

    for mac_address in mac_addresses_to_remove:
      await self._remove_device(mac_address=mac_address)

  async def scan(self,
                 timeout_seconds,
                 force_duplicates=None,
                 force_passive=False,
                 priority=ScanPriority.DEFAULT,
  ):
    log.debug("BluezDBusAdapterClient: Scan started.")
    if self._bluetooth_service_restart_in_progress:
      return

    if force_duplicates is None:
      # Only enable duplicates if we know for sure we are under the threshold (i.e. the scan has
      # already had a chance to run and pick up some devices).
      force_duplicates = bool(
          self.devices and
          len(self.devices) <= self.MAX_NEARBY_DEVICES_ALLOWED_FOR_DUPLICATES
      )

    next_scan_parameters = ScanParameters(
        timeout_seconds=timeout_seconds,
        force_duplicates=force_duplicates,
        force_passive=force_passive,
        priority=priority,
    )
    if self._active_scan_parameters and self._active_scan_parameters != next_scan_parameters:
      log.info("Scan parameters have changed. Stopping active scan.")
      await self._stop_scan()

    self._active_scan_parameters = next_scan_parameters

    discovering = await self.bluez_dbus_async_client.get_adapter_property("Discovering")
    if not discovering:
      await self._start_scan()
    else:
      log.debug("BluezDBusAdapterClient: Scan already in progress.")

    await self._curate_bluez_devices()

  async def _start_scan(self):
    async with self._scan_lock:
      await self._start_scan_with_lock()

  async def _start_scan_with_lock(self):
    log.info("Starting scan with parameters %r", self._active_scan_parameters)
    # Replicate prior behavior by using most aggressive setting as default
    window_timing = self.SCAN_WINDOW_TIMING.get(
        self._active_scan_parameters.priority, self.SCAN_WINDOW_TIMING[ScanPriority.HIGH])

    try:
      await self.bluez_dbus_async_client.set_discovery_filter(
          {
              "Transport": GLib.Variant("s", "le"),
              "DuplicateData": GLib.Variant("b", self._active_scan_parameters.force_duplicates),
          },
          force_passive=self._active_scan_parameters.force_passive,
          force_duplicates=self._active_scan_parameters.force_duplicates,
          window_timing=window_timing,
      )
    except (KeyError, GLib_GError) as e:
      if ((isinstance(e, KeyError) and bluez_dbus_async_client.ADAPTER_GET_ERROR_MSG in str(e)) or
          (isinstance(e, GLib_GError) and bluez_dbus_async_client.ADAPTER_NOT_READY_ERROR_MSG in str(e)) or
          (isinstance(e, GLib_GError) and bluez_dbus_async_client.ADAPTER_TIMEOUT_ERROR_MSG in str(e))):
        self._active_scan_parameters = None
        await self._restart_bluetooth_daemon()
      raise

    try:
      await self.bluez_dbus_async_client.start_discovery()
    except GLib_GError as e:
      self._active_scan_parameters = None

      if (bluez_dbus_async_client.ADAPTER_TIMEOUT_ERROR_MSG in str(e) or
          bluez_dbus_async_client.ADAPTER_NOT_READY_ERROR_MSG in str(e)):
        await self._restart_bluetooth_daemon()

      if bluez_dbus_async_client.ADAPTER_OPERATION_IN_PROGRESS_ERROR_MSG not in str(e):
        raise

    if self._active_scan_parameters and self._active_scan_parameters.timeout_seconds:
      await asyncio.sleep(self._active_scan_parameters.timeout_seconds)
      await self._stop_scan_with_lock()
      self._active_scan_parameters = None

  async def _curate_bluez_devices(self):
    now_ms = lib.time.get_current_time_ms()
    purge = now_ms > (self._time_ms_since_last_device_purge + self.DEVICE_PURGE_INTERVAL_MS)

    await self._prune_stale_brilliant_devices(now_ms)

    managed_objects_dict = await self.bluez_dbus_async_client.get_managed_objects()
    for object_path, object_data in managed_objects_dict.items():
      if not self.device_path_regex.match(object_path):
        # drop paths like '/org/bluez' or '/org/bluez/hci0'
        continue

      device_info = object_data.get(self.DBUS_DEVICE)
      await self._maybe_add_device(object_path, device_info, purge)

    if purge:
      self._time_ms_since_last_device_purge = now_ms

  def get_fault_conditions(self):
    faults = set()
    # Assume we are experiencing a conflict with Wi-Fi coexistence on the radio if connections have
    # failed repeatedly (and not likely due to signal strength)
    if self._aborted_connection_count > self.COEXISTENCE_ERROR_HEURISTIC_THRESHOLD:
      faults.add(bluetooth_ttypes.FaultCondition.WIFI_COEXISTENCE_CONFLICT)

    return faults

  async def get_service_information(self, mac_address, service_uuid):
    device = self.devices.get(mac_address)
    if not device:
      return None

    advertised_services = await self._loop.run_in_executor(
        None,
        device.get_service_data,
    )

    service_bytes_list = (advertised_services or {}).get(service_uuid)
    # BlueZ returns service data as a list of individual bytes
    return bytes(service_bytes_list) if service_bytes_list else None

  def register_service_data_handler(self, service_uuid, service_data_handler):
    service_data_weak_method = weakref.WeakMethod(service_data_handler)
    if service_data_weak_method not in self.service_data_handlers[service_uuid]:
      self.service_data_handlers[service_uuid].append(service_data_weak_method)

  def unregister_service_data_handler(self, service_uuid, service_data_handler):
    service_data_weak_method = weakref.WeakMethod(service_data_handler)
    if service_data_weak_method in self.service_data_handlers[service_uuid]:
      self.service_data_handlers[service_uuid].remove(service_data_weak_method)

  def _handle_service_data(self, service_data_dict):
    for service_data_uuid, service_data in service_data_dict.items():
      for service_data_handler_weak_method in self.service_data_handlers.get(service_data_uuid, []):
        service_data_handler = service_data_handler_weak_method()
        if service_data_handler:
          asyncio.run_coroutine_threadsafe(service_data_handler(service_data), self._loop)

  async def _maybe_add_device(self, object_path, device_info, purge=False):
    if not device_info:
      return

    mac_address = device_info.get("Address")
    if not mac_address:
      return

    if mac_address in self.devices:
      return

    bluetooth_services = []

    device_name = device_info.get("Name")
    uuids = device_info.get("UUIDs")
    service_data = device_info.get("ServiceData", {})

    if brilliant_device_provisioning_ibeacon.BrilliantDeviceProvisioningIBeacon.is_beacon_instance(
        device_info
    ):
      bluetooth_services.append(bluetooth_consts.BluetoothService.BRILLIANT_CONTROL_PROVISIONING)

    if bluetooth_consts.NORDIC_SERVICE_UUID_STR in service_data:
      bluetooth_services.append(bluetooth_consts.BluetoothService.NORDIC_SERVICE)

    device_mac_address = device_info.get("Address")
    device_has_brilliant_mac = (device_mac_address and
                                device_mac_address.startswith(self.BRILLIANT_OUI))
    if device_has_brilliant_mac:
      if bluetooth_consts.MESH_PROXY_SERVICE_UUID_STR in uuids:
        bluetooth_services.append(bluetooth_consts.BluetoothService.MESH_PROXY)
      if bluetooth_consts.MESH_PROV_SERVICE_UUID_STR in uuids:
        bluetooth_services.append(bluetooth_consts.BluetoothService.MESH_PROVISIONING)

    if not bluetooth_services and not device_has_brilliant_mac:
      # Bluez can build up a big device cache, which slows down the GetManagedObjects call.
      # Proactively remove devices that do not have bluetooth services we care about,
      if purge:
        await self._remove_device(object_path=object_path)
      return

    rssi = device_info.get('RSSI')
    try:
      device = await self._loop.run_in_executor(
          None,
          self._blocking_create_dbus_device_client,
          object_path,
          bluetooth_services,
          rssi,
      )
      self.devices[mac_address] = device
    except Exception as e:
      log.warning("BluezDBusAdapterClient: Exception creating device from path: %s %r.",
                  object_path, e)
      await self._remove_device(mac_address, object_path)

  def _blocking_create_dbus_device_client(self, object_path, bluetooth_services, rssi):
    device = gatt.BluezDBusDeviceClient(
        bus=self._system_bus,
        device_path=object_path,
        bluetooth_services=bluetooth_services,
        rssi=rssi,
        service_data_cb=self._handle_service_data,
    )
    device.make_permanent()
    return device

  def _blocking_unsubscribe_dbus_device_client(self, device):
    device.callback_unsubscribe()

  async def _remove_device(self, mac_address=None, object_path=None):
    remove_device_path = object_path
    if mac_address:
      device = self.devices.pop(mac_address, None)
      if device:
        self._loop.run_in_executor(
            None,
            self._blocking_unsubscribe_dbus_device_client,
            device,
        )
        remove_device_path = device.device_path
    if remove_device_path:
      try:
        await self.bluez_dbus_async_client.remove_device(remove_device_path)
      except GLib_GError as e:
        log.warning("Exception removing device from path: %r.", e)

  async def _system_bus_bluez_interface_subscribe(self):
    hci_adapter_added_subscription = await self.bluez_dbus_async_client.system_bus_subscribe(
        "InterfacesAdded",
        functools.partial(self._hci_adapter_added_callback, weakref.ref(self)),
    )
    self._system_bus_subscriptions.append(hci_adapter_added_subscription)

  @staticmethod
  def _hci_adapter_added_callback(weak_self, sender, obj, iface, signal, params):
    if params[0] == BluezDBusAdapterClient.DBUS_OBJECT_PATH and params[1].get("org.bluez.Adapter1"):
      self = weak_self()
      if not self:
        return

      log.debug("BluezDBusAdapterClient: HCI Adapter added.")
      self._restore_adapter_task = asyncio.ensure_future(
          self._restore_adapter_state_after_restart(),
          loop=self._loop,
      )

      def _log_exc(task):
        if not task.cancelled() and task.exception():
          log.error("Encountered exception restoring adapter state: %r", task.exception())
      self._restore_adapter_task.add_done_callback(_log_exc)

  async def _restore_adapter_state_after_restart(self):
    try:
      await self.bluez_config_sysfs_helper.set_advertising_interval(
          min_interval_tick=ADVERTISING_INTERVAL_TICKS,
          max_interval_tick=ADVERTISING_INTERVAL_TICKS,
      )
      await self._restart_adapter(restart_daemon_on_failure=False)
    finally:
      # Make sure we always unset this so we can try the restart again in the future
      self._bluetooth_service_restart_in_progress = False
    if self._active_scan_parameters and self._active_scan_parameters.timeout_seconds == 0:
      await self.scan(
          timeout_seconds=self._active_scan_parameters.timeout_seconds,
          force_duplicates=self._active_scan_parameters.force_duplicates,
          force_passive=self._active_scan_parameters.force_passive,
      )
    else:
      self._active_scan_parameters = None

  async def _subscribe_device_interfaces_change_callback(self):
    subscriptions_wanted = [
        ("InterfacesAdded", BluezDBusAdapterClient._device_interfaces_added_callback),
        ("InterfacesRemoved", BluezDBusAdapterClient._device_interfaces_removed_callback),
    ]
    for signal_name, callback_func in subscriptions_wanted:
      subscription = await self.bluez_dbus_async_client.device_signal_subscribe(
          signal_name,
          callback_func=functools.partial(callback_func, weakref.ref(self)),
      )
      self._device_interfaces_change_subscriptions.append(subscription)

  async def _unsubscribe_device_interfaces_change_callback(self):
    for subscription in self._device_interfaces_change_subscriptions:
      await self.bluez_dbus_async_client.device_signal_unsubscribe(subscription)
    self._device_interfaces_change_subscriptions = []

    for system_bus_subscription in self._system_bus_subscriptions:
      await self.bluez_dbus_async_client.system_bus_unsubscribe(system_bus_subscription)
    self._system_bus_subscriptions = []

  @staticmethod
  def _device_interfaces_added_callback(weak_self,
                                        connection,
                                        sender,
                                        path,
                                        interface,
                                        signal,
                                        params):
    self = weak_self()
    if not self:
      return
    object_path = params[0]
    device_info = params[1].get(self.DBUS_DEVICE)
    interface_added_task = asyncio.ensure_future(
        self._maybe_add_device(object_path, device_info), loop=self._loop
    )
    if not self._advertisement_queue.empty():
      self._advertisement_work_queue.add_job("", delay=5)

  @staticmethod
  def _device_interfaces_removed_callback(weak_self,
                                          connection,
                                          sender,
                                          sender_path,
                                          sender_interface,
                                          signal,
                                          params):
    self = weak_self()
    if not self:
      return

    try:
      path, interfaces = params
    except (TypeError, ValueError):
      log.error("Failed to unpack InterfacesRemoved parameters: %r", params)
      return

    if self.DBUS_DEVICE not in interfaces:
      return

    mac_address = gatt.BluezDBusDeviceClient.device_path_to_mac(path)
    if mac_address not in self.devices:
      return

    self.devices.pop(mac_address)

  async def restart_mesh_connection(self):
    if self._stop_connections_for_advertisement or self._bluetooth_service_restart_in_progress:
      return

    if self._restart_lock.locked():
      log.debug("BluezDBusAdapterClient: Restart mesh connection already being attempted.")
      return

    async with self._restart_lock:
      if await self._connect_to_mesh_network():
        self.mesh_connection_attempts = 0
        if self._stop_connections_for_advertisement and self._mesh_proxy_device:
          await self.bluez_dbus_async_client.disconnect_from_device(self._mesh_proxy_device)
        return

      self.mesh_connection_attempts += 1

      if self.mesh_connection_attempts > self.MESH_CONNECTION_MAX_ATTEMPTS:
        self.mesh_connection_attempts = 0
        log.warning("BluezDBusAdapterClient: Failed to connect to mesh after %d tries. "
                    "Restarting adapter.", self.MESH_CONNECTION_MAX_ATTEMPTS)
        await self._restart_adapter(restart_daemon_on_failure=True)

  def connected_to_mesh_network(self):
    if not self._mesh_proxy_device:
      return False

    if not self._mesh_proxy_device.connected():
      return False

    have_proxy_services = bool(
        self._mesh_proxy_device.data_in_service and self._mesh_proxy_device.data_out_service)

    return have_proxy_services

  def mesh_proxy_mac_address(self):
    if not self._mesh_proxy_device:
      return None

    return self._mesh_proxy_device.mac_address

  async def _maybe_select_device_as_mesh_proxy_device(self, device):
    for _ in range(self.BLUETOOTH_CONNECTION_MAX_ATTEMPTS):
      # Sleep before the first attempt so there's time for BlueZ to discover the services
      await asyncio.sleep(1)
      if not device.connected():
        log.warning("Device %s disconnected before services discovered!", device)
        return False

      log.debug("BluezDBusAdapterClient: Getting device services.")
      await self._read_device_services(device)

      if self._stop_connections_for_advertisement:
        return False

      if device.data_in_service and device.data_out_service:
        log.debug("BluezDBusAdapterClient: Connection to mesh proxy device %s successful.", device)
        await self._loop.run_in_executor(None, device.set_read_value_callback, self.receive_mesh_message)
        self._mesh_proxy_device = device
        return True

    return False

  async def _connect_to_device(self, device):
    prior_scan_parameters = self._active_scan_parameters
    log.debug("Temporarily disabling scanning before connecting to %s", device)
    await self._stop_scan()
    try:
      return await self._connect_to_device_with_scanning_disabled(device)
    except asyncio.CancelledError:
      current_scan_parameters = None
      log.warning("Connect task was cancelled; not restoring scanning.")
      raise
    finally:
      if prior_scan_parameters:
        self._active_scan_parameters = prior_scan_parameters
        await self._start_scan()

  async def _connect_to_device_with_scanning_disabled(self, device):
    for attempt_num in range(self.BLUETOOTH_CONNECTION_MAX_ATTEMPTS):
      try:
        if self._stop_connections_for_advertisement:
          return False
        log.info("BluezDBusAdapterClient: Connection attempt #%d for %s.", attempt_num + 1, device)
        await self.bluez_dbus_async_client.connect_to_device(device)
        selected_as_proxy = await self._maybe_select_device_as_mesh_proxy_device(device)
        if selected_as_proxy:
          # Don't reset counter until we see a truly successful connection. Sometimes BlueZ claims
          # to have connected but then immediately sends a disconnect notification.
          self._aborted_connection_count = 0
          return True
        log.debug("BluezDBusAdapterClient: Disconnect from device %s.", device)
        await self.bluez_dbus_async_client.disconnect_from_device(device)
      except GLib_GError as e:
        log.info("BluezDBusAdapterClient: Failed to connect to device %s: %r",
                 device, e)

        if bluez_dbus_async_client.DBUS_UNKNOWN_OBJECT_ERROR in str(e):
          # BlueZ has deleted this device; stop trying to connect
          break

        if device.signal_strength() < self.LIKELY_CONNECTABLE_SIGNAL_STRENGTH_THRESHOLD:
          # Move on quickly from this device if we didn't think it was likely to succeed anyway
          break

        # Count all failed connections as aborts unless poor signal strength is a likely culprit
        self._aborted_connection_count += 1

    return False

  async def _read_device_services(self, device):
    await self._loop.run_in_executor(
        None,
        device.get_device_services,
    )

  async def _connect_to_mesh_network(self):
    if self._stop_connections_for_advertisement:
      return

    if self._mesh_proxy_device:
      log.debug("BluezDBusAdapterClient: Disconnecting from mesh proxy device: %s.",
                self._mesh_proxy_device)
      await self.disconnect_from_mesh_network()

    now_ms = lib.time.get_current_time_ms()
    # Make a local copy so external mutations don't cause problem
    devices_to_try = list(self.devices.items())
    devices_to_try.sort(
        key=lambda item: item[1].proxy_connectivity_heuristic(now_ms),
        reverse=True,
    )
    for mac_address, _ in devices_to_try:
      # Refetch device in case it's been removed
      device = self.devices.get(mac_address)
      if not device:
        continue

      if (self._force_mesh_proxy_mac_address and
          mac_address.lower() != self._force_mesh_proxy_mac_address.lower()):
        continue

      if self._devices_allowed is not None and mac_address not in self._devices_allowed:
        continue

      if mac_address in self._devices_disallowed:
        continue

      if self._mesh_network_id and self._mesh_network_id != device.network_id():
        log.debug("BluezDBusAdapterClient: Network IDs do not match")
        continue

      try:
        log.info("Connecting to mesh proxy device: %s.", mac_address)
        if await self._connect_to_device(device):
          return True
      except Exception as e:
        log.warning("Mesh connection error '%r': for device: %s.", e, mac_address)

    log.debug("BluezDBusAdapterClient: No mesh proxy device to connect to.")
    return False

  def _disconnect_from_mesh_network(self):
    if not self._mesh_proxy_device:
      return
    self._mesh_proxy_device.disconnect()
    self._mesh_proxy_device = None

  def forward_mesh_pdu(self, pdu):
    log.debug("Mesh Adapter TX: %s", pdu)
    if not self._mesh_proxy_device:
      log.info("Adapter: no mesh proxy device")
      return
    try:
      self._mesh_proxy_device.write_value(pdu)
    except Exception as e:
      log.warning("Bluetooth device error on write_value : %r", e)
      asyncio.ensure_future(
          self.restart_mesh_connection(),
          loop=self._loop,
      )

  def receive_mesh_message(self, pdu):
    log.debug("Mesh Adapter RX: %s", pdu)
    self.receive_mesh_pdu_callback(pdu)

  async def disable_connections_for_advertisements(self):
    log.debug("BluezDBusAdapterClient: Disabling connections for advertisement.")
    self._stop_connections_for_advertisement = True
    await self.disconnect_from_mesh_network()

  def enable_all_connections(self):
    self._stop_connections_for_advertisement = False
