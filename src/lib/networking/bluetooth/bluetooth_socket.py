import asyncio
import functools
import logging
import socket

import wrapt


if not hasattr(socket, "AF_BLUETOOTH"):
  import sys
  print("Bluetooth sockets are not available on this platform!", file=sys.stderr)


log = logging.getLogger(__name__)


# The following function definitions are largely lifted from the Python standard
# library implementation. The main issue is that address resolution does not work on
# the Bluetooth addresses, so we eliminate that code.
class EventLoopCompatibilityWrapper(wrapt.ObjectProxy):

  async def sock_connect(self, sock, address):
    fut = asyncio.Future(loop=self.__wrapped__)
    self._sock_connect(fut, sock, address)
    return await fut

  def _sock_connect(self, fut, sock, address):
    fd = sock.fileno()
    try:
      sock.connect(address)
    except (BlockingIOError, InterruptedError):
      # Issue #23618: When the C function connect() fails with EINTR, the
      # connection runs in background. We have to wait until the socket
      # becomes writable to be notified when the connection succeed or
      # fails.
      fut.add_done_callback(functools.partial(self._sock_connect_done, fd))
      self.add_writer(fd, self._sock_connect_cb, fut, sock, address)
    except Exception as exc:
      fut.set_exception(exc)
    else:
      fut.set_result(None)

  def _sock_connect_done(self, fd, fut):
    self.remove_writer(fd)

  def _sock_connect_cb(self, fut, sock, address):
    if fut.cancelled():
      return

    try:
      err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
      if err != 0:
        # Jump to any except clause below.
        raise OSError(err, 'Connect call failed %s' % (address,))
    except (BlockingIOError, InterruptedError):
      # socket is still registered, the callback will be retried later
      pass
    except Exception as exc:
      fut.set_exception(exc)
    else:
      fut.set_result(None)


async def create_connection(host, port, loop, *args, server_hostname=None, ssl=None, **kwargs):
  sock = socket.socket(
      proto=socket.BTPROTO_RFCOMM,
      family=socket.AF_BLUETOOTH,
      type=socket.SOCK_STREAM,
  )
  sock.setblocking(False)
  await EventLoopCompatibilityWrapper(loop).sock_connect(sock, (host, port))
  if ssl and not server_hostname:
    server_hostname = host
  return await loop.create_connection(
      *args, sock=sock, ssl=ssl, server_hostname=server_hostname, **kwargs)


async def create_server(host, port, loop, *args, **kwargs):
  sock = socket.socket(
      proto=socket.BTPROTO_RFCOMM,
      family=socket.AF_BLUETOOTH,
      type=socket.SOCK_STREAM,
  )
  sock.bind((host or socket.BDADDR_ANY, port))
  return await loop.create_server(*args, sock=sock, **kwargs)
