import asyncio
import functools
import sys
from unittest import mock

from lib.test_helpers import async_mock_monkeypatch
from lib.test_helpers.synchronous import PatchingTestCase


# compatibility check for 3.5.2 __aiter__ protocol change
# https://docs.python.org/3/reference/datamodel.html#async-iterators
if sys.version_info < (3, 5, 2):
  def aiter_compat(func):
    @functools.wraps(func)
    async def wrapper(self):
      return func(self)
    return wrapper
else:
  def aiter_compat(func):
    return func

if sys.version_info < (3, 7):
  def all_tasks(loop=None):
    return asyncio.Task.all_tasks(loop=loop)
else:
  def all_tasks(loop=None):
    return asyncio.all_tasks(loop=loop)


def async_test(f):
  '''aysnc_test is a decorator that can be used to run an asynchronous test case on the main event
  loop. The test class must either inherit from AsyncBaseTestCase or define self.event_loop.

  Usage:
    class OlafsTestCase(lib.test_helpers.async_helpers.AsyncBaseTestCase):
      ...
      @lib.test_helpers.async_helpers.async_test
      async def test_should_effectively_contribute_to_testing_my_module(self):
        <async with, await, etc.>
      ...
  '''

  def decorated(self, *args, **kwargs):
    self.event_loop.run_until_complete(f(self, *args, **kwargs))
  return decorated


class AsyncIterableMock(mock.Mock):

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.results = []
    self._pause_future = None

  def pause(self, loop):
    self._pause_future = asyncio.Future(loop=loop)

  def unpause(self):
    self._pause_future.set_result(None)

  @aiter_compat
  def __aiter__(self):
    return self

  async def __anext__(self):
    if self._pause_future:
      await self._pause_future

    if not self.results:
      raise StopAsyncIteration

    item = self.results.pop(0)
    if isinstance(item, Exception):
      raise item
    return item


class AsyncContextManagerMock(mock.Mock):

  def __init__(self, *args, aenter_return=None, **kwargs):
    super().__init__(*args, **kwargs)

    self.aenter_return = aenter_return

  async def __aenter__(self):
    return self.aenter_return if self.aenter_return else self

  async def __aexit__(self, *args, **kwargs):
    pass


class AsyncBaseTestCase(PatchingTestCase):

  FORCE_LEGACY_ASYNC_MOCK_BEHAVIOR = True

  _unset = object()

  def setUp(self):
    super().setUp()
    self.event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(self.event_loop)
    self.async_cleanup_tasks = []
    # Workaround for forward compatibility with async mocking in Python 3.8+
    async_mock_monkeypatch.set_behavior(use_legacy=self.FORCE_LEGACY_ASYNC_MOCK_BEHAVIOR)
    self.addCleanup(async_mock_monkeypatch.restore_default_behavior)

  def tearDown(self):
    for cleanup in self.async_cleanup_tasks:
      self.event_loop.run_until_complete(cleanup())

    self.event_loop.close()
    super().tearDown()

  def _future(self, value=_unset, exception=None):
    fut = asyncio.Future(loop=self.event_loop)
    if exception:
      fut.set_exception(exception)
    elif value is not self._unset:
      fut.set_result(value)
    return fut

  def _coro(self, mock_coroutine):
    async def _wrapper(*args, **kwargs):
      return await mock_coroutine(*args, **kwargs)
    return _wrapper

  def add_async_cleanup_task(self, callable_to_cleanup):
    self.async_cleanup_tasks.append(callable_to_cleanup)


class AsyncMock(mock.Mock):

  def __call__(self, *args, **kwargs):
    sup = super()

    async def coro():
      return sup.__call__(*args, **kwargs)
    return coro()

  def __await__(self):
    return self().__await__()
