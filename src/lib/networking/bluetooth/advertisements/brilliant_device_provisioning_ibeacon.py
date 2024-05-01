import array
import logging
import uuid

from lib.networking.bluetooth.advertisements import ibeacon_le_advertisement
import thrift_types.device_provisioning.constants as device_provisioning_consts


log = logging.getLogger(__name__)


class BrilliantDeviceProvisioningIBeacon(ibeacon_le_advertisement.IBeaconLEAdvertisement):

  UUID = device_provisioning_consts.DEVICE_PROVISIONING_SERVICE_UUID

  DBUS_OBJECT_NAME_SUFFIX = ".BrilliantDeviceProvisioner"

  def __init__(self, loop):
    super().__init__(loop, uuid_str=BrilliantDeviceProvisioningIBeacon.UUID)
    # NOTE: Only 1 Brilliant Device Provisioning iBeacon advertisement can be active at a time.
    #       This is fine for now, since there's only ever 1 Brilliant iBeacon going at a time.
    self._dbus_object_name += BrilliantDeviceProvisioningIBeacon.DBUS_OBJECT_NAME_SUFFIX

  @staticmethod
  def is_beacon_instance(device_info):
    # Brilliant controls advertise a specific iBeacon UUID
    if BrilliantDeviceProvisioningIBeacon.is_ibeacon(device_info):
      manufacturer_data = device_info.get("ManufacturerData", {})
      ibeacon_data = manufacturer_data.get(
          ibeacon_le_advertisement.IBeaconLEAdvertisement.APPLE_COMPANY_ID
      )
      data_length = ibeacon_data[1]
      uuid_length = data_length - 5  # Major/minor are 2 bytes, plus tx power
      if uuid_length != 16:
        return False

      byte_array = array.array('B', ibeacon_data[2:(2 + uuid_length)]).tobytes()
      if len(byte_array) != 16:
        return False

      try:
        advertised_uuid = str(uuid.UUID(bytes=byte_array))
      except Exception as e:
        log.error('UUID error: %s with byte array: %s', e, byte_array)
        return False
      return advertised_uuid == BrilliantDeviceProvisioningIBeacon.UUID

    return False
