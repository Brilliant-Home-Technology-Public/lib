from abc import ABCMeta
from abc import abstractmethod
import asyncio
import itertools
import logging

from lib.async_helpers import async_utils
from lib.message_bus_api import subscription_utils
from lib.queueing import work_queue
import thrift_types.message_bus.ttypes as message_bus_ttypes


log = logging.getLogger(__name__)


'''
An observer class that makes requests and listens to updates
'''


class ObserverInterface(metaclass=ABCMeta):

  @abstractmethod
  async def request_set_variables_in_peripheral(
      self,
      peripheral_id,
      variable_dict,
      device_id=None,
      last_set_timestamps=None,
  ):
    pass

  @abstractmethod
  async def get_all(self):
    pass

  @abstractmethod
  async def get_device(self, device_id):
    pass

  @abstractmethod
  async def get_peripheral(self, device_id, peripheral_id):
    pass

  @abstractmethod
  async def subscribe(self, subscription_request):
    pass

  @abstractmethod
  async def unsubscribe(self, callback_func):
    pass

  @abstractmethod
  async def handle_home_id_updated(self, home_id):
    pass

  @abstractmethod
  async def handle_notification(self):
    pass

  @abstractmethod
  async def report_notification(self, notification):
    pass


class RPCObserver(ObserverInterface):

  def __init__(self, loop):
    self._loop = loop
    self._started = False
    self._message_bus_processor = None
    self._owning_device_id = None
    self._home_id = None
    self._device_id = None
    self._subscription_callbacks = set()
    self._handle_notification_queue = work_queue.WorkQueue(
        loop=self._loop,
        num_workers=1,
        process_job_func=self._handle_notification,
        max_retries=0,  # Don't retry
    )

  async def start(self, message_bus_processor, virtual_device_id=None):
    self._started = True
    self._message_bus_processor = message_bus_processor
    self._message_bus_processor.add_reconnect_callback(self._handle_reconnect)
    mb_attributes = await self._message_bus_processor.client.get_attributes()
    self._owning_device_id = mb_attributes.my_device_id
    self._device_id = virtual_device_id or self._owning_device_id
    self._home_id = mb_attributes.home_id
    self._handle_notification_queue.start()

  async def shutdown(self):
    self._handle_notification_queue.shutdown()
    self._started = False
    self._message_bus_processor = None
    self._owning_device_id = None
    self._home_id = None
    self._device_id = None
    for request, callback_func in self._subscription_callbacks:
      # Uncancelled subscriptions are a frequent cause of leaks since they keep references
      # alive to the subscriber via the callback functions.
      log.debug("Leak warning: subscription %s (callback: %s) never unsubscribed!",
                request, callback_func)
    self._subscription_callbacks.clear()

  def get_loop(self):
    return self._loop

  def get_owning_device_id(self):
    if not self._started:
      raise Exception("RPCOBserver has not been fully initialized!")
    return self._owning_device_id

  def unsafe_get_home_id(self):  # Marked unsafe since this value might change
    return self.get_home_id()

  def get_home_id(self):
    if not self._started:
      raise Exception("RPCObserver has not been fully initialized!")

    return self._home_id

  async def handle_home_id_updated(self, home_id):
    self._home_id = home_id

  async def request_set_variables_in_peripheral(self, peripheral_id, variable_dict, device_id=None,
      last_set_timestamps=None):
    return await self._message_bus_processor.client.set_variables_request(
        device_id=self._device_id if device_id is None else device_id,
        peripheral_name=peripheral_id,
        variables=variable_dict,
        last_set_timestamps=(last_set_timestamps or {}),
    )

  async def get_all(self):
    return await self._message_bus_processor.client.get_all()

  async def get_device(self, device_id):
    return await self._message_bus_processor.client.get_device(device_id)

  async def get_peripheral(self, device_id, peripheral_id):
    return await self._message_bus_processor.client.get_peripheral(
        device_id=device_id,
        peripheral_name=peripheral_id,
    )

  async def subscribe(self, subscription_request, callback_func=None, forward_to_message_bus=True):
    '''
    Specify forward_to_message_bus=False when a SubscriptionRequest is redundant with a
    SubscriptionRequest that has already been forwarded to the message bus

    Some important things to note:
    - Existing forwarded SubscriptionRequests will be cleared when we lose connection with the
      MessageBus. Upon reconnect, we will attempt to re-establish all SubscriptionRequests present
      in `_subscription_callbacks`, including those that had not previously been forwarded
    - unsubscribe calls are not forwarded to the MessageBus, so we will continue to receive
      notifications for SubscriptionRequests that have had unsubscribe called for them until we lose
      our current MessageBus connection.
    - When forward_to_message_bus is set to False, this function can be expected to pass
      deterministically
    '''
    if callback_func:
      self._subscription_callbacks.add((subscription_request, callback_func))

    if forward_to_message_bus:
      return await self._message_bus_processor.client.subscribe(subscription_request)
    return message_bus_ttypes.Devices(devices=[])

  async def unsubscribe(
      self,
      callback_func,
      subscription_request: message_bus_ttypes.SubscriptionRequest | None = None
  ):
    to_remove = [
        (request, callback) for (request, callback) in self._subscription_callbacks
        if callback == callback_func and
        (subscription_request is None or request == subscription_request)
    ]
    self._subscription_callbacks.difference_update(to_remove)

  async def _handle_reconnect(self):
    subscriptions = [
        self._message_bus_processor.client.subscribe(subscription_request)
        for subscription_request, _ in self._subscription_callbacks
    ]
    if not subscriptions:
      return

    log.info("New message bus connection; re-establishing %s subscriptions", len(subscriptions))
    subscription_results = await asyncio.gather(*subscriptions)

    # Group by ID to eliminate duplicates, choosing the most recent version
    devices_by_id = {}
    returned_devices = [matched.devices for matched in subscription_results]
    for device in itertools.chain.from_iterable(returned_devices):
      if (device.id in devices_by_id and
          (devices_by_id[device.id].timestamp or 0) > (device.timestamp or 0)):
        continue

      devices_by_id[device.id] = device

    for device in devices_by_id.values():
      notification = message_bus_ttypes.SubscriptionNotification(
          updated_device=device,
          modified_peripherals=[],
          timestamp=device.timestamp,
      )
      await self.handle_notification(notification)

  async def handle_notification(self, notification):
    self._handle_notification_queue.add_job(notification)

  async def _handle_notification(self, notification):
    def get_unique_callback_tasks():
      callbacks_to_invoke = set()
      for subscription_request, callback_func in self._subscription_callbacks:
        if callback_func not in callbacks_to_invoke and \
            subscription_utils.matches_subscription(notification, subscription_request):
          callbacks_to_invoke.add(callback_func)
          yield callback_func(notification)

    # This should await all tasks to completion even if an error is encountered, so that if we
    # shutdown, we can properly cancel all tasks.
    await async_utils.gather_logging_exceptions(*get_unique_callback_tasks())

  async def report_notification(self, notification):
    await self._message_bus_processor.client.handle_notification(notification)
