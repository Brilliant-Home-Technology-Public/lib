import asyncio


class FutureValue:

  def __init__(self, loop):
    self._loop = loop
    self._future = asyncio.Future(loop=self._loop)
    self._callbacks = set()

  def __await__(self):
    return self._future.__await__()

  def clear(self):
    if self._future.done():
      self._future = asyncio.Future(loop=self._loop)
      for callback in self._callbacks:
        self._future.add_done_callback(callback)

  def set_value(self, value):
    self.clear()
    self._future.set_result(value)

  def has_value(self):
    return self._future.done()

  def cancelled(self):
    return self._future.cancelled()

  def value(self):
    return self._future.result()

  def set_exception(self, exception):
    self._future.set_exception(exception)

  def cancel(self):
    self._future.cancel()

  def add_done_callback(self, callback):
    self._callbacks.add(callback)
    self._future.add_done_callback(callback)

  def remove_done_callback(self, callback):
    # Remove this from our list of callbacks, KeyError raised in future.remove_done_callback
    self._callbacks.discard(callback)
    self._future.remove_done_callback(callback)
