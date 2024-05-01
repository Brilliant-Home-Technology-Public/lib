import struct
import uuid

from lib.networking.bluetooth.advertisements import le_advertisement


try:
  from gi.repository import GLib
except ImportError:
  import sys
  print('Failed to import dbus libraries. Bluetooth LE will not work!', file=sys.stderr)
  GLib = None
  GLib_GError = Exception


class IBeaconLEAdvertisement(le_advertisement.LEAdvertisement):
  '''
  This class is used to represent an iBeacon-style BLE Advertisement packet.

  Links:
    - https://developer.apple.com/ibeacon/
    - https://en.wikipedia.org/wiki/IBeacon
  '''
  MAJOR = 0x1
  MINOR = 0x1
  TX_POWER = 0xb3

  APPLE_COMPANY_ID = 0x4c  # From Bluetooth SIG
  IBEACON_TYPE = 0x02
  DBUS_OBJECT_NAME_SUFFIX = ".iBeacon"

  def __init__(self, loop, uuid_str):
    super().__init__(loop)
    # NOTE: Only 1 iBeacon advertisement can be active at a time.
    #       This is fine for now, since there's only ever 1 iBeacon going at a time.
    self._dbus_object_name += IBeaconLEAdvertisement.DBUS_OBJECT_NAME_SUFFIX
    self._uuid = uuid.UUID(uuid_str)

  @property
  def ManufacturerData(self):
    suffix = struct.pack("<HHB", self.MAJOR, self.MINOR, self.TX_POWER)
    payload = b"".join((self._uuid.bytes, suffix))
    prefix = struct.pack('BB', self.IBEACON_TYPE, len(payload))
    full_data = GLib.Variant("ay", b"".join((prefix, payload)))
    manufacturing_data = {self.APPLE_COMPANY_ID: full_data}
    return manufacturing_data

  @staticmethod
  def is_ibeacon(device_info):
    ''' returns True if the manufacturing data is an iBeacon '''
    manufacturer_data = device_info.get("ManufacturerData", {})
    ibeacon_data = manufacturer_data.get(IBeaconLEAdvertisement.APPLE_COMPANY_ID)
    return (ibeacon_data
        and len(ibeacon_data) >= 2
        and ibeacon_data[0] == IBeaconLEAdvertisement.IBEACON_TYPE
    )
