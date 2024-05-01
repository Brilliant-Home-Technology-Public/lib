import threading
from unittest import mock


_ASYNC_MOCK_LEGACY_BEHAVIOR_DEFAULT = True

_mock_behavior = threading.local()
_mock_behavior._force_legacy = True


def set_behavior(use_legacy):
  _mock_behavior._force_legacy = use_legacy


def restore_default_behavior():
  _mock_behavior._force_legacy = _ASYNC_MOCK_LEGACY_BEHAVIOR_DEFAULT


if hasattr(mock, 'AsyncMockMixin'):

  async_execute_mock_call = mock.AsyncMockMixin._execute_mock_call

  def _execute_mock_monkeypatch(self, *args, **kwargs):
    if _mock_behavior._force_legacy:
      return mock.CallableMixin._execute_mock_call(self, *args, **kwargs)
    return async_execute_mock_call(self, *args, **kwargs)

  mock.AsyncMockMixin._execute_mock_call = _execute_mock_monkeypatch  # type: ignore[method-assign]
