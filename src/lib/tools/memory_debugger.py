"""
This utility class is intended to be used with [`pyrasite`](https://github.com/lmacken/pyrasite) to
debug memory leaks.

Instructions for installing `pyrasite` and using this tool on an Ubuntu instance:

- Connect to the Ubuntu host that is running the Python process to debug.
- sudo emacs /proc/sys/kernel/yama/ptrace_scope
  - Change from 1 to 0

- Install GDB:
  sudo apt-get install gdb

- Fixup some python links:

  sudo rm /usr/lib/python3.5/_sysconfigdata.py
  sudo ln -fs /usr/lib/python3.5/plat-x86_64-linux-gnu/_sysconfigdata_m.py /usr/lib/python3.5/
  sudo mv /usr/lib/python3.5/_sysconfigdata_m.py /usr/lib/python3.5/_sysconfigdata.py

- Install `pyrasite`:
  python3 -m venv pyrasite
  ./pyrasite/bin/pip install wheel
  ./pyrasite/bin/pip install pyrasite

- Make sure the pyrasite directory is owned by the same user who is running the process to debug:
  sudo chown -R <user>:<user> pyrasite

- Copy this file into a file on the machine <local_memory_debugger.py>.

- Discover the PID and connect to the process:
  sudo ps aux | grep <process_name_to_debug>
  sudo -u <user> ./pyrasite/bin/pyrasite-shell <pid_from_above>

- Once connected, load, start, and start comparing snapshots.

>>> exec(open("<path_to_local_memory_debugger.py>").read())
>>> md = MemDebugger()
>>> md.start()
>>> md.snap_and_compare()

- For example:

ubuntu@crossbar001:~$ sudo -u crossbar ./pyrasite/bin/pyrasite-shell 26071
Pyrasite Shell 2.0
Connected to 'crossbar-worker [crossbar.worker.router.RouterWorkerSession]'
Python 3.5.2 (default, Sep 14 2017, 22:51:06)
[GCC 5.4.0 20160609] on linux
Type "help", "copyright", "credits" or "license" for more information.
(DistantInteractiveConsole)

>>> exec(open("/home/ubuntu/pyrasite/memory_debugger.py").read())
>>> md = MemDebugger()
>>> md.start(10)
>>> md.snap_and_compare()
/usr/lib/python3.5/json/encoder.py:256: size=9994 B (+3658 B), count=133 (+34), average=75 B
/opt/crossbar/lib/python3.5/site-packages/autobahn/util.py:408: size=0 B (-2560 B), count=0 (-1)
/opt/crossbar/lib/python3.5/site-packages/crossbar/_logging.py:308: size=1531 B (+1531 B), count=1 (+1), average=1531 B
/usr/lib/python3.5/string.py:245: size=1184 B (+1184 B), count=2 (+2), average=592 B
/opt/crossbar/lib/python3.5/site-packages/autobahn/websocket/protocol.py:1828: size=887 B (+887 B), count=1 (+1), average=887 B
/opt/crossbar/lib/python3.5/site-packages/autobahn/wamp/serializer.py:225: size=883 B (+883 B), count=1 (+1), average=883 B
/usr/lib/python3.5/json/scanner.py:38: size=30.1 KiB (-832 B), count=37 (-1), average=832 B
/usr/lib/python3.5/string.py:265: size=805 B (+805 B), count=2 (+2), average=402 B
/opt/crossbar/lib/python3.5/site-packages/crossbar/_logging.py:101: size=741 B (+741 B), count=1 (+1), average=741 B
<console>:1: size=10.4 KiB (+664 B), count=86 (+2), average=124 B

>>> md.stop()
>>> exit()
"""

import gc
import linecache
import os
import tracemalloc


class MemDebugger():
  def __init__(self):
    self.snapshots = []

  def _take_snapshot(self):
    gc.collect()
    self.snapshots.append(tracemalloc.take_snapshot())

  def start(self, num_tracebacks=1):
    tracemalloc.start(num_tracebacks)
    self._take_snapshot()

  def display_top(self, snapshot_index=-1, group_by='lineno', limit=10):
    top_stats = self.snapshots[snapshot_index].statistics(group_by)

    print("Top %s lines" % limit)
    for index, stat in enumerate(top_stats[:limit], 1):
      frame = stat.traceback[0]
      # replace "/path/to/module/file.py" with "module/file.py"
      filename = os.sep.join(frame.filename.split(os.sep)[-2:])
      print("#%s: %s:%s: %.1f KiB"
            % (index, filename, frame.lineno, stat.size / 1024))
      line = linecache.getline(frame.filename, frame.lineno).strip()
      if line:
        print('    %s' % line)

    other = top_stats[limit:]
    if other:
      size = sum(stat.size for stat in other)
      print("%s other: %.1f KiB" % (len(other), size / 1024))
    total = sum(stat.size for stat in top_stats)
    print("Total allocated size: %.1f KiB" % (total / 1024))

  def compare(self, group_by="lineno", compare_to=-2, limit=10, print_traceback=False):
    """
    group_by: lineno, filename, traceback.
    compare_to: The index of the snapshot to which the most recent snapshot will be compared.
    limit: The number of stats to print out from the snapshot comparision.
    """
    stats = self.snapshots[-1].compare_to(self.snapshots[compare_to], group_by)
    for stat in stats[:limit]:
      print(stat)
      if print_traceback:
        for line in stat.traceback.format():
          print(line)

  def snap_and_compare(self, **kwargs):
    self._take_snapshot()
    self.compare(**kwargs)

  def stop(self):
    tracemalloc.stop()


def get_objects_of_type(type_to_find):
  def safe_typecheck(obj):
    # isinstance() fails on certain objects tracked by the garbage collector
    try:
      return isinstance(obj, type_to_find)
    except Exception:
      return False

  return [o for o in gc.get_objects() if safe_typecheck(o)]
