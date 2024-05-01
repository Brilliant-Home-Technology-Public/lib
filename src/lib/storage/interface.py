import abc


class ObjectStoreBase(metaclass=abc.ABCMeta):

  @abc.abstractmethod
  async def get(self, key, owner):
    pass

  @abc.abstractmethod
  async def put(self, value, metadata):
    pass

  @abc.abstractmethod
  async def head(self, key, owner):
    pass

  async def delete(self, key, owner):
    return "OK"


class ObjectMetadata:

  class CacheControl:

    NO_STORE = "no-store"

  _attrs = [
      ("size", "Content-Length", int),
      ("content_type", "Content-Type", str),
      ("content_encoding", "Content-Encoding", str),
      ("brilliant_content_encoding", "Brilliant-Content-Encoding", str),
      ("cache_control", "Cache-Control", str),
      ("home_id", "X-Home-Id", str),
      ("device_id", "X-Device-Id", str),
      ("name", "X-Object-Name", str),
      ("release_tag", "X-Release-Tag", str),
      ("environment", "X-Environment", str),
  ]

  def __init__(self, **kwargs):
    for attr_name, _, _ in self._attrs:
      setattr(self, attr_name, kwargs.pop(attr_name, None))

    if kwargs:
      raise TypeError(
          "__init__() got an unexpected keyword argument '{}'".format(kwargs.popitem()[0])
      )

  @classmethod
  def from_headers(cls, headers):
    constructor_args = {}
    for attr_name, header_name, attr_type in cls._attrs:
      header_val = headers.get(header_name)
      if not header_val:
        header_val = headers.get(header_name.upper())

      if header_val:
        constructor_args[attr_name] = attr_type(header_val)

    return cls(**constructor_args)

  def to_headers(self):
    header_dict = {}
    for attr_name, header_name, _ in self._attrs:
      val = getattr(self, attr_name)
      if val:
        header_dict[header_name] = str(val)

    return header_dict

  def __eq__(self, other):
    return (isinstance(other, ObjectMetadata) and
            self.to_headers() == other.to_headers())

  def __repr__(self):
    return "ObjectMetadata({})".format(repr(self.to_headers()))
