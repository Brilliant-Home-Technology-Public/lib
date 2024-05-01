from unittest import mock


class DummyClass:

  def dummy_method(self):
    pass


def dummy_func():
  pass


# The mock class doesn't properly recognize functions and methods in Cython-compiled modules
for func_type in (type(dummy_func), type(DummyClass.dummy_method)):
  if func_type not in mock.FunctionTypes:  # type: ignore[attr-defined]
    mock.FunctionTypes += (func_type,)  # type: ignore[attr-defined]
