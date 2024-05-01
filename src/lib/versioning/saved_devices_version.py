from lib.message_bus_api import device_utils
import lib.time
from lib.versioning import peripheral_version
from lib.versioning.base_version import BaseVersion
import lib.versioning.utils as versioning_utils
import thrift_types.version.constants as v_consts


class BaseSavedDevicesVersion(BaseVersion):
  service = "SavedDevices"

  @classmethod
  def _read_state_args_base(cls, direction, devices):
    for device in devices:
      peripherals = device.peripherals or {}
      for peripheral_name, peripheral in peripherals.items():
        version = peripheral_version.get_peripheral_version(device.id, peripheral_name, cls.version)
        updated_map = version.apply_migrations_to_variables(
            direction=direction,
            variables=peripheral.variables,
            device_id=device.id,
        )
        peripheral.variables = versioning_utils.update_variables_map(
            peripheral_name,
            peripheral.variables,
            updated_map,
        )

    return devices

  # this is a hack to satisfy the base version translation semantics
  @classmethod
  def _read_state_args_up(cls, devices, context=None):
    return cls._read_state_args_base("up", devices)

  @classmethod
  def _read_state_args_down(cls, devices, context=None):
    return cls._read_state_args_base("down", devices)

  @classmethod
  def _migrate_peripheral_args_base(cls, direction, args):
    peripherals = args["peripherals"]
    device_id = args["device_id"]
    for peripheral in peripherals:
      version = peripheral_version.get_peripheral_version(device_id, peripheral.name, cls.version)
      updated_map = version.apply_migrations_to_variables(
          direction=direction,
          variables=peripheral.variables,
          device_id=device_id,
      )
      peripheral.variables = versioning_utils.update_variables_map(
          peripheral.name,
          peripheral.variables,
          updated_map,
      )
      peripheral.version = cls.version

    return args

  # this is a hack to satisfy the base version translation semantics
  @classmethod
  def _migrate_peripheral_args_up(cls, args, context=None):
    return cls._migrate_peripheral_args_base("up", args)

  @classmethod
  def _migrate_peripheral_args_down(cls, args, context=None):
    return cls._migrate_peripheral_args_base("down", args)


class SavedDevicesVersion20180221(BaseSavedDevicesVersion):
  prev_version = None
  version = v_consts.VERSION_20180221
  next_version = v_consts.VERSION_20180420


class SavedDevicesVersion20180420(BaseSavedDevicesVersion):
  prev_version = v_consts.VERSION_20180221
  version = v_consts.VERSION_20180420
  next_version = v_consts.VERSION_20180605

  @classmethod
  def _read_state_args_up(cls, devices, context=None):
    devices = super()._read_state_args_up(devices=devices)
    for device in devices:
      if not device.timestamp:
        device.timestamp = lib.time.get_current_time_ms()

    return devices


class SavedDevicesVersion20180605(BaseSavedDevicesVersion):
  prev_version = v_consts.VERSION_20180420
  version = v_consts.VERSION_20180605
  next_version = v_consts.VERSION_20180620


class SavedDevicesVersion20180620(BaseSavedDevicesVersion):
  prev_version = v_consts.VERSION_20180605
  version = v_consts.VERSION_20180620
  next_version = v_consts.VERSION_20181005


class SavedDevicesVersion20181005(BaseSavedDevicesVersion):
  prev_version = v_consts.VERSION_20180620
  version = v_consts.VERSION_20181005
  next_version = v_consts.VERSION_20181018


class SavedDevicesVersion20181018(BaseSavedDevicesVersion):
  prev_version = v_consts.VERSION_20181005
  version = v_consts.VERSION_20181018
  next_version = v_consts.VERSION_20190130


class SavedDevicesVersion20190130(BaseSavedDevicesVersion):
  prev_version = v_consts.VERSION_20181018
  version = v_consts.VERSION_20190130
  next_version = v_consts.VERSION_20190204


class SavedDevicesVersion20190204(BaseSavedDevicesVersion):
  prev_version = v_consts.VERSION_20190130
  version = v_consts.VERSION_20190204
  next_version = v_consts.VERSION_20190412


class SavedDevicesVersion20190412(BaseSavedDevicesVersion):
  prev_version = v_consts.VERSION_20190204
  version = v_consts.VERSION_20190412
  next_version = v_consts.VERSION_20190530


class SavedDevicesVersion20190530(BaseSavedDevicesVersion):
  prev_version = v_consts.VERSION_20190412
  version = v_consts.VERSION_20190530
  next_version = v_consts.VERSION_20190604


class SavedDevicesVersion20190604(BaseSavedDevicesVersion):
  prev_version = v_consts.VERSION_20190530
  version = v_consts.VERSION_20190604
  next_version = v_consts.VERSION_20190614


class SavedDevicesVersion20190614(BaseSavedDevicesVersion):
  prev_version = v_consts.VERSION_20190604
  version = v_consts.VERSION_20190614
  next_version = v_consts.VERSION_20190903


class SavedDevicesVersion20190903(BaseSavedDevicesVersion):
  prev_version = v_consts.VERSION_20190614
  version = v_consts.VERSION_20190903
  next_version = v_consts.VERSION_20200923


class SavedDevicesVersion20200923(BaseSavedDevicesVersion):
  prev_version = v_consts.VERSION_20190903
  version = v_consts.VERSION_20200923
  next_version = None

  @classmethod
  def _read_state_args_up(cls, devices, context=None):
    devices = super()._read_state_args_up(devices=devices)
    for device in devices:
      device.version = cls.version
      if device.device_type is None:
        device.device_type = device_utils.guess_device_type_for_id(device.id)
    return devices


CURRENT_API_VERSION = SavedDevicesVersion20200923
