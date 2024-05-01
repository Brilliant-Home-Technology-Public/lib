import functools
import logging
import re
import threading
import weakref

import lib.networking.utils as networking_utils
import lib.time


try:
  from gi.repository import GLib
except ImportError:
  import sys
  print('Failed to import dbus libraries. Bluetooth LE will not work!', file=sys.stderr)
  GLib = None


if GLib:
  # Force pygobject to generate Bytes class, as it's normally created on demand. This may avoid a
  # race condition where the class ends up partially initialized.
  GLib.Bytes  # pylint: disable=pointless-statement


log = logging.getLogger(__name__)

# Need a long timeout here because BlueZ/Linux has its own internal timeout mechanism and
# we'd rather allow that to operate (instead of competing with it)
DEFAULT_CONNECT_TIMEOUT_SECONDS = 120


class BluezDBusDeviceClient:
  '''
  Wrapper for managing GATT Services + Characteristics

  A GATT Device contains multiple Services.
  A Service contains multiple Characteristics
  '''

  MESH_PROXY_SERVICE_UUID_STR = "00001828-0000-1000-8000-00805f9b34fb"
  SERVICE_CACHE_TTL_MS = 10 * 60 * 1000  # 10 minutes

  def __init__(self, bus, device_path, bluetooth_services, rssi=None, service_data_cb=None):
    self.bus = bus
    self.device_path = device_path
    self.bluetooth_services = bluetooth_services
    self.rssi = rssi

    self.service_lock = threading.RLock()
    self.last_updated_timestamp = lib.time.get_current_time_ms()

    self.manager = self.bus.get("org.bluez", "/")
    self.mac_address = BluezDBusDeviceClient.device_path_to_mac(device_path)
    self.device = self.bus.get('org.bluez', device_path)

    # example service path: /org/bluez/hci0/dev_EB_34_4B_35_DF_50/service000e
    self.service_path_regex = re.compile(self.device_path + r'/service[0-9a-f]{4}$')

    self.services = {}  # {service_id : BluezDBusServiceClient}
    self.property_subscription_id = None
    self.data_in_service = None
    self.data_out_service = None
    self.service_data_cb = service_data_cb
    # Cache received Service Data because bluez's caching is not guaranteed to hold onto it.
    self.service_data_cache = {}  # UUID -> Tuple[data, last_seen_timestamp]

    self.callback_subscribe()
    # Handle any existing Service Data that wouldn't get handled with the PropertiesChanged callback.
    serv_data = self.service_data()
    if serv_data and self.service_data_cb:
      self.service_data_cb(serv_data)

  def __repr__(self):
    return str(self)

  def __str__(self):
    return "org.bluez.Device1 Wrapper: {}".format(self.device_path)

  @classmethod
  def device_path_to_mac(cls, device_path):
    if len(device_path) >= 17:
      try:
        return networking_utils.normalize_mac_address(device_path[-17:].replace('_', ':'))
      except ValueError:
        pass

    return ""

  def connect(self, timeout=DEFAULT_CONNECT_TIMEOUT_SECONDS):
    '''
    raises GLib.Error
    '''
    self.device.Connect(timeout=timeout)
    log.info("Bluetooth device %s connected.", self.mac_address)

  def make_permanent(self):
    try:
      self.device.Blocked = True
      self.device.Blocked = False
    except GLib.GError as e:
      log.warning("Failed to toggle Blocked property: %s", e)

  def signal_strength(self):
    ''' returns a value for signal strength from 0-100'''
    if self.rssi is None:
      return 0
    return self.rssi + 100

  def connected(self):
    try:
      return self.device.Connected
    except GLib.GError:
      return False

  def service_data(self):
    try:
      return self.device.ServiceData
    except GLib.GError:
      return None

  def RSSI(self):
    ''' RSSI is optional '''
    try:
      return self.device.RSSI
    except GLib.GError:
      return 0

  def get_service_data(self, cached_is_ok=True):
    ''' Returns the mesh network id of the device if specified '''
    service_data = self.service_data()

    # BlueZ seems to report only the most recently advertised service. Merge with the fresh
    # values from the cache so callers can see all services.
    if cached_is_ok:
      service_data = dict(service_data or {})  # Make a copy so we can freely mutate
      now_ms = lib.time.get_current_time_ms()
      for key in list(self.service_data_cache.keys()):  # Handle concurrent mutations
        cached_value, last_seen = self.service_data_cache.get(key, (None, 0))
        if (key not in service_data and
            cached_value is not None and
            now_ms - last_seen < self.SERVICE_CACHE_TTL_MS):
          service_data[key] = cached_value

    return service_data

  def network_id(self):
    ''' Returns the mesh network id of the device if specified '''
    service_data = self.get_service_data()

    if self.MESH_PROXY_SERVICE_UUID_STR not in service_data:
      return None

    network_id = service_data[self.MESH_PROXY_SERVICE_UUID_STR]
    if len(network_id) != 9 or network_id[0] != 0:
      return None

    return bytes(network_id[1:9])

  def proxy_connectivity_heuristic(self, now_ms):
    '''Returns a rough estimate of connectivity. Larger numbers (more positive) are better.'''
    _, last_update_ms = self.service_data_cache.get(
        self.MESH_PROXY_SERVICE_UUID_STR, (None, 0))

    # Gets larger as time progresses since the last update for the proxy service
    staleness_seconds = (now_ms - last_update_ms) // 1000
    metric = self.signal_strength() - staleness_seconds
    return metric

  def disconnect(self):
    try:
      self.device.Disconnect()
      log.info("Bluetooth device %s disconnected.", self.mac_address)
    except GLib.Error as e:
      log.warning("Device: %s error on disconnect() : %s", self, e)

  def get_device_services(self):
    # call after successful connection of device
    with self.service_lock:
      self._get_device_services_with_lock()

  def _get_device_services_with_lock(self):
    for object_path, _ in self.manager.GetManagedObjects().items():
      if not self.service_path_regex.match(object_path):
        continue

      service_id = object_path[-4:]
      prior_service = self.services.pop(service_id, None)
      if prior_service:
        prior_service.callback_unsubscribe()

      try:
        service = BluezDBusServiceClient(self.bus, object_path)
      except Exception as e:
        log.warning("Exception creating service from path: %s %s", object_path, e)
        continue

      service.get_service_characteristics()
      self.services[service_id] = service

    self.data_in_service = None
    self.data_out_service = None
    for _, service in self.services.items():
      if service.data_in_characteristic is not None:
        self.data_in_service = service
      if service.data_out_characteristic is not None:
        self.data_out_service = service

  @staticmethod
  def _properties_changed_cb(weak_self, connection, sender_name, object_path, interface_name, signal_name, parameters):
    self = weak_self()
    if not self:
      return

    now_ms = lib.time.get_current_time_ms()
    self.last_updated_timestamp = now_ms

    device_info = parameters[1]
    log.debug("Device property changed: %s, %s, %s", self.mac_address, signal_name, parameters)
    if 'RSSI' in device_info:
      try:
        self.rssi = int(device_info['RSSI'])
      except:
        log.warning("bad RSSI value: %s for device: %s", device_info['RSSI'], self.mac_address)

    if 'ServiceData' in device_info:
      service_data_dict = device_info['ServiceData']
      # Update the Service Data cache
      to_cache = {
          key: (data, now_ms) for key, data in service_data_dict.items()
      }
      self.service_data_cache.update(to_cache)

      if self.service_data_cb:
        self.service_data_cb(service_data_dict)

    if 'Connected' in device_info and not device_info['Connected']:
      log.info("Device %s disconnected", self.mac_address)
      with self.service_lock:
        # Proxy service characteristics are now invalid as well
        for service in self.services.values():
          service.callback_unsubscribe()

        self.services.clear()
        self.data_in_service = None
        self.data_out_service = None

  def callback_subscribe(self):
    # signal_subscribe api matches g_dbus_connection_signal_subscribe
    self.property_subscription_id = self.bus.con.signal_subscribe(
        'org.bluez',  # sender name
        "org.freedesktop.DBus.Properties",  # iface name
        "PropertiesChanged",  # signal name
        self.device_path,  # object path
        None,  # arg0
        0,  # GDBusSignalFlags
        functools.partial(self._properties_changed_cb, weakref.ref(self)),  # callback
    )

  def callback_unsubscribe(self):
    if self.property_subscription_id:
      self.bus.con.signal_unsubscribe(self.property_subscription_id)
      self.property_subscription_id = None

  def set_read_value_callback(self, read_value_callback):
    if not self.data_out_service:
      return

    self.data_out_service.set_read_value_callback(read_value_callback)

  def write_value(self, value):
    '''
    Writes bytes to a proxy data in characteristic

    raises GLib.Error
    '''
    if not self.data_in_service:
      log.warning("No data_in_service for device: %s", self.device_path)
      return
    self.data_in_service.write_value(value)


class BluezDBusServiceClient:
  '''
  Wrapper for managing GATT Characteristics

  A GATT Device contains multiple Services.
  A Service contains multiple Characteristics
  '''

  MESH_PROXY_DATA_IN_UUID_STR = "00002add-0000-1000-8000-00805f9b34fb"
  MESH_PROXY_DATA_OUT_UUID_STR = "00002ade-0000-1000-8000-00805f9b34fb"

  def __init__(self, bus, service_path):
    self.bus = bus
    self.manager = self.bus.get("org.bluez", "/")
    self.service_path = service_path
    self.service_id = service_path[-4:]

    # example characteristic path: /org/bluez/hci0/dev_EB_34_4B_35_DF_50/service000a/char000b
    self.characteristic_path_regex = re.compile(self.service_path + r'/char[0-9a-f]{4}$')
    self.characteristics = {}  # {characteristic_id : BluezDBusCharacteristicClient}
    self.characteristic_lock = threading.RLock()

    self.data_in_characteristic = None
    self.data_out_characteristic = None

  def __repr__(self):
    return str(self)

  def __str__(self):
    return "org.bluez.GattService1 Wrapper: {}".format(self.service_path)

  def write_value(self, value):
    '''
    Writes bytes to a proxy data in characteristic

    raises GLib.Error
    '''
    if not self.data_in_characteristic:
      log.warning("No data_in_characteristic for service: %s", self.service_path)
      return
    self.data_in_characteristic.write_value(value)

  def set_read_value_callback(self, read_value_callback):
    if not self.data_out_characteristic:
      return
    self.data_out_characteristic.read_value_callback = read_value_callback
    # Read any data we may have seen after connecting to the device but before setting the callback
    self.data_out_characteristic.read_value()

  def get_service_characteristics(self):
    with self.characteristic_lock:
      self._get_service_characteristics_with_lock()

  def _get_service_characteristics_with_lock(self):
    for object_path, _ in self.manager.GetManagedObjects().items():
      if not self.characteristic_path_regex.match(object_path):
        continue

      characteristic = BluezDBusCharacteristicClient(self.bus, object_path)
      if characteristic.UUID == self.MESH_PROXY_DATA_IN_UUID_STR:
        log.info("Found mesh proxy data in characteristic: %s", characteristic)
        self.data_in_characteristic = characteristic
        characteristic.callback_subscribe()
      elif characteristic.UUID == self.MESH_PROXY_DATA_OUT_UUID_STR:
        log.info("Found mesh proxy data out characteristic %s", characteristic)
        self.data_out_characteristic = characteristic
        characteristic.callback_subscribe()
        characteristic.start_notify()
      else:
        log.info("not a mesh proxy data characteristic: %s", characteristic)

      characteristic_id = object_path[-4:]
      self.characteristics[characteristic_id] = characteristic

  def callback_unsubscribe(self):
    with self.characteristic_lock:
      for characteristic in self.characteristics.values():
        characteristic.callback_unsubscribe()


class BluezDBusCharacteristicClient:
  '''
  This class uses dbus to communicate to Bluez

  It wraps Bluez Characteristic API

  A GATT Device contains multiple Services.
  A Service contains multiple Characteristics
  '''

  def __init__(self, bus, characteristic_path):
    self.bus = bus
    self.manager = self.bus.get("org.bluez", "/")
    self.characteristic_path = characteristic_path
    self.characteristic_id = characteristic_path[-4:]
    self.characteristic = self.bus.get('org.bluez', characteristic_path)
    self.property_subscription_id = None
    self.read_value_callback = lambda pdu: None  # callback takes 1 argument, byte string
    self.write_lock = threading.RLock()

  def __repr__(self):
    return str(self)

  def __str__(self):
    return "org.bluez.GattCharacteristic1 Wrapper: {}".format(self.characteristic_path)

  def acquire_notify(self):
    ''' Locks the characteristic. Read/writes must happen through the returned file descriptor '''
    try:
      fd, mtu = self.characteristic.AcquireNotify({})
    except GLib.Error as e:
      log.warning("Characteristic: %s error on acquire_notify : %s", self.characteristic_path, e)
    else:
      log.info("AcquireNotify success: fd %s mtu %s", fd, mtu)

  def read_value(self):
    '''
    raises GLib.Error
    '''
    try:
      self.characteristic.ReadValue({})
    except GLib.Error as e:
      log.warning("Characteristic: %s error on read_value : %s", self.characteristic_path, e)

  def start_notify(self):
    '''
    call start_notify before write_value to ensure a Brilliant Switch will not disconnect

    raises GLib.Error
    '''
    try:
      self.characteristic.StartNotify()
    except GLib.Error as e:
      log.warning("Characteristic: %s error on start_notify : %s", self.characteristic_path, e)

  def stop_notify(self):
    '''
    raises GLib.Error
    '''
    try:
      self.characteristic.StopNotify()
    except GLib.Error as e:
      log.warning("Characteristic: %s error on stop_notify : %s", self.characteristic_path, e)

  def write_value(self, value):
    '''
    raises GLib.Error
    '''
    with self.write_lock:
      self.characteristic.WriteValue(
          value,
          {"type": GLib.Variant("s", "command")},
      )

  def _properties_changed_cb(self, connection, sender_name, object_path, interface_name, signal_name, parameters):
    device_info = parameters[1]
    if 'Value' in device_info:
      value_update = bytes(device_info['Value'])
      self.read_value_callback(value_update)
    else:
      log.info("Characteristic properties changed: %s, %s", self.characteristic_path, parameters)

  @property
  def UUID(self):
    return self.characteristic.UUID

  def callback_subscribe(self):
    # signal_subscribe api matches g_dbus_connection_signal_subscribe
    self.property_subscription_id = self.bus.con.signal_subscribe(
        'org.bluez',  # sender name
        "org.freedesktop.DBus.Properties",  # iface name
        "PropertiesChanged",  # signal name
        self.characteristic_path,  # object path
        None,  # arg0
        0,  # GDBusSignalFlags
        self._properties_changed_cb,  # callback
    )

  def callback_unsubscribe(self):
    if self.property_subscription_id:
      self.bus.con.signal_unsubscribe(self.property_subscription_id)
      self.property_subscription_id = None
