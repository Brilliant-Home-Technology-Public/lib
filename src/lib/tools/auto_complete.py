from abc import abstractmethod
from functools import cached_property
import typing


# GNU readline expected to be installed on developer machines running python
READLINE_IMPORTED = False

# GNU readline must be installed for the readline package and auto-complete to work.
# if we can't import readline, this module will not error but will do nothing
try:
  import readline
  READLINE_IMPORTED = True
except ImportError:
  pass


class CommandLineAutoCompleter:
  """
  This class gives command and argument autocompletion to selected commands!

  Add this to your command line tool:
      1. Define your completion class with this as a super class
      (e.g. class YourCompleter(auto_complete.CommandLineAutoCompleter))
      2. Override abstract methods
  """

  def __init__(
      self,
  ):
    if READLINE_IMPORTED:
      # https://github.com/python/cpython/issues/112510
      readline_doc = getattr(readline, '__doc__', '')
      if readline_doc is not None and 'libedit' in readline_doc:
        readline.parse_and_bind('bind ^I rl_complete')
      else:
        readline.parse_and_bind('tab: complete')
      readline.set_completer(self._complete)
      # readline pastes completion options after delimiter symbols such as ":"
      readline.set_completer_delims(" ")

  # includes all commands, if no complete function, map to None
  @abstractmethod
  @cached_property
  def _all_commands(self) -> typing.Dict[
      str,
      typing.Optional[typing.Callable[[typing.List[str]], typing.List[str]]]
  ]:
    pass

  # https://docs.python.org/3/library/readline.html#readline.set_completer
  def _complete(self, text: str, state: int) -> typing.Optional[str]:
    if READLINE_IMPORTED:
      # we need the whole line rather than just the last word
      text = readline.get_line_buffer()
    args = text.split(" ")
    if not text.strip():
      return None
    options = None
    if len(args) == 1:
      options = self._all_commands
    elif self._all_commands[args[0]]:
      options = self._all_commands[args[0]](args)  # type: ignore
    if options:
      return [option for option in options if option.startswith(args[-1])][state]
    return None
