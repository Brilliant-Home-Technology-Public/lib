import asyncio
import errno
import logging

from lib import exceptions
from lib.async_helpers import iterable_queue
from lib.networking import interface
from lib.networking import utils
from lib.queueing import work_queue
import lib.utils
import thrift_types.protocol.ttypes as protocol_ttypes


log = logging.getLogger(__name__)


class ProcessLocalPeer(interface.PeerInterface):

  serialization_protocol = protocol_ttypes.SerializationProtocol.NONE

  def __init__(self, remote_address, loop):
    self.remote_address = remote_address
    self._loop = loop
    self._remote_peer = None
    self._inbox_queue = iterable_queue.IterableQueue(loop=self._loop)
    self._connection_closed_future = asyncio.Future(loop=self._loop)

  def set_peer(self, remote_peer):
    if self._remote_peer:
      raise Exception("This peer is already bound to another remote peer!")

    self._remote_peer = remote_peer

  async def start(self):
    if not self._remote_peer:
      raise exceptions.NoConnectionError("Connection to peer has been lost")

  async def shutdown(self):
    return await self._shutdown(was_requested=True)

  async def _shutdown(self, was_requested=False):
    if not self._remote_peer:
      return

    # Clear this out so we don't re-enter this function
    remote_peer = self._remote_peer
    self._remote_peer = None

    await remote_peer._shutdown(was_requested=False)
    self._inbox_queue.shutdown()
    self._connection_closed_future.set_result(was_requested)

  def register_connection_closed_callback(self, callback_func):
    def wrapped_callback(future):
      callback_func(self, future.result())
    self._connection_closed_future.add_done_callback(wrapped_callback)

  def enqueue_message(self, message):
    if not self._remote_peer:
      raise exceptions.NoConnectionError("Connection to peer has been lost")

    self._remote_peer._inbox_queue.put_nowait(lib.utils.fast_copy(message, deep=True))

  def incoming_message_iterator(self):
    return self._inbox_queue

  def is_validated(self):
    # TLS not supported
    return False

  def get_peer_common_name(self):
    # TLS not supported
    return None

  def get_peer_certificate(self):
    # TLS not supported
    return None

  def get_peer_connection_parameters(self):
    # No header support
    return None

  @property
  def negotiated_api_version(self):
    return None


_server = None


class ProcessLocalPeerServer(asyncio.AbstractServer):

  def __init__(self, new_peer_async_callback, loop):
    self._loop = loop
    self._new_peer_async_callback = new_peer_async_callback
    self._active = True
    self._accept_queue = work_queue.WorkQueue(
        loop=self._loop,
        num_workers=1,
        process_job_func=self._accept_new_peer,
        max_retries=0,  # Don't retry
    )
    self.sockets = []  # Compatibility with other Server instances

  def start(self):
    self._accept_queue.start()

  def close(self):
    self._active = False
    self._accept_queue.shutdown()

  async def wait_closed(self):
    pass

  async def _accept_new_peer(self, peer):
    await self._new_peer_async_callback(peer)

  async def connect(self, remote_address):
    if not self._active:
      raise ConnectionRefusedError("This server is not accepting connections")

    initiating_peer = ProcessLocalPeer(loop=self._loop, remote_address=remote_address)
    receiving_peer = ProcessLocalPeer(loop=self._loop, remote_address=None)
    initiating_peer.set_peer(receiving_peer)
    receiving_peer.set_peer(initiating_peer)

    self._accept_queue.add_job(receiving_peer)
    return initiating_peer


async def open_connection(remote_address,
                          loop,
                          params=None,
                          timeout=None,
                          authenticator=None,
                          supported_api_versions=None,
                          cert_file_directory=None):
  if params is not None:
    raise NotImplementedError("Params support in ProcessLocalPeer not implemented")

  protocol, addr_family, kwargs, secure = utils.parse_address(remote_address)
  assert protocol == utils.MessagingProtocol.PROCESS_LOCAL
  if secure:
    raise NotImplementedError("SSL client support not implemented")

  if not _server:
    raise ConnectionRefusedError("No process-local server available!")

  if authenticator:
    raise NotImplementedError("Authenticator support in ProcessLocalPeer not implemented")

  if supported_api_versions is not None:
    raise NotImplementedError("Supported API versions not implemented for ProcessLocalPeer")

  if cert_file_directory is not None:
    raise NotImplementedError("The certificate file directory is not implemented for "
                              "ProcessLocalPeer")

  peer = await _server.connect(remote_address)
  return peer


async def start_server(listen_address,
                       new_peer_async_callback,
                       loop,
                       params=None,
                       timeout=None,
                       authenticator=None,
                       supported_api_versions=None,
                       reuse_port=False):
  global _server  # pylint: disable=global-statement
  if _server and _server._active:
    raise OSError(errno.EADDRINUSE, "Local server already exists")

  if params is not None:
    raise NotImplementedError("Params support in ProcessLocalPeer not implemented")

  if timeout is not None:
    log.warning("timeout parameter is ignored by ProcessLocalPeer server")

  if authenticator:
    raise NotImplementedError("Authenticator support in ProcessLocalPeer not implemented")

  if supported_api_versions is not None:
    raise NotImplementedError("Supported API versions not implemented for ProcessLocalPeer")

  if reuse_port:
    raise NotImplementedError("reuse_port support in ProcessLocalPeer not implemented")

  protocol, addr_family, kwargs, secure = utils.parse_address(listen_address)
  assert protocol == utils.MessagingProtocol.PROCESS_LOCAL
  if secure:
    raise NotImplementedError("SSL server support not implemented")

  _server = ProcessLocalPeerServer(loop=loop, new_peer_async_callback=new_peer_async_callback)
  _server.start()
  return _server
