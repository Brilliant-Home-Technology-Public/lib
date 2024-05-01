import collections
import importlib
import json
import logging
import os

from thrift.Thrift import TType

from lib import serialization
from lib.exceptions import PeripheralInterfaceException
import thrift_types
from thrift_types import peripheral_interfaces
import thrift_types.message_bus.ttypes as mb_ttypes
import thrift_types.protocol.ttypes as protocol_ttypes


log = logging.getLogger(__name__)

PeripheralInterface = collections.namedtuple(
    'PeripheralInterface',
    'ttype_class, dynamic_variable_prefix, dynamic_variable_ttype_class, required_variables',
)


def _read_peripheral_interfaces_from_files():
  peripheral_type_to_thrift_class = {}

  base_path = os.path.split(thrift_types.__file__)[0]

  for elem in os.scandir(os.path.split(peripheral_interfaces.__file__)[0]):
    if elem.is_dir() and not elem.name.startswith('__'):
      base_module_name = 'thrift_types' + elem.path.replace(base_path, '').replace('/', '.')

      consts_module = importlib.import_module(base_module_name + '.constants')
      ttypes_module = importlib.import_module(base_module_name + '.ttypes')

      if hasattr(consts_module, 'peripheral'):
        peripheral = consts_module.peripheral
        ttype_class = getattr(ttypes_module, peripheral.peripheral_interface_name)

        dynamic_var_prefix = None
        dynamic_var_ttype_cls = None
        if peripheral.dynamic_variable_prefix and peripheral.dynamic_variable_ttype:
          dynamic_var_prefix = peripheral.dynamic_variable_prefix

          dynamic_var_ttype_cls_name = peripheral.dynamic_variable_ttype.split('.')[-1]
          dynamic_var_ttype_module = importlib.import_module(
              ('thrift_types.' + '.'.join(peripheral.dynamic_variable_ttype.split('.')[:-1]) + '.ttypes'))
          dynamic_var_ttype_cls = getattr(dynamic_var_ttype_module, dynamic_var_ttype_cls_name)

        required_fields = set(ttype_class.thrift_required_fields)
        peripheral_type_to_thrift_class[peripheral.peripheral_type] = PeripheralInterface(
            ttype_class,
            dynamic_var_prefix,
            dynamic_var_ttype_cls,
            required_fields,
        )

  return peripheral_type_to_thrift_class


PERIPHERAL_TYPE_TO_THRIFT_INTERFACE = _read_peripheral_interfaces_from_files()


def get_peripheral_interface(peripheral_type):
  return PERIPHERAL_TYPE_TO_THRIFT_INTERFACE.get(peripheral_type)


def _get_ttype_and_struct(peripheral_type, name):
  peripheral_interface = get_peripheral_interface(peripheral_type)
  if peripheral_interface is None:
    return None

  thrift_var_specs = {}
  for thrift_var_spec in peripheral_interface.ttype_class.thrift_spec[1:]:
    if thrift_var_spec is not None:
      _, var_ttype, var_name, var_struct, _ = thrift_var_spec
      thrift_var_specs[var_name] = (var_ttype, var_struct)
  dynamic_var_prefix = peripheral_interface.dynamic_variable_prefix

  if ((name not in thrift_var_specs) and
      (dynamic_var_prefix is None or not name.startswith(dynamic_var_prefix))):
    return None

  if dynamic_var_prefix is not None and name.startswith(dynamic_var_prefix):
    ttype = TType.STRUCT
    struct = (peripheral_interface.dynamic_variable_ttype_class, )
  else:
    ttype, struct = thrift_var_specs[name]

  return ttype, struct


def is_valid_variable(peripheral_type, name):
  """Whether or not the provided variable name is a valid variable or dynamic variable for the
  provided peripheral type.
  """
  return _get_ttype_and_struct(peripheral_type, name) is not None


def deserialize_peripheral_variable(peripheral_type, name, value, log_on_missing=False):
  if value is None:
    return None

  maybe_ttype_and_struct = _get_ttype_and_struct(peripheral_type, name)
  if not maybe_ttype_and_struct:
    if log_on_missing:
      log.error("Could not find variable %s for peripheral type %s",
                name,
                peripheral_type)
    return None

  ttype, struct = maybe_ttype_and_struct
  if ttype in (TType.I16, TType.I32, TType.I64):
    deserialized_val = int(value)
  elif ttype == TType.DOUBLE:
    deserialized_val = float(value)
  elif ttype == TType.STRING:
    deserialized_val = str(value)
  elif ttype == TType.BOOL:
    deserialized_val = bool(int(value))
  elif ttype == TType.STRUCT:
    deserialized_val = serialization.deserialize(struct[0], value)
  else:
    raise PeripheralInterfaceException(
        "Could not deserialize variable of type: %s, value: %s" % (ttype, value))
  return deserialized_val


def deserialize_peripheral_variables(peripheral_type, variables):
  deserialized_variables = {}

  for key, value in variables.items():
    deserialzied_value = deserialize_peripheral_variable(peripheral_type, key, value.value)
    if deserialzied_value is not None:
      deserialized_variables[key] = deserialzied_value

  return deserialized_variables


def serialize_peripheral_variable(peripheral_type, name, value):
  if value is None:
    raise TypeError("Expected non-None value!")

  maybe_ttype_and_struct = _get_ttype_and_struct(peripheral_type, name)
  if not maybe_ttype_and_struct:
    raise PeripheralInterfaceException(
        "Could not identify type for variable {}".format(name)
    )

  ttype, struct = maybe_ttype_and_struct
  if ttype in (TType.I16, TType.I32, TType.I64):
    serialized_val = str(value)
  elif ttype == TType.STRING:
    serialized_val = str(value)
  elif ttype == TType.BOOL:
    serialized_val = str(int(value))
  elif ttype == TType.STRUCT:
    serialized_val = serialization.serialize(value)
  else:
    raise PeripheralInterfaceException(
        "Could not serialize variable of type: {}, value: {}".format(ttype, value)
    )
  return serialized_val


def _serialize_dict_variable_to_thrift(peripheral_type, variable_name, variable):
  if not variable["value"]:
    return None
  maybe_ttype_and_struct = _get_ttype_and_struct(
      peripheral_type,
      variable_name,
  )
  if not maybe_ttype_and_struct:
    # If we can't read the peripheral interface, it's likely that the variable is still a
    # serialized string anyways since we wouldn't have been able to convert it to JSON in the
    # first place. So, just keep it the same value.
    log.error("Could not find variable %s for peripheral type %s",
              variable_name,
              peripheral_type)
    return None
  ttype, struct = maybe_ttype_and_struct
  if ttype == TType.STRUCT:
    thrift_variable = serialization.deserialize(
        thrift_cls=struct[0],
        data=variable["value"],
        protocol=protocol_ttypes.SerializationProtocol.JSON,
    )
  else:
    thrift_variable = variable["value"]
  serialized_value = serialize_peripheral_variable(
      peripheral_type,
      variable_name,
      thrift_variable,
  )
  return serialized_value


def dict_peripheral_to_thrift(json_peripheral, assert_required_variables=False):
  peripheral_type = json_peripheral["peripheral_type"]
  _assert_required_variables_exist(
      peripheral_name=json_peripheral["name"],
      peripheral_type=peripheral_type,
      peripheral_variables=json_peripheral["variables"],
      strict=assert_required_variables,
  )
  for variable_name, variable in json_peripheral["variables"].items():
    serialized_value = _serialize_dict_variable_to_thrift(
        peripheral_type,
        variable_name,
        variable,
    )
    if not serialized_value:
      continue
    json_peripheral["variables"][variable_name]["value"] = serialized_value

  # deleted_variables should always contain ModifiedVariables with variable=None, so there is no
  # need to spend time trying to deserialize them.

  return serialization.deserialize(
      thrift_cls=mb_ttypes.Peripheral,
      data=json_peripheral,
      protocol=protocol_ttypes.SerializationProtocol.JSON,
  )


def variable_thrift_to_dict(variable_value):
  if variable_value is None:
    return None
  if not isinstance(variable_value, (int, bool, str)):
    return json.loads(serialization.serialize(
        variable_value,
        protocol=protocol_ttypes.SerializationProtocol.JSON,
    ))
  return variable_value


def _assert_required_variables_exist(peripheral_name,
                                     peripheral_type,
                                     peripheral_variables,
                                     strict):
  peripheral_interface = get_peripheral_interface(peripheral_type)
  if peripheral_interface is None:
    if strict:
      raise PeripheralInterfaceException(
          "Could not find matching interface for type {}".format(peripheral_type)
      )
    log.error("Could not find matching interface for type %s", peripheral_type)
    return
  # If there are any missing required variables, we should let the caller know.
  missing_vars = peripheral_interface.required_variables - peripheral_variables.keys()
  if missing_vars:
    if strict:
      raise PeripheralInterfaceException(
          "Peripheral {} of type {} missing required variables {}".format(
              peripheral_name,
              peripheral_type,
              missing_vars,
          )
      )
    log.error("Peripheral %s of type %s missing required variables %s",
              peripheral_name,
              peripheral_type,
              missing_vars)


def peripheral_thrift_to_dict(peripheral, assert_required_variables=False):
  _assert_required_variables_exist(
      peripheral_name=peripheral.name,
      peripheral_type=peripheral.peripheral_type,
      peripheral_variables=peripheral.variables,
      strict=assert_required_variables,
  )
  peripheral_json = json.loads(serialization.serialize(
      peripheral,
      protocol=protocol_ttypes.SerializationProtocol.JSON,
  ))
  for var_name, variable in peripheral_json["variables"].items():
    if "value" not in variable:
      variable["value"] = None
    deserialized_value = deserialize_peripheral_variable(
        peripheral_json["peripheral_type"],
        name=var_name,
        value=variable["value"],
        log_on_missing=True,
    )
    if deserialized_value:
      variable["value"] = variable_thrift_to_dict(deserialized_value)
  # deleted_variables should always contain ModifiedVariables with variable=None, so there is no
  # need to spend time trying to deserialize them.

  return peripheral_json


def format_dynamic_variable_name(peripheral_type, variable_suffix):
  peripheral_interface = get_peripheral_interface(peripheral_type)
  if not peripheral_interface:
    raise PeripheralInterfaceException(
        "Could not find matching interface for type {}".format(peripheral_type)
    )

  if peripheral_interface.dynamic_variable_prefix is None:
    raise TypeError("No dynamic variable prefix found!")

  return "{}{}".format(peripheral_interface.dynamic_variable_prefix, variable_suffix)


def is_dynamic_variable_name(peripheral_type, variable_name):
  peripheral_interface = get_peripheral_interface(peripheral_type)
  if not peripheral_interface:
    raise PeripheralInterfaceException(
        "Could not find matching interface for type {}".format(peripheral_type)
    )

  if peripheral_interface.dynamic_variable_prefix is None:
    raise TypeError("No dynamic variable prefix found!")

  return variable_name.startswith(peripheral_interface.dynamic_variable_prefix)


def parse_dynamic_variable_name(peripheral_type, variable_name):
  peripheral_interface = get_peripheral_interface(peripheral_type)
  if not is_dynamic_variable_name(peripheral_type, variable_name):
    raise ValueError(
        "Invalid dynamic variable name: {} (expected prefix: {}".format(
            variable_name,
            peripheral_interface.dynamic_variable_prefix,
        )
    )

  prefix_len = len(peripheral_interface.dynamic_variable_prefix)
  return variable_name[prefix_len:]


if __name__ == '__main__':
  print(PERIPHERAL_TYPE_TO_THRIFT_INTERFACE)
