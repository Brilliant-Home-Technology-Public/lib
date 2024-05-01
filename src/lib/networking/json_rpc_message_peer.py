import asyncio
import json
import logging

from lib import exceptions
from lib.networking import newline_delimited_message_peer
from lib.networking import utils
import thrift_types.protocol.ttypes as protocol_ttypes


log = logging.getLogger(__name__)


class InvalidStartByteError(Exception):
  pass


class MessageTooLargeError(Exception):
  pass


class JsonRPCMessagePeer(newline_delimited_message_peer.NewlineDelimitedMessagePeer):
  serialization_protocol = protocol_ttypes.SerializationProtocol.NONE
  MAX_MESSAGE_SIZE_BYTES = 10**6
  PROMPT_DELIMITER = b":"

  def __init__(self, *args, user, password, timeout, **kwargs):
    super().__init__(*args, **kwargs)
    self.timeout = timeout
    self.user = user
    self.password = password

  def enqueue_message(self, json_message):  # pylint: disable=arguments-renamed
    try:
      message = json.dumps(json_message) + "\r\n"
      self._outbox_queue.put_nowait(message)
    except asyncio.InvalidStateError as e:
      raise exceptions.NoConnectionError("Connection to peer has been lost") from e

  async def _handle_inbox(self):
    authenticating = True
    try:
      if self.user:
        await asyncio.wait_for(
            self._handle_authentication(),
            timeout=self.timeout,
        )
      authenticating = False
      while True:
        # We want to start listening for a full json object as soon as we get any data
        initial_byte = await self.reader.read(n=1)
        # An initial bytestring of b'' from an asyncio.StreamReader indicates EOF
        # https://docs.python.org/3/library/asyncio-stream.html#asyncio.StreamReader.read
        if not initial_byte:
          break
        # Allows us to continue listening after receiving whitespace chars
        if not initial_byte.strip():
          continue
        json_message = await asyncio.wait_for(
            self._wait_for_json_message(initial_byte=initial_byte),
            timeout=self.timeout,
        )
        await self._inbox_queue.put(json_message)
    except asyncio.TimeoutError:
      if authenticating:
        log.error("Unable to authenticate user, Resetting connection")
      else:
        log.error("Failed to read message within timeout. Resetting connection.")
    except (InvalidStartByteError, MessageTooLargeError) as error:
      log.error("Unable to parse incoming message. %s Resetting connection.", error)
    except asyncio.CancelledError:  # pylint: disable=try-except-raise
      raise
    except ConnectionError as e:
      log.error("Failed to read message: %r", e)
    except Exception:
      log.exception("Exception in peer reader loop")

    await self._shutdown(was_requested=False)

  async def _wait_for_json_message(self, initial_byte):
    try:
      message = initial_byte.decode()
      separator = self._retrieve_expected_ending_byte(initial_byte)
      while True:
        raw_message = await self.readuntil(separator)
        try:
          message += raw_message.decode()
          if self.utf8len(message) > self.MAX_MESSAGE_SIZE_BYTES:
            raise MessageTooLargeError(message)
          decoded_message = json.loads(message)
          return decoded_message
        except json.JSONDecodeError:
          pass
    except asyncio.CancelledError:
      log.error("Peer did not receive valid json within timeout window. Incomplete message: %s",
                 message)
      raise

  async def _handle_authentication(self):
    while True:
      raw = await self.readuntil(self.PROMPT_DELIMITER)
      prompt = self._clean_prompt(raw.decode())
      if prompt == "user":
        message = self.user + "\r\n"
        self.writer.write(message.encode())
      elif prompt == "password":
        message = self.password + "\r\n"
        self.writer.write(message.encode())
      elif prompt == "connected":
        return
      else:
        log.error("Received unexpected prompt: %s. Sending carriage return, hopefully will"
                  "continue.", prompt)
        message = "\r\n"
        self.writer.write(message.encode())

  def _clean_prompt(self, prompt):
    return prompt.strip().lower()[:-1]

  def utf8len(self, byte_str):
    return len(byte_str.encode('utf-8'))

  def _retrieve_expected_ending_byte(self, initial_byte):
    # We do not accept all valid json objects. With no delimiter it is impossible
    # to parse all valid json objects over a stream.
    try:
      return {b'{': b'}', b'[': b']', b'"': b'"'}[initial_byte]
    except KeyError as e:
      raise InvalidStartByteError(initial_byte) from e

  async def readuntil(self, separator=b'\n'):
    raw = b''
    while True:
      next_byte = await self.reader.read(n=1)
      raw += next_byte
      if next_byte == separator:
        return raw


async def open_connection(remote_address,
                          loop,
                          params=None,
                          timeout=None,
                          authenticator=None,
                          supported_api_versions=None,
                          cert_file_directory=None):
  if authenticator:
    raise NotImplementedError(
        "Authenticator support in JsonRPCMessagePeer not implemented"
    )

  if supported_api_versions is not None:
    raise NotImplementedError(
        "Supported API Versions in JsonRPCMessagePeer not implemented"
    )

  if cert_file_directory is not None:
    raise NotImplementedError("The certificate file directory is not implemented for "
                              "JsonRPCMessagePeer")

  protocol, addr_family, connection_args, secure = utils.parse_address(remote_address)
  assert protocol == utils.MessagingProtocol.JSON_RPC
  params = params or {}
  user = connection_args.pop("user", None)
  password = connection_args.pop("password", None)
  ssl_context = params.get("ssl_context")
  if ssl_context:
    connection_args["ssl_context"] = ssl_context

  reader, writer = await utils.open_stream(
      loop=loop,
      addr_family=addr_family,
      timeout=timeout,
      read_limit=JsonRPCMessagePeer.MAX_MESSAGE_SIZE_BYTES,
      secure=secure,
      **connection_args,
  )
  peer = JsonRPCMessagePeer(
      remote_address=remote_address,
      reader=reader,
      writer=writer,
      loop=loop,
      user=user,
      password=password,
      timeout=timeout,
  )
  return peer
