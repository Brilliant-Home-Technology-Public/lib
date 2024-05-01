import base64
import collections
import inspect
import io
import json
import warnings

from thrift import TSerialization
from thrift.Thrift import TType
from thrift.protocol import TBinaryProtocol
from thrift.protocol import TJSONProtocol
from thrift.transport import TTransport

import thrift_types.protocol.ttypes as protocol_ttypes


MAGIC_STRING = "MTIxOTg0"  # 121984 Base64 encoded
MAGIC_STRING_LEN = 8
MAGIC_STRING_BINARY = b"121984"
MAGIC_STRING_BINARY_LEN = 6

# Versions must be in the format YYYYMMDD. The base64 encoded version will be 12 characters long.
VERSION_LEN = 12
BINARY_VERSION_LEN = 8


# Occasionally we are in a situation where we know the serialization protocol but not the type of
# the underlying data, or vice versa.
TaggedSerializedData = collections.namedtuple('TaggedSerializedData',
                                              ['serialized_data', 'protocol'])


DeserializedData = collections.namedtuple('DeserializedData', ['thrift_obj', 'version'])


def serialize(thrift_object,
              protocol=protocol_ttypes.SerializationProtocol.BASE64_THRIFT_BINARY,
              version=None):
  """Serialize a Thrift object into base64-encoded Thrift binary.

  thrift_object: The Thrift object to serialize.
  protocol: The thrift_types.protocol.ttypes.SerializationProtocol use to serialize the object.
  version: The current Thrift migration version as defined in lib.versioning. If the version is
      given, the version will be encoded with the object. If the version is None, then no version
      information will be encoded with the serialized object.

  Returns: A base64 encoded string.
  """
  return {
      protocol_ttypes.SerializationProtocol.NONE: _serialize_none,
      protocol_ttypes.SerializationProtocol.BASE64_THRIFT_BINARY: _serialize_base64_thrift_binary,
      protocol_ttypes.SerializationProtocol.JSON: _serialize_to_json,
      protocol_ttypes.SerializationProtocol.THRIFT_BINARY: _serialize_thrift_binary,
  }[protocol](thrift_object, version)


def deserialize(thrift_cls,
                data,
                protocol=protocol_ttypes.SerializationProtocol.BASE64_THRIFT_BINARY):
  return deserialize_with_version(thrift_cls=thrift_cls,
                                  data=data,
                                  protocol=protocol).thrift_obj


def deserialize_with_version(thrift_cls,
                             data,
                             protocol=protocol_ttypes.SerializationProtocol.BASE64_THRIFT_BINARY):
  if not inspect.isclass(thrift_cls):
    warnings.warn("Passing an instance to deserialize is deprecated!")
    thrift_cls = type(thrift_cls)

  if (protocol == protocol_ttypes.SerializationProtocol.NONE and
      isinstance(data, TaggedSerializedData)):
    protocol = data.protocol
    data = data.serialized_data

  return {
      protocol_ttypes.SerializationProtocol.NONE: _deserialize_none,
      protocol_ttypes.SerializationProtocol.BASE64_THRIFT_BINARY: _deserialize_base64_thrift_binary,
      protocol_ttypes.SerializationProtocol.JSON: _deserialize_from_json,
      protocol_ttypes.SerializationProtocol.THRIFT_BINARY: _deserialize_thrift_binary,
  }[protocol](thrift_cls, data)


def _serialize_none(obj, version=None):  # pylint: disable=unused-argument
  return obj


def _serialize_base64_thrift_binary(thrift_object, version=None):
  binary_data = _serialize_binary(thrift_object)
  # b64encode returns bytes, but callers expect a string
  base64_data = base64.b64encode(binary_data).decode()
  if not version:
    return base64_data

  # The MAGIC_STRING is already base64 encoded. Base64 encode the version so that the final
  # serialized string is all base64 encoded and ready for storage/transport.
  return "{magic_string}{version}{base64_data}".format(
      magic_string=MAGIC_STRING,
      version=base64.b64encode(version.encode()).decode(),
      base64_data=base64_data
  )


def _serialize_thrift_binary(thrift_object, version=None):
  binary_data = _serialize_binary(thrift_object)
  if not version:
    return binary_data
  # It is not possible to use format on byte strings, so use % instead.
  return b"%s%s%s" % (MAGIC_STRING_BINARY, version.encode(), binary_data)


def _deserialize_none(thrift_cls, data):
  if not isinstance(data, thrift_cls):
    raise TypeError("Incompatible types: {} and {}".format(type(data), thrift_cls))

  return DeserializedData(thrift_obj=data, version=None)


def _deserialize_base64_thrift_binary(thrift_cls, data):
  version = None
  if data.find(MAGIC_STRING, 0, MAGIC_STRING_LEN) == 0:
    version_start = MAGIC_STRING_LEN
    version_end = MAGIC_STRING_LEN + VERSION_LEN
    version = base64.b64decode(data[version_start:version_end]).decode()
    data = data[version_end:]

  binary_data = base64.b64decode(data)
  return DeserializedData(thrift_obj=_deserialize_binary(thrift_cls(), binary_data),
                          version=version)


def _deserialize_thrift_binary(thrift_cls, data):
  version = None
  if data.startswith(MAGIC_STRING_BINARY):
    version_start = MAGIC_STRING_BINARY_LEN
    version_end = MAGIC_STRING_BINARY_LEN + BINARY_VERSION_LEN
    version = data[version_start:version_end].decode()
    data = data[version_end:]
  return DeserializedData(thrift_obj=_deserialize_binary(thrift_cls(), data),
                          version=version)


class _BytesBuffer(TTransport.TMemoryBuffer):
  """A custom subclass of TMemoryBuffer which uses BytesIO instead of StringIO"""

  def __init__(self, value=None):  # pylint: disable=super-init-not-called
    self._buffer = io.BytesIO(*((value,) if value is not None else ()))


def _serialize_binary(thrift_object):
  transport = _BytesBuffer()
  protocol = TBinaryProtocol.TBinaryProtocolAcceleratedFactory().getProtocol(transport)
  thrift_object.write(protocol)
  return transport.getvalue()


def _deserialize_binary(thrift_instance, data):
  thrift_instance.read(
      TBinaryProtocol.TBinaryProtocolAcceleratedFactory().getProtocol(_BytesBuffer(data))
  )
  return thrift_instance


def _serialize_to_json(thrift_obj, _version=None):
  """Converts a thrift object to a serialized json string."""
  return TSerialization.serialize(
      thrift_obj,
      protocol_factory=TJSONProtocol.TSimpleJSONProtocolFactory(),
  )


def _convert_dict_to_thrift(val, ttype, ttype_info):
  if val is None:
    return None
  if ttype == TType.STRUCT:
    (thrift_class, thrift_spec) = ttype_info
    ret = thrift_class()
    for field in thrift_spec:
      if field is not None:
        (tag, field_ttype, field_name, field_ttype_info, dummy) = field
        if field_name in val:
          converted_val = _convert_dict_to_thrift(val[field_name], field_ttype, field_ttype_info)
          setattr(ret, field_name, converted_val)
  elif ttype == TType.LIST:
    (element_ttype, element_ttype_info) = ttype_info
    ret = [_convert_dict_to_thrift(x, element_ttype, element_ttype_info) for x in val]
  elif ttype == TType.SET:
    (element_ttype, element_ttype_info) = ttype_info
    ret = {_convert_dict_to_thrift(x, element_ttype, element_ttype_info) for x in val}
  elif ttype == TType.MAP:
    (key_ttype, key_ttype_info, val_ttype, val_ttype_info) = ttype_info
    ret = {
        _convert_dict_to_thrift(k, key_ttype, key_ttype_info):
            _convert_dict_to_thrift(v, val_ttype, val_ttype_info)
        for k, v in val.items()
    }
  elif ttype == TType.STRING:
    if ttype_info:
      (type_obj,) = ttype_info
      if issubclass(type_obj, bytes):
        # TJSONProtocol serializes binary data to base64
        ret = base64.b64decode(val)
      elif issubclass(type_obj, str):
        ret = str(val)
      else:
        raise TypeError("Unrecognized string type: {}".format(type_obj))
    else:
      ret = str(val)
  elif ttype == TType.DOUBLE:
    ret = float(val)
  elif ttype in (TType.I32, TType.I64, TType.I16, TType.BYTE):
    ret = int(val)
  elif ttype == TType.BOOL:
    ret = bool(val)
  else:
    raise Exception("Unrecognized thrift field type {}".format(ttype))
  return ret


def _deserialize_from_json(thrift_cls, data):
  """Converts serialized json to the thrift class of the requested type."""
  if isinstance(data, str):
    data = json.loads(data)
  thrift_obj = _convert_dict_to_thrift(data, TType.STRUCT, (thrift_cls, thrift_cls.thrift_spec))
  # JSON protocol does not support versioning.
  return DeserializedData(thrift_obj=thrift_obj, version=None)
