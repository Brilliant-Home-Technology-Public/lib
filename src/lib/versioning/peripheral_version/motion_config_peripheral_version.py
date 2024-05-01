import logging

from lib import serialization
from lib.versioning.peripheral_version.base import PeripheralVersion
from lib.versioning.peripheral_version.base import register
import thrift_types.configuration.constants as config_consts
import thrift_types.configuration.ttypes as config_ttypes
import thrift_types.message_bus.constants as mb_consts
import thrift_types.message_bus.ttypes as mb_ttypes
from thrift_types.version import constants as version_consts


log = logging.getLogger(__name__)


class MotionConfigPeripheralVersion20180605(PeripheralVersion):
  peripheral_name = mb_consts.MOTION_DETECTION_IDENTIFIER
  version = version_consts.VERSION_20180605

  GANGBOX_PERIPHERAL_ID = mb_consts.GANGBOX_IDENTIFIER + "_0"

  @classmethod
  def apply_migrations_to_variables(cls, direction, variables, device_id=None):
    if not device_id:
      return {}
    if direction == "up":
      return cls._apply_up_migration_to_variables(variables, device_id)
    return cls._apply_down_migration_to_variables(variables, device_id)

  @classmethod
  def _apply_up_migration_to_variables(cls, variables, device_id):
    # In release-20180530 we began supporting motion control for multiple loads. Motion configs are
    # now stored as dynamic variables in a LightMotionConfig struct. For gangbox_peripheral_0
    # specifically, we need to migrate the individual variables into a single config struct.
    updated_map = {}
    trigger_lights_var = variables.get("trigger_lights")
    trigger_on_var = variables.get("trigger_lights_on")
    trigger_off_var = variables.get("trigger_lights_off")
    trigger_off_timeout_sec_var = variables.get("trigger_lights_off_timeout_sec")

    # Mark all old variables as removed
    if trigger_lights_var:
      updated_map["trigger_lights"] = None
    if trigger_on_var:
      updated_map["trigger_lights_on"] = None
    if trigger_off_var:
      updated_map["trigger_lights_off"] = None
    if trigger_off_timeout_sec_var:
      updated_map["trigger_lights_off_timeout_sec"] = None

    if trigger_lights_var and trigger_on_var and trigger_off_var and trigger_off_timeout_sec_var:
      # If trigger_lights is False, we should not create a LightMotionConfig (absence of the config
      # indicates it is disabled)
      trigger_lights = cls._get_bool(trigger_lights_var)
      if trigger_lights:
        trigger_on = cls._get_bool(trigger_on_var)
        trigger_off = cls._get_bool(trigger_off_var)
        trigger_off_timeout_sec = int(trigger_off_timeout_sec_var.value or "0")
        config = config_ttypes.LightMotionConfig(
            device_id=device_id,
            peripheral_id=cls.GANGBOX_PERIPHERAL_ID,
            trigger_on=trigger_on,
            trigger_off=trigger_off,
            trigger_off_timeout_sec=trigger_off_timeout_sec,
        )
        config_raw = serialization.serialize(config)
        config_var_name = "{}{}:{}".format(
            config_consts.LIGHT_MOTION_CONFIG_VARIABLE_PREFIX,
            device_id,
            cls.GANGBOX_PERIPHERAL_ID,
        )
        updated_map[config_var_name] = mb_ttypes.Variable(
            name=config_var_name,
            value=config_raw,
            timestamp=trigger_lights_var.timestamp,
            externally_settable=True,
        )
    elif any([trigger_lights_var, trigger_on_var, trigger_off_var, trigger_off_timeout_sec_var]):
      log.error(
          "Unable to retrieve all variables for motion config migration of device %s. Vars are: %s",
          device_id,
          variables,
      )

    return updated_map

  @classmethod
  def _get_bool(cls, variable):
    if variable.value is None:
      return False
    return bool(int(variable.value))

  @classmethod
  def _get_str_from_bool(cls, bool_value):
    if bool_value is None:
      bool_value = False
    return str(int(bool_value))

  @classmethod
  def _apply_down_migration_to_variables(cls, variables, device_id):
    # NOTE: We do not have a way of down migrating the config if it does not exist (i.e. a non
    # existent LightMotionConfig dynamic variable means it is not enabled, however, the variables
    # dict is not a complete representation of all state)
    updated_map = {}

    var_to_migrate = None
    for var_name, _ in variables.items():
      if var_name.startswith(config_consts.LIGHT_MOTION_CONFIG_VARIABLE_PREFIX):
        parts = var_name.split(":")
        if len(parts) >= 3 and parts[1] == device_id and parts[2] == cls.GANGBOX_PERIPHERAL_ID:
          var_to_migrate = var_name
          break

    if var_to_migrate:
      # Mark the newer variable as removed
      updated_map[var_to_migrate] = None

      config_var = variables.get(var_to_migrate)
      if config_var:
        config = serialization.deserialize(config_ttypes.LightMotionConfig, config_var.value)
        updated_map["trigger_lights"] = mb_ttypes.Variable(
            name="trigger_lights",
            value="1",
            timestamp=config_var.timestamp,
            externally_settable=True,
        )
        updated_map["trigger_lights_on"] = mb_ttypes.Variable(
            name="trigger_lights_on",
            value=cls._get_str_from_bool(config.trigger_on),
            timestamp=config_var.timestamp,
            externally_settable=True,
        )
        updated_map["trigger_lights_off"] = mb_ttypes.Variable(
            name="trigger_lights_off",
            value=cls._get_str_from_bool(config.trigger_off),
            timestamp=config_var.timestamp,
            externally_settable=True,
        )
        updated_map["trigger_lights_off_timeout_sec"] = mb_ttypes.Variable(
            name="trigger_lights_off_timeout_sec",
            value=str(config.trigger_off_timeout_sec),
            timestamp=config_var.timestamp,
            externally_settable=True,
        )

    return updated_map


class MotionConfigPeripheralVersion20181018(PeripheralVersion):

  peripheral_name = mb_consts.MOTION_DETECTION_IDENTIFIER
  version = version_consts.VERSION_20181018

  @classmethod
  def migrate_variables_up(cls, variables, last_set_timestamps, device_id=None):
    trigger_screen_off_added = False
    if "trigger_screen" in variables and variables["trigger_screen"]:
      trigger_screen = bool(int(variables["trigger_screen"]))
      # If trigger_screen was set to true, we need to carry over that state for trigger_screen_off
      # Otherwise, let trigger_screen_off be the default False option
      if trigger_screen:
        variables["trigger_screen_off"] = "1"
        trigger_screen_off_added = True
    if "trigger_screen" in last_set_timestamps and trigger_screen_off_added:
      last_set_timestamps["trigger_screen_off"] = last_set_timestamps["trigger_screen"]

    return variables, last_set_timestamps

  @classmethod
  def migrate_variables_down(cls, variables, last_set_timestamps, device_id=None):
    if "trigger_screen_off" in variables:
      variables.pop("trigger_screen_off")
    if "trigger_screen_off" in last_set_timestamps:
      last_set_timestamps.pop("trigger_screen_off")

    return variables, last_set_timestamps


register(MotionConfigPeripheralVersion20180605)
register(MotionConfigPeripheralVersion20181018)
