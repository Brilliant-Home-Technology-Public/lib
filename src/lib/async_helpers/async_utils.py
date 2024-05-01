import asyncio
import logging


log = logging.getLogger(__name__)


async def log_exception(awaitable):
  try:
    return await awaitable
  except Exception:
    log.exception("Caught exception awaiting %s", awaitable)
    raise


async def gather_logging_exceptions(*aws):
  # NOTE: From asyncio.gather documentation:
  # If return_exceptions is False (default), the first raised exception is immediately propagated
  # to the task that awaits on gather(). Other awaitables in the aws sequence won’t be cancelled and
  # will continue to run.
  # This also means that when an exception is raised, those other awaitables become "detached" and
  # cancellations (CancelledError) can no longer propagate to them.
  # This util function guarantees to block until all awaitables have completed (via
  # return_exceptions=True) and thus enables propagating cancellations amidst encountering other
  # errors. Any errors encountered will be logged but will not result in detached, uncancellable
  # tasks. This function should also never raise/propagate an error since it swallows all errors
  # encountered.
  # This property of guaranteeing cancel propagation is especially useful for shutdown behavior
  # since that is when we often want to propagate cancellation through a portion of our system;
  # using this function instead of asyncio.gather ensures tasks do not run after shutdown when they
  # should have been cancelled.
  return await asyncio.gather(
      *(
          log_exception(awaitable)
          for awaitable in aws
      ),
      return_exceptions=True,
  )
