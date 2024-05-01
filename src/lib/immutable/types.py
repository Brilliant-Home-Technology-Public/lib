"""
The message bus sometimes communicates with another endpoint in the same process. When the message
bus invokes a method that passes an object to another endpoint in the same process, if the receiving
endpoint modifies the object, the caller's object would be modified as well. Immutable objects were
introduced to prevent these types of cases.
"""

import abc
import copy

from thrift.Thrift import TType


class ImmutableBase(metaclass=abc.ABCMeta):

  _immutable = True

  @abc.abstractmethod
  def __copy__(self):
    pass

  @abc.abstractmethod
  def __deepcopy__(self, memo):
    pass


def _raise_immutable_error(*args, **kwargs):
  raise TypeError("This object does not support mutation")


class _ProtoImmutableThriftMixin:

  # Thrift deserialization first creates the object then populates its members, so we temporarily
  # allow modifications when the object is first created. Once it's been fully populated, we latch
  # permanently into the immutable mode.
  _immutable_cls = None

  def _latch(self):
    for spec in self._wrapped_cls.thrift_spec:
      if not spec:
        continue

      field_type, field_name, subspec = spec[1:4]
      if field_type in _thrift_primitives:  # Short circuit to avoid unnecessary work
        continue

      val = getattr(self, field_name)
      if val is None:
        continue

      latched_child = _freeze_attr(field_type, val, subspec, None)
      setattr(self, field_name, latched_child)

    self.__class__ = self._immutable_cls  # pylint: disable=invalid-class-object

  def read(self, *args):
    super().read(*args)
    self._latch()


class _ImmutableThriftMixin(ImmutableBase):

  __setattr__ = _raise_immutable_error

  def __new__(cls, *args, **kwargs):
    obj = cls._proto_cls(*args, **kwargs)
    obj._latch()
    return obj

  def __init__(self, *args, **kwargs):
    # __new__ will pass all of these args to the Thrift __init__, so nothing to do here
    pass

  # Suppress warning on overriding read-write property
  @property  # type: ignore[misc]
  def __class__(self):
    return self._wrapped_cls

  def __copy__(self):
    return self._wrapped_cls(**vars(self))

  def __deepcopy__(self, memo):
    return thaw(self)

  def read(self, *args):
    proto_instance = self._proto_cls()
    proto_instance.read(*args)
    for k, v in vars(proto_instance).items():
      super().__setattr__(k, v)


class ImmutableList(ImmutableBase, tuple):

  def __eq__(self, other):
    return other == list(self)

  def copy(self):
    return list(self)

  def __copy__(self):
    return self.copy()

  def __deepcopy__(self, memo):
    return list(copy.deepcopy(i, memo) for i in self)


class ImmutableSet(ImmutableBase, frozenset):

  def copy(self):
    return set(self)

  def __copy__(self):
    return self.copy()

  def __deepcopy__(self, memo):
    return set(copy.deepcopy(k, memo) for k in self)


class ImmutableMap(ImmutableBase, dict):

  __setitem__ = _raise_immutable_error
  __delitem__ = _raise_immutable_error
  pop = _raise_immutable_error
  popitem = _raise_immutable_error
  clear = _raise_immutable_error
  update = _raise_immutable_error
  setdefault = _raise_immutable_error

  def __copy__(self):
    return dict(self)

  def __deepcopy__(self, memo):
    return {k: copy.deepcopy(self[k], memo) for k in self}


_thrift_typecache = {}


def _get_immutable_subspec(field_type, subspec):
  if field_type in _thrift_primitives:
    new_subspec = subspec
  elif field_type == TType.STRUCT:
    proto_cls = get_immutable_type(subspec[0])._proto_cls
    new_subspec = (proto_cls, proto_cls.thrift_spec)
  elif field_type == TType.LIST:
    value_subspec = _get_immutable_subspec(subspec[0], subspec[1])
    new_subspec = (subspec[0], value_subspec)
  elif field_type == TType.SET:
    value_subspec = _get_immutable_subspec(subspec[0], subspec[1])
    new_subspec = (subspec[0], value_subspec)
  elif field_type == TType.MAP:
    value_subspec = _get_immutable_subspec(subspec[2], subspec[3])
    new_subspec = (subspec[0], subspec[1], subspec[2], value_subspec)
  else:
    raise ValueError("Don't know how to handle {}".format(field_type))

  return new_subspec


def get_immutable_type(thrift_cls):
  if thrift_cls not in _thrift_typecache:
    new_spec_list = []
    for entry in thrift_cls.thrift_spec:
      if entry:
        new_entry = (*entry[:3], _get_immutable_subspec(entry[1], entry[3]), *entry[4:])
      else:
        new_entry = entry

      new_spec_list.append(new_entry)

    class_members = {
        "_wrapped_cls": thrift_cls,
        "thrift_spec": tuple(new_spec_list),
    }
    proto_cls = type(
        "{}<Immutable>[Proto]".format(thrift_cls.__name__),
        (_ProtoImmutableThriftMixin, thrift_cls),
        class_members,
    )
    new_cls = type(
        "{}<Immutable>".format(thrift_cls.__name__),
        (_ImmutableThriftMixin, thrift_cls),
        {
            "_proto_cls": proto_cls,
            **class_members
        },
    )
    proto_cls._immutable_cls = new_cls
    _thrift_typecache[thrift_cls] = new_cls

  return _thrift_typecache[thrift_cls]


_thrift_primitives = {
    TType.BOOL,
    TType.BYTE,
    TType.I08,
    TType.DOUBLE,
    TType.I16,
    TType.I32,
    TType.I64,
    TType.STRING,
    TType.UTF7,
    TType.UTF8,
    TType.UTF16,
}


def is_immutable_type(obj):
  return getattr(obj, "_immutable", None)


def freeze(thrift_obj, proxied=None):
  if not hasattr(thrift_obj, 'thrift_spec'):
    raise TypeError("Expected a Thrift object")

  # The proxied arg and the following check are here to help implement the MutableProxy types
  # (see mutable_proxy.py), which allow us to efficiently track changes when we want to update
  # an immutable object.
  proxied = {}
  if hasattr(thrift_obj, "_mutable_copy"):
    proxied = thrift_obj._proxied
    thrift_obj = thrift_obj._mutable_copy

  return _freeze_thrift_obj(thrift_obj, proxied=proxied)


def thaw(thrift_obj):
  return _thaw_thrift_obj(thrift_obj)


def _freeze_thrift_obj(thrift_obj, proxied):
  if thrift_obj is None:
    return None

  if isinstance(thrift_obj, _ProtoImmutableThriftMixin):
    thrift_obj._latch()
    return thrift_obj
  if is_immutable_type(thrift_obj):
    return thrift_obj

  base_cls = type(thrift_obj)
  new_cls = get_immutable_type(base_cls)

  constructor_args = {}
  for spec in (s for s in thrift_obj.thrift_spec if s):
    field_type, field_name, subspec = spec[1:4]
    frozen_val = _freeze_attr(field_type, getattr(thrift_obj, field_name), subspec, proxied)
    constructor_args[field_name] = frozen_val

  new_obj = new_cls(**constructor_args)
  return new_obj


def _freeze_attr(field_type, val, subspec, proxied):
  if proxied is not None:
    # The following checks are actually somewhat expensive so only do them if necessary
    if id(val) in proxied:
      val = proxied[id(val)]

    val = getattr(val, "_mutable_copy", val)

  if val is None:
    return val
  if (field_type == TType.STRUCT or
      # Hack to handle Thrift objects masquerading as strings when we're using null serialization.
      # We also check for `bytes` here because TType.BYTES is an alias of TType.STRING.
      (field_type == TType.STRING and not isinstance(val, (str, bytes)))):
    return _freeze_thrift_obj(val, proxied)
  if field_type in _thrift_primitives:
    return val
  if field_type == TType.LIST:
    immutable_items = (_freeze_attr(subspec[0], v, subspec[1], proxied) for v in val)
    return ImmutableList(immutable_items)
  if field_type == TType.SET:
    immutable_items = set(_freeze_attr(subspec[0], v, subspec[1], proxied) for v in val)
    return ImmutableSet(immutable_items)
  if field_type == TType.MAP:
    immutable_items = {
        k: _freeze_attr(subspec[2], v, subspec[3], proxied) for k, v in val.items()
    }
    return ImmutableMap(immutable_items)
  raise ValueError("Don't know how to handle {}".format(field_type))


def _thaw_thrift_obj(thrift_obj):
  if thrift_obj is None:
    return None

  # Always recurse through Thrift objects, even if they are mutable at the top level
  constructor_args = {}
  for spec in (s for s in thrift_obj.thrift_spec if s):
    field_type, field_name, subspec = spec[1:4]
    thawed_val = _thaw_attr(field_type, getattr(thrift_obj, field_name), subspec)
    constructor_args[field_name] = thawed_val

  new_obj = thrift_obj.__class__(**constructor_args)
  return new_obj


def _thaw_attr(field_type, val, subspec):
  if (field_type == TType.STRUCT or
      # See comment above
      (field_type == TType.STRING and not isinstance(val, (str, bytes)))):
    return _thaw_thrift_obj(val)
  if field_type in _thrift_primitives:
    return val
  if val is None:
    return val
  if field_type == TType.LIST:
    return list(_thaw_attr(subspec[0], v, subspec[1]) for v in val)
  if field_type == TType.SET:
    return set(_thaw_attr(subspec[0], v, subspec[1]) for v in val)
  if field_type == TType.MAP:
    new_mapping = {
        k: _thaw_attr(subspec[2], v, subspec[3]) for k, v in val.items()
    }
    return new_mapping
  raise ValueError("Don't know how to handle {}".format(field_type))
