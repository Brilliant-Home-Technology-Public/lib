import asyncio


class IterableQueue(asyncio.Queue):

  def __init__(self, loop=None, maxsize=0):  # loop parameter retained for compatibility
    super().__init__(maxsize=maxsize)
    self._active = True

  def start(self):
    self._active = True

  def shutdown(self, drop_current_items=False):
    self._active = False
    # self._getters is a deque of Futures waiting to consume items from the queue
    while self._getters:
      waiter = self._getters.popleft()
      if not waiter.done():
        waiter.cancel()

    if drop_current_items:
      while not self.empty():
        self.get_nowait()
        self.task_done()

  def active(self):
    return self._active

  async def put(self, item):
    if not self._active:
      raise asyncio.InvalidStateError("Queue has been shut down")

    return await super().put(item)

  def put_nowait(self, item):
    if not self._active:
      raise asyncio.InvalidStateError("Queue has been shut down")

    return super().put_nowait(item)

  async def get(self):
    if not self._active:
      return self.get_nowait()

    return await super().get()

  def get_nowait(self):
    try:
      return super().get_nowait()
    except asyncio.QueueEmpty as e:
      if not self._active:
        raise asyncio.InvalidStateError("Queue has been shut down") from e
      raise

  def __aiter__(self):
    return self

  async def __anext__(self):
    try:
      return await self.get()
    except (asyncio.InvalidStateError, asyncio.CancelledError) as e:
      raise StopAsyncIteration from e
