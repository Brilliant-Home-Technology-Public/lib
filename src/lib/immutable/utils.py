import contextlib
import copy
import io
import pickle

from lib.immutable import mutable_proxy
import lib.immutable.types as immutable_types


class ImmutableThriftValuesMap(dict):

  def __setitem__(self, key, value):
    super().__setitem__(key, immutable_types.freeze(value))

  @contextlib.contextmanager
  def get_mutable(self, key):
    item = self[key]
    mutable_root = mutable_proxy.ThriftObjectMutableProxy(item)
    yield mutable_root
    frozen = immutable_types.freeze(mutable_root)
    self[key] = frozen

  def get_copy(self, key):
    return immutable_types.thaw(self[key])


class DummyImmutableThriftValuesMap(dict):

  @contextlib.contextmanager
  def get_mutable(self, key):
    item = self[key]
    yield self[key]
    self[key] = item

  def get_copy(self, key):
    return copy.deepcopy(self[key])


class ImmutableCompatiblePickleCopier(pickle.Pickler):

  class Unpickler(pickle.Unpickler):
    def __init__(self, cache, *args, **kwargs):
      super().__init__(*args, **kwargs)
      self._cache = cache

    def persistent_load(self, pid):
      return self._cache[pid]

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._cache = {}

  def persistent_id(self, obj):
    if immutable_types.is_immutable_type(obj):
      key = id(obj)
      self._cache[key] = obj
      return key
    return None

  @classmethod
  def deepcopy(cls, obj):
    file = io.BytesIO()
    pickler = cls(file, protocol=pickle.HIGHEST_PROTOCOL)
    pickler.dump(obj)
    file.seek(0)
    copied = cls.Unpickler(pickler._cache, file).load()
    return copied
