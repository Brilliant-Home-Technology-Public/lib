import asyncio
import base64
import json
import logging
import typing
import zlib

from lib.storage import stream_object


log = logging.getLogger(__name__)


class ChunkedJSONFileSentryTransport:

  def __init__(self, loop, unit_name, storage_dir):
    self._loop = loop
    self._unit_name = unit_name
    self._stream_object = stream_object.ChunkedFileStreamObject(
        loop=self._loop,
        storage_dir=storage_dir,
    )

  async def start(self):
    await self._stream_object.start()

  async def shutdown(self):
    await self._stream_object.shutdown()

  def async_send(self, data: typing.Dict[typing.Any, typing.Any]) -> asyncio.Task:
    def _handle_task_done(t):
      if t.cancelled():
        return

      if t.exception():
        log.warning("Failed to store Sentry data: %r", t.exception())

    # The Sentry SDK no longer populates this field, but our server code expects it
    if 'project' not in data:
      data['project'] = self._unit_name

    # The Raven SDK would previously invoke our custom transport with a zlib-compressed JSON object,
    # so we maintain that encoding for compatibility with our existing server code.
    task = self._loop.create_task(self._do_store(data=zlib.compress(json.dumps(data).encode())))
    task.add_done_callback(_handle_task_done)
    return task

  async def _do_store(self, data: bytes):
    dumped = json.dumps(dict(data=base64.b64encode(data).decode()))
    self._stream_object.write_bytes(dumped.encode() + b'\n')
