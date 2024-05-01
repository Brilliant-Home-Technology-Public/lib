import asyncio
import json
import logging

from lib import connection_manager
from lib.error_logging import chunked_file_sentry_client


log = logging.getLogger(__name__)


class ErrorServer:

  LOG_LEVEL_MAP = {
      "D": logging.DEBUG,
      "I": logging.INFO,
      "W": logging.WARNING,
      "E": logging.ERROR,
      "C": logging.CRITICAL,
      "F": logging.CRITICAL,
  }

  def __init__(self, loop, listen_address, storage_dir, sample_rate):
    self._loop = loop
    self._listen_address = listen_address
    self._storage_dir = storage_dir
    self._sample_rate = sample_rate
    self._environment_name = None
    self._release_tag = None
    self._connection_manager = connection_manager.PeerConnectionManager(
        loop=self._loop,
        new_peer_async_callback=self._handle_new_peer,
        connection_params=None,
    )
    self._server_tasks = set()

    self._clients_by_unit_name = {}

  async def start(self):
    if self._listen_address:
      await self._connection_manager.start_server(listen_address=self._listen_address)

  async def shutdown(self):
    await self._connection_manager.shutdown()
    for task in list(self._server_tasks):
      task.cancel()

    shutdown_tasks = []
    for client in self._clients_by_unit_name.values():
      shutdown_tasks.append(client.shutdown())

    self._clients_by_unit_name.clear()
    await asyncio.gather(*shutdown_tasks)

  def set_environment_name(self, environment_name):
    self._environment_name = environment_name

  def set_release_tag(self, release_tag):
    self._release_tag = release_tag

  async def _handle_new_peer(self, peer):
    task = self._loop.create_task(self._handle_event_messages(peer))
    self._server_tasks.add(task)
    task.add_done_callback(self._server_tasks.discard)

  async def _handle_event_messages(self, peer):
    async for message in peer.incoming_message_iterator():
      try:
        await self._handle_event_message(message)
      except asyncio.CancelledError:  # pylint: disable=try-except-raise
        raise
      except Exception:
        log.exception("Failed to capture event for message: %s", message)

  async def _handle_event_message(self, message):
    event = json.loads(message)
    await self._capture_event(event)

  async def _capture_event(self, event):
    unit_name = event.get("unit_name")
    if not unit_name:
      log.warning("No unit specified in event %s; ignoring.")
      return

    log_message = event.get("message")
    if not log_message:
      log.warning("No message specified in event %s; ignoring.")
      return

    levelno = self.LOG_LEVEL_MAP.get(event.get("level"), logging.NOTSET)

    extra_params = {}
    for extra_param in ("filename", "lineno"):
      if extra_param in event:
        extra_params[extra_param] = event[extra_param]

    if self._sample_rate > 0:
      client = await self._get_client(unit_name)
      client.report_message(
          message=log_message,
          levelno=levelno,
          format_string=event.get("format_string"),
          format_parameters=event.get("format_parameters"),
          fingerprint=event.get("fingerprint"),
          timestamp=event.get("timestamp"),
          platform=event.get("platform"),
          extra=extra_params,
      )

  async def _get_client(self, unit_name):
    if unit_name not in self._clients_by_unit_name:
      self._clients_by_unit_name[unit_name] = await self._make_client(unit_name)

    return self._clients_by_unit_name[unit_name]

  async def _make_client(self, unit_name):
    client = chunked_file_sentry_client.ChunkedFileSentryClient(
        loop=self._loop,
        storage_dir=self._storage_dir,
        sample_rate=self._sample_rate,
        unit_name=unit_name,
        software_version=self._release_tag,
        configure_logger=False,
        environment=self._environment_name,
    )
    await client.start()
    return client
