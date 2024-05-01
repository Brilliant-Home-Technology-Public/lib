import configparser
import importlib
import logging
import os
import pwd

import gflags

import lib.exceptions


log = logging.getLogger(__name__)


class StartableConfig:

  def __init__(self, startable_class, parameters=None):
    self.startable_class = startable_class
    self.parameters = parameters or []

  def get_startable_class(self, all_defined_parameters):
    return self.startable_class

  @property
  def startable_parameters(self):
    return self.parameters


class StartableParameter:

  _no_default = object()

  def __init__(self,
               param_key,
               param_type,
               default_value=_no_default,
               description=None,
               gflag_name=None):
    self.param_key = param_key
    self.param_type = param_type
    self.default_value = default_value
    self.description = description
    self.gflag_name = gflag_name or self.param_key

  def has_default(self):
    return self.default_value != StartableParameter._no_default


def define_gflags(startable_config):
  for param in startable_config.parameters:
    define_gflag_from_parameter(param)


def define_gflag_from_parameter(param):
  if hasattr(gflags.FLAGS, param.gflag_name):
    if is_param_equal_to_gflag(param):
      return
    raise ValueError("Conflicting gflag definitions for flag:", param.gflag_name)

  gflags_funcs = {
      str: gflags.DEFINE_string,
      int: gflags.DEFINE_integer,
      bool: gflags.DEFINE_bool,
      float: gflags.DEFINE_float,
      list: gflags.DEFINE_list,
  }
  gflags_funcs[param.param_type](param.gflag_name, param.default_value, param.description)


def startable_host_flags(startable_id, config_path):
  startable_host_flags = {
      "startable_id": startable_id,
      "startable_host_config_path": config_path,
  }
  return startable_host_flags


def is_param_equal_to_gflag(param):
  if not hasattr(gflags.FLAGS, param.gflag_name):
    raise lib.exceptions.DoesNotExistError("gflag", param.gflag_name, "is undefined")
  flag_dict = gflags.FLAGS.FlagDict()
  return (flag_dict[param.gflag_name].default == param.default_value)


def generate_startable_host_ini(startables_to_host, flags, file_path, owning_user=None):
  '''
  startables_to_host: list of hosted startable configs
  flags: a dictionary of relevant flags for the startables to host
  file_path: file path to write the ini config to
  '''

  # Process contents for ini config
  # Disable interpolation so we don't have to escape % characters in values
  ini_config = configparser.ConfigParser(interpolation=None)
  for startable_info in startables_to_host:
    module = importlib.import_module(startable_info.startable_module)
    startable_config = module.__startable_config__
    ini_config[startable_info.startable_id] = {
        'module_path': startable_info.startable_module
    }
    for param in startable_config.parameters:
      if param.gflag_name in flags:
        ini_config[startable_info.startable_id][param.param_key] = str(flags[param.gflag_name])

  # Write out the ini config
  directory = os.path.dirname(file_path)
  if not os.path.exists(directory):
    os.makedirs(directory)
  with open(file_path, 'w', encoding="utf-8") as ini_config_file:
    ini_config.write(ini_config_file)

  if owning_user:
    try:
      pwd_entry = pwd.getpwnam(owning_user)
      os.chown(file_path, pwd_entry.pw_uid, pwd_entry.pw_gid)
    except (KeyError, OSError) as e:
      log.error("Failed to set ownership for file %s: %r", file_path, e)


##############################
# Shared StartableParameters #
##############################

RAISE_ERRORS_FOR_LOST_USER_CONFIGURED_DATA_STARTABLE_PARAM = StartableParameter(
    param_key="raise_errors_for_lost_user_configured_data",
    gflag_name="raise_errors_for_lost_user_configured_data",
    param_type=bool,
    description="Whether to raise or log an error when lost configured data is detected",
    default_value=True,
)
