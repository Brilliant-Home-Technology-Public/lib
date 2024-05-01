import binascii
import logging
import uuid

import lib.ulid
import thrift_types.message_bus.constants as message_bus_constants
import thrift_types.message_bus.ttypes as message_bus_ttypes


KNOWN_VIRTUAL_DEVICE_IDS = set(message_bus_constants.KNOWN_VIRTUAL_DEVICE_IDS)
CLOUD_OWNED_VIRTUAL_DEVICE_IDS = {message_bus_constants.CONFIGURATION_VIRTUAL_DEVICE,
                                  message_bus_constants.CLOUD_VIRTUAL_DEVICE}
NON_CLOUD_OWNED_KNOWN_VIRTUAL_DEVICE_IDS = KNOWN_VIRTUAL_DEVICE_IDS - CLOUD_OWNED_VIRTUAL_DEVICE_IDS

# These are the devices categorized by device type.
CLOUD_DEVICES = {message_bus_constants.CLOUD_VIRTUAL_DEVICE}
VIRTUAL_DEVICES = {
    message_bus_constants.BLE_MESH_VIRTUAL_DEVICE,
    message_bus_constants.BRILLIANT_VIRTUAL_DEVICE_IDENTIFIER,
    message_bus_constants.CONFIGURATION_VIRTUAL_DEVICE,
}
THIRDPARTY_VIRTUAL_DEVICES = KNOWN_VIRTUAL_DEVICE_IDS - CLOUD_DEVICES - VIRTUAL_DEVICES


log = logging.getLogger(__name__)


def is_mobile_device_id(device_id):
  # Mobile device IDs are currently 20 hex digits
  if len(device_id) != 20:
    return False

  try:
    binascii.unhexlify(device_id)
  except binascii.Error:
    return False

  return True


def is_valid_uuid(id_string):
  try:
    uuid.UUID(id_string)
  except ValueError:
    return False

  return True


def guess_device_type_for_id(device_id):
  if lib.ulid.validate(device_id, lib.ulid.IDType.FACEPLATE):
    return message_bus_ttypes.DeviceType.CONTROL
  if lib.ulid.validate(device_id, lib.ulid.IDType.VIRTUAL_CONTROL):
    return message_bus_ttypes.DeviceType.VIRTUAL_CONTROL
  if device_id in CLOUD_DEVICES:
    return message_bus_ttypes.DeviceType.CLOUD
  if device_id in VIRTUAL_DEVICES:
    return message_bus_ttypes.DeviceType.VIRTUAL
  if device_id in THIRDPARTY_VIRTUAL_DEVICES:
    return message_bus_ttypes.DeviceType.THIRDPARTY_VIRTUAL
  if is_mobile_device_id(device_id):
    return message_bus_ttypes.DeviceType.MOBILE_APP
  if is_valid_uuid(device_id):
    # Assume any UUID is a Brilliant Control for now for compatibility with ad-hoc flashes
    return message_bus_ttypes.DeviceType.CONTROL
  log.warning("Could not match device id %s to type", device_id)
  return message_bus_ttypes.DeviceType.UNKNOWN
