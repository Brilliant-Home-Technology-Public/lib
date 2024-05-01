import abc
import collections
import datetime
import logging
import typing
import zoneinfo

import thrift_types.configuration.ttypes as configuration_ttypes


class ThrottlePolicy(metaclass=abc.ABCMeta):

  # Assume num_occurrences will always be >= 1

  @abc.abstractmethod
  def should_emit(self, num_occurrences: int) -> tuple[bool, int | None]:
    '''Returns a tuple of (should_emit, current message compression ratio)'''

  @property
  def log_compression_ratio(self):
    return True


class LinearBackoffPolicy(ThrottlePolicy):

  def __init__(self, period=10):
    self.period = period

  def should_emit(self, num_occurrences: int) -> tuple[bool, int | None]:
    return (num_occurrences % self.period == 1, self.period)


class ExponentialBackoffPolicy(ThrottlePolicy):
  # Matches when num_occurences is a multiple of the nearest power of the specified base
  # E.g. 1, 2, 3, 4...; then 10, 20, 30..., then 100, 200, 300...
  def __init__(self, base=10):
    if base <= 1:
      raise ValueError("Invalid base for {}".format(type(self).__name__))

    self.base = base

  def should_emit(self, num_occurrences: int) -> tuple[bool, int | None]:
    # Logarithm is the "right" way to do this but it's susceptible to float rounding problems
    order_of_magnitude = 0
    while self.base ** (order_of_magnitude + 1) <= num_occurrences:
      order_of_magnitude += 1

    nearest_power = self.base ** order_of_magnitude
    return (num_occurrences % nearest_power == 0, nearest_power)


class PacificDailyTimeRangePolicy(ThrottlePolicy):

  PACIFIC_TIMEZONE = zoneinfo.ZoneInfo("America/Los_Angeles")

  def __init__(self, daily_time_range: configuration_ttypes.DailyTimeRange) -> None:
    super().__init__()
    if (daily_time_range.start_reference != configuration_ttypes.TimeReferencePoint.MIDNIGHT or
        daily_time_range.end_reference != configuration_ttypes.TimeReferencePoint.MIDNIGHT):
      raise ValueError("DailyTimeRange must be midnight based")
    self.daily_time_range = daily_time_range

  def should_emit(self, num_occurrences: int) -> tuple[bool, int | None]:
    now = datetime.datetime.now(self.PACIFIC_TIMEZONE)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seconds_from_midnight = (now - midnight).seconds
    start = self.daily_time_range.start_seconds_from_midnight
    end = self.daily_time_range.end_seconds_from_midnight
    should_emit = start <= seconds_from_midnight <= end
    return (should_emit, None)

  @property
  def log_compression_ratio(self):
    return False


class EmitOncePolicy(ThrottlePolicy):

  def should_emit(self, num_occurrences: int) -> tuple[bool, int | None]:
    return (num_occurrences == 1, None)


class ThrottledLogger:

  EMIT_ONCE = EmitOncePolicy()

  def __init__(
      self,
      log_instance: logging.Logger,
      default_policy: ThrottlePolicy,
      log_throttled_as_warning: bool = False,
  ):
    self.log_instance = log_instance
    self.occurrences_by_key: dict[typing.Any, int] = collections.defaultdict(int)
    self.default_policy = default_policy
    self.log_throttled_as_warning = log_throttled_as_warning

  def reset_count(self, key):
    self.occurrences_by_key[key] = 0

  def __getattr__(self, attr_name):
    logger_attr = getattr(self.log_instance, attr_name)
    if attr_name not in ("debug", "info", "warning", "error", "exception", "critical", "fatal"):
      return logger_attr

    def _log_at_level(msg, *args, key_override=None, policy_override=None, **kwargs):
      nonlocal logger_attr
      key = key_override or msg
      policy = policy_override or self.default_policy
      if policy:
        self.occurrences_by_key[key] += 1

        should_emit, period = policy.should_emit(self.occurrences_by_key[key])
        log_compression_ratio = policy.log_compression_ratio
        if not should_emit:
          if self.log_throttled_as_warning:
            logger_attr = self.log_instance.warning
            log_compression_ratio = False
          else:
            return

        if log_compression_ratio:
          throttle_info = ""
          if period is None:
            throttle_info = " [showing no further messages]"
          elif period > 1:
            throttle_info = " [showing 1/{} messages]".format(period)
          msg += "%s"
          args = (*args, throttle_info)

      logger_attr(msg, *args, **kwargs)

    return _log_at_level
