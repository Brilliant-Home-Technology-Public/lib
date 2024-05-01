import asyncio
import logging

import autobahn.asyncio.websocket
import autobahn.websocket.protocol

from lib.async_helpers import iterable_queue
from lib.networking import interface
from lib.networking import utils
import thrift_types.protocol.ttypes as protocol_ttypes


log = logging.getLogger(__name__)


class GenericWebSocketProtocol(autobahn.websocket.protocol.WebSocketProtocol,
                               interface.PeerInterface):

  serialization_protocol = protocol_ttypes.SerializationProtocol.NONE

  def __init__(self, *args, loop=None, **kwargs):
    super().__init__(*args, **kwargs)
    self.loop = loop
    self._ready_future = asyncio.Future(loop=self.loop)
    self._closed_future = asyncio.Future(loop=self.loop)
    self._close_requested = False
    self._inbox_queue = iterable_queue.IterableQueue(loop=self.loop)

  async def start(self):
    await self._ready_future

  async def shutdown(self):
    if not self._close_requested:
      self._close_requested = True
      self.sendClose(
          code=autobahn.websocket.protocol.WebSocketProtocol.CLOSE_STATUS_CODE_NORMAL,
      )
    await self._closed_future

  def register_connection_closed_callback(self, callback_func):
    def _callback(future):
      callback_func(self, future.result())
    self._closed_future.add_done_callback(_callback)

  def onConnect(self, response):
    pass

  async def onOpen(self):
    self._ready_future.set_result(True)

  async def onMessage(self, payload, is_binary):  # pylint: disable=arguments-renamed
    if is_binary:
      await self._inbox_queue.put(payload)
    else:
      await self._inbox_queue.put(payload.decode('utf-8'))

  def onClose(self, wasClean, code, reason):
    if not self._ready_future.done():
      self._ready_future.set_exception(
          IOError("Lost connection. Code {}, Reason: {}".format(code, reason))
      )
    self._inbox_queue.shutdown()
    if not self._closed_future.done():
      self._closed_future.set_result(self._close_requested)

  def incoming_message_iterator(self):
    return self._inbox_queue

  def is_validated(self):
    return False

  def get_peer_common_name(self):
    return None

  def get_peer_certificate(self):
    return None

  def get_peer_connection_parameters(self):
    return None

  @property
  def negotiated_api_version(self):
    return None


class GenericWebSocketClientProtocol(autobahn.asyncio.websocket.WebSocketClientProtocol,
                                     GenericWebSocketProtocol):
  # The autobahn implementation does not close aggressively when abort=True. Use our own
  # version which behaves better when the connection has dropped entirely (e.g. we lost wifi)
  # and we haven't yet noticed.
  def _closeConnection(self, abort=False):
    if abort:
      self.transport.abort()
    else:
      super()._closeConnection(abort=abort)


class GenericWebSocketClientProtocolFactory(autobahn.asyncio.websocket.WebSocketClientFactory):
  protocol = GenericWebSocketClientProtocol

  def __init__(self, *args, timeout=None, **kwargs):
    super().__init__(*args, **kwargs)
    self.setProtocolOptions(
        openHandshakeTimeout=timeout,
        closeHandshakeTimeout=timeout,
        autoPingInterval=timeout,
        autoPingTimeout=timeout,
    )

  def __call__(self):
    protocol = super().__call__()
    protocol.remote_address = self.url
    return protocol


async def open_connection(remote_address,
                          loop,
                          params=None,
                          timeout=None,
                          authenticator=None,
                          supported_api_versions=None,
                          cert_file_directory=None):

  if authenticator is not None:
    raise NotImplementedError("Authentication support not implemented")
  if supported_api_versions is not None:
    raise NotImplementedError("Supported API versions not implemented")
  if cert_file_directory is not None:
    raise NotImplementedError("Cert file directory not implemented")

  messaging_protocol, addr_family, connection_args, secure = utils.parse_address(remote_address)

  assert messaging_protocol == utils.MessagingProtocol.WEB_SOCKET
  assert addr_family == utils.AddressFamily.INET

  if params is None:
    params = {}

  headers = params.get("headers")
  protocols = params.get("protocols")
  ssl_context = params.get("ssl_context")

  protocol_factory = GenericWebSocketClientProtocolFactory(
      loop=loop,
      url=remote_address,
      headers=headers,
      protocols=protocols,
      timeout=timeout,
  )
  _, websocket_protocol = await loop.create_connection(
      protocol_factory=protocol_factory,
      ssl=(ssl_context or secure),
      host=connection_args["host"],
      port=connection_args["port"],
  )
  return websocket_protocol
