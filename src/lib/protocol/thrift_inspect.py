import collections
import functools
import inspect

from lib import serialization
from lib.immutable import types as immutable_types


ThriftMethodPythonSpec = collections.namedtuple("ThriftMethodPythonSpec",
                                                ["name", "args", "result"])


def make_server_class(service_module, use_immutable_types=False):
  '''The purpose of this function is to a wrap a service implementation such that all methods are
     called with serialized strings and return serialized strings both of whose underlying
     structures correspond to their thrift specs.
     WHY: A server is implemented using a class that implements the methods specified in
     a thrift service definition, but we don't use the native server capabilities.
     HOW: This method takes the thrift module that corresponds to a service (for example:
     thrift_types.message_bus.MessageBusService) and returns a wrapped instance of that class such
     that:
     1. All methods of the wrapped class are called with serialized thrift arguments as a single
        string. This wrapper will deserialize these arguments and invoke the underlying method
        with arguments as specified in the thrift spec.
        For example: If the underlying method being called is "foo(a=1, b=2)" the wrapped method
        must be called as "foo(serialize(foo_args(a=1,b=2)))"
     2. All methods of the wrapped class will return a serialized version of their return object
        as it is specified in their thrift specs.
     3. The class initializer takes a single object -- a handler that implements the methods from
        the service description. (See _ServerBase)
     NOTE: This function returns a CLASS, not an instance.
  '''
  return type(
      service_module.Iface.__name__ + "Server",
      (_ServerBase,),
      _make_class_dict(
          _handle_method_prototype,
          service_module,
          use_immutable_types=use_immutable_types,
      ),
  )


def make_client_class(service_module, use_immutable_types=False):
  '''This function is the counterpart to make_server_class. It creates a client class based on the
     thrift spec for a service. The returned class has the following rules:
     1. There is a method for each method in corresponding service
     2. When these methods are invoked, their arguments are serialized and sent to the processor
        to send them to the remote server.
     3. When the remote server sends back a serialized response, the arguments are deserialized
        and that value is returned to the caller.
     4. The initializer for the class takes three arguments (also see: _ClientBase):
        - The rpc_peer instance connected to the server the client is communicating with
        - The peer_name of the server
        - A function/coroutine accepting two arguments (method name, serialized_arguments) that
          will actually make the request
  '''
  return type(
      service_module.Iface.__name__ + "Client",
      (_ClientBase,),
      _make_class_dict(
          _invoke_method_prototype,
          service_module,
          use_immutable_types=use_immutable_types,
      ),
  )


def accept_request_context(handler_method):
  handler_method._accept_request_context = True
  return handler_method


def _make_class_dict(prototype_function, service_module, use_immutable_types):
  interface_class = service_module.Iface
  class_dict = {
      method_name: prototype_function(method_name, method)
      for method_name, method in _get_service_methods(interface_class)
  }
  class_dict["METHOD_NAME_TO_ARGS_AND_RESULT"] = \
      _generate_method_name_to_args_and_result(service_module, use_immutable_types)
  return class_dict


def _handle_method_prototype(method_name, _):
  async def handle_method(self, args_serialized, request_context=None):
    args_class, result_class = self.METHOD_NAME_TO_ARGS_AND_RESULT[method_name]

    serialization_kwargs = {}
    if request_context and request_context.serialization_protocol is not None:
      serialization_kwargs.update(protocol=request_context.serialization_protocol)

    args_object = serialization.deserialize(
        args_class,
        args_serialized,
        **serialization_kwargs
    )
    args_to_pass = vars(args_object)
    handler_method = getattr(self.handler, method_name)

    if getattr(handler_method, '_accept_request_context', False):
      args_to_pass['request_context'] = request_context

    if (request_context and request_context.negotiated_api_version is not None and
        self.current_api_version is not None):
      args_to_pass = self.current_api_version.translate_args_from_version(
          method_name,
          args_to_pass,
          request_context.negotiated_api_version,
      )

    result_value = await handler_method(**args_to_pass)

    if not result_class:
      return None
    if (request_context and request_context.negotiated_api_version is not None and
        self.current_api_version is not None):
      result_value = self.current_api_version.translate_response_to_version(
          method_name,
          result_value,
          request_context.negotiated_api_version,
          context={"args": args_to_pass},
      )
    result_args = {}
    if result_class.thrift_spec:
      result_args.update(success=result_value)
    result_obj = result_class(**result_args)
    return serialization.serialize(
        result_obj,
        **serialization_kwargs
    )

  return handle_method


def _invoke_method_prototype(method_name, method):
  signature = inspect.signature(method)

  @functools.wraps(method)
  async def invoke_method(self, *args, **kwargs):
    # Raises a TypeError if signature does not match args passed
    bound_args = signature.bind(*args, **kwargs)
    args_class, result_class = self.METHOD_NAME_TO_ARGS_AND_RESULT[method_name]
    rpc_peer = self._thrift_wrapped_rpc_peer
    if rpc_peer.current_api_version is not None:
      new_arguments = rpc_peer.current_api_version.translate_args_to_version(
          method_name,
          bound_args.arguments,
          rpc_peer.negotiated_api_version
      )
    else:
      new_arguments = bound_args.arguments
    result_serialized = await self._thrift_wrapped_rpc_peer.make_thrift_request(
        method_name,
        serialization.serialize(args_class(**new_arguments),
                                protocol=self._thrift_wrapped_rpc_peer.serialization_protocol),
        is_oneway=not bool(result_class),
    )
    if result_class:
      result_object = serialization.deserialize(
          result_class,
          result_serialized,
          protocol=self._thrift_wrapped_rpc_peer.serialization_protocol,
      )
      if not hasattr(result_object, "success"):
        return None
      if rpc_peer.current_api_version is not None:
        return rpc_peer.current_api_version.translate_response_from_version(
            method_name,
            result_object.success,
            rpc_peer.negotiated_api_version,
            context={"args": new_arguments},
        )
      return result_object.success
    return None

  return invoke_method


def _generate_method_name_to_args_and_result(service_module, use_immutable_types):
  interface_class = service_module.Iface
  return {
      method_name: _get_args_and_result(service_module, method_name, use_immutable_types)
      for method_name, _ in _get_service_methods(interface_class)
  }


def _get_args_and_result(service_module, method_name, use_immutable_types):
  args_cls = getattr(service_module, method_name + "_args")
  # Oneway methods have no results
  result_cls = getattr(service_module, method_name + "_result", None)
  if use_immutable_types:
    args_cls = immutable_types.get_immutable_type(args_cls)
    result_cls = immutable_types.get_immutable_type(result_cls) if result_cls else None

  return (args_cls, result_cls)


def _get_service_methods(interface_class):
  return inspect.getmembers(interface_class(), inspect.ismethod)


class _ClientBase:

  def __init__(self, thrift_wrapped_rpc_peer):
    self._thrift_wrapped_rpc_peer = thrift_wrapped_rpc_peer

  @property
  def rpc_peer(self):
    return self._thrift_wrapped_rpc_peer.rpc_peer

  @property
  def peer_name(self):
    return self._thrift_wrapped_rpc_peer.peer_name

  @property
  def unqualified_peer_name(self):
    return self._thrift_wrapped_rpc_peer.unqualified_peer_name


class _ServerBase:
  def __init__(self, handler, current_api_version=None):
    self.handler = handler
    self.current_api_version = current_api_version
