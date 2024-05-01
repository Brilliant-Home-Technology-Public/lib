"""The Cloud Remote Bridge test client provides a default interface for interacting with the Cloud
Remote Bridge. The test client is intended to be used for manual testing and integration tests, and
should not be directly used in production code.
"""

import asyncio
import socket
import typing

from lib.clients.cloud_remote_bridge_test_client.authentication_policy import AuthenticationPolicy
from lib.clients.cloud_remote_bridge_test_client.remote_interface import RemoteInterface
import lib.networking.utils
import lib.protocol.processor
import lib.protocol.thrift_inspect
import lib.versioning.remote_bridge_version
import thrift_types.remote_bridge.RemoteBridgeService
import thrift_types.remote_bridge.ttypes as remote_bridge_ttypes


RemoteBridgeClient = lib.protocol.thrift_inspect.make_client_class(
    thrift_types.remote_bridge.RemoteBridgeService,
    use_immutable_types=True,
)
RemoteBridgeServer = lib.protocol.thrift_inspect.make_server_class(
    thrift_types.remote_bridge.RemoteBridgeService,
    use_immutable_types=True,
)


class CloudRemoteBridgeTestClient:
  """The CloudRemoteBridgeTestClient provides a way to easily interact with the Cloud Remote Bridge
  and analyze messages that have been received from the Cloud Remote Bridge.

  Example usage:

    client = CloudRemoteBridgeTestClient(device_id=<device_id>,
                                         home_id=<home_id>,
                                         loop=<loop>)
    await client.start()

    # Assert that the client received a notification from the Cloud Remote Bridge
    notification = await get_received_notification()
    if notification.updated_device.id == message_bus_consts.CONFIGURATION_VIRTUAL_DEVICE:
      # Perform assertions

    # Forward a notification to the Cloud Remote Bridge
    await client.forward_notification(message_bus_ttypes.SubscriptionNotification(...))

    # Forward a set variables request to the configuration virtual device
    await client.forward_set_variables_request(
      device_id=message_bus_consts.CONFIGURATION_VIRTUAL_DEVICE,
      ...
    )

    await client.stop()
  """

  def __init__(
      self,
      device_id: str,
      home_id: str,
      loop: asyncio.AbstractEventLoop,
      cert_file_directory: str,
      host: str = "localhost",
      port: int = 5321,
      start_timeout: typing.Optional[int] = None,
      brilliant_auth_token: typing.Optional[str] = None,
      current_peer_api_version: typing.Optional[lib.versioning.remote_bridge_version.BaseRemoteBridgeVersion] = None,
  ):
    # Specifically check the device_id type here. If the device_id is not a string (e.g. a UUID),
    # then the error occurs far removed from here and is difficult to debug.
    if not isinstance(device_id, str):
      raise Exception("The device_id is of type {} instead of `str`.".format(type(device_id)))

    self._device_id = device_id
    self._home_id = home_id

    self._remote_interface = RemoteInterface(device_id=self._device_id,
                                             home_id=self._home_id)
    connection_params = {
        "device-id": self._device_id,
        "home-id": self._home_id,
    }
    if brilliant_auth_token is not None:
      connection_params["authentication-token"] = brilliant_auth_token

    current_api_version = current_peer_api_version or lib.versioning.remote_bridge_version.CURRENT_API_VERSION
    self._peer_processor = lib.protocol.processor.SinglePeerProcessor(
        peer_address=lib.networking.utils.format_address(
            host=host,
            port=port,
            address_family=socket.AF_INET,
            messaging_protocol=lib.networking.utils.MessagingProtocol.WEB_SOCKET,
            secure=True,
        ),
        my_name=self._device_id,
        handler=RemoteBridgeServer(
            self._remote_interface,
            current_api_version=current_api_version,
        ),
        client_class=RemoteBridgeClient,
        my_domain=self._home_id,
        authentication_policy=AuthenticationPolicy(),
        connection_params=connection_params,
        loop=loop,
        synchronous_requests=True,
        supported_api_versions=[current_api_version],
        current_api_version=current_api_version,
        cert_file_directory=cert_file_directory,
    )
    self._start_timeout = start_timeout

  async def start(self):
    """Establishes a connection to the Cloud Remote Bridge."""
    await asyncio.wait_for(self._peer_processor.start(), timeout=self._start_timeout)

  async def shutdown(self):
    """Closes a connection to the Cloud Remote Bridge."""
    await self._peer_processor.shutdown()

  async def forward_set_variables_request(self,
                                          device_id,
                                          peripheral_name,
                                          variables,
                                          last_set_timestamps):
    """Forwards a set variables request to the specified `device_id` through the Cloud Remote
    Bridge.
    """
    return await self._peer_processor.client.forward_set_variables_request(
        device_id=device_id,
        peripheral_name=peripheral_name,
        variables=variables,
        last_set_timestamps=last_set_timestamps,
    )

  async def forward_notification(self, notification):
    """Sends a SubscriptionNotification to the Cloud Remote Bridge."""
    return await self._peer_processor.client.forward_notification(notification)

  async def synchronize_home(
      self,
      known_devices: dict[str, remote_bridge_ttypes.DeviceCheckpoint],
  ) -> remote_bridge_ttypes.SynchronizeHomeResponse:
    """Sends a synchronize home request to the Cloud Remote Bridge."""
    return await self._peer_processor.client.synchronize_home(known_devices)

  async def get_synchronize_home_call(self) -> dict[str, remote_bridge_ttypes.DeviceCheckpoint]:
    """Retrieve the parameters for a synchronize home call from the Cloud Remote Bridge."""
    return await self._remote_interface.get_synchronize_home_call()

  async def ping(self):
    """Sends a ping to the Cloud Remote Bridge."""
    return await self._peer_processor.client.ping()

  async def get_received_notification(self):
    """Retrieve a received SubscriptionNotification.

    If notifications have already been received, then return the oldest, buffered
    SubscriptionNotification. If all of the received notifications have be retrieved already, then
    awaiting this method will wait for the next notification.
    """
    return await self._remote_interface.get_received_notification()

  async def get_received_set_variables_request(self):
    """Retrieve a tuple contianing the parameters to a set variables request.

    If requests have already been received, then return the oldest, buffered set variables request.
    If all of the received requests have be retrieved already, then awaiting this method will wait
    for the next request.

    Returns: A thrift_types.remote_bridge.RemoteBridgeService.forward_set_variables_request_args
        object.
    """
    return await self._remote_interface.get_received_set_variables_request()

  def is_connected(self):
    return self._peer_processor.is_connected()
