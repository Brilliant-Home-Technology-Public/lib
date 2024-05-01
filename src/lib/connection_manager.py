import asyncio
import collections
import itertools
import logging
import os
import random
import socket
import typing

import autobahn.exception

import lib.exceptions
from lib.networking import authentication
from lib.networking import interface
from lib.networking import json_rpc_message_peer
from lib.networking import newline_delimited_message_peer
from lib.networking import process_local_peer
from lib.networking import utils
from lib.networking import websocket_peer
import lib.time


log = logging.getLogger(__name__)


class OutboundConnectionHandle:

  JITTER_RATIO = 0.2
  MAX_BACKOFF_SECONDS = 180
  MAX_CONNECTION_ATTEMPTS_PER_MINUTES = {
      # NOTE: Larger minute ranges should have larger max connection attempts.
      1: 2,  # max 2 connections per 1 minute
      5: 5,
      10: 7,
  }
  MAX_CONNECTION_ATTEMPTS_TO_TRACK = max(MAX_CONNECTION_ATTEMPTS_PER_MINUTES.values())

  def __init__(self, remote_address, expected_peer_parameters):
    self.remote_address = remote_address
    self.expected_peer_parameters = expected_peer_parameters
    self._connect_task = None
    self._ordered_most_recent_connection_attempts_ms = \
        collections.deque([], self.MAX_CONNECTION_ATTEMPTS_TO_TRACK)

  async def shutdown(self):
    if self.is_connected():
      peer = self._connect_task.result()
      try:
        await peer.shutdown()
      except Exception as e:
        log.error("Failed to close connection to %s: %r",
                  self.remote_address, e)
    elif self._connect_task:
      self._connect_task.cancel()

    self._connect_task = None

  def is_connected(self):
    connected = (
        self._connect_task and
        self._connect_task.done() and
        not self._connect_task.cancelled() and
        not self._connect_task.exception()
    )
    return connected

  def is_active(self):
    return bool(self._connect_task)

  def replace_pending_connection(self, connect_task):
    if self._connect_task and not self._connect_task.done():
      self._connect_task.cancel()

    self._connect_task = connect_task

  async def backoff_before_attempting_connection(self, attempt_number, is_reconnect):
    # Hack: Task.cancel() is not reliable due to changes in Python 3.10 which cause
    # asyncio.wait_for() to swallow the CancelledException if the future it's awaiting is already
    # done: https://github.com/python/cpython/pull/21894
    # The unfortunate consequence for us is that a connect task which had been replaced may yet
    # continue to run.
    connecting_task = asyncio.current_task()
    if connecting_task is not self._connect_task:
      log.warning("Task %s is no longer the current connect task; self-cancelling!",
                  connecting_task)
      # Self-cancel and exit the task
      connecting_task.cancel()
      await asyncio.sleep(0)

    backoff_seconds = 5 * attempt_number
    if is_reconnect and attempt_number == 0:
      log.info('Backing off after failed connection to %s', self.remote_address)
      backoff_seconds = 10
    now_ms = lib.time.get_current_time_ms()
    past_connection_attempt_buckets = collections.defaultdict(int)
    for past_attempt_ms in self._ordered_most_recent_connection_attempts_ms:
      past_attempt_age_minutes = (now_ms - past_attempt_ms) / 1000 / 60
      for age_minutes_bucket, max_attempts in self.MAX_CONNECTION_ATTEMPTS_PER_MINUTES.items():
        if past_attempt_age_minutes < age_minutes_bucket:
          past_connection_attempt_buckets[age_minutes_bucket] += 1
          if past_connection_attempt_buckets[age_minutes_bucket] == max_attempts:
            # Bucket is filled. Backoff until bucket capacity frees up.
            # Assuming self._ordered_most_recent_connection_attempts_ms is ordered most to least
            # recent, past_attempt_age_minutes should correspond to the Nth most recent attempt,
            # where N is max_attempts (the bucket capacity). So we need to wait till that attempt
            # ages out of the bucket before we can make another connection attempt.
            bucket_backoff_seconds = (age_minutes_bucket - past_attempt_age_minutes) * 60
            backoff_seconds = max(backoff_seconds, bucket_backoff_seconds)
    if not backoff_seconds:
      return
    # NOTE: The MAX_BACKOFF_SECONDS constraint supercedes MAX_CONNECTION_ATTEMPTS_PER_MINUTES.
    # Because of this and jitter, MAX_CONNECTION_ATTEMPTS_PER_MINUTES is NOT a hard constraint.
    backoff_seconds = min(backoff_seconds, self.MAX_BACKOFF_SECONDS)
    backoff_seconds = backoff_seconds * (1 + random.uniform(-self.JITTER_RATIO, self.JITTER_RATIO))
    await asyncio.sleep(backoff_seconds)
    # Order self._ordered_most_recent_connection_attempts_ms most to least recent.
    self._ordered_most_recent_connection_attempts_ms.appendleft(lib.time.get_current_time_ms())

  def __await__(self):
    if not self.is_active():
      raise asyncio.CancelledError("This connection has been shut down")

    return self._connect_task.__await__()


class ParameterMismatchError(Exception):

  def __init__(self, parameter_name, expected_value, actual_value):
    message = "{!r} expected {!r}, got {!r}".format(
        parameter_name,
        expected_value,
        actual_value,
    )
    super().__init__(message)


class PeerConnectionManager:

  DEFAULT_MAX_CONCURRENT_PEER_STARTS = 1024

  _authenticator: typing.Optional[authentication.Authenticator]

  def __init__(self,
               loop,
               new_peer_async_callback,
               connection_params,
               max_concurrent_peer_starts=None,
               peer_socket_timeout=None,
               module_overrides=None,
               authentication_policy=None,
               supported_api_versions=None,
               cert_file_directory=None,
               reuse_port=None):
    """
    module_overrides: optional peer modules to override the default ones
    """
    self.loop = loop
    self.new_peer_async_callback = new_peer_async_callback
    if authentication_policy:
      self._authenticator = authentication.Authenticator(
          authentication_policy=authentication_policy,
      )
    else:
      self._authenticator = None
    self._peers = set()
    self._servers = []
    self._connection_handle_by_remote_addr = {}
    self._shutdown_requested = False
    self._connection_params = connection_params
    self._peer_socket_timeout = peer_socket_timeout
    self._supported_api_versions = supported_api_versions
    self._cert_file_directory = cert_file_directory
    self._peer_modules = {
        utils.MessagingProtocol.WEB_SOCKET: websocket_peer,
        utils.MessagingProtocol.NEWLINE_DELIMITED_MESSAGE: newline_delimited_message_peer,
        utils.MessagingProtocol.PROCESS_LOCAL: process_local_peer,
        utils.MessagingProtocol.JSON_RPC: json_rpc_message_peer,
    }
    self._reuse_port = reuse_port
    if module_overrides:
      self._peer_modules.update(module_overrides)
    self._start_concurrency_semaphore = asyncio.BoundedSemaphore(
        value=max_concurrent_peer_starts or self.DEFAULT_MAX_CONCURRENT_PEER_STARTS,
    )

  async def start_server(self, listen_address):
    self._shutdown_requested = False
    peer_module = None
    messaging_protocol, *ign = utils.parse_address(listen_address)
    peer_module = self._peer_modules[messaging_protocol]
    server = await peer_module.start_server(
        listen_address=listen_address,
        new_peer_async_callback=self._add_new_peer,
        loop=self.loop,
        params=self._connection_params,
        timeout=self._peer_socket_timeout,
        authenticator=self._authenticator,
        supported_api_versions=self._supported_api_versions,
        reuse_port=self._reuse_port,
    )
    self._servers.append(server)

  def open_connection(self, remote_address, expected_peer_parameters=None):
    self._shutdown_requested = False
    connection_handle = self._connection_handle_by_remote_addr.get(remote_address)
    if not (connection_handle and connection_handle.is_active()):
      connection_handle = OutboundConnectionHandle(
          remote_address=remote_address,
          expected_peer_parameters=expected_peer_parameters,
      )
      self._connection_handle_by_remote_addr[remote_address] = connection_handle
      connect_task = self.loop.create_task(
          self._open_connection(
              outbound_connection_handle=connection_handle,
          )
      )
      connection_handle.replace_pending_connection(connect_task)

    return connection_handle

  def cancel_pending_connection(self, remote_address):
    handle = self._connection_handle_by_remote_addr.pop(remote_address, None)
    if handle:
      self.loop.create_task(handle.shutdown())

  async def _open_connection(self,
                             outbound_connection_handle,
                             is_reconnect=False):
    remote_address = outbound_connection_handle.remote_address
    expected_peer_parameters = outbound_connection_handle.expected_peer_parameters
    messaging_protocol, *ign = utils.parse_address(remote_address)
    peer_module = self._peer_modules[messaging_protocol]
    for attempt_number in itertools.count():
      await outbound_connection_handle.backoff_before_attempting_connection(
          attempt_number=attempt_number,
          is_reconnect=is_reconnect,
      )
      try:
        peer = await peer_module.open_connection(
            remote_address,
            loop=self.loop,
            params=self._connection_params,
            timeout=self._peer_socket_timeout,
            authenticator=self._authenticator,
            supported_api_versions=self._supported_api_versions,
            cert_file_directory=self._cert_file_directory,
        )
        await self._add_new_peer(peer, expected_peer_parameters=expected_peer_parameters)
        return peer
      except asyncio.CancelledError:  # pylint: disable=try-except-raise
        raise
      except Exception as err:
        # In the event of a socket error, log the error and retry connecting
        log.warning('Problem opening connection %s: %r', remote_address, err)

  async def shutdown(self):
    if self._shutdown_requested:
      return

    self._shutdown_requested = True

    servers = list(self._servers)
    connection_handles = list(self._connection_handle_by_remote_addr.values())
    peers = list(self._peers)

    self._servers.clear()
    self._connection_handle_by_remote_addr.clear()
    self._peers.clear()

    await asyncio.gather(*(self._shutdown_server(s) for s in servers))
    await asyncio.gather(
        *(handle.shutdown() for handle in connection_handles),
    )
    await asyncio.gather(*(peer.shutdown() for peer in peers))

  async def _shutdown_server(self, server):
    socket_path = None
    if (server.sockets and
        server.sockets[0].family == socket.AF_UNIX):
      socket_path = server.sockets[0].getsockname()

    server.close()
    await server.wait_closed()
    if socket_path:
      try:
        os.unlink(socket_path)
      except OSError:
        pass

  async def _add_new_peer(self, peer, *, expected_peer_parameters=None):
    peer.register_connection_closed_callback(self._peer_closed_callback)
    try:
      async with self._start_concurrency_semaphore:
        try:
          await peer.start()
        except interface.UnauthorizedError:
          log.warning("Peer %s [%s] failed to authenticate!",
                      id(peer),
                      peer.get_peer_common_name() or "<unknown>")
          return
        except asyncio.TimeoutError:
          log.warning("Peer %s [%s] timed out on start()",
                      id(peer),
                      peer.get_peer_common_name() or "<unknown>")
          return
        except OSError:
          log.warning("Peer %s [%s] lost connection before start completed",
                      id(peer),
                      peer.get_peer_common_name() or "<unknown>")
          # This happens when the peer loses its connection before the start is completed.
          return

        actual_parameters = peer.get_peer_connection_parameters() or {}
        for key, expected_value in (expected_peer_parameters or {}).items():
          actual_value = actual_parameters.get(key)
          if actual_value != expected_value:
            raise ParameterMismatchError(
                parameter_name=key,
                expected_value=expected_value,
                actual_value=actual_value,
            )

        self._peers.add(peer)
        await self.new_peer_async_callback(peer)
    except (asyncio.CancelledError, Exception) as e:
      peer_info = "{} [{}]".format(id(peer), peer.get_peer_common_name() or "<unknown>")
      if isinstance(e, asyncio.CancelledError):
        log.warning("Cancelled task to add new peer %s; discarding!", peer_info)
      elif isinstance(e, ParameterMismatchError):
        log.warning("Mismatch on peer %s: %s", peer_info, e)
      elif isinstance(e, asyncio.TimeoutError):
        log.warning("Timed out on adding new peer %s", peer_info)
      elif (
          isinstance(e, lib.exceptions.NoConnectionError) and
          isinstance(e.__cause__, autobahn.exception.Disconnected) and
          str(e.__cause__) == "Attempt to send on a closed protocol"
      ):
        log.warning("Failed to add new peer %s with exception %r %r", peer_info, e, e.__cause__)
      else:
        log.exception("Failed to add new peer %s!", peer_info)
      self._peers.discard(peer)
      await peer.shutdown()
      raise

  def _peer_closed_callback(self, peer, was_requested):
    if self._shutdown_requested:
      # Ignore spurious notifications when the service is shutting down
      return

    self._peers.discard(peer)
    if not was_requested:
      log.warning("Lost connection to peer %s [%s]",
                  id(peer),
                  peer.get_peer_common_name() or "<unknown>")
      self._maybe_reconnect(peer)
    else:
      log.info("Closed connection to %s [%s]",
               id(peer),
               peer.get_peer_common_name() or "<unknown>")

  def _maybe_reconnect(self, peer):
    if not peer.remote_address:
      # This was an inbound connection, so not our responsibility to re-establish
      return

    try:
      prior_handle = self._connection_handle_by_remote_addr[peer.remote_address]
    except KeyError:
      log.warning("Could not find connection for peer at %s", peer.remote_address)
      return

    log.info("Initiating reconnect attempt to %s", peer.remote_address)
    connect_task = self.loop.create_task(
        self._open_connection(
            outbound_connection_handle=prior_handle,
            is_reconnect=True,
        )
    )
    prior_handle.replace_pending_connection(connect_task)


def main():
  loop = asyncio.get_event_loop()

  async def _print_messages(peer):
    async for message in peer.incoming_message_iterator():
      log.info("message received: %r", message)

  async def _new_peer(peer):
    log.info("Accepted a connection for peer %s", id(peer))
    loop.create_task(_print_messages(peer))

  peer_manager = PeerConnectionManager(
      loop=loop,
      new_peer_async_callback=_new_peer,
      connection_params=None,
  )
  loop.run_until_complete(
      peer_manager.start_server(listen_address="tcp://:5455"),
  )
  try:
    loop.run_forever()
  except KeyboardInterrupt:
    log.info("Shutting down!")

  loop.run_until_complete(peer_manager.shutdown())
  loop.close()


if __name__ == "__main__":
  logging.basicConfig(level=logging.DEBUG)
  main()
