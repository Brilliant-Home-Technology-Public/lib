import copy
import logging

import lib.time
from lib.versioning.peripheral_version.base import PeripheralVersion
from lib.versioning.peripheral_version.base import register
import thrift_types.message_bus.constants as mb_consts
from thrift_types.version import constants as version_consts


log = logging.getLogger(__name__)


class LifxConfigPeripheralVersion20190903(PeripheralVersion):

  prev_version = None
  version = version_consts.VERSION_20190903
  next_version = None
  peripheral_name = mb_consts.LIFX_CONFIG_IDENTIFIER

  @classmethod
  def migrate_variables_up(cls, variables, last_set_timestamps, device_id=None):
    # Add OAuth variables to the lifx configuration for any homes who recieved a configuration
    # before it began supporting OAuth
    timestamp = lib.time.get_current_time_ms()
    updated_variables = copy.deepcopy(variables)
    if "access_token" not in variables:
      variables["access_token"] = ""
      last_set_timestamps["access_token"] = timestamp
    if "expiration_date" not in variables:
      variables["expiration_date"] = "0"
      last_set_timestamps["expiration_date"] = timestamp
    if "refresh_token" not in variables:
      variables["refresh_token"] = ""
      last_set_timestamps["refresh_token"] = timestamp
    return variables, last_set_timestamps

  @classmethod
  def migrate_variables_down(cls, variables, last_set_timestamps, device_id=None):
    # No need for a down migration
    return variables, last_set_timestamps


register(LifxConfigPeripheralVersion20190903)
