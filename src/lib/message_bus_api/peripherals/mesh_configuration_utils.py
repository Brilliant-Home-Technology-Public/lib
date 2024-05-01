import thrift_types.message_bus.ttypes as mb_ttypes


_ALLOWED_PLUG_PERIPHERAL_TYPES = set([
    mb_ttypes.PeripheralType.LIGHT,
    mb_ttypes.PeripheralType.OUTLET,
])

_ALLOWED_SWITCH_PERIPHERAL_TYPES = set([
    mb_ttypes.PeripheralType.GENERIC_ON_OFF,
    mb_ttypes.PeripheralType.LIGHT,
    mb_ttypes.PeripheralType.ALWAYS_ON,
])


def is_plug_peripheral_info(peripheral_info):
  config_vars = peripheral_info.configuration_variables
  if config_vars:
    is_plug_bool = bool(int(config_vars.get("is_plug", "0")))
    if is_plug_bool and peripheral_info.peripheral_type not in _ALLOWED_PLUG_PERIPHERAL_TYPES:
      raise ValueError("Type %s not allowed for Brilliant plug" % peripheral_info.peripheral_type)
    return is_plug_bool
  return False


def is_switch_peripheral_info(peripheral_info):
  return (
      not is_plug_peripheral_info(peripheral_info) and
      peripheral_info.peripheral_type in _ALLOWED_SWITCH_PERIPHERAL_TYPES
  )


def is_switch_or_plug_peripheral_type(peripheral_type):
  return peripheral_type in _ALLOWED_PLUG_PERIPHERAL_TYPES | _ALLOWED_SWITCH_PERIPHERAL_TYPES
