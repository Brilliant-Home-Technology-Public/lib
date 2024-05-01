import thrift_types.bluetooth.constants as bluetooth_consts


def get_plug_peripheral_load_index_for_mesh_device_id(mesh_device_id: str) -> int:
  return int(mesh_device_id.split("_")[-1])


def get_plug_load_peripheral_name_for_mesh_device_id(
    mesh_device_id: str,
    load_index: int = 0,
) -> str:
  # We currently assume the load index is always 0
  return f"{mesh_device_id}_{load_index}"


def get_switch_load_peripheral_name_for_mesh_device_id(mesh_device_id: str) -> str:
  return mesh_device_id


def get_switch_config_peripheral_name_for_mesh_device_id(mesh_device_id: str) -> str:
  return f"{bluetooth_consts.SWITCH_CONFIG_PERIPHERAL_PREFIX}{mesh_device_id}"


def get_plug_config_peripheral_name_for_mesh_device_id(mesh_device_id: str) -> str:
  return mesh_device_id


def get_switch_id_for_config_peripheral(config_peripheral_id: str) -> str:
  return config_peripheral_id.replace(bluetooth_consts.SWITCH_CONFIG_PERIPHERAL_PREFIX, "")
