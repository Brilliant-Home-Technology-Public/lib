import collections
import logging
import os.path

import lib.dbus.utils
import lib.networking.bluetooth.exceptions
import lib.utils


try:
  from gi._error import GError as GLib_GError
except ImportError:
  import sys
  print("Failed to import GLib. Bluetooth LE will not work.", file=sys.stderr)
  GLib_GError = Exception

log = logging.getLogger(__name__)

# Bluez DBus handles
BLUEZ_DBUS_SERVICE_NAME = "org.bluez"
BLUEZ_ADAPTER_OBJECT_PATH = "/org/bluez/hci0"
BLUEZ_MANAGER_OBJECT_PATH = "/"
BLUEZ_OBJECT_MANAGER_NAME = "org.freedesktop.DBus.ObjectManager"

# DBus configurations
DBUS_METHOD_TIMEOUT_SECS = 15

# DBus error messages
ADAPTER_GET_ERROR_MSG = "object does not export any interfaces"
ADAPTER_DISCONNECT_ERROR_MSG = "Message recipient disconnected from message bus without replying"
ADAPTER_TIMEOUT_ERROR_MSG = "Timeout was reached"
ADAPTER_NOT_READY_ERROR_MSG = "Resource Not Ready"
ADAPTER_OPERATION_IN_PROGRESS_ERROR_MSG = "Operation already in progress"
ADAPTER_CONNECTION_ABORT_ERROR_MSG = "le-connection-abort-by-local"
DBUS_UNKNOWN_OBJECT_ERROR = "org.freedesktop.DBus.Error.UnknownObject"

SYSFS_DURATION_PATH = "/sys/class/bluetooth/hci0/scan_duration"
SYSFS_FILTER_POLICY_PATH = "/sys/class/bluetooth/hci0/scan_filter_policy"


'''
From the Bluetooth Core Specification v4.2, 7.8.10:

LE_Scan_Interval:
  - This is defined as the time interval from when the Controller started its last LE scan
    until it begins the subsequent LE scan.
  - Range: 0x0004 to 0x4000
  - Default: 0x0010 (10 ms)
  - Time = N * 0.625 msec
  - Time Range: 2.5 msec to 10.24 seconds

LE_Scan_Window:
  - The duration of the LE scan. LE_Scan_Window shall be less than or equal to LE_Scan_Interval
  - Range: 0x0004 to 0x4000
  - Default: 0x0010 (10 ms)
  - Time = N * 0.625 msec
  - Time Range: 2.5 msec to 10.24 seconds
'''
ScanWindowTiming = collections.namedtuple("ScanWindowTiming", ["window", "interval"])


class BluezDBusAsyncClient:
  '''
  Asyncio wrapper for our calls to Bluez through the DBus.

  Given all calls through the DBus are blocking calls, this
  wraps all the blocking calls for other systems.
  '''

  def __init__(self, loop):
    self._loop = loop
    self._system_bus = None
    self._is_started = False
    self._glib_run_loop = lib.dbus.utils.GLibRunLoop()

  def _verify_system_bus_loaded(self):
    if not self._system_bus:
      raise lib.networking.bluetooth.exceptions.BluezDBusAsyncClientError("System Bus not loaded.")

  @property
  def _adapter(self):
    self._verify_system_bus_loaded()
    return self._system_bus.get(BLUEZ_DBUS_SERVICE_NAME, BLUEZ_ADAPTER_OBJECT_PATH)

  @property
  def _manager(self):
    self._verify_system_bus_loaded()
    return self._system_bus.get(BLUEZ_DBUS_SERVICE_NAME, BLUEZ_MANAGER_OBJECT_PATH)

  async def start(self):
    log.debug("BluezDBusAsyncClient: Start")
    if self._is_started:
      return
    self._glib_run_loop.start()
    self._system_bus = await self._loop.run_in_executor(
        None,
        self._get_system_bus,
    )
    self._is_started = True

  def _get_system_bus(self):
    system_bus = lib.dbus.utils.get_system_bus()
    system_bus.default_timeout = DBUS_METHOD_TIMEOUT_SECS
    return system_bus

  async def shutdown(self):
    self._glib_run_loop.shutdown()
    self._is_started = False

  async def set_adapter_property(self, property_name, property_value):
    '''
    Sets the adapter property.
    @property_name: property that needs to be updated
    @property_value: value to set the property to

    @return: True is the set succeeded and False otherwise
    '''
    return await self._loop.run_in_executor(
        None,
        self._set_adapter_property,
        property_name,
        property_value,
    )

  def _set_adapter_property(self, property_name, property_value):
    '''
    The blocking version of set_adapter_property.
    '''
    try:
      setattr(self._adapter, property_name, property_value)
      return True
    except (KeyError, GLib_GError) as e:
      if ((isinstance(e, KeyError) and ADAPTER_GET_ERROR_MSG in str(e)) or
          (isinstance(e, GLib_GError) and ADAPTER_DISCONNECT_ERROR_MSG in str(e))):
        log.debug("Failed to set adapter property %s to %s because a restart is in progress.",
                  property_name,
                  property_value)
        return False
      raise

  async def get_adapter_property(self, property_name):
    return await self._loop.run_in_executor(
        None,
        self._get_adapter_property,
        property_name,
    )

  def _get_adapter_property(self, property_name):
    '''
    The blocking version of get_adapter_property.
    '''
    try:
      return getattr(self._adapter, property_name)
    except (KeyError, GLib_GError) as e:
      if ((isinstance(e, KeyError) and ADAPTER_GET_ERROR_MSG in str(e)) or
          (isinstance(e, GLib_GError) and ADAPTER_DISCONNECT_ERROR_MSG in str(e))):
        log.debug("Failed to get adapter property %s because a restart is in progress.",
                  property_name)
        return None
      raise

  async def get_managed_objects(self):
    '''
    Gets all Bluez managed objects via DBus.

    @return: Mapping object paths to object data
    '''
    return await self._loop.run_in_executor(
        None,
        self._get_managed_objects,
    )

  def _get_managed_objects(self):
    '''
    The blocking version of get_managed_object.
    '''
    return self._manager.GetManagedObjects()

  async def register_advertisement(self, advertisement_object_path, advertisement_options):
    '''
    Registers an advertisement.

    @advertisement_object_path: The DBus object path the advertisement was published at
    advertisement_options: Options for this advertisement (e.g. timeouts)
    '''
    await self._loop.run_in_executor(
        None,
        self._register_advertisement,
        advertisement_object_path,
        advertisement_options,
    )

  def _register_advertisement(self, advertisement_object_path, advertisement_options):
    '''
    The blocking version of register_advertisement.
    '''
    self._adapter.RegisterAdvertisement(advertisement_object_path, advertisement_options)

  async def unregister_advertisement(self, advertisement_object_path):
    '''
    Unregisters an advertisement.

    @advertisement_object_path: The DBus object path the advertisement was published at
    '''
    await self._loop.run_in_executor(
        None,
        self._unregister_advertisement,
        advertisement_object_path,
    )

  def _unregister_advertisement(self, advertisement_object_path):
    '''
    The blocking version of unregister_advertisement.
    '''
    self._adapter.UnregisterAdvertisement(advertisement_object_path)

  async def set_discovery_filter(self,
                                 discovery_filter,
                                 force_duplicates=False,
                                 force_passive=False,
                                 window_timing=None,
  ):
    '''
    Sets the discovery filter.

    @discovery_filter: The discovery filter to use.
    '''
    await self._loop.run_in_executor(
        None,
        self._set_discovery_filter,
        discovery_filter,
        force_duplicates,
        force_passive,
        window_timing,
    )

  def _set_discovery_filter(self,
                            discovery_filter,
                            force_duplicates=False,
                            force_passive=False,
                            window_timing=None,
  ):
    '''
    The blocking version of set_discovery_filter
    '''
    # The DuplicateData parameter doesn't actually get passed through to the kernel, so we use a
    # hacked a setting in sysfs to force the kernel to set the value we want on the controller.
    scan_policy = (0x1 if force_duplicates else 0) | (0x4 if force_passive else 0)
    # Possible flag values (can be OR'd):
    # 0x1: Force reporting of duplicates
    # 0x2: Force use of whitelist
    # 0x4: Force passive scanning
    if os.path.exists(SYSFS_FILTER_POLICY_PATH):
      try:
        lib.utils.write_file(SYSFS_FILTER_POLICY_PATH, str(scan_policy))
      except OSError as e:
        log.warning("Failed to set scan policy %s: %r", scan_policy, e)
    else:
      log.warning("Scan policy file %s does not exist; cannot set filter policy!",
                  SYSFS_FILTER_POLICY_PATH)

    if window_timing:
      # The scan_duration file packs two 16-bit values into a 32-bit int. The lower 16 bits specify
      # the window and the upper 16 bits specify the interval
      packed = ((0xFFFF & window_timing.interval) << 16) | (0xFFFF & window_timing.window)
      if os.path.exists(SYSFS_DURATION_PATH):
        try:
          lib.utils.write_file(SYSFS_DURATION_PATH, str(packed))
        except OSError as e:
          log.warning("Failed to set scan window=%s, interval=%s, duration=%s: %r",
                      window_timing.window, window_timing.interval, packed, e)
      else:
        log.warning("Scan duration file %s does not exist; cannot set timing!",
                    SYSFS_DURATION_PATH)

    self._adapter.SetDiscoveryFilter(discovery_filter)

  async def start_discovery(self):
    '''
    Starts bluetooth discovery.
    '''
    await self._loop.run_in_executor(
        None,
        self._start_discovery,
    )

  def _start_discovery(self):
    '''
    The blocking version of start_discovery.
    '''
    self._adapter.StartDiscovery()

  async def stop_discovery(self):
    '''
    Stops bluetooth discovery.
    '''
    await self._loop.run_in_executor(
        None,
        self._stop_discovery,
    )

  def _stop_discovery(self):
    '''
    The blocking version of stop_discovery.
    '''
    self._adapter.StopDiscovery()

  async def remove_device(self, device_path):
    '''
    Removes a device from the Bluez's internal cache.

    @device_path: The DBus path of the object that we need to remove
    '''
    await self._loop.run_in_executor(
        None,
        self._remove_device,
        device_path,
    )

  def _remove_device(self, device_path):
    '''
    The blocking version of remove_device.
    '''
    self._adapter.RemoveDevice(device_path)

  async def device_signal_subscribe(self, signal_name, callback_func):
    '''
    Subscribes to device interface add and remove callbacks.

    @signal_name: The name of the signal to subscribe to
    @callback_func: The callback function to use when the signal triggers.
    '''
    return await self._loop.run_in_executor(
        None,
        self._device_signal_subscribe,
        signal_name,
        callback_func,
    )

  def _device_signal_subscribe(self, signal_name, callback_func):
    '''
    The blocking version of device_signal_subscribe.
    '''
    self._verify_system_bus_loaded()
    return self._system_bus.con.signal_subscribe(
        BLUEZ_DBUS_SERVICE_NAME,
        BLUEZ_OBJECT_MANAGER_NAME,
        signal_name,
        None,
        None,
        0,
        callback_func,
    )

  async def device_signal_unsubscribe(self, subscription_id):
    '''
    Unsubscribes to device interface add and remove callbacks.

    @subscription_id: The subscription id to unsubscribe from. The ID is
                      returned from self._system_bus.con.signal_subscribe.
    '''
    await self._loop.run_in_executor(
        None,
        self._device_signal_unsubscribe,
        subscription_id,
    )

  def _device_signal_unsubscribe(self, subscription_id):
    '''
    The blocking version of device_signal_unsubscribe
    '''
    self._verify_system_bus_loaded()
    self._system_bus.con.signal_unsubscribe(subscription_id)

  async def system_bus_subscribe(self, signal, callback):
    '''
    Subscribes to adapter interface add and remove callbacks.
    An example use case here would be to subscribe for the
    hci0 adapter add callback.

    @signal: The signal to attach the callback to. "InterfacesAdded"
             and "InterfacesRemoved" are examples of signals we can
             subscribe to.
    @callback: The callback function to use when the signal triggers.
    '''
    return await self._loop.run_in_executor(
        None,
        self._system_bus_subscribe,
        signal,
        callback,
    )

  def _system_bus_subscribe(self, signal, callback):
    '''
    The blocking version of system_bus_subscribe.
    '''
    self._verify_system_bus_loaded()
    return self._system_bus.subscribe(
        sender=BLUEZ_DBUS_SERVICE_NAME,
        signal=signal,
        signal_fired=callback,
    )

  async def system_bus_unsubscribe(self, subscription):
    '''
    Unsubscribe from the adapter interface add and remove callbacks.

    @subscription: The subscription to unsubscribe from.
    '''
    await self._loop.run_in_executor(
        None,
        self._system_bus_unsubscribe,
        subscription,
    )

  def _system_bus_unsubscribe(self, subscription):
    '''
    The blocking version of system_bus_unsubscribe.
    '''
    subscription.unsubscribe()

  async def connect_to_device(self, device):
    '''
    This makes a connection to a bluetooth device.

    @device: The device to be connected to.
    '''
    await self._loop.run_in_executor(
        None,
        self._connect_to_device,
        device,
    )

  def _connect_to_device(self, device):
    '''
    The blocking version of connect_to_device.
    '''
    device.connect()

  async def disconnect_from_device(self, device):
    '''
    This disconnects from a device that the control is already
    connected to.

    @device: The device to disconnect from.
    '''
    return self._loop.run_in_executor(
        None,
        self._disconnect_from_device,
        device,
    )

  def _disconnect_from_device(self, device):
    '''
    The blocking version of disconnect_from_device.
    '''
    device.disconnect()

  async def publish_advertisement_to_dbus(self, advertisement, dbus_object_name):
    '''
    This publishes an advertisement object to the DBus.

    @advertisement: The advertisement object to be published
    @dbus_object_name: The path to publish the object to
    '''
    return await self._loop.run_in_executor(
        None,
        self._publish_advertisement_to_dbus,
        advertisement,
        dbus_object_name,
    )

  def _publish_advertisement_to_dbus(self, advertisement, dbus_object_name):
    '''
    The blocking version of publish_advertisement_to_dbus.
    '''
    self._verify_system_bus_loaded()
    return self._system_bus.publish(dbus_object_name, advertisement)

  async def unpublish_advertisement_from_dbus(self, dbus_object):
    '''
    Unpublishes the advertisement object from the DBus.

    @dbus_object: The advertisement object to unpublish
    '''
    await self._loop.run_in_executor(
        None,
        self._unpublish_advertisement_from_dbus,
        dbus_object,
    )

  def _unpublish_advertisement_from_dbus(self, dbus_object):
    '''
    The blocking version of unpublish_advertisement_from_dbus.
    '''
    dbus_object.unpublish()

  async def restart_bluetooth_service(self):
    '''
    This restarts the bluetooth service via the system bus.
    '''
    await self._loop.run_in_executor(
        None,
        self._restart_bluetooth_service,
    )

  def _restart_bluetooth_service(self):
    '''
    The blocking version of restart_bluetooth_service
    '''
    self._verify_system_bus_loaded()
    self._system_bus.get(".systemd1").RestartUnit("bluetooth.service", "fail")
