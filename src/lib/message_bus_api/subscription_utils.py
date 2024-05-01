import collections
import fnmatch

import lib.immutable.utils as immutable_utils
from lib.message_bus_api import peripheral_utils
import lib.time
import thrift_types.message_bus.ttypes as mb_ttypes


def matches_subscription(notification, subscription):
  notifying_device_id = notification.updated_device.id

  if subscription.device_id and subscription.device_id != notifying_device_id:
    return False

  if subscription.peripheral_id_glob:
    modified_peripheral_ids = [mp.peripheral_id for mp in notification.modified_peripherals]
    if not fnmatch.filter(modified_peripheral_ids, subscription.peripheral_id_glob):
      return False

  if subscription.peripheral_type is not None:
    modified_types = {
        modified_peripheral.peripheral_type
        for modified_peripheral in notification.modified_peripherals
    }
    if subscription.peripheral_type not in modified_types:
      return False

  return True


def get_matching_devices_for_subscription_request(
    subscription_request: mb_ttypes.SubscriptionRequest,
    devices_by_id: immutable_utils.ImmutableThriftValuesMap,
    home_id: str | None = None,
) -> mb_ttypes.Devices:
  matching_devices = []
  now_ms = lib.time.get_current_time_ms()
  devices_to_check: collections.abc.Iterable[mb_ttypes.Device] = []
  if subscription_request.device_id:
    if subscription_request.device_id in devices_by_id:
      devices_to_check = [devices_by_id[subscription_request.device_id]]
  else:
    devices_to_check = devices_by_id.values()
  for device in devices_to_check:
    modified_peripherals = peripheral_utils.get_modified_peripherals(None, device)
    notification = mb_ttypes.SubscriptionNotification(
        updated_device=device,
        modified_peripherals=modified_peripherals,
        timestamp=now_ms,
    )
    if matches_subscription(notification, subscription_request):
      matching_devices.append(device)

  matched = mb_ttypes.Devices(
      devices=matching_devices,
      home_id=home_id,
  )
  return matched
