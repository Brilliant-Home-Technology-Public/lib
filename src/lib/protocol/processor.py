import abc
import asyncio
import collections
import copy
import functools
import logging
import sys

import async_timeout
import gflags

from lib import connection_manager
from lib import exceptions
from lib import serialization
from lib.async_helpers import future_value
from lib.async_helpers import iterable_queue
import lib.networking.utils as networking_utils
from lib.protocol import interface
import lib.time
import thrift_types.protocol.constants as protocol_consts
import thrift_types.protocol.ttypes as protocol_ttypes


gflags.DEFINE_integer("socket_timeout_seconds", 5, "")

log = logging.getLogger(__name__)

FLAGS = gflags.FLAGS


class NameInUseError(Exception):
  pass


class ProcessorBase(metaclass=abc.ABCMeta):

  def __init__(self, my_name,
               handler,
               client_class,
               my_domain=None,
               my_aliases=None,
               new_client_async_callback=None,
               loop=None,
               synchronous_requests=True,
               authentication_policy=None,
               connection_params=None,
               supported_api_versions=None,
               current_api_version=None,
               max_concurrent_peer_starts=None,
               cert_file_directory=None):
    '''
      handler: All methods in this class must match the commands we receive as requests. They will
          be invoked as handler.command_name(args_serialized) and should return a serialized
          response
      client_class: A class that takes (rpc_peer, peer_name, make_request_func) as __init__ args
    '''
    self.handler = handler
    self.loop = loop
    self.client_class = client_class
    self._my_name = my_name
    self._my_domain = my_domain
    self._my_aliases = set(my_aliases or [])
    self._new_client_async_callback = new_client_async_callback
    self._synchronous_requests = synchronous_requests
    self._rpc_peers = set()
    self._supported_api_versions = supported_api_versions
    self._current_api_version = current_api_version
    if supported_api_versions is not None:
      # connection manager only cares about the string version
      cm_api_versions = [v.version for v in supported_api_versions]
    else:
      cm_api_versions = None
    self._connection_manager = connection_manager.PeerConnectionManager(
        loop=self.loop,
        new_peer_async_callback=self._new_peer_async_callback,
        connection_params=connection_params,
        peer_socket_timeout=FLAGS.socket_timeout_seconds,
        authentication_policy=authentication_policy,
        supported_api_versions=cm_api_versions,
        cert_file_directory=cert_file_directory,
        max_concurrent_peer_starts=max_concurrent_peer_starts,
    )

  async def shutdown(self):
    """ Shuts down the protocol processor's peer connection manager.
    """
    await self._connection_manager.shutdown()
    try:
      await asyncio.gather(
          *[rpc_peer.shutdown() for rpc_peer in self._rpc_peers],
      )
    except Exception:
      log.exception("Ignoring error in shutdown")

  @abc.abstractmethod
  async def start(self):
    """A start function"""

  async def __aenter__(self):
    try:
      await asyncio.wait_for(
          self.start(),
          timeout=FLAGS.socket_timeout_seconds,
      )
      return self
    except (asyncio.CancelledError, Exception) as e:
      # Need to attempt to clean up even if we failed to start
      await self.__aexit__(*sys.exc_info())
      raise

  async def __aexit__(self, exc_type, exc_value, traceback):
    try:
      await self.shutdown()
    except Exception as e:
      log.error("Ignoring error in context manager shutdown: %r", e)

  @abc.abstractmethod
  async def _register_new_client(self, client):
    pass

  async def _new_peer_async_callback(self, peer):
    """The callback for new peers coming from the connection manager"""
    client = await self._make_client_for_peer(peer, is_initiator=bool(peer.remote_address))
    try:
      await self._register_new_client(client)
    except NameInUseError as e:
      log.error("Cannot add client for peer: %s", e)
      raise

    # Start handling requests from this peer now that it's been accepted as valid
    client.rpc_peer.start_server()
    await self._invoke_new_client_callback(client)

  async def _invoke_new_client_callback(self, client):
    if self._new_client_async_callback:
      try:
        await self._new_client_async_callback(client)
      except asyncio.CancelledError:  # pylint: disable=try-except-raise
        raise
      except Exception:
        log.exception("Error in new client callback!")

  async def _dead_rpc_peer_async_callback(self, peer):
    await self._discard_peer(peer)

  async def _updated_hello_async_callback(self, rpc_peer, updated_hello):
    pass

  def cancel_pending_connection(self, peer_address):
    self._connection_manager.cancel_pending_connection(peer_address)

  def _get_qualified_name(self, name, domain=None):
    if not domain:
      domain = self._my_domain

    if domain:
      return "%s.%s" % (domain, name)
    return name

  def _my_hello(self):
    hello = protocol_ttypes.Hello(
        name=self._my_name,
        domain=self._my_domain,
        aliases=list(self._my_aliases),
    )
    return hello

  async def _make_client_for_peer(self, peer, is_initiator):
    rpc_peer = MultiplexedRPCPeer(
        my_hello=self._my_hello(),
        peer=peer,
        handle_request_async_callback=self.handle_request,
        handle_connection_lost_async_callback=self._dead_rpc_peer_async_callback,
        handle_updated_hello_async_callback=self._updated_hello_async_callback,
        loop=self.loop,
        is_initiator=is_initiator,
        synchronous_requests=self._synchronous_requests,
    )
    peer_hello = await asyncio.wait_for(
        # Don't want to cancel the FutureValue underneath
        asyncio.shield(rpc_peer.start(start_server=False)),
        timeout=FLAGS.socket_timeout_seconds,
    )
    self._rpc_peers.add(rpc_peer)
    client = self.client_class(
        thrift_wrapped_rpc_peer=ThriftWrappedMultiplexedRPCPeer(
            peer_name=self._get_qualified_name(peer_hello.name, peer_hello.domain),
            unqualified_peer_name=peer_hello.name,
            rpc_peer=rpc_peer,
            loop=self.loop,
            current_api_version=self._current_api_version,
        ),
    )
    return client

  async def handle_request(self, request, request_context=None):
    return await ThriftWrappedRPCProtocol.handle_request(
        loop=self.loop,
        handler=self.handler,
        request=request,
        request_context=request_context,
    )

  async def _discard_peer(self, rpc_peer):
    self._rpc_peers.discard(rpc_peer)
    await rpc_peer.shutdown()


class ThriftWrappedRPCPeerBase(metaclass=abc.ABCMeta):

  def __init__(self, loop, current_api_version=None):
    self._loop = loop
    self.current_api_version = current_api_version

  @property
  @abc.abstractmethod
  def peer_name(self):
    pass

  @property
  @abc.abstractmethod
  def unqualified_peer_name(self):
    pass

  @property
  @abc.abstractmethod
  def rpc_peer(self):
    pass

  @property
  @abc.abstractmethod
  def serialization_protocol(self):
    pass

  @abc.abstractmethod
  async def make_request_to_peer(self, request):
    pass

  @property
  @abc.abstractmethod
  def negotiated_api_version(self):
    pass

  async def make_thrift_request(self, command, args_serialized, is_oneway=False):
    return await ThriftWrappedRPCProtocol.make_request(
        loop=self._loop,
        make_thrift_request_func=self.make_request_to_peer,
        command=command,
        args_serialized=args_serialized,
        is_oneway=is_oneway,
    )


class ThriftWrappedMultiplexedRPCPeer(ThriftWrappedRPCPeerBase):

  def __init__(self, peer_name, unqualified_peer_name, rpc_peer, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._peer_name = peer_name
    self._unqualified_peer_name = unqualified_peer_name
    self._rpc_peer = rpc_peer

  @property
  def rpc_peer(self):
    return self._rpc_peer

  @property
  def peer_name(self):
    return self._peer_name

  @property
  def unqualified_peer_name(self):
    return self._unqualified_peer_name

  @property
  def serialization_protocol(self):
    return self._rpc_peer.serialization_protocol

  @property
  def negotiated_api_version(self):
    return self._rpc_peer.negotiated_api_version

  async def make_request_to_peer(self, request):
    return await self._rpc_peer.make_request(request)


class MulticastThriftWrappedPeer(ThriftWrappedRPCPeerBase):

  def __init__(self, rpc_peers, log_errors=False, **kwargs):
    super().__init__(**kwargs)
    self._rpc_peers = rpc_peers
    self._log_errors = log_errors

  @property
  def rpc_peer(self):
    return None

  @property
  def peer_name(self):
    return None

  @property
  def unqualified_peer_name(self):
    return None

  @property
  def serialization_protocol(self):
    return protocol_ttypes.SerializationProtocol.NONE

  @property
  def negotiated_api_version(self):
    return self.current_api_version.version if self.current_api_version is not None else None

  async def make_request_to_peer(self, request):
    # Arbitrarily return the result from the first peer
    # TODO: enforce that this is only used to make requests returning void!

    request_args = request.args_serialized
    serialization_cache = {}

    futures = []
    for rpc_peer in self._rpc_peers:
      cache_key = (rpc_peer.serialization_protocol, rpc_peer.negotiated_api_version)
      try:
        if cache_key not in serialization_cache:
          reserialized = copy.copy(request)
          if self.current_api_version is not None:
            new_arg_dict = self.current_api_version.translate_args_to_version(
                request.command,
                vars(request_args),
                rpc_peer.negotiated_api_version
            )
            args_class = request_args.__class__
            new_args = args_class(**new_arg_dict)
          else:
            new_args = request_args
          reserialized.args_serialized = serialization.serialize(
              new_args,
              protocol=rpc_peer.serialization_protocol,
          )
          serialization_cache[cache_key] = reserialized

        # make_request() is an ordinary function that returns an awaitable, and it might
        # raise an exception. We don't want this exception to interfere with delivery of
        # the request to other peers, so we catch those exceptions here.
        future = rpc_peer.make_request(serialization_cache[cache_key])
      except Exception as e:
        future = asyncio.Future(loop=self._loop)
        future.set_exception(e)

      # Regardless of whether we succeeded in making the request, add a (possibly dummy) awaitable
      # to the list. This approach is a little stilted but allows us to simplify and unify error
      # handling logic.
      futures.append(future)

    results = await asyncio.gather(
        *futures,
        return_exceptions=True,
    )
    non_error_results = []
    # this result doesn't actually matter, so we don't need to worry about converting versions here.
    for result, peer in zip(results, self._rpc_peers):
      if isinstance(result, Exception):
        if self._log_errors:
          level = logging.ERROR
          if isinstance(result, (asyncio.TimeoutError, TimeoutError, exceptions.NoConnectionError)):
            level = logging.WARNING
          log.log(
              level,
              "Encountered exception making request %s to peer %s: %r",
              request.command, peer.peer_name(), result,
          )
        else:
          raise result
      else:
        result_tagged = copy.copy(result)
        if result_tagged:
          result_tagged.result_serialized = serialization.TaggedSerializedData(
              serialized_data=result.result_serialized,
              protocol=peer.serialization_protocol,
          )
        non_error_results.append(result_tagged)

    if non_error_results:
      return non_error_results[0]
    if results:
      raise results[0]
    raise exceptions.NoConnectionError("No results available!")


class ThriftWrappedRPCProtocol:

  EXCEPTIONS_BY_STATUS_CODE = {
      protocol_consts.StatusCode.AUTHORIZATION_VALIDATION_ERROR: (
          exceptions.AuthorizationValidationError,
      ),
      protocol_consts.StatusCode.BAD_ARGS_ERROR: (exceptions.BadArgsError,),
      protocol_consts.StatusCode.CONNECTION_ERROR: (
          exceptions.NoConnectionError,
          asyncio.CancelledError,
      ),
      protocol_consts.StatusCode.CONSISTENCY_ERROR: (exceptions.ConsistencyError,),
      protocol_consts.StatusCode.DOES_NOT_EXIST_ERROR: (exceptions.DoesNotExistError,),
      protocol_consts.StatusCode.PERMISSION_ERROR: (PermissionError,),
      protocol_consts.StatusCode.TIMEOUT: (asyncio.TimeoutError, TimeoutError),
      protocol_consts.StatusCode.PROTOCOL_ERROR: (exceptions.ProtocolError,),
      protocol_consts.StatusCode.SET_REQUEST_ERROR: (
          exceptions.PeripheralSetRequestError,
      ),
      protocol_consts.StatusCode.UART_COMMUNICATION_ERROR: (exceptions.UARTCommunicationError,),
  }

  STATUS_CODES_BY_EXCEPTION = {e: k for k, v in EXCEPTIONS_BY_STATUS_CODE.items() for e in v}

  @classmethod
  async def handle_request(cls,
                           loop,
                           handler,
                           request,
                           request_context=None,
                           extra_status_codes_by_exception=None):
    """ Sends a request with the given command and args to the peer
    Should only be used by the MessageBusPeerClient
    """
    result = None
    extra_status_codes_by_exception = extra_status_codes_by_exception or {}
    try:
      # TODO: Might want to explicitly handle attributeErrors here (for bad command)
      handler_func = getattr(handler, request.command)
      async with async_timeout.timeout(FLAGS.socket_timeout_seconds):
        result_serialized = await handler_func(
            request.args_serialized,
            request_context=request_context
        )
      return interface.Response(status=cls._get_success_status_response(),
                                result_serialized=result_serialized)
    except (asyncio.CancelledError, Exception) as e:
      if type(e) in cls.STATUS_CODES_BY_EXCEPTION:
        status_code = cls.STATUS_CODES_BY_EXCEPTION[type(e)]
      elif type(e) in extra_status_codes_by_exception:
        status_code = extra_status_codes_by_exception[type(e)]
      else:
        # Only spam the logs on errors we don't explicitly remap.
        log.exception("Caught exception when handling request")
        status_code = protocol_ttypes.StatusCode.GENERAL_ERROR
      if status_code == protocol_consts.StatusCode.CONNECTION_ERROR:
        log.warning("Received connection error when handling %s: %s", request.command, str(e))

      status_response = protocol_ttypes.StatusResponse(
          status_code=status_code,
          error_msg=str(e),
      )
      # If an error was raised, we'll end up returning none for the result
      return interface.Response(status=status_response)

  @classmethod
  async def make_request(cls, loop, make_thrift_request_func, command, args_serialized, is_oneway):
    request = interface.Request(
        command=command,
        args_serialized=args_serialized,
        is_oneway=is_oneway,
    )
    response = await make_thrift_request_func(request)
    if is_oneway:
      if response:
        log.warning("Got a non-None response %r for oneway method!", response)
      return

    if response.status.status_code == protocol_consts.StatusCode.NO_ERROR:
      return response.result_serialized
    excs = cls.EXCEPTIONS_BY_STATUS_CODE.get(response.status.status_code, (Exception,))
    raise excs[0](response.status.error_msg)

  @classmethod
  def _get_success_status_response(cls):
    return protocol_ttypes.StatusResponse(
        status_code=protocol_ttypes.StatusCode.NO_ERROR,
        error_msg=None
    )


class SinglePeerProcessor(ProcessorBase):
  """Subclass of the protocol processor. Establishes a connection with the messagebus"""

  def __init__(self, socket_path=None, peer_address=None, **kwargs):
    super().__init__(**kwargs)
    if bool(socket_path) == bool(peer_address):
      raise ValueError("Exactly one of socket_path/peer_address must be specified")

    if socket_path:
      self.peer_address = networking_utils.format_address(
          path=socket_path,
          address_family=networking_utils.AddressFamily.UNIX,
      )
    else:
      self.peer_address = peer_address

    self.client = None
    self._connection = None
    self._first_callback_future = future_value.FutureValue(loop=self.loop)
    self._reconnect_callbacks = set()

  async def _register_new_client(self, client):
    self.client = client

  async def start(self):
    # Will block until the connection is established (for the first time)
    self._connection = self._connection_manager.open_connection(self.peer_address)
    await self._connection
    await self._first_callback_future

  async def shutdown(self):
    await super().shutdown()
    # Only clear _first_callback_future if we've successfully shutdown self._connection_manager,
    # which should happen in the super call. If we haven't shutdown self._connection_manager, then
    # we may not get a new client when we call open_connection, because the client already exists
    # from a previous start call. If that happens, we don't want to deadlock ourselves on
    # _first_callback_future waiting for a new client that will never show up.
    self._first_callback_future.clear()

  async def _invoke_new_client_callback(self, client):
    if self._first_callback_future.has_value():
      await super()._invoke_new_client_callback(client)
      await self._invoke_reconnect_callbacks()
      return

    # Override the parent method so we can make start() fail with an exception if the callback
    # fails, which should usually be a fatal error for the whole program.
    if self._new_client_async_callback:
      try:
        await self._new_client_async_callback(client)
      except Exception as e:
        self._first_callback_future.set_exception(e)
        return

    self._first_callback_future.set_value(None)

  async def _invoke_reconnect_callbacks(self):
    try:
      reconnect_callback_tasks = [callback() for callback in self._reconnect_callbacks]
      await asyncio.gather(*reconnect_callback_tasks)
    except asyncio.CancelledError:  # pylint: disable=try-except-raise
      raise
    except Exception:
      log.exception("Exception encountered invoking client reconnect callbacks!")

  def add_alias(self, alias):
    if alias != self._my_name and alias not in self._my_aliases:
      self._my_aliases.add(alias)
      if self.client:
        try:
          self.client.rpc_peer.update_hello(self._my_hello())
        except Exception:
          self._my_aliases.remove(alias)
          raise

  def remove_alias(self, alias):
    if alias == self._my_name:
      log.error("Cannot remove primary name!")
      return

    if alias in self._my_aliases:
      self._my_aliases.remove(alias)
      if self.client:
        try:
          self.client.rpc_peer.update_hello(self._my_hello())
        except Exception:
          self._my_aliases.add(alias)
          raise

  def add_reconnect_callback(self, callback):
    self._reconnect_callbacks.add(callback)

  def is_connected(self):
    return bool(self._connection and self._connection.is_connected())


class MultiPeerProcessor(ProcessorBase):
  """Subclass of the protocol processor. Starts the messagebus server"""

  def __init__(self, *args,
               listen_address=None,
               listen_addresses=None,
               removed_client_async_callback=None,
               **kwargs):
    super().__init__(*args, **kwargs)
    if bool(listen_address) == bool(listen_addresses):
      raise ValueError("Exactly one of listen_address/listen_addresses must be specified!")

    self.listen_addresses = listen_addresses or [listen_address]
    self._removed_client_async_callback = removed_client_async_callback
    self._clients_by_qualified_name = {}

  async def start(self):
    for listen_address in self.listen_addresses:
      await self._connection_manager.start_server(listen_address=listen_address)

  async def _discard_peer(self, rpc_peer):
    await super()._discard_peer(rpc_peer)
    if not rpc_peer.get_peer_hello():
      log.warning("Never received hello from peer %s", id(rpc_peer))
      return

    name, aliases = self._get_qualified_name_and_aliases_for_peer(rpc_peer)

    if (name not in self._clients_by_qualified_name or
        self._clients_by_qualified_name[name].rpc_peer != rpc_peer):
      log.warning("Could not match name %s to client", name)
      return

    await self._remove_names_for_client(
        self._clients_by_qualified_name[name],
        [name] + aliases,
    )

  async def _remove_names_for_client(self, client, names_to_remove):
    names_removed = []
    for name in names_to_remove:
      maybe_our_client = self._clients_by_qualified_name.get(name)
      if maybe_our_client == client:
        self._clients_by_qualified_name.pop(name)
        names_removed.append(name)

    if self._removed_client_async_callback and names_removed:
      try:
        await self._removed_client_async_callback(names_removed)
      except asyncio.CancelledError:  # pylint: disable=try-except-raise
        raise
      except Exception as e:
        log.exception("Error in removed_client_async_callback")

  def open_connection(self, peer_address, *, expected_peer_parameters=None):
    return self._connection_manager.open_connection(
        peer_address,
        expected_peer_parameters=expected_peer_parameters,
    )

  def _get_qualified_name_and_aliases_for_peer(self, rpc_peer, hello_override=None):
    peer_hello = hello_override or rpc_peer.get_peer_hello()
    name = self._get_qualified_name(peer_hello.name, domain=peer_hello.domain)
    aliases = [
        self._get_qualified_name(alias, domain=peer_hello.domain)
        for alias in (peer_hello.aliases or [])
    ]
    return name, aliases

  async def _register_new_client(self, client):
    existing_client = self._clients_by_qualified_name.get(client.peer_name)
    if existing_client:
      if existing_client.peer_name == client.peer_name:
        raise NameInUseError("Cannot rebind name %s to new client; already in use!" %
                             client.peer_name)
      log.warning("Removed alias %s for %s", client.peer_name, existing_client.peer_name)

    self._clients_by_qualified_name[client.peer_name] = client
    for alias in self._get_qualified_name_and_aliases_for_peer(client.rpc_peer)[1]:
      self._maybe_add_alias(client, alias)

  def _maybe_add_alias(self, client, alias):
    if alias not in self._clients_by_qualified_name:
      self._clients_by_qualified_name[alias] = client
    else:
      log.warning("Alias %s for %s already in use (actual name: %s)",
                  alias, client.peer_name, self._clients_by_qualified_name[alias].peer_name)

  async def _updated_hello_async_callback(self, rpc_peer, updated_hello):
    await super()._updated_hello_async_callback(rpc_peer, updated_hello)

    name, prior_aliases = self._get_qualified_name_and_aliases_for_peer(rpc_peer)
    new_name, new_aliases = self._get_qualified_name_and_aliases_for_peer(
        rpc_peer, hello_override=updated_hello)

    prior_alias_set = set(prior_aliases)
    new_alias_set = set(new_aliases)

    if new_name != name:
      log.error("Peer cannot change name to %s (previously: %s)", new_name, name)
      return

    client = self._clients_by_qualified_name[name]
    for alias_to_add in (new_alias_set - prior_alias_set):
      self._maybe_add_alias(client, alias_to_add)

    await self._remove_names_for_client(client, (prior_alias_set - new_alias_set))

  def get_client(self, peer_name, domain=None):
    """ Returns the associated Thrift client wrapping a peer"""
    client = self._clients_by_qualified_name.get(
        self._get_qualified_name(peer_name, domain=domain))
    if not client:
      # Attempt to use client associated with the wildcard alias if present
      client = self._clients_by_qualified_name.get(self._get_qualified_name("*", domain=domain))
    return client

  def get_multicast_client(self, peer_names_and_domains, log_errors=False):
    qualified_names = [self._get_qualified_name(pn, d) for pn, d in peer_names_and_domains]

    # Eliminate duplicates
    clients = set()
    for peer_name, domain in peer_names_and_domains:
      client = self.get_client(peer_name, domain=domain)
      if client:
        clients.add(client)
      else:
        log.warning("No matching client for %s.%s", peer_name, domain)

    return self.client_class(
        thrift_wrapped_rpc_peer=MulticastThriftWrappedPeer(
            rpc_peers=[c.rpc_peer for c in clients],
            log_errors=log_errors,
            loop=self.loop,
            current_api_version=self._current_api_version,
        ),
    )

  def get_broadcast_client(self, log_errors=False):
    return self.client_class(
        thrift_wrapped_rpc_peer=MulticastThriftWrappedPeer(
            rpc_peers=[c.rpc_peer for c in set(self._clients_by_qualified_name.values())],
            log_errors=log_errors,
            loop=self.loop,
            current_api_version=self._current_api_version,
        ),
    )

  async def drop_client(self, peer_name, domain=None):
    client = self.get_client(peer_name, domain=None)
    if client:
      await self._discard_peer(client.rpc_peer)


class MultiplexedRPCPeer:

  def __init__(self,
               peer,
               my_hello,
               handle_request_async_callback,
               loop,
               synchronous_requests=True,
               handle_connection_lost_async_callback=None,
               handle_updated_hello_async_callback=None,
               is_initiator=False):
    '''
      handle_request_async_callback: Takes interface.Request object and returns an
          interface.Response object
    '''
    self._my_hello = my_hello
    self._peer = peer
    self._handle_request_async_callback = handle_request_async_callback
    self._handle_connection_lost_async_callback = handle_connection_lost_async_callback
    self._handle_updated_hello_async_callback = handle_updated_hello_async_callback
    self._loop = loop
    self._is_initiator = is_initiator
    self._synchronous_requests = synchronous_requests
    self._next_seq_num = 0
    self._outstanding_requests = {}
    # Use a bounded deque to keep track of timed out requests. This should cover almost all
    # cases where we receive a response even after a request has timed out.
    self._timed_out_requests = collections.deque(maxlen=20)
    self._server_task_future = future_value.FutureValue(loop=loop)
    self._triage_task = None
    self._request_queue = iterable_queue.IterableQueue(loop=loop)
    self._hello_result = future_value.FutureValue(loop=loop)
    self._shutdown_task = None
    # Use a Future here so we have more flexibility to add additional listeners
    self._connection_lost_future = asyncio.Future(loop=loop)
    self._connection_lost_future.add_done_callback(self._maybe_notify_of_lost_connection)
    self._hello_sent = False

  def _handle_triage_error(self, triage_task):
    if not self._hello_result.has_value():
      self._hello_result.cancel()

    if not triage_task.cancelled() and triage_task.exception():
      log.error("Triage task failed with error: %r", triage_task.exception())

  def start(self, start_server=True):
    self._triage_task = self._loop.create_task(self._handle_incoming_messages())
    self._triage_task.add_done_callback(self._handle_triage_error)

    if self._is_initiator:
      self._send_hello()

    if start_server:
      self.start_server()
    return self._hello_result

  def update_hello(self, my_hello):
    self._my_hello = my_hello
    if self._hello_sent:
      self._send_hello()

  @property
  def serialization_protocol(self):
    return self._peer.serialization_protocol

  @property
  def negotiated_api_version(self):
    return self._peer.negotiated_api_version

  def _maybe_notify_of_lost_connection(self, future):
    if future.done() and not future.cancelled():
      shutdown_was_requested = future.result()
      if not shutdown_was_requested and self._handle_connection_lost_async_callback:
        self._loop.create_task(self._handle_connection_lost_async_callback(self))

  def _maybe_trigger_shutdown(self, was_requested):
    if not self._shutdown_task:
      self._shutdown_task = self._loop.create_task(self._do_shutdown(was_requested))

    return self._shutdown_task

  def start_server(self):
    # Provide a mechanism to start the server task separately so we can prevent any requests from
    # this peer being serviced before we are ready to accept them
    if not self._server_task_future.has_value():
      self._server_task_future.set_value(self._loop.create_task(self._handle_request_queue()))

  async def shutdown(self):
    await self._maybe_trigger_shutdown(was_requested=True)
    if not self._hello_result.has_value():
      self._hello_result.cancel()

  async def _do_shutdown(self, was_requested):
    await self._peer.shutdown()
    tasks_to_gather = []
    if self._triage_task:
      tasks_to_gather.append(self._triage_task)
    if self._server_task_future.has_value() and not self._server_task_future.cancelled():
      tasks_to_gather.append(self._server_task_future.value())
      # NOTE: We don't clear _server_task_future here. It's unclear if this is intentional.

    # Swallow exceptions from the tasks. They will be logged elsewhere.
    await asyncio.gather(*tasks_to_gather, return_exceptions=True)
    self._connection_lost_future.set_result(was_requested)

    # This maybe should be NoConnectionError instead, but currently TimeoutError is a nice choice
    # because the logging around it is less verbose
    connection_lost_exc = asyncio.TimeoutError(
        "Connection to {} lost before request completed!".format(self.peer_name()),
    )
    for outstanding_request in self._outstanding_requests.values():
      outstanding_request.set_exception(connection_lost_exc)

    self._outstanding_requests.clear()

  def make_request(self, request):
    '''Pass in a interface.Request and returns a future that returns interface.Response.
    '''
    seq_num = self._get_next_seq_num()
    request_message_body_union = protocol_ttypes.MessageBodyUnion(request=request.to_thrift())
    request_message = protocol_ttypes.Message(message_type=protocol_ttypes.MessageType.REQUEST,
                                              sequence_number=seq_num,
                                              body_union=request_message_body_union)

    # Try to send *before* constructing OutstandingRequest. That way if sending fails, we bail
    # out and avoid some unnecessary work.
    self._send_message(request_message)

    future_result = asyncio.Future(loop=self._loop)
    if not request.is_oneway:
      timeout_handle = self._loop.call_later(
          delay=FLAGS.socket_timeout_seconds,
          callback=functools.partial(self._handle_request_timeout, seq_num),
      )
      self._outstanding_requests[seq_num] = OutstandingRequest(
          future=future_result,
          message=request_message,
          timeout_handle=timeout_handle,
      )
    else:
      future_result.set_result(None)

    return future_result

  def _handle_request_timeout(self, seq_num):
    outstanding_request = self._outstanding_requests.pop(seq_num, None)
    if outstanding_request:
      outstanding_request.set_exception(asyncio.TimeoutError("No response received!"))
      self._timed_out_requests.append(seq_num)

  def _send_message(self, message):
    message_raw = serialization.serialize(message, protocol=self.serialization_protocol)
    self._peer.enqueue_message(message_raw)

  def _get_next_seq_num(self):
    seq_num = self._next_seq_num
    self._next_seq_num += 1
    return seq_num

  def _send_hello(self):
    hello_message = protocol_ttypes.Message(
        body_union=protocol_ttypes.MessageBodyUnion(
            hello=self._my_hello,
        ),
        sequence_number=self._get_next_seq_num(),
        message_type=protocol_ttypes.MessageType.HELLO,
    )
    self._send_message(hello_message)
    self._hello_sent = True

  async def _handle_incoming_messages(self):
    """ Callback for handling incoming messages received by the peer connection manager
    """
    try:
      async for message_raw in self._peer.incoming_message_iterator():
        log.debug("Received message: %.80s... from peer %d", message_raw, id(self._peer))
        message = serialization.deserialize(
            protocol_ttypes.Message,
            message_raw,
            protocol=self.serialization_protocol,
        )
        if message.message_type == protocol_ttypes.MessageType.REQUEST:
          await self._schedule_request_message(message)
        elif message.message_type == protocol_ttypes.MessageType.RESPONSE:
          self._handle_response_message(message)
        elif message.message_type == protocol_ttypes.MessageType.HELLO:
          try:
            await self._handle_hello_message(message)
          except exceptions.NoConnectionError:
            log.warning("Lost connection to %s responding to Hello!",
                        self.peer_name())

      # Signal the task in _server_task_future that we won't have any more messages and drop any
      # already enqueued.
      self._request_queue.shutdown()
      self._server_task_future.cancel()

      # Don't await this as otherwise we have a deadlock situation
      self._maybe_trigger_shutdown(was_requested=False)
    except asyncio.CancelledError:  # pylint: disable=try-except-raise
      raise
    except Exception as e:
      # Log the exception from here so we get a useful stack trace
      log.exception("Exception in triage process: %r", e)
      raise

  async def _schedule_request_message(self, request_message):
    if self._synchronous_requests:
      # Synchronous request handling means a subsequent request will not START executing until the
      # current request FINISHES. Note that this synchronous request logic, by using a queue on a
      # disjointed task, does NOT block _handle_incoming_messages from handling subsequent incoming
      # (non-request) messages and thus makes no synchronization guarantees between requests and
      # other types of incoming messages (in particular, responses). Notably, this means synchronous
      # requests does NOT guarantee in-order handling between incoming requests and responses.
      # Whether this behavior is desired may be worth revisiting at some point.
      await self._request_queue.put(request_message)
    else:
      # NOTE: For asynchronous requests, it is currently a desired and thus expected behavior that
      # the handling of all incoming messages (notably, both requests AND responses) START executing
      # in the order in which those incoming messages were received. It is NOT necessary that the
      # handling of an incoming message FINISHES before the handling of a subsequent message STARTS
      # or even FINISHES. If any additional synchronization guarantees are desired, it is left to
      # the application developer using this library to implement them in their own application
      # logic, with the expectation that as long as this library guarantees START order, it should
      # be reasonably easy to add those guarantees in the application code (such as by using a
      # queue). Note that this desired start ordering behavior seems to hold true empirically,
      # though it currently has not yet been analytically vetted that between
      # _handle_response_message's set_result call and this function's create_task call that this
      # ordering behavior is actually guaranteed in all cases. If we find it to not be ordered
      # correctly in some case, we should be able to yield to the event loop after each respective
      # call to provide that guarantee, though this may warrant some investigation into possible
      # performance impact.
      self._loop.create_task(self._handle_request_message_when_ready(request_message))

  async def _handle_request_message_when_ready(self, request_message):
    await self._server_task_future
    await self._handle_request_message(request_message)

  async def _handle_request_queue(self):
    async for message in self._request_queue:
      await self._handle_request_message(message)

  async def _handle_request_message(self, request_message):
    try:
      response = await self._handle_request_async_callback(
          interface.Request.from_thrift(request_message.body_union.request),
          request_context=protocol_ttypes.RequestContext(
              peer_hello=self.get_peer_hello(),
              tls_info=self.get_peer_tls_info(),
              serialization_protocol=self.serialization_protocol,
              negotiated_api_version=self.negotiated_api_version,
          ),
      )
      if not request_message.body_union.request.is_oneway:
        response_message = protocol_ttypes.Message(
            message_type=protocol_ttypes.MessageType.RESPONSE,
            sequence_number=request_message.sequence_number,
            body_union=protocol_ttypes.MessageBodyUnion(response=response.to_thrift()),
        )
        try:
          self._send_message(response_message)
        except exceptions.NoConnectionError:
          log.warning("Lost connection to  %s before response delivered!",
                      self.peer_name())
    except Exception:
      log.exception("Error in request handler callback!")

  def _handle_response_message(self, message):
    '''The future for this request will get a Response object'''
    request = self._outstanding_requests.pop(message.sequence_number, None)
    if request is not None:
      request.set_result(interface.Response.from_thrift(message.body_union.response))
      return
    try:
      # If we see a response for a timed out request, we should just remove it, since we will
      # have already responded with a TimeoutError to the caller.
      self._timed_out_requests.remove(message.sequence_number)
      log.debug("Received a response for timed out message seq_num %d", message.sequence_number)
    except ValueError:
      log.warning(
          "Received response with no matching or timed out request seq_num: %d",
          message.sequence_number,
      )

  async def _handle_hello_message(self, message):
    if not self._hello_result.has_value():
      if not self._is_initiator:
        self._send_hello()
    else:
      if self._handle_updated_hello_async_callback:
        await self._handle_updated_hello_async_callback(self, message.body_union.hello)

    self._hello_result.set_value(message.body_union.hello)

  def get_peer_hello(self):
    if self._hello_result.has_value() and not self._hello_result.cancelled():
      return self._hello_result.value()

    return None

  def peer_name(self):
    '''For use in debug logging'''
    peer_hello = self.get_peer_hello()
    return peer_hello.name if peer_hello else "<anonymous>"

  def get_peer_tls_info(self):
    peer_cert = self._peer.get_peer_certificate()
    fingerprint = networking_utils.get_certificate_fingerprint(peer_cert) if peer_cert else None
    return protocol_ttypes.TLSInfo(
        peer_common_name=self._peer.get_peer_common_name(),
        is_validated=self._peer.is_validated(),
        peer_certificate_fingerprint=fingerprint,
    )


class OutstandingRequest:
  """A simple record class for keeping track of outgoing requests"""

  def __init__(self, future, message, timeout_handle):
    self.future = future
    self.message = message
    self.timeout_handle = timeout_handle
    self.sent_at = lib.time.get_current_time_ms()

  def _maybe_cancel_timeout(self):
    if self.timeout_handle:
      self.timeout_handle.cancel()
    # Drop the reference to the handle to make this easier to garbage collect
    self.timeout_handle = None

  def seconds_since_sent(self):
    now = lib.time.get_current_time_ms()
    return (now - self.sent_at) / 1000

  def set_result(self, result):
    self._maybe_cancel_timeout()
    try:
      self.future.set_result(result)
    except asyncio.InvalidStateError:
      log.warning("Tried to set result on future that already has a result: %r", self.future)

  def set_exception(self, exc):
    self._maybe_cancel_timeout()
    try:
      self.future.set_exception(exc)
    except asyncio.InvalidStateError:
      if not self.future.cancelled():
        # Don't whine if the Future has already been cancelled
        log.warning("Tried to set exception %s on future that already has a result: %r",
                    exc, self.future)
