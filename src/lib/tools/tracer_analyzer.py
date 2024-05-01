import operator
import pickle
import sys

import gflags


gflags.DEFINE_string("file_name", None, "")
gflags.DEFINE_string("filter_handle_request", None, "")
gflags.MarkFlagAsRequired("file_name")

FLAGS = gflags.FLAGS


def analyze_traces():
  FLAGS(sys.argv)
  with open(FLAGS.file_name, 'rb') as trace_file:
    traces = pickle.load(trace_file)
  if FLAGS.filter_handle_request:
    traces = filter_handle_request(traces, FLAGS.filter_handle_request)
  elapsed_times_by_key = {}
  for trace in traces:
    print("Attributes: ", trace.attributes)
    print("Events:")
    start_time = trace.timeline[0].timestamp
    for event in trace.timeline:
      elapsed_time = (event.timestamp - start_time) * 1000
      print("{:10.6f}".format(event.timestamp) + " " + event.key)
      if event.key in elapsed_times_by_key:
        elapsed_times_by_key[event.key].append(elapsed_time)
      else:
        elapsed_times_by_key[event.key] = [elapsed_time]
    print("**************")
  if len(traces) > 1:
    # Now print the average elapsed times for each key
    print("**************")
    print("Averages:")
    for key, elasped_times in elapsed_times_by_key.items():
      average = sum(elasped_times) / float(len(elasped_times))
      elapsed_times_by_key[key] = average
    sorted_elapsed_times = sorted(elapsed_times_by_key.items(), key=operator.itemgetter(1))
    for event in sorted_elapsed_times:
      print("{:10.4f}".format(event[1]) + " ms   " + event[0])


def filter_handle_request(traces, command):
  filtered_traces = [trace for trace in traces if
      trace.attributes["handle_request"].command == command]
  return filtered_traces


if __name__ == '__main__':
  analyze_traces()
