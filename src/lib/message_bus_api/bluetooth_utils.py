import dataclasses

from lib import serialization
from lib.tools import peripheral_interface_helpers
import thrift_types.configuration.ttypes as config_ttypes
import thrift_types.message_bus.constants as mb_consts
import thrift_types.message_bus.ttypes as mb_ttypes


@dataclasses.dataclass(frozen=True)
class BleMeshOwnerInformation:
  owning_device_id: str
  ownership_timestamp: int
  # FIXME: Remove this after upgrading Cython. https://github.com/cython/cython/issues/2552
  __annotations__ = dict(
      owning_device_id=str,
      ownership_timestamp=int,
  )


def get_dynamic_mesh_device_name(peripheral):
  variable_suffix = peripheral.name
  if mb_consts.PERIPHERAL_INFO_ID_VARIABLE_NAME in peripheral.variables:
    variable_suffix = peripheral.variables[mb_consts.PERIPHERAL_INFO_ID_VARIABLE_NAME].value
  return peripheral_interface_helpers.format_dynamic_variable_name(
      peripheral_type=mb_ttypes.PeripheralType.MESH_CONFIGURATION,
      variable_suffix=variable_suffix,
  )


def get_owner_information_for_ble_mesh_peripheral(peripheral, mesh_configuration_peripheral):
  if not mesh_configuration_peripheral or not peripheral:
    return None
  process_config_var_name = get_dynamic_mesh_device_name(peripheral)
  process_config_var = mesh_configuration_peripheral.variables.get(process_config_var_name)
  if not process_config_var:
    return None

  process_config = serialization.deserialize(
      config_ttypes.PeripheralInfo,
      process_config_var.value,
  )
  return BleMeshOwnerInformation(
      owning_device_id=process_config.owner,
      ownership_timestamp=process_config_var.timestamp,
  )


def get_owning_device_id_for_ble_mesh_peripheral(peripheral, mesh_configuration_peripheral):
  owner_info = get_owner_information_for_ble_mesh_peripheral(
      peripheral, mesh_configuration_peripheral)
  return owner_info.owning_device_id if owner_info else None
