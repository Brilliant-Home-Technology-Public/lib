import copy

import lib.immutable.types
from lib.message_bus_api import device_utils
from lib.versioning import peripheral_version
from lib.versioning.base_version import BaseVersion
import lib.versioning.utils as versioning_utils
from thrift_types.version import constants


def supports_synchronize_home_api(version_str):
  return version_str >= constants.VERSION_20230702


def requires_synchronize_home_api(version_str):
  return version_str >= constants.VERSION_20230704


class BaseRemoteBridgeVersion(BaseVersion):
  service = "RemoteBridge"

  @classmethod
  def _forward_set_variables_args_base(cls, direction, args):
    """
    Migrates the arguments of the forward_set_variables_request method, by adjusting the
    peripheral specific variables and last_set_timestamps, if necessary.
    """
    new_args = copy.deepcopy(args)
    version = peripheral_version.get_peripheral_version(new_args["device_id"],
                                                        new_args["peripheral_name"],
                                                        cls.version)
    new_variables, new_timestamps = getattr(version, "migrate_variables_{}".format(direction))(
        new_args["variables"],
        new_args["last_set_timestamps"],
    )
    new_args["variables"] = new_variables
    new_args["last_set_timestamps"] = new_timestamps
    return new_args

  @classmethod
  def _forward_set_variables_request_args_up(cls, args, context=None):
    return cls._forward_set_variables_args_base("up", args)

  @classmethod
  def _forward_set_variables_request_args_down(cls, args, context=None):
    return cls._forward_set_variables_args_base("down", args)

  @classmethod
  def _forward_set_variables_response_base(cls, direction, response, context):
    """
    Handles migrating the forward_set_variables_request response object. This function goes through
    all of the modified variables in the response and tries to migrate them. It will only return
    a new object if any of the variables have been changed, otherwise it will return the original
    response object.
    """
    if not context or "args" not in context or "peripheral_name" not in context["args"]:
      return response

    updated_map = {}
    peripheral_name = context["args"]["peripheral_name"]
    version = peripheral_version.get_peripheral_version(
        context["args"].get("device_id"),
        peripheral_name,
        cls.version,
    )
    variables = {var.variable_name: var.variable for var in response.modified_variables}
    updated_map = version.apply_migrations_to_variables(
        direction,
        variables,
    )

    # saves having to do a deepcopy if we don't need it
    if not updated_map:
      return response

    new_response = copy.deepcopy(response)
    new_response.modified_variables = versioning_utils.update_modified_variables(
        peripheral_name,
        new_response.modified_variables,
        updated_map,
    )
    return new_response

  @classmethod
  def _forward_set_variables_request_response_up(cls, response, context=None):
    return cls._forward_set_variables_response_base("up", response, context)

  @classmethod
  def _forward_set_variables_request_response_down(cls, response, context=None):
    return cls._forward_set_variables_response_base("down", response, context)

  @classmethod
  def _forward_notification_args_base(cls, direction, args):
    """
    Handles migrating the forward_notification request arguments. This function goes through all
    of the modified variables in the modified peripherals and tries to migrate them. It will only
    return a new copy of the notification struct iff any variable value or timestamp value has
    been changed. Otherwise, it will just return the arguments passed in. The idea here is that
    for most peripherals, the variables will not change from version to version, so there is no
    need to create a copy of the notification struct every time.
    """
    # Always do a shallow copy of the args dictionary for the benefit of child classes. Only do a
    # shallow copy to avoid an expensive deepcopy on the notification if the notification doesn't
    # need to be mutated.
    args = copy.copy(args)
    notification = args["notification"]
    device_id = notification.updated_device.id
    peripheral_updated_map = {}
    peripheral_deleted_variable_map = {}

    # update device peripherals
    for peripheral_name, peripheral in notification.updated_device.peripherals.items():
      version = peripheral_version.get_peripheral_version(device_id, peripheral_name, cls.version)
      updated_map = version.apply_migrations_to_variables(direction, peripheral.variables)
      if updated_map:
        peripheral_updated_map[peripheral_name] = updated_map

      # update deleted variables list
      variables = {var.variable_name: var.variable for var in peripheral.deleted_variables}
      deleted_map = version.apply_migrations_to_variables(direction, variables)
      if deleted_map:
        peripheral_deleted_variable_map[peripheral_name] = deleted_map

    # update notification modified peripherals
    modified_peripheral_updated_map = {}
    for peripheral in notification.modified_peripherals:
      version = peripheral_version.get_peripheral_version(
          device_id,
          peripheral.peripheral_id,
          cls.version,
      )
      if peripheral.modified_variables:
        variables = {var.variable_name: var.variable for var in peripheral.modified_variables}
        updated_map = version.apply_migrations_to_variables(direction, variables)
        if updated_map:
          modified_peripheral_updated_map[peripheral.peripheral_id] = updated_map

    # saves having to do a deepcopy if we don't need it
    if not (modified_peripheral_updated_map or peripheral_updated_map or
            peripheral_deleted_variable_map):
      return args

    new_notification = copy.deepcopy(notification)
    if peripheral_updated_map or peripheral_deleted_variable_map:
      for peripheral_name, peripheral in new_notification.updated_device.peripherals.items():
        if peripheral_name in peripheral_updated_map:
          peripheral.variables = versioning_utils.update_variables_map(
              peripheral_name,
              peripheral.variables,
              peripheral_updated_map[peripheral_name],
          )

        if peripheral_name in peripheral_deleted_variable_map:
          peripheral.deleted_variables = versioning_utils.update_modified_variables(
              peripheral_name,
              peripheral.deleted_variables,
              peripheral_deleted_variable_map[peripheral_name],
          )

    if modified_peripheral_updated_map:
      for peripheral in new_notification.modified_peripherals:
        name = peripheral.peripheral_id
        if peripheral.modified_variables and name in modified_peripheral_updated_map:
          peripheral.modified_variables = versioning_utils.update_modified_variables(
              name,
              peripheral.modified_variables,
              modified_peripheral_updated_map[name],
          )

    args.update(notification=new_notification)
    return args

  @classmethod
  def _forward_notification_args_up(cls, args, context=None):
    return cls._forward_notification_args_base("up", args)

  @classmethod
  def _forward_notification_args_down(cls, args, context=None):
    return cls._forward_notification_args_base("down", args)


class RemoteBridgeVersion20180221(BaseRemoteBridgeVersion):
  prev_version = None
  version = constants.VERSION_20180221
  next_version = constants.VERSION_20180420


class RemoteBridgeVersion20180420(BaseRemoteBridgeVersion):
  prev_version = constants.VERSION_20180221
  version = constants.VERSION_20180420
  next_version = constants.VERSION_20180620

  @classmethod
  def _forward_notification_args_up(cls, args, context=None):
    args = super()._forward_notification_args_up(args=args, context=context)

    notification = args["notification"]
    if not notification.updated_device.timestamp:
      if lib.immutable.types.is_immutable_type(notification):
        notification = copy.deepcopy(notification)
        args.update(notification=notification)
      notification.updated_device.timestamp = notification.timestamp

    return args

  # We do not need to perform a downgrade here. Thrift will automatically discard any fields that
  # are not present on the local thrift version. Thus, if the server sends down the "timestamp" in
  # the Device object, but the Brilliant Control does not have a Device.timestamp in its thrift, the
  # Brilliant Control will just ignore the Device.timestamp.


class RemoteBridgeVersion20180620(BaseRemoteBridgeVersion):

  prev_version = constants.VERSION_20180420
  version = constants.VERSION_20180620
  next_version = constants.VERSION_20180808


class RemoteBridgeVersion20180808(BaseRemoteBridgeVersion):

  prev_version = constants.VERSION_20180620
  version = constants.VERSION_20180808
  next_version = constants.VERSION_20180925


class RemoteBridgeVersion20180925(BaseRemoteBridgeVersion):

  prev_version = constants.VERSION_20180808
  version = constants.VERSION_20180925
  next_version = constants.VERSION_20181005


class RemoteBridgeVersion20181005(BaseRemoteBridgeVersion):

  prev_version = constants.VERSION_20180925
  version = constants.VERSION_20181005
  next_version = constants.VERSION_20181018


class RemoteBridgeVersion20181018(BaseRemoteBridgeVersion):

  prev_version = constants.VERSION_20181005
  version = constants.VERSION_20181018
  next_version = constants.VERSION_20190604


class RemoteBridgeVersion20190604(BaseRemoteBridgeVersion):
  prev_version = constants.VERSION_20181018
  version = constants.VERSION_20190604
  next_version = constants.VERSION_20190716


class RemoteBridgeVersion20190716(BaseRemoteBridgeVersion):
  prev_version = constants.VERSION_20190604
  version = constants.VERSION_20190716
  next_version = constants.VERSION_20200923


class RemoteBridgeVersion20200923(BaseRemoteBridgeVersion):
  prev_version = constants.VERSION_20190716
  version = constants.VERSION_20200923
  next_version = constants.VERSION_20230702

  @classmethod
  def _forward_notification_args_up(cls, args, context=None):
    args = super()._forward_notification_args_up(args=args, context=context)

    notification = args["notification"]
    if notification.updated_device.device_type is None:
      if lib.immutable.types.is_immutable_type(notification):
        notification = copy.deepcopy(notification)
        args.update(notification=notification)
      notification.updated_device.device_type = device_utils.guess_device_type_for_id(
          notification.updated_device.id
      )
      notification.updated_device.version = cls.version

    return args


class RemoteBridgeVersion20230702(BaseRemoteBridgeVersion):
  prev_version = constants.VERSION_20200923
  version = constants.VERSION_20230702
  next_version = constants.VERSION_20230704


class RemoteBridgeVersion20230704(BaseRemoteBridgeVersion):
  prev_version = constants.VERSION_20230702
  version = constants.VERSION_20230704
  next_version = None


ALL_API_VERSIONS = [
    RemoteBridgeVersion20180221,
    RemoteBridgeVersion20180420,
    RemoteBridgeVersion20180620,
    RemoteBridgeVersion20180808,
    RemoteBridgeVersion20180925,
    RemoteBridgeVersion20181005,
    RemoteBridgeVersion20181018,
    RemoteBridgeVersion20190604,
    RemoteBridgeVersion20190716,
    RemoteBridgeVersion20200923,
    RemoteBridgeVersion20230702,
    RemoteBridgeVersion20230704,
]


CURRENT_API_VERSION = RemoteBridgeVersion20200923

EXPERIMENTAL_SYNC_SUPPORTED_API_VERSION = RemoteBridgeVersion20230702
EXPERIMENTAL_SYNC_REQUIRED_API_VERSION = RemoteBridgeVersion20230704
