import asyncio
import collections
import contextlib
import enum
import functools
import logging
import random

from lib.async_helpers import iterable_queue
from lib.logging import conditional_logger
import lib.time


log = logging.getLogger(__name__)
throttled_log = conditional_logger.ThrottledLogger(
    log_instance=log,
    default_policy=conditional_logger.ExponentialBackoffPolicy(),
)


class CancellationReason(enum.Enum):
  UNSET = 0
  QUEUE_FULL = 1
  SHUTDOWN = 2
  NEW_JOBS_AVAILABLE = 3
  MANUAL_CANCELLATION = 4


class PendingJob(asyncio.Future):

  def __init__(self, job_params, loop):
    super().__init__(loop=loop)
    self.job_params = job_params
    self.attempts = 0
    self._process_task = None
    self._scheduled_handle = None
    self._cancellation_reason = CancellationReason.UNSET

  def is_in_progress(self):
    return self._process_task is not None

  def cancel(self, msg=None, *, reason=None):
    if not super().cancel(msg):
      return False

    if reason and self._cancellation_reason == CancellationReason.UNSET:
      self._cancellation_reason = reason

    if self._scheduled_handle:
      self._scheduled_handle.cancel()

    if self._process_task:
      self._process_task.cancel()

    return True

  def set_scheduled_handle(self, handle):
    self._scheduled_handle = handle

  def set_result(self, result):
    # We might be in a race to set the result before the job gets cancelled
    if not self.cancelled():
      super().set_result(result)

  def set_exception(self, exception):
    super().set_exception(exception)
    # Silence any warning about uncollected exceptions. Failures are already logged and there's
    # often no one awaiting the job.
    self.exception()

  def cancellation_reason(self):
    if not self.cancelled():
      return None
    return self._cancellation_reason

  @contextlib.contextmanager
  def attempt(self, worker):
    self.attempts += 1
    self._process_task = worker
    try:
      yield self.job_params
    except asyncio.CancelledError:
      # Don't propagate the Cancelled
      if not self.cancelled():
        raise
    finally:
      self._process_task = None


class WorkQueue:

  def __init__(self, loop,
               num_workers,
               process_job_func,
               max_pending_jobs=None,
               retry_interval=0,
               max_retries=0,
               exponential_base=1,
               max_wait_secs=60,
               expected_exceptions=None,
               exceptions_to_throttle_logging=None,
               stop_retries_on_unexpected_exception=False):
    '''A queue that holds PendingJobs and runs QueueWorkers to process the PendingJobs. To create a
    queue that uses expontial backoff to retry jobs, see the ExponentialBackoffWorkQueue.

    loop: The event loop on which the QueueWorker will execute.
    num_workers: The number of QueueWorkers to create to the process the PendingJobs.
    process_job_func: The function the QueueWorker will call to run the job.
    max_pending_jobs: The maximum number of PendingJobs to allow in the queue at a given time. If
        None, the queue will allow an unlimited number of PendingJobs.
    retry_interval: The base number of seconds to wait until attempting to run a job again after a
        failure.
    max_retries: The maximum number of times to attempt to process a PendingJob.
    exponential_base: The exponent to use in the exponential backoff algorithm.
    max_wait_secs: The maximum number of seconds to wait to retry a given call.
    expected_exceptions: A tuple of exceptions that the user expects may occur and should be retried
        silently.
    exceptions_to_throttle_logging: A tuple of exceptions that the user expects may occur and should be
        logged with a throttled logger.
    '''
    self.loop = loop
    self.num_workers = num_workers
    self.workers = []
    self.queue = TimeDelayedWorkQueue(self.loop, max_pending_jobs=max_pending_jobs)
    for _ in range(self.num_workers):
      worker = QueueWorker(
          loop=self.loop,
          queue=self.queue,
          process_job_func=process_job_func,
          retry_interval=retry_interval,
          max_retries=max_retries,
          exponential_base=exponential_base,
          max_wait_secs=max_wait_secs,
          expected_exceptions=expected_exceptions,
          exceptions_to_throttle_logging=exceptions_to_throttle_logging,
          stop_retries_on_unexpected_exception=stop_retries_on_unexpected_exception,
      )
      self.workers.append(worker)

  @property
  def idle(self):
    return len(self.queue.scheduled_jobs) == 0 and all(worker.idle for worker in self.workers)

  def start(self):
    self.queue.start()
    for worker in self.workers:
      worker.start()

  def shutdown(self):
    for worker in self.workers:
      worker.shutdown()
    self.queue.shutdown()

  def reset(self):
    self.queue.clear(CancellationReason.MANUAL_CANCELLATION)
    for worker in self.workers:
      worker.cancel()

  def add_job(self, job, delay=None):
    pending_job = PendingJob(job_params=job, loop=self.loop)
    self.queue.add_job(
        pending_job=pending_job,
        delay=delay,
    )
    return pending_job


class ExponentialBackoffWorkQueue(WorkQueue):

  def __init__(self, **kwargs):
    super().__init__(retry_interval=1,
                     max_retries=None,
                     exponential_base=2,
                     **kwargs)


class KeyedSingletonWorkQueue(WorkQueue):

  def __init__(self,
               replace_existing_job=True,
               throttle_window_ms=None,
               num_workers=1,
               drop_throttled_jobs=True,
               independent_key_throttles=True,
               **kwargs):
    super().__init__(max_pending_jobs=None, num_workers=num_workers, **kwargs)
    self.replace_existing_job = replace_existing_job
    self.outstanding_pending_job_futures = {}
    self.throttle_window_ms = throttle_window_ms
    self.last_job_scheduled_timestamps = {}
    self.drop_throttled_jobs = drop_throttled_jobs
    self.independent_key_throttles = independent_key_throttles

  def add_job(self, key, job, delay=None):  # pylint: disable=arguments-renamed
    if self.has_active_job(key):
      if self.replace_existing_job:
        log.debug("Cancelling outstanding job for key: %s", key)
        self.outstanding_pending_job_futures[key].cancel()
      else:
        log.debug("Not adding job, pending job for key exists")
        return None

    if self.throttle_window_ms is not None:
      current_time_ms = lib.time.get_current_time_ms()
      if self.independent_key_throttles:
        last_time_scheduled_ms = self.last_job_scheduled_timestamps.get(key, 0)
      else:
        all_timestamps = self.last_job_scheduled_timestamps.values()
        last_time_scheduled_ms = max(all_timestamps) if all_timestamps else 0

      delta_ms = current_time_ms - last_time_scheduled_ms
      if delta_ms < self.throttle_window_ms:
        if self.drop_throttled_jobs:
          log.debug("Not scheduling job for key %s, last scheduled %sms ago", key, delta_ms)
          return None
        delay_until_window_end_s = (self.throttle_window_ms - delta_ms) / 1000
        delay = max(delay_until_window_end_s, delay) if delay else delay_until_window_end_s
        log.debug(
            "Delaying job for key %s by %ss, last scheduled %sms ago, current_time: %sms, "
            "throttle_window: %sms", key, delay, delta_ms, current_time_ms, self.throttle_window_ms
        )
      self.last_job_scheduled_timestamps[key] = current_time_ms

    self.outstanding_pending_job_futures[key] = super().add_job(job, delay)
    return self.outstanding_pending_job_futures[key]

  def cancel_job(self, key):
    if key in self.outstanding_pending_job_futures:
      self.outstanding_pending_job_futures[key].cancel()

  def has_active_job(self, key):
    return (key in self.outstanding_pending_job_futures
            and not self.outstanding_pending_job_futures[key].done())


class SingletonJobWorkQueue(KeyedSingletonWorkQueue):
  DEFAULT_KEY = object()

  def __init__(self, **kwargs):
    super().__init__(**kwargs)
    self.last_pending_job_future = None

  def add_job(self, job, delay=None):
    job = super().add_job(key=self.DEFAULT_KEY, job=job, delay=delay)
    if job:
      self.last_pending_job_future = job
    return job

  def cancel_job(self):
    super().cancel_job(self.DEFAULT_KEY)

  def has_active_job(self, key=None):
    return super().has_active_job(self.DEFAULT_KEY)


class TimeDelayedWorkQueue:

  def __init__(self, loop, max_pending_jobs=None):
    self.loop = loop
    self.queue = iterable_queue.IterableQueue(loop=self.loop)
    if max_pending_jobs is not None and max_pending_jobs <= 0:
      raise ValueError("max_pending_jobs must be non-negative")
    self.max_pending_jobs = max_pending_jobs
    self.scheduled_jobs = collections.deque()

  def start(self):
    if not self.queue.active():
      self.queue.start()

  def shutdown(self):
    self.queue.shutdown()
    self.clear(CancellationReason.SHUTDOWN)

  def clear(self, cancellation_reason=CancellationReason.UNSET):
    for scheduled_job in self.scheduled_jobs:
      scheduled_job.cancel(reason=cancellation_reason)

    self.scheduled_jobs.clear()

  def add_job(self, pending_job, delay=None):
    # Prefer more recently submitted jobs when there's a queue bound in place:
    # -- Don't retry on failure if that requires cancelling a different job
    # -- Drop jobs from head of queue to make space for new jobs
    if pending_job.attempts > 0 and self.is_full():
      pending_job.cancel(reason=CancellationReason.NEW_JOBS_AVAILABLE)
      return

    while self.is_full():
      scheduled_job = self.scheduled_jobs.popleft()
      scheduled_job.cancel(reason=CancellationReason.QUEUE_FULL)

    self.scheduled_jobs.append(pending_job)

    submit_func = functools.partial(self._submit_pending_job, pending_job)
    if delay:
      job_handle = self.loop.call_later(delay, submit_func)
      pending_job.set_scheduled_handle(job_handle)
      # Make sure the job is dropped properly if it's cancelled before scheduling
      pending_job.add_done_callback(self._drop_cancelled_job)
    else:
      submit_func()

  def is_full(self):
    return self.max_pending_jobs and len(self.scheduled_jobs) >= self.max_pending_jobs

  def _submit_pending_job(self, pending_job):
    try:
      self.queue.put_nowait(pending_job)
    except asyncio.InvalidStateError:
      pending_job.cancel(reason=CancellationReason.SHUTDOWN)

  def _drop_cancelled_job(self, pending_job):
    if pending_job.cancelled() and pending_job in self.scheduled_jobs:
      self.scheduled_jobs.remove(pending_job)

  async def get_next_job(self):
    while True:
      pending_job = await self.queue.get()
      if pending_job in self.scheduled_jobs:
        self.scheduled_jobs.remove(pending_job)
      if pending_job.cancelled():
        continue
      return pending_job


class QueueWorker:

  def __init__(self, loop,
               queue,
               process_job_func,
               retry_interval,
               max_retries,
               exponential_base,
               max_wait_secs,
               expected_exceptions=None,
               exceptions_to_throttle_logging=None,
               stop_retries_on_unexpected_exception=False):
    '''
    A worker that processes PendingJobs in a WorkQueue.

    To use exponential backoff with jitter when retrying a job, make sure to set:
    - The retry_interval above 0 (e.g. 0.5, 1, etc.).
    - The max_retries to None (for infinite retries) or an integer greater than 0.
    - The exponential_base to two or more.
    For example:
        QueueWorker(loop, queue, process_job_func,
                    retry_interval=1,
                    max_retries=None,
                    exponential_base=2)

    loop: The event loop on which the QueueWorker will execute.
    queue: The TimeDelayedWorkQueue that holds the PendingJobs.
    process_job_func: The function the QueueWorker will call to run the job.
    retry_interval: The base number of seconds to wait until attempting to run a job again after a
        failure.
    max_retries: The maximum number of times to attempt to process a PendingJob.
    exponential_base: The exponent to use in the exponential backoff algorithm.
    max_wait_secs: The maximum number of seconds to wait to retry a given call.
    expected_exceptions: A tuple of exceptions that the user expects may occur and should be retried
        silently.
    exceptions_to_throttle_logging: A tuple of exceptions that the user expects may occur and should be
        logged with a throttled logger.
    stop_retries_on_unexpected_exception: True/False for whether we want to stop retrying when an
        unexpected exception is received. Most useful in conjunction with max_retries = None or
        max_retries > 0 Default is False to maintain existing behavior.
    '''
    self.loop = loop
    self.queue = queue
    self.process_job_func = process_job_func
    self.retry_interval = retry_interval
    self.max_retries = max_retries
    self.exponential_base = exponential_base
    self.max_wait_secs = max_wait_secs
    self.expected_exceptions = expected_exceptions or tuple()
    self.exceptions_to_throttle_logging = exceptions_to_throttle_logging or tuple()
    self.stop_retries_on_unexpected_exception = stop_retries_on_unexpected_exception
    self._process_task = None
    self._most_recent_job = None

  @property
  def idle(self):
    return not self._most_recent_job or self._most_recent_job.done()

  def start(self):
    if self._process_task:
      return
    self._process_task = self.loop.create_task(self.run())

  def shutdown(self):
    task_to_cancel = self._process_task
    self._process_task = None

    if task_to_cancel:
      task_to_cancel.cancel()

  def cancel(self):
    if not self.idle:
      self._most_recent_job.cancel(reason=CancellationReason.MANUAL_CANCELLATION)

  def _calculate_delay_secs(self, attempt_number):
    '''If the exponential_base is one, then just use the set retry_interval.

    If an exponential_base greater than one is specified, calculate an exponential backoff with
    jitter based on the attempt number. Uses the "Full Jitter" algorithm as discussed in
    https://www.awsarchitectureblog.com/2015/03/backoff.html.
    '''
    if self.exponential_base == 1:
      return self.retry_interval

    return random.uniform(0, min(self.max_wait_secs,
                                 self.retry_interval * self.exponential_base ** attempt_number))

  async def run(self):
    try:
      await self._run()
    except Exception:
      log.exception("Queue worker with task func: %s failed!", self.process_job_func)

  async def _run(self):
    while self._process_task:
      pending_job = None
      try:
        self._most_recent_job = await self.queue.get_next_job()
        pending_job = self._most_recent_job
      except (asyncio.CancelledError, asyncio.InvalidStateError, RuntimeError):
        if pending_job:
          pending_job.cancel(reason=CancellationReason.SHUTDOWN)
        break

      try:
        with pending_job.attempt(self._process_task) as job_params:
          result = await self.process_job_func(job_params)
          if pending_job.cancelled():
            # Handle a nasty edge case where jobs cancel themselves immediately before returning.
            # This invocation will yield to the event loop, which will raise the CancelledError
            # while we're still processing this job.
            await asyncio.sleep(0)

          pending_job.set_result(result)
      except asyncio.CancelledError as e:
        # Mark the job as cancelled, but don't break out of the processing loop
        log.info("PendingJob cancelled, exception swallowed.", exc_info=e)
        pending_job.cancel()
      except Exception as e:
        expected_exception = isinstance(e, self.expected_exceptions)
        if not expected_exception:
          logger = throttled_log if isinstance(e, self.exceptions_to_throttle_logging) else log
          logger.exception("Got exception processing job: %s %s", type(e).__name__, str(e))
        should_retry = expected_exception or not self.stop_retries_on_unexpected_exception
        if ((self.max_retries is None or pending_job.attempts < self.max_retries + 1) and
            should_retry):
          self.queue.add_job(
              pending_job=pending_job,
              delay=self._calculate_delay_secs(pending_job.attempts),
          )
        else:
          pending_job.set_exception(e)
