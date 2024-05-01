from lib.networking.bluetooth.advertisements import le_advertisement


try:
  from gi.repository import GLib
except ImportError:
  GLib = None


class NordicDFULEAdvertisement(le_advertisement.LEAdvertisement):
  '''
  This class is used for Nordic's Mesh DFU (Device Firmware Upgrade) protocol. Commands and new
  firmware are placed within this BLE Advertisement packet and broadcasted out to all nearby
  devices.

  Links:
    - https://brillianthome.atlassian.net/wiki/spaces/HI/pages/68157441/OTA-Update+Info
    - https://infocenter.nordicsemi.com/topic/com.nordic.infocenter.meshsdk.v3.1.0/md_doc_libraries_dfu_dfu_protocol.html
  '''
  NORDIC_SERVICE_UUID_STR = "0000fee4-0000-1000-8000-00805f9b34fb"  # 16-Bit Form: "fee4"
  DBUS_OBJECT_NAME_SUFFIX = ".dfu"

  def __init__(self, loop, dfu_payload, transaction_id=None, relative_index=None, timeout=1):
    super().__init__(loop, timeout)
    # NOTE: Only 1 DFU advertisement can be active at a time.
    #       This is fine for now, since each DFU advertisement packet is broadcasted sequentially by
    #       the library.
    self._dbus_object_name += NordicDFULEAdvertisement.DBUS_OBJECT_NAME_SUFFIX
    self._payload = dfu_payload
    self.transaction_id = transaction_id
    self.relative_index = relative_index

  @property
  def ServiceData(self):
    return {self.NORDIC_SERVICE_UUID_STR: GLib.Variant("ay", bytes.fromhex(self._payload))}
