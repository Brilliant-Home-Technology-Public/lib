import inspect

from lib import serialization


class ThriftSerializingHandlerWrapper:
  '''Wraps an instance of an object exposing a Thrift service to exercise serialization logic.

  This class essentially inverts the logic of lib.protocol.thrift_inspect.
  '''

  __slots__ = ("_service_implementation", "_thrift_handler")

  def __init__(self, service_implementation, thrift_handler):
    self._service_implementation = service_implementation
    self._thrift_handler = thrift_handler

  def __getattr__(self, attr_name):
    if hasattr(self._thrift_handler, attr_name):
      args_class, result_class = self._thrift_handler.METHOD_NAME_TO_ARGS_AND_RESULT[attr_name]

      async def _wrapper(*args, **kwargs):
        request_context = None
        service_implementation_method = getattr(self._service_implementation, attr_name)
        sig = inspect.signature(service_implementation_method)
        thrift_args = dict(sig.bind(*args, **kwargs).arguments)
        if getattr(service_implementation_method, '_accept_request_context', False):
          request_context = thrift_args.pop('request_context')

        args_serialized = serialization.serialize(args_class(**thrift_args))
        method = getattr(self._thrift_handler, attr_name)
        result = await method(args_serialized, request_context=request_context)
        if result_class:
          result = serialization.deserialize(result_class, result)
          result = getattr(result, "success", None)
        return result
      return _wrapper
    return getattr(self._service_implementation, attr_name)

  def __setattr__(self, attr_name, value):
    if attr_name in self.__slots__:
      super().__setattr__(attr_name, value)
    else:
      setattr(self._service_implementation, attr_name, value)
