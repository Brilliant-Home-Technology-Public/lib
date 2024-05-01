import abc
import collections.abc
import copy

import lib.immutable.types as immutable_types


class MutableProxyBase(metaclass=abc.ABCMeta):

  __slots__ = ("_proxied", "_mutable_copy", "_immutable_obj")

  def __init__(self, immutable_obj, proxied=None):
    self._proxied = proxied if proxied is not None else {}
    self._proxied[id(immutable_obj)] = self
    self._mutable_copy = copy.copy(immutable_obj)
    # Keep this live so the id in the proxied map doesn't get reused
    self._immutable_obj = immutable_obj

  def _get_proxy(self, val):
    if id(val) in self._proxied:
      return self._proxied[id(val)]
    if isinstance(val, MutableProxyBase):
      return val
    if val is None or not immutable_types.is_immutable_type(val):
      return val
    if isinstance(val, collections.abc.Mapping):
      return MapMutableProxy(val, self._proxied)
    if isinstance(val, collections.abc.Sequence):
      return ListMutableProxy(val, self._proxied)
    if hasattr(val, 'thrift_spec'):
      return ThriftObjectMutableProxy(val, self._proxied)
    raise NotImplementedError("Can't proxy type: {}".format(type(val)))

  def __eq__(self, other):
    if isinstance(other, type(self)):
      return self._mutable_copy == other._mutable_copy

    return self._mutable_copy == other

  def __ne__(self, other):
    return not (self == other)

  def __repr__(self):
    return "{}({})".format(type(self).__name__, repr(self._mutable_copy))

  def __copy__(self):
    return copy.copy(self._mutable_copy)


class ThriftObjectMutableProxy(MutableProxyBase):

  def __getattr__(self, name, *args):
    v = getattr(self._mutable_copy, name, *args)
    return self._get_proxy(v)

  def __setattr__(self, name, value):
    if name in self.__slots__:
      super().__setattr__(name, value)
      return

    setattr(self._mutable_copy, name, value)

  # Following two magic properties are defined so equality checks work with plain Thrift objects
  @property  # type: ignore[misc]
  def __class__(self):
    return type(self._mutable_copy)

  @property
  def __dict__(self):
    return vars(self._mutable_copy)


class MapMutableProxy(MutableProxyBase, collections.abc.MutableMapping):

  def __delitem__(self, key):
    del self._mutable_copy[key]

  def __getitem__(self, key):
    return self._get_proxy(self._mutable_copy[key])

  def __iter__(self):
    return iter(self._mutable_copy)

  def __len__(self):
    return len(self._mutable_copy)

  def __setitem__(self, key, value):
    self._mutable_copy[key] = value


class ListMutableProxy(MutableProxyBase, collections.abc.MutableSequence):

  def __delitem__(self, key):
    del self._mutable_copy[key]

  def __getitem__(self, key):
    return self._get_proxy(self._mutable_copy[key])

  def __iter__(self):
    return iter(self._mutable_copy)

  def __len__(self):
    return len(self._mutable_copy)

  def __setitem__(self, key, value):
    self._mutable_copy[key] = value

  def insert(self, index, obj):  # pylint: disable=arguments-renamed
    self._mutable_copy.insert(index, obj)

  def copy(self):
    return list(self._mutable_copy)
