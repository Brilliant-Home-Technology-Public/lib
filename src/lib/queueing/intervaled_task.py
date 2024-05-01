# pylint: disable=unused-argument
import asyncio
import logging
import random

from lib.queueing.work_queue import WorkQueue


log = logging.getLogger(__name__)


class IntervaledTask:

  def __init__(self, loop, interval, task_func, jitter=None):
    self.loop = loop
    self.interval = interval
    self.task_func = task_func
    self.dummy_job_info = None
    self.queue = WorkQueue(loop=self.loop, num_workers=1, process_job_func=self._process_job)
    self.has_shutdown = False
    if not (jitter is None or 0. <= jitter <= 1.):
      raise ValueError("Jitter must be a float in range [0, 1] (got {})".format(jitter))
    self.jitter = jitter

  def start(self, delay_first_job=False):
    self.has_shutdown = False
    self.queue.start()
    if delay_first_job:
      return self.queue.add_job(job=self.dummy_job_info, delay=self.interval)
    return self.queue.add_job(job=self.dummy_job_info)

  def shutdown(self):
    self.queue.shutdown()
    self.has_shutdown = True

  async def _process_job(self, job=None):
    try:
      await self.task_func()
    except asyncio.CancelledError:
      pass
    except Exception as e:
      log.exception("Got exception processing job: %s %s", type(e).__name__, str(e))
    if not self.has_shutdown:
      next_delay = self.interval
      if self.jitter is not None:
        next_delay += self.interval * random.uniform(
            -self.jitter,  # pylint: disable=invalid-unary-operand-type
            self.jitter
        )

      self.queue.add_job(job=self.dummy_job_info, delay=next_delay)
