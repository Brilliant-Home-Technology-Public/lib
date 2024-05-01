import asyncio
import logging
import os
import tempfile

from lib.storage import local_file_collector
import lib.time


log = logging.getLogger(__name__)


class ChunkedFileStreamObject:

  def __init__(
      self,
      loop,
      storage_dir,
      metadata_args=None,
      gzip_compress_level=5,
      rollover_size_bytes=2**16,
      rollover_age_seconds=(60 * 60 * 6),
      file_collector_cls=None,
      rollover_on_shutdown=False,
  ):
    self._loop = loop
    self._storage_dir = storage_dir
    self._rollover_size_bytes = rollover_size_bytes
    self._rollover_age_seconds = rollover_age_seconds
    self._file = None
    self._file_created_ms = None
    self._bytes_written = None
    self._delayed_rollover = None
    self._local_file_collector = None
    self._rollover_on_shutdown = rollover_on_shutdown
    file_collector_cls = file_collector_cls or local_file_collector.LocalFileCollector
    if metadata_args:
      self._local_file_collector = file_collector_cls(
          loop=loop,
          scan_directory=storage_dir,
          file_pattern="*",  # Doesn't match files starting with .
          metadata_args=metadata_args,
          gzip_compress_level=gzip_compress_level,
          remove_collected_files=True,
      )

  async def start(self):
    os.makedirs(self._storage_dir, exist_ok=True)
    for filename in os.listdir(self._storage_dir):
      if filename.startswith("."):
        self._mark_ready(os.path.join(self._storage_dir, filename))

    self._start_new_file()
    if self._local_file_collector:
      await self._local_file_collector.start()

  async def shutdown(self):
    if self._rollover_on_shutdown:
      self._maybe_do_rollover(force=True)
      await self._local_file_collector.scan_for_files()

    if self._file:
      self._file.close()
      self._file = None

    if self._local_file_collector:
      await self._local_file_collector.shutdown()

  def update_metadata(self, updates):
    self._local_file_collector.update_metadata(updates)

  def set_object_store_port(self, port):
    self._local_file_collector.set_object_store_port(port)

  def write_bytes(self, data):
    self._bytes_written += self._file.write(data)
    self._file.flush()
    self._maybe_do_rollover()

  def _start_new_file(self):
    if self._file:
      # Add previous file to upload queue
      self._file.close()
      log.info("Queuing %s for upload", self._file.name)
      self._mark_ready(self._file.name)

    self._file = tempfile.NamedTemporaryFile(  # pylint: disable=consider-using-with
        mode='wb', dir=self._storage_dir, delete=False, prefix=".")

    log.info("Creating file at path %s", self._file.name)
    self._file_created_ms = lib.time.get_current_time_ms()
    self._bytes_written = 0

  def _maybe_do_rollover(self, force=False):
    if self._delayed_rollover:
      self._delayed_rollover.cancel()
      self._delayed_rollover = None

    file_age_seconds = (lib.time.get_current_time_ms() - self._file_created_ms) / 1000
    if (file_age_seconds > self._rollover_age_seconds or
        self._bytes_written > self._rollover_size_bytes or
        force):
      self._start_new_file()
    else:
      # Set up the rollover to happen once the file ages out, in case we aren't called until then
      self._delayed_rollover = self._loop.call_later(
          delay=(self._rollover_age_seconds - file_age_seconds),
          callback=self._start_new_file,
      )

  def _mark_ready(self, file_path):
    if not os.path.getsize(file_path):
      os.unlink(file_path)
      return

    dir_path, file_name = os.path.split(file_path)
    if not file_name.startswith("."):
      log.warning("Cannot mark file %s ready!", file_path)
      return

    ready_path = os.path.join(dir_path, file_name[1:])
    os.rename(file_path, ready_path)


# For backwards compatibility
GzippedStreamObject = ChunkedFileStreamObject


if __name__ == "__main__":
  logging.basicConfig(level=logging.INFO)
  loop = asyncio.get_event_loop()
  stream_obj = ChunkedFileStreamObject(loop=loop,
                                       storage_dir="/tmp/stream_object",
                                       metadata_args={},
                                       rollover_size_bytes=64,
                                       rollover_age_seconds=15)
  loop.run_until_complete(stream_obj.start())
  stream_obj.set_object_store_port(7455)
  for _ in range(25):
    stream_obj.write_bytes(b"abcd")
  loop.run_until_complete(asyncio.sleep(30))
  loop.run_until_complete(stream_obj.shutdown())
