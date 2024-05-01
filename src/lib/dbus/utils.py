import concurrent.futures
import logging
import threading
import time


try:
  from gi.repository import GLib
  import pydbus
except ImportError:
  GLib = None
  pydbus = None


log = logging.getLogger(__name__)


def get_system_bus():
  if not pydbus:
    log.warning("dbus is not available on this platform.")
    return None

  return pydbus.SystemBus()


def get_object_with_introspection_data(bus, bus_name, object_path, introspection_data):
  '''Get a D-Bus object using known introspection data

  Some libraries that expose objects via D-Bus don't support the Introspect() call, which pydbus
  invokes in its normal proxy object creation flow.
  '''
  iface_cls = pydbus.proxy.CompositeInterface(introspection_data)
  return iface_cls(bus, bus_name, object_path)


class InterruptibleRepeatingThreadedTask:
  def __init__(self, task_func, interval_ms=0, daemon=True):
    self._active = False
    self._task_func = task_func
    self._interval_ms = interval_ms
    self._sleep_quantum_ms = min(500., float(self._interval_ms) / 10)
    self._daemon = daemon
    self._thread = None

  def start(self):
    self._active = True
    self._thread = threading.Thread(target=self._run_task)
    self._thread.daemon = self._daemon
    self._thread.start()

  def _run_task(self):
    while self._active:
      if self._active:
        try:
          self._task_func()
        except KeyboardInterrupt:
          break
        except Exception:
          log.exception("Error running task in thread")

      if self._interval_ms:
        start_wait = time.time()
        # Periodically check to see if we've been shut down
        while ((time.time() - start_wait) * 1000) < self._interval_ms and self._active:
          time.sleep(self._sleep_quantum_ms / 1000)

  def shutdown(self, join=True):
    self._active = False
    if join and self._thread and self._thread.is_alive():
      log.debug("Waiting for task %s", self._task_func)
      self._thread.join()
      self._thread = None


class _DummyLoop:

  def __init__(self):
    self._fut = concurrent.futures.Future()

  def run(self):
    # Blocks until a result is set by quit()
    self._fut.result()

  def quit(self):
    self._fut.set_result(None)


class GLibRunLoop:

  def __init__(self):
    self._loop = None
    self._run_loop_thread = InterruptibleRepeatingThreadedTask(task_func=self._run_loop)

  def start(self):
    self._run_loop_thread.start()

  def _run_loop(self):
    if not self._loop:
      if GLib:
        self._loop = GLib.MainLoop()
      else:
        log.warning("GLib is not available; using DummyLoop implementation.")
        self._loop = _DummyLoop()

    log.debug("Running GLib loop")
    self._loop.run()

  def shutdown(self):
    # The shutdown dance is unfortunately slightly complicated. Mark the background thread for
    # shutdown so it doesn't re-enter MainLoop.run() again right after it's interrupted.
    self._run_loop_thread.shutdown(join=False)
    # Now force MainLoop.run() to return
    if self._loop:
      self._loop.quit()

    # Finally, we can join() on the background thread to make sure it exited
    self._run_loop_thread.shutdown(join=True)
    log.debug("GLib run loop shutdown complete!")
