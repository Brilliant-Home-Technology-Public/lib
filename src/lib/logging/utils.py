import functools
import logging


def log_pre_and_post_call(logger, log_level=logging.INFO):
  """
  Decorator factory for logging before and after the decorated function is called.

  Example Usage:
  - @log_pre_and_post_call(log)
  - @log_pre_and_post_call(log, logging.DEBUG)

  """
  def _function_decorator(function):

    @functools.wraps(function)
    def wrapped_function(*args, **kwargs):
      logger.log(log_level, "Pre call %s(args=%s, kwargs=%s)", function.__name__, args, kwargs)
      try:
        return function(*args, **kwargs)
      finally:
        logger.log(log_level, "Post call %s(args=%s, kwargs=%s)", function.__name__, args, kwargs)

    return wrapped_function

  return _function_decorator
