import logging

from lib import serialization
import lib.time
from lib.versioning.peripheral_version.base import PeripheralVersion
from lib.versioning.peripheral_version.base import register
import thrift_types.configuration.ttypes as config_ttypes
import thrift_types.message_bus.constants as mb_consts
from thrift_types.version import constants as version_consts


log = logging.getLogger(__name__)


class DeviceConfigPeripheralVersion20190130(PeripheralVersion):
  peripheral_name = mb_consts.DEVICE_CONFIG_IDENTIFIER
  prev_version = None
  version = version_consts.VERSION_20190130
  next_version = version_consts.VERSION_20190204

  @classmethod
  def migrate_variables_up(cls, variables, last_set_timestamps, device_id=None):
    # If a device doesn't have the Two Finger Gesture in its GestureConfigs, add it
    # and make sure it is enabled by default
    if "gesture_configs" in variables and variables["gesture_configs"]:
      gesture_configs = serialization.deserialize(
          config_ttypes.GestureConfigs,
          variables["gesture_configs"],
      )
      if not gesture_configs.gesture_configs.get(config_ttypes.GestureType.TWO):
        default_two_finger_gesture = [config_ttypes.GestureConfig(
            gesture_type=config_ttypes.GestureType.TWO,
            device_id=device_id,
            peripheral_id=mb_consts.DEVICE_CONFIG_IDENTIFIER,
        )]
        gesture_configs.gesture_configs[config_ttypes.GestureType.TWO] = default_two_finger_gesture
        variables["gesture_configs"] = serialization.serialize(gesture_configs)
        last_set_timestamps["gesture_configs"] = lib.time.get_current_time_ms()
    return variables, last_set_timestamps

  @classmethod
  def migrate_variables_down(cls, variables, last_set_timestamps, device_id=None):
    # When downgrading, remove the two finger gesture config
    if "gesture_configs" in variables and variables["gesture_configs"]:
      gesture_configs = serialization.deserialize(
          config_ttypes.GestureConfigs,
          variables["gesture_configs"],
      )
      if gesture_configs.gesture_configs.get(config_ttypes.GestureType.TWO):
        gesture_configs.gesture_configs.pop(config_ttypes.GestureType.TWO)
        variables["gesture_configs"] = serialization.serialize(gesture_configs)
    return variables, last_set_timestamps


register(DeviceConfigPeripheralVersion20190130)


class DeviceConfigPeripheralVersion20190204(PeripheralVersion):
  peripheral_name = mb_consts.DEVICE_CONFIG_IDENTIFIER
  prev_version = version_consts.VERSION_20190130
  version = version_consts.VERSION_20190204
  next_version = None

  @classmethod
  def migrate_variables_up(cls, variables, last_set_timestamps, device_id=None):
    # We repeat the migration from 20190130 because 20190130 was released to latest
    # before a timestamping bug was found and resolved. This migration is meant to address
    # any devices that received the faulty 20190130 migration on Latest.
    return DeviceConfigPeripheralVersion20190130.migrate_variables_up(
        variables,
        last_set_timestamps,
        device_id,
    )

  @classmethod
  def migrate_variables_down(cls, variables, last_set_timestamps, device_id=None):
    # No need for a down migration because 0130 will do the actual down migration
    # If we were to have a proper down migration here, we would be putting devices that
    # never received the faulty 20190130 migration into an erroneous state that they
    # had never been in before.
    return variables, last_set_timestamps


register(DeviceConfigPeripheralVersion20190204)
