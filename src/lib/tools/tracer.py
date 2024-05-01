import asyncio
import logging
import os
import pickle
import sys
import time

import gflags


gflags.DEFINE_string("trace_dir", "/tmp/", "Directory to write traces to")

log = logging.getLogger(__name__)


class Trace:

  def __init__(self, attributes):
    self.attributes = attributes
    self.timeline = []

  def add_attributes(self, attributes):
    self.attributes.update(attributes)

  def mark_timeline(self, key):
    self.timeline.append(Event(key, time.time()))

  def __str__(self):
    return '\n'.join(map(str, self.timeline))


class Event:

  def __init__(self, key, timestamp):
    self.key = key
    self.timestamp = timestamp

  def __str__(self):
    return "{}\t{}".format(int(self.timestamp * 1000), self.key)


_traces_in_progress = {}
_traces_completed = []
_global_trace = Trace({"is_global": True})


def start_trace(attributes):
  if not gflags.FLAGS.enable_tracing:
    return
  task_id = _current_task_id()
  if task_id in _traces_in_progress:
    raise Exception(
        "Trace for task %s already in progress. Only one trace per task allowed" % (task_id)
    )
  trace = Trace(attributes)
  trace.mark_timeline("start_trace")
  _traces_in_progress[task_id] = trace


def add_attributes(attributes):
  if not gflags.FLAGS.enable_tracing:
    return
  task_id = _current_task_id()
  if task_id not in _traces_in_progress:
    raise Exception("No trace in progress for task %s" % (task_id))
  _traces_in_progress[task_id].add_attributes(attributes)


def mark_timeline(key):
  if not gflags.FLAGS.enable_tracing:
    return
  task_id = _current_task_id()
  if task_id not in _traces_in_progress:
    raise Exception("No trace in progress for task %s" % (task_id))
  _traces_in_progress[task_id].mark_timeline(key)
  _global_trace.mark_timeline(key)


def mark_global_timeline(key):
  if not gflags.FLAGS.enable_tracing:
    return
  _global_trace.mark_timeline(process_name() + "," + key)


def end_trace():
  if not gflags.FLAGS.enable_tracing:
    return
  task_id = _current_task_id()
  if task_id not in _traces_in_progress:
    raise Exception("No trace in progress for task %s" % (task_id))
  trace = _traces_in_progress[task_id]
  trace.mark_timeline("end_trace")
  del _traces_in_progress[task_id]
  _traces_completed.append(trace)


def write_traces(process_name):
  write_global_trace(process_name)
  _write_traces("trace_" + process_name, _traces_completed)


def write_global_trace(process_name):
  _write_traces("global_trace_" + process_name, [_global_trace])


def _write_traces(process_name, traces_to_write):
  if not gflags.FLAGS.enable_tracing:
    return
  trace_file = None
  try:
    if not os.path.exists(gflags.FLAGS.trace_dir):
      os.mkdir(gflags.FLAGS.trace_dir)
    file_name = gflags.FLAGS.trace_dir + process_name
    with open(file_name, 'wb') as trace_file:
      pickle.dump(traces_to_write, trace_file)
  except Exception as e:
    log.error("Error writing traces: %s", str(e))
  finally:
    if trace_file is not None:
      trace_file.close()


def reset_traces():
  _traces_in_progress.clear()
  del _traces_completed[:]
  reset_global_trace()


def reset_global_trace():
  _global_trace.attributes = {"is_global": True}
  _global_trace.timeline = []


def _current_task_id():
  curr_task = asyncio.current_task()
  return id(curr_task)


def process_name():
  file_name = sys.argv[0].rsplit('/', maxsplit=1)[-1]
  file_name = file_name.replace(".py", "")
  parts = file_name.split("_")
  cap_parts = [p[0].upper() + p[1:] for p in parts]
  return "".join(cap_parts)
