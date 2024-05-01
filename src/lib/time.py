from datetime import datetime
import logging
import time


log = logging.getLogger(__name__)

ONE_DAY_IN_MS = 1000 * 60 * 60 * 24
FORMAT_STRING = "%a %b %d %Y %H:%M:%S"


def get_current_time_ms():
  return int(round(time.time() * 1000))


def convert_duration_to_ms(duration):
  """Convert duration string in format 00:00:00 hh:mm:ss to milliseconds"""
  struct_time = time.strptime(duration, "%H:%M:%S")
  duration_seconds = struct_time.tm_hour * 3600 + struct_time.tm_min * 60 + struct_time.tm_sec
  return duration_seconds * 1000


def convert_utc_timestamp_to_human_readable(ts):
  """Convert int timestamp into format Weekday Month Day Year hh:mm:ss"""
  return datetime.utcfromtimestamp(ts // 1000).strftime(FORMAT_STRING)


def convert_datetime_to_human_readable(dt):
  """Convert datetime.datetime object into format Weekday Month Day Year hh:mm:ss"""
  return dt.strftime(FORMAT_STRING) if dt else ""


def convert_datetime_to_utc_timestamp_ms(dt):
  """Convert datetime.datetime object into int milliseconds from epoch """
  return int(dt.timestamp() * 1000.0)
