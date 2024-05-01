from lib import serialization
import lib.time
from lib.tools import peripheral_interface_helpers
from lib.versioning.peripheral_version.base import PeripheralVersion
from lib.versioning.peripheral_version.base import register
import thrift_types.configuration.ttypes as config_ttypes
import thrift_types.message_bus.constants as mb_consts
import thrift_types.message_bus.ttypes as mb_ttypes
from thrift_types.version import constants as version_consts


class SceneConfigPeripheralVersion20180925(PeripheralVersion):

  prev_version = None
  version = version_consts.VERSION_20180925
  next_version = version_consts.VERSION_20181005
  peripheral_name = mb_consts.SCENE_CONFIG_IDENTIFIER

  @classmethod
  def migrate_variables_up(cls, variables, last_set_timestamps, device_id=None):
    # No need for an up_migration
    return variables, last_set_timestamps

  @classmethod
  def migrate_variables_down(cls, variables, last_set_timestamps, device_id=None):
    # Earlier versions cannot yet handle expected(excluded)_variable_states or
    # scene.editable, so we will delete scenes with these properties
    updated_variables = {}
    for var_name in variables:
      should_keep = True
      if var_name.startswith("scene:") and variables[var_name]:
        scene = serialization.deserialize(config_ttypes.Scene, variables[var_name])
        if scene.multi_actions:
          for multi_action in scene.multi_actions:
            if multi_action.expected_variable_states:
              should_keep = False
            if multi_action.excluded_variable_states:
              should_keep = False
        if scene.editable is not None and not scene.editable:
          should_keep = False
      if should_keep:
        updated_variables[var_name] = variables[var_name]
    return updated_variables, last_set_timestamps


register(SceneConfigPeripheralVersion20180925)


class SceneConfigPeripheralVersion20181005(PeripheralVersion):

  prev_version = version_consts.VERSION_20180925
  version = version_consts.VERSION_20181005
  next_version = version_consts.VERSION_20190412
  peripheral_name = mb_consts.SCENE_CONFIG_IDENTIFIER

  @classmethod
  def migrate_variables_up(cls, variables, last_set_timestamps, device_id=None):
    # For sonos scenes, we need to make sure that when translating to new
    # versions, if we have both of ["play", "play_uri"] in a SceneAction's
    # variables, we need to strip "play" to ensure that we don't encounter a
    # bug where activating a scene to play a uri will play the previous song,
    # for 1 second, pause, then play the new song
    for var_name in variables:
      should_update = False
      if var_name.startswith("scene:") and variables[var_name]:
        scene = serialization.deserialize(config_ttypes.Scene, variables[var_name])
        for scene_action in scene.actions:
          if "playing" in scene_action.variables and "play_uri" in scene_action.variables:
            scene_action.variables.pop('playing')
            should_update = True
        if should_update:
          variables[var_name] = serialization.serialize(scene)
    return variables, last_set_timestamps

  @classmethod
  def migrate_variables_down(cls, variables, last_set_timestamps, device_id=None):
    # To down migrate a Sonos Scene, if it contains "play_uri", we must
    # re-insert "playing": 1 for the scene action to still render properly
    # in the edit SceneAction Screen
    for var_name in variables:
      if var_name.startswith("scene:") and variables[var_name]:
        scene = serialization.deserialize(config_ttypes.Scene, variables[var_name])
        should_update = False
        for scene_action in scene.actions:
          if "play_uri" in scene_action.variables and "playing" not in scene_action.variables:
            scene_action.variables["playing"] = "1"
            should_update = True
        if should_update:
          variables[var_name] = serialization.serialize(scene)
    return variables, last_set_timestamps


register(SceneConfigPeripheralVersion20181005)


class SceneConfigPeripheralVersion20190412(PeripheralVersion):

  prev_version = version_consts.VERSION_20181005
  version = version_consts.VERSION_20190412
  next_version = version_consts.VERSION_20190604
  peripheral_name = mb_consts.SCENE_CONFIG_IDENTIFIER

  @classmethod
  def migrate_variables_up(cls, variables, last_set_timestamps, device_id=None):
    if "scene_validity_states" not in variables:
      default_scene_validity_states = serialization.serialize(config_ttypes.SceneValidityStates(
          scene_validity_states={},
      ))
      variables["scene_validity_states"] = default_scene_validity_states
      last_set_timestamps["scene_validity_states"] = lib.time.get_current_time_ms()
    return variables, last_set_timestamps

  @classmethod
  def migrate_variables_down(cls, variables, last_set_timestamps, device_id=None):
    return variables, last_set_timestamps


register(SceneConfigPeripheralVersion20190412)


class SceneConfigPeripheralVersion20190604(PeripheralVersion):

  prev_version = version_consts.VERSION_20190412
  version = version_consts.VERSION_20190604
  next_version = version_consts.VERSION_20190614
  peripheral_name = mb_consts.SCENE_CONFIG_IDENTIFIER

  @classmethod
  def migrate_variables_up(cls, variables, last_set_timestamps, device_id=None):
    for var_name in variables:
      should_update = False
      if var_name.startswith("scene:") and variables[var_name]:
        scene = serialization.deserialize(config_ttypes.Scene, variables[var_name])
        for scene_action in scene.actions:
          if scene_action.peripheral_name == mb_consts.ART_CONFIG_IDENTIFIER and \
              not "use_global_art_config" in scene_action.variables:
            scene_action.variables["use_global_art_config"] = "0"
            should_update = True
      if should_update:
        variables[var_name] = serialization.serialize(scene)
    return variables, last_set_timestamps

  @classmethod
  def migrate_variables_down(cls, variables, last_set_timestamps, device_id=None):
    for var_name in variables:
      should_update = False
      if var_name.startswith("scene:") and variables[var_name]:
        scene = serialization.deserialize(config_ttypes.Scene, variables[var_name])
        for scene_action in scene.actions:
          if (scene_action.peripheral_name == mb_consts.ART_CONFIG_IDENTIFIER
              and "use_global_art_config" in scene_action.variables):
            scene_action.variables.pop("use_global_art_config")
            should_update = True
      if should_update:
        variables[var_name] = serialization.serialize(scene)
    return variables, last_set_timestamps


register(SceneConfigPeripheralVersion20190604)


class SceneConfigPeripheralVersion20190614(PeripheralVersion):

  prev_version = version_consts.VERSION_20190604
  version = version_consts.VERSION_20190614
  next_version = version_consts.VERSION_20190716
  peripheral_name = mb_consts.SCENE_CONFIG_IDENTIFIER

  @classmethod
  def migrate_variables_up(cls, variables, last_set_timestamps, device_id=None):
    for var_name in variables:
      should_update = False
      if var_name.startswith("scene:") and variables[var_name]:
        scene = serialization.deserialize(config_ttypes.Scene, variables[var_name])
        for scene_action in scene.actions:
          if (scene_action.peripheral_name == mb_consts.ART_CONFIG_IDENTIFIER and
              scene_action.device_id == mb_consts.CONFIGURATION_VIRTUAL_DEVICE and
              "use_global_art_config" in scene_action.variables):
            scene_action.variables.pop("use_global_art_config")
            should_update = True
      if should_update:
        variables[var_name] = serialization.serialize(scene)
        last_set_timestamps[var_name] = lib.time.get_current_time_ms()
    return variables, last_set_timestamps

  @classmethod
  def migrate_variables_down(cls, variables, last_set_timestamps, device_id=None):
    return variables, last_set_timestamps


register(SceneConfigPeripheralVersion20190614)


class SceneConfigPeripheralVersion20190716(PeripheralVersion):

  prev_version = version_consts.VERSION_20190614
  version = version_consts.VERSION_20190716
  next_version = None
  peripheral_name = mb_consts.SCENE_CONFIG_IDENTIFIER

  @classmethod
  def migrate_variables_up(cls, variables, last_set_timestamps, device_id=None):
    # No need for an up migration
    return variables, last_set_timestamps

  @classmethod
  def migrate_variables_down(cls, variables, last_set_timestamps, device_id=None):
    for var_name in variables:
      should_update = False
      if (peripheral_interface_helpers.is_dynamic_variable_name(
          mb_ttypes.PeripheralType.SCENE_CONFIGURATION, var_name) and variables[var_name]):
        scene = peripheral_interface_helpers.deserialize_peripheral_variable(
            peripheral_type=mb_ttypes.PeripheralType.SCENE_CONFIGURATION,
            name=var_name,
            value=variables[var_name],
        )
        for scene_action in scene.actions:
          if "color" in scene_action.variables:
            scene_action.variables.pop("color")
            should_update = True
      if should_update:
        last_set_timestamps[var_name] -= 1
        variables[var_name] = serialization.serialize(scene)
    return variables, last_set_timestamps


register(SceneConfigPeripheralVersion20190716)
