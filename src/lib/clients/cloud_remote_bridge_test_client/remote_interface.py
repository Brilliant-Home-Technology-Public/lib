import asyncio
import logging

import lib.time
import thrift_types.message_bus.ttypes as message_bus_ttypes
import thrift_types.remote_bridge.RemoteBridgeService
import thrift_types.remote_bridge.ttypes as remote_bridge_ttypes


log = logging.getLogger(__name__)


class RemoteInterface:
  """The RemoteInterface handles incoming requests from the Cloud Remote Bridge.

  All incoming notifications and set varaibles requests are buffered into `asyncio.Queue` objects.
  To retrieve received notifications or requests, use the `get_received_notification()` or
  `get_received_set_variables_request()`.
  """

  def __init__(self,
               device_id,
               home_id):
    self._device_id = device_id
    self._home_id = home_id

    self._received_notifications = asyncio.Queue()
    self._received_set_variables_requests = asyncio.Queue()
    self._received_synchronize_home_requests = asyncio.Queue()

  async def forward_notification(self, notification):
    """Receives a notification forwarded on by the Cloud Remote Bridge."""
    log.info("(home_id:%s, device_id:%s): Received forwarded notification: %s", self._home_id,
             self._device_id, notification)
    await self._received_notifications.put(notification)

  async def forward_set_variables_request(self,
                                          device_id,
                                          peripheral_name,
                                          variables,
                                          last_set_timestamps):
    """Receives a set variables request forwarded on by the Cloud Remote Bridge."""
    log.info("(home_id:%s, device_id:%s): Received forwarded set_variables_request:\n"
             "device_id=%s\n"
             "peripheral_name=%s\n"
             "variables=%a\n"
             "last_set_timestamps=%s\n",
             self._home_id,
             self._device_id,
             device_id,
             peripheral_name,
             variables,
             last_set_timestamps)
    await self._received_set_variables_requests.put(
        thrift_types.remote_bridge.RemoteBridgeService.forward_set_variables_request_args(
            device_id=device_id,
            peripheral_name=peripheral_name,
            variables=variables,
            last_set_timestamps=last_set_timestamps,
        )
    )
    return message_bus_ttypes.SetVariableResponse(
        timestamp=lib.time.get_current_time_ms(),
    )

  async def get_received_notification(self):
    """Retrieve a received SubscriptionNotification.

    If notifications have already been received, then return the oldest, buffered
    SubscriptionNotification. If all of the received notifications have be retrieved already, then
    awaiting this method will wait for the next notification.
    """
    return await self._received_notifications.get()

  async def get_received_set_variables_request(self):
    """Retrieve a tuple contianing the parameters to a set variables request.

    If requests have already been received, then return the oldest, buffered set variables request.
    If all of the received requests have be retrieved already, then awaiting this method will wait
    for the next request.

    Returns: A thrift_types.remote_bridge.RemoteBridgeService.forward_set_variables_request_args
        object.
    """
    return await self._received_set_variables_requests.get()

  async def synchronize_home(
      self,
      known_devices: dict[str, remote_bridge_ttypes.DeviceCheckpoint],
  ):
    """Receives a synchronize home request forwarded on by the Cloud Remote Bridge."""
    log.info("(home_id:%s, device_id:%s): Received synchronize home request",
             self._home_id,
             self._device_id)
    await self._received_synchronize_home_requests.put(known_devices)
    return thrift_types.remote_bridge.RemoteBridgeService.SynchronizeHomeResponse()

  async def get_synchronize_home_call(self) -> dict[str, remote_bridge_ttypes.DeviceCheckpoint]:
    """Retrieve a dict containing the know_devices of a synchronize home request.

    If requests have already been received, then return the oldest, buffered synchronize home
    request. If all of the received requests have be retrieved already, then awaiting this method
    will wait for the next request.

    Returns: A dictionary of the known devices passed to the synchronize home request.
    """
    return await self._received_synchronize_home_requests.get()
