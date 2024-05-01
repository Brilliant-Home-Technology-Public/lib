import copy
import typing

import lib.serialization
import lib.time
import lib.tools.peripheral_interface_helpers
from lib.versioning import peripheral_version
from lib.versioning.base_version import BaseVersion
import lib.versioning.utils as versioning_utils
import thrift_types.configuration.ttypes as config_ttypes
import thrift_types.message_bus.constants as mb_consts
import thrift_types.message_bus.ttypes as mb_ttypes
import thrift_types.version.constants as version_consts


if typing.TYPE_CHECKING:
  # Provide a dummy type interface as we can't actually import this module
  class organizations_service:
    class common:
      class interface:
        PropertyInstallation: typing.Any


class BasePropertyInstallationsVersion(BaseVersion):
  service = "PropertyInstallations"

  @classmethod
  def _migrate_variables_for_peripheral(
      cls,
      direction: str,
      variables: typing.Dict[str, typing.Any],
      peripheral_name: str,
      device_id: typing.Optional[str] = None,
  ) -> typing.Dict[str, str]:
    """Return a new migrated set of variables for the peripheral.

    Args:
      direction: The direction in which to migrate the variables ("up" or "down").
      variables: A mapping of variable names to variable values.
      peripheral_name: The name of the peripheral (see message_bus.thrift for more info).
      device_id: The ID of the device that owns the peripheral.
    """
    # Set the timestamp to now; however, the timestamp will be ignored.
    now_timestamp = lib.time.get_current_time_ms()
    # Convert variable values into Variable type objects before attempting to apply the peripheral
    # migration.
    variable_objects = {}
    for var_name, var_value in variables.items():
      variable_objects[var_name] = mb_ttypes.Variable(
          name=var_name,
          value=var_value,
          timestamp=now_timestamp,
          externally_settable=True,
      )

    version = peripheral_version.get_peripheral_version(
        device_id=device_id,
        peripheral_name=peripheral_name,
        version=cls.version,
    )
    updated_map = version.apply_migrations_to_variables(
        direction=direction,
        variables=variable_objects,
        device_id=device_id,
    )

    if not updated_map:
      return variables

    variable_objects = versioning_utils.update_variables_map(
        peripheral_name=peripheral_name,
        variables=variable_objects,
        updated_map=updated_map,
    )

    # Unpack the Variable objects.
    updated_variables = {}
    for var_name, var_object in variable_objects.items():
      updated_variables[var_name] = var_object.value

    return updated_variables

  @classmethod
  def _migrate_device_provision_state_field(
      cls,
      direction: str,
      device_provision_state: typing.List[typing.Dict[str, str]],
  ) -> typing.List[typing.Dict[str, str]]:
    """Returns a new migrated `device_provision_state`.

    Args:
      direction: The direction in which to migrate the `device_provision_state` ("up" or "down").
      device_provision_state: A list of dictionaries with serialized PeripheralInfo objects and
          their corresponding variable names.
    """
    new_device_provision_state = []

    for provisioned_device in device_provision_state:
      var_name = provisioned_device["variable_name"]
      serialized_peripheral_info = provisioned_device["serialized_peripheral_info"]
      peripheral_info = lib.serialization.deserialize(
          thrift_cls=config_ttypes.PeripheralInfo,
          data=serialized_peripheral_info,
      )
      new_peripheral_info = cls._migrate_variables_for_peripheral(
          direction=direction,
          variables={var_name: serialized_peripheral_info},
          peripheral_name=peripheral_info.configuration_peripheral_id,
          device_id=mb_consts.CONFIGURATION_VIRTUAL_DEVICE,
      )
      # Ignore any unexpected variables in `new_peripheral_info` since there's no defined method to
      # adapt them to the `device_provision_state` structure.
      if var_name in new_peripheral_info:
        new_device_provision_state.append({
            "variable_name": var_name,
            "serialized_peripheral_info": new_peripheral_info[var_name],
        })

    return new_device_provision_state

  @classmethod
  def _migrate_post_provision_state_field(
      cls,
      direction: str,
      post_provision_state: str,
  ) -> str:
    """Returns a new migrated `post_provision_state`.

    Args:
      direction: The direction in which to migrate the `post_provision_state` ("up" or "down").
      post_provision_state: A serialized StateConfig object.
    """
    # Use a placeholder dynamic variable name for the StateConfig object.
    dynamic_var_name = lib.tools.peripheral_interface_helpers.format_dynamic_variable_name(
        peripheral_type=mb_ttypes.PeripheralType.STATE_CONFIGURATION,
        variable_suffix="placeholder",
    )
    # Migrate the State Config peripheral's serialized StateConfig object.
    new_state_config_vars = cls._migrate_variables_for_peripheral(
        direction=direction,
        variables={dynamic_var_name: post_provision_state},
        peripheral_name=mb_consts.STATE_CONFIG_IDENTIFIER,
        device_id=mb_consts.CONFIGURATION_VIRTUAL_DEVICE,
    )

    return new_state_config_vars[dynamic_var_name]

  @classmethod
  def _migrate_property_installation_object(
      cls,
      direction: str,
      prop_install: "organizations_service.common.interface.PropertyInstallation",
  ) -> "organizations_service.common.interface.PropertyInstallation":
    """Migrate a PropertyInstallation object in the specified direction.

    Args:
      direction: The direction in which to migrate the PropertyInstallation object ("up" or "down").
      prop_install: The PropertyInstallation object to migrate.

    Returns: A new migrated PropertyInstallation object.
    """
    new_prop_install = copy.deepcopy(prop_install)
    new_prop_install.device_provision_state = cls._migrate_device_provision_state_field(
        direction=direction,
        device_provision_state=prop_install.device_provision_state,
    )
    new_prop_install.post_provision_state = cls._migrate_post_provision_state_field(
        direction=direction,
        post_provision_state=prop_install.post_provision_state,
    )
    return new_prop_install

  @classmethod
  def _migrate_property_installation_args_up(
      cls,
      args: typing.Dict[str, typing.Any],
      context=None,
  ) -> typing.Dict[str, typing.Any]:
    new_property_installation = cls._migrate_property_installation_object(
        direction="up",
        prop_install=args["property_installation"],
    )
    return {"property_installation": new_property_installation}

  @classmethod
  def _migrate_property_installation_args_down(
      cls,
      args: typing.Dict[str, typing.Any],
      context=None,
  ) -> typing.Dict[str, typing.Any]:
    new_property_installation = cls._migrate_property_installation_object(
        direction="down",
        prop_install=args["property_installation"],
    )
    return {"property_installation": new_property_installation}


class PropertyInstallationsVersion20200923(BasePropertyInstallationsVersion):
  prev_version = None
  version = version_consts.VERSION_20200923
  next_version = None


ALL_API_VERSIONS = [
    PropertyInstallationsVersion20200923,
]


CURRENT_API_VERSION = PropertyInstallationsVersion20200923
