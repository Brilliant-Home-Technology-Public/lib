import abc
import asyncio
import glob
import gzip
import io
import logging
import os
import shutil

from lib.async_helpers import future_value
from lib.queueing import intervaled_task
from lib.queueing import work_queue
from lib.storage import object_store_client_library
import lib.storage.interface as storage_interface


log = logging.getLogger(__name__)


class BaseFileCollector(metaclass=abc.ABCMeta):
  def __init__(self,
               loop,
               scan_directory,
               file_pattern,
               metadata_args,
               gzip_compress_level=5,
               poll_interval_seconds=30,
               remove_collected_files=False):
    self._loop = loop
    self._scan_directory = scan_directory
    self._file_pattern = file_pattern
    self._metadata_args = metadata_args
    self._gzip_compress_level = gzip_compress_level
    self._remove_collected_files = remove_collected_files

    self._processed = set()
    self._work_queue = work_queue.WorkQueue(
        loop=self._loop,
        num_workers=1,
        max_retries=0,
        process_job_func=self._upload_file,
    )
    self._scan_task = intervaled_task.IntervaledTask(
        loop=self._loop,
        interval=poll_interval_seconds,
        task_func=self.scan_for_files,
    )

  async def start(self):
    self._work_queue.start()
    self._scan_task.start()

  async def shutdown(self):
    self._scan_task.shutdown()
    self._work_queue.shutdown()

  def update_metadata(self, updates):
    self._metadata_args.update(updates)

  async def scan_for_files(self):
    if not os.path.exists(self._scan_directory):
      log.debug("Can't scan directory %s for upload files; doesn't exist!", self._scan_directory)
      return

    full_path = os.path.join(self._scan_directory, self._file_pattern)
    present_files = set(glob.iglob(full_path))

    # Don't need to track status of files that no longer exist
    self._processed &= present_files

    files_to_process = present_files - self._processed
    job_futures = [self._work_queue.add_job(file_path) for file_path in files_to_process]
    # Block from scheduling any more jobs until these are all done
    await asyncio.gather(*job_futures, return_exceptions=True)

  @abc.abstractmethod
  async def _upload_file(self, file_path):
    pass


class LocalFileCollector(BaseFileCollector):
  def __init__(self,
               loop,
               scan_directory,
               file_pattern,
               metadata_args,
               gzip_compress_level=5,
               poll_interval_seconds=30,
               remove_collected_files=False):

    super().__init__(loop=loop,
                     scan_directory=scan_directory,
                     file_pattern=file_pattern,
                     metadata_args=metadata_args,
                     gzip_compress_level=gzip_compress_level,
                     poll_interval_seconds=poll_interval_seconds,
                     remove_collected_files=remove_collected_files)

    self._object_store_port_val = future_value.FutureValue(loop=loop)

  def set_object_store_port(self, port):
    self._object_store_port_val.set_value(port)

  async def scan_for_files(self):
    await self._object_store_port_val
    await super().scan_for_files()

  async def _upload_file(self, file_path):
    data_buffer = io.BytesIO()
    with open(file_path, 'rb') as file_in:
      with gzip.open(data_buffer, mode='wb', compresslevel=self._gzip_compress_level) as gzip_out:
        shutil.copyfileobj(file_in, gzip_out)

    data = data_buffer.getvalue()
    base_args = dict(
        size=len(data),
        name=os.path.relpath(file_path, self._scan_directory),
        content_encoding="identity",
        brilliant_content_encoding="gzip"
    )
    base_args.update(self._metadata_args)
    metadata = storage_interface.ObjectMetadata(**base_args)

    local_object_store = object_store_client_library.LocalObjectStoreInterface(
        local_listen_port=self._object_store_port_val.value(),
    )
    await local_object_store.make_put_request(data, metadata)
    self._processed.add(file_path)
    if self._remove_collected_files:
      os.unlink(file_path)
