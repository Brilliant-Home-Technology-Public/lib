# pylint: disable=too-many-ancestors
import asyncio
import logging

import autobahn.asyncio.websocket
import autobahn.exception
import autobahn.websocket.compress
import autobahn.websocket.protocol
import autobahn.websocket.types

from lib.async_helpers import iterable_queue
import lib.exceptions
from lib.networking import interface
from lib.networking import utils
import lib.queueing.work_queue
import thrift_types.protocol.ttypes as protocol_ttypes


log = logging.getLogger(__name__)
API_VERSION_HEADER = "x-brilliant-api-version"
SERIALIZATION_PROTOCOL_HEADER = "x-brilliant-serialization-protocol"


class VersionNotNegotiatedError(autobahn.websocket.types.ConnectionDeny):

  def __init__(self):
    super().__init__(
        code=autobahn.websocket.types.ConnectionDeny.BAD_REQUEST,
        reason="Version Not Negotiated",
    )


class InvalidSerializationProtocolError(autobahn.websocket.types.ConnectionDeny):

  def __init__(self, protocol):
    super().__init__(
        code=autobahn.websocket.types.ConnectionDeny.BAD_REQUEST,
        reason="Invalid serialization protocol header: {}".format(protocol),
    )


class WebSocketPeer(autobahn.websocket.protocol.WebSocketProtocol, interface.PeerInterface):

  def __init__(self, *args, loop=None, **kwargs):
    super().__init__(*args, **kwargs)
    self.loop = loop or asyncio.get_event_loop()
    self.remote_address = None
    self.authenticator = None
    self.timeout = None
    self._inbox_queue = iterable_queue.IterableQueue(loop=self.loop)
    self._ready_future = asyncio.Future(loop=self.loop)
    self._closed_future = asyncio.Future(loop=self.loop)
    self._shutdown_invoked = False
    self._sent_close_frame = False
    self.headers = None
    self.valid_connection = False
    self._peer_common_name = None
    self._raw_certificate = None
    self._validation_task = None
    self.supported_api_versions = None
    self._negotiated_api_version = None
    self._serialization_protocol = protocol_ttypes.SerializationProtocol.BASE64_THRIFT_BINARY
    self._connection_expiration_work_queue = lib.queueing.work_queue.SingletonJobWorkQueue(
        loop=self.loop,
        process_job_func=self._expire_connection,
    )

  async def start(self):
    self._connection_expiration_work_queue.start()
    try:
      await asyncio.wait_for(
          self._ready_future,
          timeout=self.timeout,
      )
    except Exception as e:
      # HACK: Ideally this queue shutdown would only need to be handled by WebSocketPeer's
      # shutdown, but we currently do not call shutdown if start fails
      self._connection_expiration_work_queue.shutdown()
      if isinstance(e, asyncio.TimeoutError):
        self.force_close()
      raise

  async def shutdown(self):
    # Interrupt any start task in progress. If an exception has already been set,
    # this will suppress the "exception never retrieved" error
    self._ready_future.cancel()

    self._shutdown_invoked = True
    await self._ensure_connection_closed()
    self._connection_expiration_work_queue.shutdown()

  async def _ensure_connection_closed(self):
    if not self._sent_close_frame:
      self._sent_close_frame = True
      try:
        self.sendClose(
            code=autobahn.websocket.protocol.WebSocketProtocol.CLOSE_STATUS_CODE_NORMAL,
        )
      except Exception as e:
        log.warning("Encountered exception sending close frame: %r", e)

    try:
      await asyncio.wait_for(
          # Don't want to cancel the Future if we time out
          asyncio.shield(self._closed_future),
          timeout=self.timeout,
      )
    except asyncio.TimeoutError:
      log.warning("Timed out waiting for connection to close; forcing!")
      self.force_close()

  async def _expire_connection(self, _):
    await self._ensure_connection_closed()

  @property
  def serialization_protocol(self):
    return self._serialization_protocol

  def register_connection_closed_callback(self, callback_func):
    def _callback(fut):
      callback_func(self, fut.result())
    self._closed_future.add_done_callback(_callback)

  def incoming_message_iterator(self):
    return self._inbox_queue

  def _enqueue_message(self, message):
    if self.serialization_protocol == protocol_ttypes.SerializationProtocol.THRIFT_BINARY:
      self.sendMessage(message, isBinary=True)
    else:
      self.sendMessage(message.encode("utf-8"), isBinary=False)

  def enqueue_message(self, message):
    try:
      self._enqueue_message(message)
    except autobahn.exception.Disconnected as e:
      raise lib.exceptions.NoConnectionError("Connection to peer has been lost") from e

  async def onOpen(self):
    try:
      if not self._validation_task:
        raise asyncio.InvalidStateError("Validation task never started!")
      await self._validation_task
      self._ready_future.set_result(True)
    except asyncio.CancelledError:
      self._ready_future.cancel()
      raise
    except Exception as e:
      if not self._ready_future.done():  # May have already timed out/failed somehow
        self._ready_future.set_exception(e)
      self.force_close()
      # Don't bother re-raising; typically there's no one to collect this exception

  async def onMessage(self, payload, isBinary):
    if self.serialization_protocol == protocol_ttypes.SerializationProtocol.THRIFT_BINARY:
      await self._inbox_queue.put(payload)
    else:
      await self._inbox_queue.put(payload.decode('utf-8'))

  async def onClose(self, wasClean, code, reason):
    if self._validation_task and not self._validation_task.done():
      self._validation_task.cancel()

    log.info("WebSocket for peer %s [%s] closed. Code: %s, Reason: %s",
             id(self), self._peer_common_name or "<unknown>", code, reason)

    # Use remote_address as a proxy to determine if we are the client. When we hit a ping timeout,
    # we want to wait for at least that amount of time again for the server to also recognize the
    # connection was dropped and clean up appropriately.
    if reason and "ping timeout" in reason and self.remote_address and self.timeout:
      log.info("Sleeping %s seconds to allow peer to observe timeout.", self.timeout)
      await asyncio.sleep(self.timeout)

    if not self._ready_future.done():
      self._ready_future.set_exception(
          OSError("Lost connection to peer! Code: {}, Reason: {}".format(code, reason)),
      )

    self._inbox_queue.shutdown()
    if not self._closed_future.done():
      self._closed_future.set_result(self._shutdown_invoked)

  def force_close(self):
    if getattr(self, 'transport', None):
      # This might be called before the transport was ever attached
      self.dropConnection(abort=True)

  def get_peer_connection_parameters(self):
    if self.headers is None:
      return None
    return dict(
        home_id=self.headers.get("x-brilliant-home-id", None),
        device_id=self.headers.get("x-brilliant-device-id", None),
        authentication_token=self.headers.get("x-brilliant-authentication-token", None),
    )

  async def _save_and_validate_ssl_parameters(self, headers, am_server):
    self.headers = headers
    if (am_server and
        self.authenticator and
        self.authenticator.authentication_policy.accept_client_certificate_as_header()):
      self._raw_certificate = self._get_cert_from_headers()
      self._peer_common_name = utils.get_common_name_from_headers(self.headers)
    else:
      # The built-in APIs around SSL certificates are pretty crappy. The object returned by
      # get_extra_info is actually a dictionary of fields extracted from the certificate, not
      # the raw cert data itself. Meanwhile to compute the fingerprint we actually need to see the
      # raw bytes, but there's no simple way to parse that data without a bunch of dependencies.
      self._raw_certificate = self._get_cert_from_transport()
      peer_cert_info = self.transport.get_extra_info('peercert')
      if peer_cert_info:
        self._peer_common_name = utils.get_common_name_from_peer_cert(peer_cert_info)

    self.valid_connection = await self._is_peer_authentication_valid(am_server)
    if self.authenticator and not self.valid_connection:
      peer_connection_params = self.get_peer_connection_parameters() or {}
      device_id = peer_connection_params.get("device_id")
      home_id = peer_connection_params.get("home_id")
      log.warning("Failed to authenticate device %s on home %s!", device_id, home_id)
      if self.authenticator.authentication_policy.strict:
        raise interface.UnauthorizedError()

  def _get_authentication_method(self, peer_connection_params):
    if not self.authenticator:
      return interface.AuthenticationMethod.NONE

    return self.authenticator.get_authentication_method_for_peer(
        maybe_address=self.remote_address,
        connection_params=peer_connection_params,
    )

  async def _is_peer_authentication_valid(self, am_server):
    peer_connection_params = self.get_peer_connection_parameters()
    authentication_method = self._get_authentication_method(peer_connection_params)
    if authentication_method == interface.AuthenticationMethod.NONE:
      return True
    if authentication_method == interface.AuthenticationMethod.CERTIFICATE_SUBJECT:
      ssl_object = self._get_ssl_object()
      # Make sure the SSL library checked the hostname on the certificate
      verified = (
          self._raw_certificate and
          ssl_object and
          ssl_object.context.check_hostname
      )
      return verified
    device_id = peer_connection_params.get('device_id')
    home_id = peer_connection_params.get('home_id')
    if not (device_id and home_id):
      return False
    if authentication_method == interface.AuthenticationMethod.CERTIFICATE_FINGERPRINT:
      if not self._raw_certificate:
        return False

      is_cert_authentic = await self.authenticator.validate_certificate(
          device_id=device_id,
          home_id=home_id,
          certificate=self._raw_certificate,
      )
      return is_cert_authentic
    if authentication_method == interface.AuthenticationMethod.JWT:
      home_auth_token = peer_connection_params.get("authentication_token")
      if not home_auth_token:
        return False
      validity_interval_seconds = \
          await self.authenticator.authentication_policy.get_token_validity_interval_seconds(
              home_id=home_id,
              peer_device_id=device_id,
              home_auth_token=peer_connection_params.get("authentication_token"),
          )
      if (validity_interval_seconds or 0) > 0:
        self._connection_expiration_work_queue.add_job(None, delay=validity_interval_seconds)
        return True
      return False
    log.warning("Unrecognized authentication method: %s", authentication_method)
    return False

  def _get_api_version_header(self, headers):
    return headers.get(API_VERSION_HEADER)

  def negotiate_api_version(self, headers):
    # this socket doesn't support API version negotiation
    if self.supported_api_versions is None:
      log.error("This object doesn't support API versions, most likely developer error")
      return

    client_supported_versions = self._get_api_version_header(headers)
    # client doesn't support version negotiation, assume earliest API
    if client_supported_versions is None:
      self._negotiated_api_version = min(self.supported_api_versions)
      log.info("Client does not support versioning, using min version %s",
               self._negotiated_api_version)
      return

    client_supported_versions = client_supported_versions.split(",")
    intersecting_versions = set(self.supported_api_versions) & set(client_supported_versions)
    if intersecting_versions:
      self._negotiated_api_version = max(intersecting_versions)
      log.info("Forcing API version to %s", self._negotiated_api_version)
    else:
      # no compatible versions, connection should be terminated
      log.warning("Failed to negotiate API version, no compatible versions available")
      raise VersionNotNegotiatedError()

  def negotiate_serialization_protocol(self, headers):
    client_protocols = headers.get(SERIALIZATION_PROTOCOL_HEADER)
    if not client_protocols:
      # Use the default base64 thrift binary if no header is present.
      return

    client_protocol_list = client_protocols.split(",")
    try:
      client_protocol_list = [int(client_protocol) for client_protocol in client_protocol_list]
    except (TypeError, ValueError) as e:
      raise InvalidSerializationProtocolError(client_protocols) from e

    # Prefer raw binary over base64.
    if protocol_ttypes.SerializationProtocol.THRIFT_BINARY in client_protocol_list:
      self._serialization_protocol = protocol_ttypes.SerializationProtocol.THRIFT_BINARY
      return
    if protocol_ttypes.SerializationProtocol.BASE64_THRIFT_BINARY in client_protocol_list:
      # This is already the default, so no need to set it.
      return
    raise InvalidSerializationProtocolError(",".join(client_protocols))

  def receive_api_version(self, headers):
    # this socket doesn't support API version negotiation
    if self.supported_api_versions is None:
      log.error("This object doesn't support API versions, most likely developer error")
      return

    server_version = self._get_api_version_header(headers)
    # server doesn't support version negotiation, assume earliest API
    if server_version is None:
      self._negotiated_api_version = min(self.supported_api_versions)
      log.info("Server does not support versioning, using min version %s",
               self._negotiated_api_version)
      return
    # the server will have force closed the connection if there are no compatible versions,
    # so we do not need to check if other_expected_versions is empty
    self._negotiated_api_version = server_version
    log.info("Server negotiated version is %s", self._negotiated_api_version)

  def receive_serialization_protocol(self, headers):
    server_protocol = headers.get(SERIALIZATION_PROTOCOL_HEADER)

    # If the server didn't provide a header back, assume base64.
    if not server_protocol:
      log.info("Server did not provide serialization protocol, using base64.")
      return

    self._serialization_protocol = int(server_protocol)

  def start_certificate_validation(self, headers, am_server):
    # Structure this as a task since onConnect() cannot be a coroutine (see comment below)
    self._validation_task = self.loop.create_task(
        # TODO: should this be am_server instead of always True?
        self._save_and_validate_ssl_parameters(headers, am_server=True)
    )
    return self._validation_task  # For testing convenience

  def is_validated(self):
    return self.valid_connection

  def get_peer_common_name(self):
    return self._peer_common_name

  def _get_ssl_object(self):
    ssl_object = self.transport.get_extra_info("ssl_object")
    return ssl_object

  def _get_cert_from_transport(self):
    ssl_object = self._get_ssl_object()
    if not ssl_object:
      return None

    der_encoded_cert = ssl_object.getpeercert(binary_form=True)
    return der_encoded_cert

  def _get_cert_from_headers(self):
    return utils.get_certificate_from_headers(self.headers)

  def get_peer_certificate(self):
    return self._raw_certificate

  @property
  def negotiated_api_version(self):
    return self._negotiated_api_version


class WebSocketPeerClientProtocol(autobahn.asyncio.websocket.WebSocketClientProtocol,
                                  WebSocketPeer):
  # Unlike pretty much all of the other onXXX() callbacks, onConnect() needs to be a plain function
  # or autobahn will get upset.
  def onConnect(self, response):
    log.info("Server peer %s connected with headers: %s", id(self), response.headers)
    self.start_certificate_validation(response.headers, am_server=False)
    self.receive_api_version(response.headers)
    self.receive_serialization_protocol(response.headers)

  # The autobahn implementation does not close aggressively when abort=True. Use our own
  # version which behaves better when the connection has dropped entirely (e.g. we lost wifi)
  # and we haven't yet noticed.
  def _closeConnection(self, abort=False):
    if abort:
      self.transport.abort()
    else:
      super()._closeConnection(abort=abort)


class WebSocketPeerServerProtocol(autobahn.asyncio.websocket.WebSocketServerProtocol,
                                  WebSocketPeer):

  WHITELISTED_HEADERS = {
      "x-brilliant-home-id", "x-brilliant-device-id", "x-forwarded-for", "host", "user-agent",
      API_VERSION_HEADER, "cache-control", "x-forwarded-proto",
      SERIALIZATION_PROTOCOL_HEADER,
  }

  # See comment above
  def onConnect(self, request):
    logged_headers = {
        header: value for header, value in request.headers.items()
        if header in self.WHITELISTED_HEADERS
    }
    log.info("Client peer %s connected with headers: %s", id(self), logged_headers)
    self.negotiate_api_version(request.headers)
    self.negotiate_serialization_protocol(request.headers)
    # Do this after version and protocol negotiation since that might abort the request.
    self.start_certificate_validation(request.headers, am_server=True)
    headers_to_return = {SERIALIZATION_PROTOCOL_HEADER: str(self._serialization_protocol)}
    if self._negotiated_api_version is not None:
      headers_to_return[API_VERSION_HEADER] = self._negotiated_api_version
    return (None, headers_to_return)

  # See comment above.
  # TODO anyway to unify these? Not sure we can change the inheritance order
  def _closeConnection(self, abort=False):
    if abort:
      self.transport.abort()
    else:
      super()._closeConnection(abort=abort)

  # XXX HACK: The mechanism we use to pass the client certificate from nginx to Python uses a
  # deprecated method of folding together a multiline header. In particular, autobahn doesn't parse
  # the headers correctly. For now our best workaround is to intercept the problematic line
  # continuation (nginx simply inserts a tab character after every newline it sees) and rewrite it.
  def _dataReceived(self, data):
    if self.state in (
        autobahn.websocket.protocol.WebSocketProtocol.STATE_CONNECTING,
        autobahn.websocket.protocol.WebSocketProtocol.STATE_PROXY_CONNECTING,
    ):
      data = data.replace(b"\n\t", b"\t")

    super()._dataReceived(data)


class WebSocketPeerClientProtocolFactory(autobahn.asyncio.websocket.WebSocketClientFactory):

  protocol = WebSocketPeerClientProtocol

  def __init__(self,
               remote_address,
               authenticator,
               *args,
               timeout=None,
               supported_api_versions=None,
               **kwargs):
    super().__init__(*args, **kwargs)
    self._remote_address = remote_address
    self._authenticator = authenticator
    self._supported_api_versions = supported_api_versions
    self._timeout = timeout
    self.setProtocolOptions(
        autoPingInterval=timeout,
        autoPingTimeout=timeout,
        openHandshakeTimeout=timeout,
        closeHandshakeTimeout=timeout,
        serverConnectionDropTimeout=timeout,
        perMessageCompressionOffers=[autobahn.websocket.compress.PerMessageDeflateOffer()],
        perMessageCompressionAccept=self._accept_compression,
    )

  def __call__(self):
    protocol = super().__call__()
    protocol.remote_address = self._remote_address
    protocol.authenticator = self._authenticator
    protocol.supported_api_versions = self._supported_api_versions
    protocol.timeout = self._timeout
    return protocol

  def _accept_compression(self, response):
    if isinstance(response, autobahn.websocket.compress.PerMessageDeflateResponse):
      return autobahn.websocket.compress.PerMessageDeflateResponseAccept(response)

    return None


class WebSocketPeerServerProtocolFactory(autobahn.asyncio.websocket.WebSocketServerFactory):

  protocol = WebSocketPeerServerProtocol

  def __init__(self,
               client_connected_cb,
               authenticator,
               *args,
               timeout=None,
               supported_api_versions=None,
               **kwargs):
    super().__init__(*args, **kwargs)
    self._client_connected_cb = client_connected_cb
    self._authenticator = authenticator
    self._supported_api_versions = supported_api_versions
    self._timeout = timeout
    self.setProtocolOptions(
        autoPingInterval=timeout,
        autoPingTimeout=timeout,
        openHandshakeTimeout=timeout,
        closeHandshakeTimeout=timeout,
        perMessageCompressionAccept=self._accept_compression,
    )
    self._callback_tasks = set()

  def __call__(self):
    protocol = super().__call__()
    protocol.authenticator = self._authenticator
    if self._client_connected_cb:
      callback_task = self.loop.create_task(self._client_connected_cb(protocol))
      self._callback_tasks.add(callback_task)
      callback_task.add_done_callback(self._handle_done_callback)

    protocol.supported_api_versions = self._supported_api_versions
    protocol.timeout = self._timeout
    return protocol

  def _accept_compression(self, offers):
    for offer in offers:
      if isinstance(offer, autobahn.websocket.compress.PerMessageDeflateOffer):
        return autobahn.websocket.compress.PerMessageDeflateOfferAccept(offer)

    return None

  def _handle_done_callback(self, task):
    self._callback_tasks.discard(task)
    if not task.cancelled() and task.exception():
      exc = task.exception()
      if isinstance(exc, asyncio.TimeoutError):
        log.warning("Client connected callback timed out.")
      else:
        log.error("Client connected callback %s failed with error: %r",
                  self._client_connected_cb,
                  exc)


async def open_connection(remote_address,
                          loop,
                          params=None,
                          timeout=None,
                          authenticator=None,
                          supported_api_versions=None,
                          cert_file_directory=None):
  protocol, addr_family, kwargs, secure = utils.parse_address(remote_address)
  assert protocol == utils.MessagingProtocol.WEB_SOCKET
  params = params or {}
  if "serialization-protocol" not in params:
    params["serialization-protocol"] = str(protocol_ttypes.SerializationProtocol.THRIFT_BINARY)
  if supported_api_versions is not None:
    params["api-version"] = ",".join(supported_api_versions)

  protocol_factory = WebSocketPeerClientProtocolFactory(
      remote_address=remote_address,
      loop=loop,
      headers=utils.format_headers(params),
      timeout=timeout,
      authenticator=authenticator,
      supported_api_versions=supported_api_versions,
      url=remote_address if addr_family == utils.AddressFamily.INET else None,
  )
  _, client_protocol = await utils.create_connection(
      address_family=addr_family,
      protocol_factory=protocol_factory,
      secure=secure,
      loop=loop,
      timeout=timeout,
      cert_file_directory=cert_file_directory,
      **kwargs
  )
  return client_protocol


async def start_server(listen_address,
                       new_peer_async_callback,
                       loop, params=None,
                       timeout=None,
                       authenticator=None,
                       supported_api_versions=None,
                       reuse_port=False):
  protocol, addr_family, kwargs, secure = utils.parse_address(listen_address)
  assert protocol == utils.MessagingProtocol.WEB_SOCKET

  protocol_factory = WebSocketPeerServerProtocolFactory(
      client_connected_cb=new_peer_async_callback,
      loop=loop,
      headers=utils.format_headers(params),
      timeout=timeout,
      authenticator=authenticator,
      supported_api_versions=supported_api_versions,
  )

  server = await utils.create_server(
      address_family=addr_family,
      protocol_factory=protocol_factory,
      secure=secure,
      loop=loop,
      reuse_port=reuse_port,
      **kwargs
  )
  return server
