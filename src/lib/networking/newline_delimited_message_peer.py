import asyncio
import logging

from lib import exceptions
from lib.async_helpers import iterable_queue
from lib.networking import interface
from lib.networking import utils
import thrift_types.protocol.ttypes as protocol_ttypes


log = logging.getLogger(__name__)


class NewlineDelimitedMessagePeer(interface.PeerInterface):

  MAX_MESSAGE_SIZE_BYTES = 2**26  # 64 MB

  serialization_protocol = protocol_ttypes.SerializationProtocol.BASE64_THRIFT_BINARY

  def __init__(self,
               remote_address,
               reader,
               writer,
               loop,
               *,
               max_send_queue_backlog=100):
    self.remote_address = remote_address
    self.reader = reader
    self.writer = writer
    self.loop = loop
    self.max_send_queue_backlog = max_send_queue_backlog
    self._active = False
    self._inbox_queue = iterable_queue.IterableQueue(loop=self.loop)
    self._outbox_queue = iterable_queue.IterableQueue(
        loop=self.loop, maxsize=max_send_queue_backlog)
    self._inbox_task, self._outbox_task = None, None
    self._connection_closed_future = asyncio.Future(loop=self.loop)

  async def start(self):
    # TODO raise error if already started
    self._active = True
    self._inbox_task = self.loop.create_task(self._handle_inbox())
    self._outbox_task = self.loop.create_task(self._handle_outbox())

  def register_connection_closed_callback(self, callback_func):
    def wrapped_callback(future):
      callback_func(self, future.result())
    self._connection_closed_future.add_done_callback(wrapped_callback)

  def enqueue_message(self, message):
    try:
      if not message.endswith("\n"):
        message += "\n"
      self._outbox_queue.put_nowait(message)
    except asyncio.InvalidStateError as e:
      raise exceptions.NoConnectionError("Connection to peer has been lost") from e

  async def shutdown(self):
    await self._shutdown(was_requested=True)

  async def _shutdown(self, was_requested):
    if not self._active:
      return

    self._active = False
    if was_requested:
      self._inbox_task.cancel()

    self._inbox_queue.shutdown()
    self._outbox_queue.shutdown()
    await self._outbox_task
    self._connection_closed_future.set_result(was_requested)

  async def _handle_inbox(self):
    try:
      async for line in self.reader:
        try:
          data = line.decode()
        except ValueError:
          log.exception("Invalid data received: %r", line)
          continue

        if not data.endswith("\n"):
          if data:
            log.error("incomplete read: %s", data)
          break

        message = data.strip()
        await self._inbox_queue.put(message)
    except asyncio.CancelledError:  # pylint: disable=try-except-raise
      raise
    except ConnectionError as e:
      log.warning("Failed to read message: %r", e)
    except Exception:
      log.exception("Exception in peer reader loop")

    await self._shutdown(was_requested=False)

  def incoming_message_iterator(self):
    return self._inbox_queue

  async def _handle_outbox(self):
    async for message in self._outbox_queue:
      try:
        self.writer.write(message.encode())
        if not message.endswith("\n"):
          log.warning("Protocol error: missing \\n at end of message")
          self.writer.write(b"\n")
        await self.writer.drain()
      except ValueError:
        log.exception("Encoding error")
      except ConnectionError as e:
        log.error("Failed to deliver message: %r", e)
        # Don't have a connection any more; no reason to keep processing messages
        break
      except Exception:
        log.exception("Message delivery failed")
      finally:
        self._outbox_queue.task_done()

    self.writer.close()

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


async def start_server(listen_address,
                       new_peer_async_callback,
                       loop,
                       params=None,
                       timeout=None,
                       authenticator=None,
                       supported_api_versions=None,
                       reuse_port=False):
  if params is not None:
    raise NotImplementedError("Params support in newline delimited message peer not implemented")

  if authenticator:
    raise NotImplementedError(
        "Authenticator support in NewlineDelimitedMessagePeer not implemented"
    )

  if supported_api_versions is not None:
    raise NotImplementedError(
        "Supported API Versions in NewlineDelimitedMessagePeer not implemented"
    )

  if timeout is not None:
    log.warning("timeout parameter is ignored by NewlineDelimitedMessagePeer server")

  if reuse_port:
    raise NotImplementedError("Reuse port in NewlineDelimitedMessagePeer not implemented")

  protocol, addr_family, kwargs, secure = utils.parse_address(listen_address)
  assert protocol == utils.MessagingProtocol.NEWLINE_DELIMITED_MESSAGE
  if secure:
    raise NotImplementedError("SSL server support not implemented")

  async def _connection_accepted(reader, writer):
    peer = NewlineDelimitedMessagePeer(
        remote_address=None,
        reader=reader,
        writer=writer,
        loop=loop,
    )
    await new_peer_async_callback(peer)

  def protocol_factory():
    reader = asyncio.StreamReader(
        limit=NewlineDelimitedMessagePeer.MAX_MESSAGE_SIZE_BYTES,
        loop=loop,
    )
    reader_protocol = asyncio.StreamReaderProtocol(reader, _connection_accepted, loop=loop)
    return reader_protocol

  server = await utils.create_server(
      address_family=addr_family,
      protocol_factory=protocol_factory,
      loop=loop,
      secure=False,
      **kwargs
  )
  return server


async def open_connection(remote_address,
                          loop,
                          params=None,
                          timeout=None,
                          authenticator=None,
                          supported_api_versions=None,
                          cert_file_directory=None):
  if params is not None:
    raise NotImplementedError("Params support in newline delimited message peer not implemented")

  if authenticator:
    raise NotImplementedError(
        "Authenticator support in NewlineDelimitedMessagePeer not implemented"
    )

  if supported_api_versions is not None:
    raise NotImplementedError(
        "Supported API Versions in NewlineDelimitedMessagePeer not implemented"
    )

  if cert_file_directory is not None:
    raise NotImplementedError("The certificate file directory is not implemented for "
                              "NewlineDelimitedMessagePeer")

  protocol, addr_family, kwargs, secure = utils.parse_address(remote_address)
  assert protocol == utils.MessagingProtocol.NEWLINE_DELIMITED_MESSAGE
  if secure:
    raise NotImplementedError("SSL client support not implemented")

  reader, writer = await utils.open_stream(
      loop=loop,
      addr_family=addr_family,
      timeout=timeout,
      read_limit=NewlineDelimitedMessagePeer.MAX_MESSAGE_SIZE_BYTES,
      **kwargs,
  )
  peer = NewlineDelimitedMessagePeer(
      remote_address=remote_address,
      reader=reader,
      writer=writer,
      loop=loop,
  )
  return peer
