import asyncio
import concurrent.futures
import logging

from lib.queueing import work_queue


log = logging.getLogger(__name__)


class ThreadSafeTimer:

  def __init__(self, loop, pending_job):
    self._loop = loop
    self._pending_job = pending_job

  def is_alive(self):
    return not self._pending_job.done()

  def is_firing(self):
    return self._pending_job.is_in_progress()

  def cancel(self):
    self._loop.call_soon_threadsafe(self._pending_job.cancel)


class ThreadSafeTimerQueue:

  def __init__(self, loop, max_concurrency=5):
    self._loop = loop
    self._max_concurrency = max_concurrency
    self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=self._max_concurrency)
    self._queue = work_queue.WorkQueue(
        loop=loop,
        num_workers=self._max_concurrency,
        process_job_func=self._handle_timeout,
    )

  async def start(self):
    if not self._executor:
      self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=self._max_concurrency)
    self._queue.start()

  async def shutdown(self):
    if self._executor:
      self._executor.shutdown(wait=False)
      self._executor = None
    self._queue.shutdown()

  async def _set_timer_async(self, timeout_ms, callback_func, args):
    job = self._queue.add_job((callback_func, args), delay=timeout_ms / 1000)
    return ThreadSafeTimer(self._loop, job)

  def set_timer(self, timeout_ms, callback_func, args=()):
    blocking_future = asyncio.run_coroutine_threadsafe(
        self._set_timer_async(timeout_ms, callback_func, args),
        loop=self._loop,
    )
    return blocking_future.result()

  async def _handle_timeout(self, callback_func_and_args):
    if not self._executor:
      log.warning("Timer queue has been shut down; can't handle timer callback!")
      return

    callback_func, args = callback_func_and_args
    await self._loop.run_in_executor(
        executor=self._executor,
        func=lambda: callback_func(*args),
    )
