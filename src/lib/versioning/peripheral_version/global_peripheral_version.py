from lib import serialization
from lib.versioning.peripheral_version import base
import thrift_types.configuration.ttypes as configuration_ttypes
import thrift_types.version.constants as version_consts


class GlobalPeripheralVersion20180620(base.PeripheralVersion):

  peripheral_name = None  # Applies to all peripherals
  version = version_consts.VERSION_20180620

  @classmethod
  def migrate_variables_up(cls, variables, last_set_timestamps, device_id=None):
    if "room_id" in variables:
      room_id = variables.pop("room_id")
      room_assignment_val = configuration_ttypes.RoomAssignment(
          room_ids=[room_id] if room_id else [],
      )
      variables["room_assignment"] = serialization.serialize(room_assignment_val)
      if "room_id" in last_set_timestamps:
        last_set_timestamps["room_assignment"] = last_set_timestamps.pop("room_id")

    return variables, last_set_timestamps

  @classmethod
  def migrate_variables_down(cls, variables, last_set_timestamps, device_id=None):
    if "room_assignment" in variables:
      room_assignment_val = configuration_ttypes.RoomAssignment()
      room_assignment_serialized = variables.pop("room_assignment")
      if room_assignment_serialized:
        room_assignment_val = serialization.deserialize(
            configuration_ttypes.RoomAssignment,
            room_assignment_serialized,
        )

      variables["room_id"] = room_assignment_val.room_ids[0] if room_assignment_val.room_ids else ""
      if "room_assignment" in last_set_timestamps:
        last_set_timestamps["room_id"] = last_set_timestamps.pop("room_assignment")

    return variables, last_set_timestamps


base.register(GlobalPeripheralVersion20180620)
