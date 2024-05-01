import asyncio
import logging
import socket
import ssl
import sys


log = logging.getLogger(__name__)


# Set of SSLError.reason values that may be indicative of a problem on the other end and not our end
# These will be downgraded to a warning level log
SSL_ERROR_WARNING_REASONS = set([
    "CERTIFICATE_VERIFY_FAILED",
    "NO_SHARED_CIPHER",
    "CCS_RECEIVED_EARLY",
    "WRONG_VERSION_NUMBER",
])


def dump_task_chain(task):
  chain = []
  next_to_check = getattr(task, '_coro', None)
  while next_to_check:
    # In python3.6, if a couroutine is waiting on a future, it is an instance of
    # _asyncio.FutureIter.
    # HACK, you can't actually import _asyncio.FutureIter since it is a C type. So, do this to
    # maintain compatibility with the behavior in python 3.5.
    if sys.version_info >= (3, 6) and hasattr(next_to_check, "__iter__"):
      chain.append("__iter__()")
      break
    chain.append("{}()".format(getattr(next_to_check, '__qualname__', None)))
    previous = next_to_check
    next_to_check = None
    for attr_to_try in ("cr_await", "gi_yieldfrom"):
      next_to_check = getattr(previous, attr_to_try, None)
      if next_to_check:
        break

  return chain


def dump_task_state_exception_handler(loop, context):
  task = context['task']
  awaiting = " -> ".join(dump_task_chain(task))
  log.error("Informed of error with task: %r, awaiting: %s", task, awaiting)
  return False


def transport_exception_handler(loop, context):
  exc = context.get('exception')
  if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
    transport = context['transport']
    peer = transport.get_extra_info('peername')
    log.warning("Transport for peer %s timed out: %r", peer, exc)
    return True
  if isinstance(exc, ssl.SSLError) and getattr(exc, "reason", "") in SSL_ERROR_WARNING_REASONS:
    # Docs say SSLError should have a reason attribute, but we'll access defensively just in case
    # Updated versions of uvloop should catch these as OSErrors and log debug level logs, but for
    # now we will handle these explicitly to log as a warning rather than an error.
    log.warning("Encountered SSLError: %r", context, exc_info=(type(exc), exc, exc.__traceback__))
    return True

  message = context.get("message", "")
  if "Fatal error on transport" in message:
    log.error("Transport %r reported fatal exception: %r with message: %r (protocol:%r)",
              context.get("transport"),
              exc,
              message,
              context.get("protocol"))
    return True

  return False


def future_exception_handler(loop, context):
  if context.get('message') in ('Future exception was never retrieved',
                                'Task exception was never retrieved'):
    exc = context.get('exception')
    if isinstance(exc, socket.gaierror) and exc.strerror == 'Temporary failure in name resolution':
      # Cancelling a loop.create_connection task can lead to an internal future not being properly
      # cancelled and causing this message to surface when that future eventually gets deleted. This
      # specific error is typically caused by transient DNS issues. See JIRA CQ-963 for more details
      log.warning('Caught future exception: "%s": %s', context.get('message'), exc)
      return True
  return False


def exception_handler(loop, context):
  handled = False
  if 'task' in context:
    handled = dump_task_state_exception_handler(loop, context)
  elif 'transport' in context:
    handled = transport_exception_handler(loop, context)
  elif 'future' in context:
    handled = future_exception_handler(loop, context)

  if not handled:
    loop.default_exception_handler(context)


_std_format_coroutine = None


def cython_aware_format_coroutine(coro):
  unset = object()
  func_name = unset
  # Cython returns `None` for these properties after it cleans up due to an exception, which breaks
  # asyncio's coroutine printing code.
  for name_property in ('__qualname__', '__name__'):
    func_name = getattr(coro, name_property, unset)
    if func_name is not unset:
      break

  if func_name is None:
    return "<deleted>"

  return _std_format_coroutine(coro)


def patch_format_coroutine():
  from asyncio import coroutines  # pylint: disable=import-outside-toplevel
  global _std_format_coroutine  # pylint: disable=global-statement
  if hasattr(coroutines, '_format_coroutine'):
    _std_format_coroutine = coroutines._format_coroutine
    coroutines._format_coroutine = cython_aware_format_coroutine
