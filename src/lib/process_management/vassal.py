from enum import IntEnum
import logging
import os

import gflags

from lib.queueing.intervaled_task import IntervaledTask


log = logging.getLogger(__name__)

FLAGS = gflags.FLAGS


class VassalMessage(IntEnum):
  SPAWNED = 1
  READY = 5
  LOYAL = 17
  VOLUNTARY_SHUTDOWN = 22
  HEARTBEAT = 26


class EmperorMessage(IntEnum):
  STOP = 0
  RELOAD = 1


class Vassal:

  def __init__(self,
               startable_object,
               emperor_fd,
               loop,
               request_stop_callback,
               enable_heartbeat=True,
  ):
    self.startable_object = startable_object
    self.emperor_fd = emperor_fd
    self.loop = loop
    self.request_stop_callback = request_stop_callback
    if enable_heartbeat:
      self.heartbeat_task = IntervaledTask(
          loop=self.loop,
          interval=10,
          task_func=self.heartbeat,
      )
    else:
      self.heartbeat_task = None
    self._listening_to_emperor = False

  async def start(self):
    self._send_message_to_emperor(VassalMessage.SPAWNED)
    self.loop.add_reader(self.emperor_fd, self._handle_message_from_emperor)
    self._listening_to_emperor = True
    await self.startable_object.start()
    self._send_message_to_emperor(VassalMessage.READY)
    self._send_message_to_emperor(VassalMessage.LOYAL)
    if self.heartbeat_task:
      self.heartbeat_task.start()

  async def shutdown(self):
    self._maybe_stop_listening_to_emperor()
    await self.startable_object.shutdown()

  async def heartbeat(self):
    self._send_message_to_emperor(VassalMessage.HEARTBEAT)

  def _send_message_to_emperor(self, message):
    message_bytes = bytes([message])
    # Note: There's a possibility this blocks if the file isn't available for writing, but in
    # practice it is unlikely
    os.write(self.emperor_fd, message_bytes)

  def _handle_message_from_emperor(self):
    # Emperor protocol messages are only one byte
    data = os.read(self.emperor_fd, 1)
    if not data:
      # Empty read -> peer closed the socket
      if self._listening_to_emperor:
        log.warning("Emperor closed the management socket! Shutting down.")
        self._initiate_shutdown()
      return

    message = ord(data)
    if message == EmperorMessage.STOP:
      # Stop
      log.info("The Emperor commands you to STOP")
      self._initiate_shutdown()
    elif message == EmperorMessage.RELOAD:
      log.info("The Emperor commands you to RELOAD")
      # Reload not supported - voluntarily shutdown instead and let the Emperor respawn this vassal
      self._send_message_to_emperor(VassalMessage.VOLUNTARY_SHUTDOWN)
    else:
      # Unexpected command
      log.warning("Unexpected command from Emperor: %s", message)

  def _initiate_shutdown(self):
    # Stop listening for more commands from the Emperor before interrupting the loop so
    # we don't have to deal with more messages during the shutdown process
    self._maybe_stop_listening_to_emperor()
    # Interrupting the loop will trigger the runner to call our shutdown() method
    self.request_stop_callback()

  def _maybe_stop_listening_to_emperor(self):
    if not self._listening_to_emperor:
      return
    if self.heartbeat_task:
      self.heartbeat_task.shutdown()
    self.loop.remove_reader(self.emperor_fd)
    self._listening_to_emperor = False
