import gflags

from lib.protocol import thrift_inspect
from thrift_types.message_bus import MessageBusService
from thrift_types.message_bus import PeripheralService


FLAGS = gflags.FLAGS

gflags.DEFINE_string("message_bus_server_socket_path", "/tmp/server_socket",
                     "Path to use for the message bus server socket")


def get_message_bus_server_socket_path():
  return FLAGS.message_bus_server_socket_path


MessageBusClient = thrift_inspect.make_client_class(MessageBusService, use_immutable_types=True)
MessageBusServer = thrift_inspect.make_server_class(MessageBusService, use_immutable_types=True)
PeripheralClient = thrift_inspect.make_client_class(PeripheralService, use_immutable_types=True)
PeripheralServer = thrift_inspect.make_server_class(PeripheralService, use_immutable_types=True)
