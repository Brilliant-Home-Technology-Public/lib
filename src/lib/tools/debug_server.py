import asyncio
import inspect
import logging

from lib import connection_manager


log = logging.getLogger(__name__)


class DebugCommand:

  def __init__(self, command_name, handler_func, help_text=""):
    self.command_name = command_name
    self.handler_func = handler_func
    self.help_text = help_text


class DebugFlag:

  def __init__(self, flag_name, help_text=""):
    self.flag_name = flag_name.upper()
    self.help_text = help_text


class DebugServer:

  def __init__(self, loop, commands, flags=None, include_help=True, listen_port=None):
    self._loop = loop
    self._listen_address = "tcp://localhost:{}".format(listen_port) if listen_port else None
    self._connection_manager = connection_manager.PeerConnectionManager(
        loop=loop,
        new_peer_async_callback=self._handle_new_peer,
        connection_params=None,
    )
    self._flag_map = {}
    self._active_flags = set()
    if flags:
      commands.extend([
          DebugCommand(
              command_name="flags",
              handler_func=self._manage_flags,
              help_text="Set/enable flags to control debugger behavior",
          ),
      ])
      self._flag_map = {f.flag_name: f for f in flags}
    self._command_map = {c.command_name: c for c in commands}
    if include_help:
      self._command_map['help'] = DebugCommand(
          command_name="help",
          handler_func=self._format_help,
          help_text="Get help for a command, or list all commands with help info",
      )

  async def start(self):
    if self._listen_address:
      await self._connection_manager.start_server(self._listen_address)

  async def shutdown(self):
    await self._connection_manager.shutdown()

  async def _handle_new_peer(self, peer):
    self._loop.create_task(self._handle_commands(peer))

  async def _handle_commands(self, peer):
    async for message in peer.incoming_message_iterator():
      args = message.split()
      if not args:
        peer.enqueue_message("Error: No command received")
        continue

      if args[0] not in self._command_map:
        peer.enqueue_message("Error: Unknown command '{}'".format(args[0]))
        continue

      handler_func = self._command_map[args[0]].handler_func
      try:
        result = await handler_func(*args[1:])
        peer.enqueue_message(str(result))
      except asyncio.CancelledError:  # pylint: disable=try-except-raise
        raise
      except Exception as e:
        log.warning("Exception processing debug command %s", args[0], exc_info=True)
        peer.enqueue_message("Error: {!r}".format(e))

  def _format_args(self, handler_func):
    results = []
    for param in inspect.signature(handler_func).parameters.values():
      if param.default != inspect.Parameter.empty:
        results.append(f'[{param.name}={param.default!r}]')
      else:
        results.append(f'<{param.name}>')
    return " " + " ".join(results)

  async def _format_help(self, name=None):
    if name:
      if name in self._command_map:
        command = self._command_map[name]
        text = "\n".join((
            command.command_name + self._format_args(command.handler_func),
            "\t" + command.help_text,
        ))
      elif name.upper() in self._flag_map:
        text = self._flag_map[name.upper()].help_text
      else:
        add_flag = " or flag" if self._flag_map else ""
        text = f"Unrecognized command{add_flag}: '{name}'"
    else:
      text = "\n".join(
          "{}\t{}".format(c.command_name, c.help_text)
          for c in sorted(self._command_map.values(), key=lambda c: c.command_name)
      )
      if self._flag_map:
        flag_help = "\n".join(
            "Flag: {}\t{}".format(f.flag_name, f.help_text)
            for f in sorted(self._flag_map.values(), key=lambda f: f.flag_name)
        )
        text = "\n".join((text, flag_help))
    return text

  async def _manage_flags(self, *flag_ops):
    flags_to_operate = []
    for flag_op in flag_ops:
      op, canonical_name = flag_op[0], flag_op[1:].upper()
      if op not in ("+", "-"):
        raise Exception("Invalid operation: {}".format(op))

      if canonical_name not in self._flag_map:
        raise KeyError(f'Unknown flag: {canonical_name}')

      flags_to_operate.append((op, self._flag_map[canonical_name]))

    results = []
    if flags_to_operate:
      for op, flag in flags_to_operate:
        if op == "+":
          self._active_flags.add(flag.flag_name)
        else:
          self._active_flags.discard(flag.flag_name)
        results.append(op + flag.flag_name)
    else:
      for flag in sorted(self._flag_map.values(), key=lambda f: f.flag_name):
        set_value = "+" if self.is_set(flag.flag_name) else "-"
        results.append(set_value + flag.flag_name)

    return " ".join(results)

  def is_set(self, flag_name):
    return flag_name.upper() in self._active_flags
