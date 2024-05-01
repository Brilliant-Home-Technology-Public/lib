from lib.versioning.peripheral_version.base import PeripheralVersion
from lib.versioning.peripheral_version.base import register
from thrift_types.version import constants as version_consts


class ExamplePeripheralVersion20180221(PeripheralVersion):
  peripheral_name = "example_peripheral"
  version = version_consts.VERSION_20180221

  @classmethod
  def migrate_variables_up(cls, variables, last_set_timestamps, device_id=None):
    """
    Describes how to migrate the variables for example_peripheral from the version before to this
    version.
    """
    # for some reason we decided to change our temperature scale from Farenheit to Celcius
    # NOTE: how we don't assume that the variable is in the map or that it is non-null. This is
    # because this function could be executed in any number of contexts (for example, we are
    # executing this one variable at a time, or the variable is being deleted so it's value is
    # None)
    updated_variables = {}
    if "temperature" in variables and variables["temperature"] is not None:
      # NOTE that all variable values are in string format, so they must be converted to the
      # proper data type and then converted back!
      temp = float(variables["temperature"])
      updated_variables["temperature"] = str((temp - 32) * 5 / 9)
    # Note: If you want to delete a variable, you should not include it in updated_variables
    for var_name in variables:
      if not var_name == "variable_to_remove":
        updated_variables[var_name] = variables[var_name]
    # Note: If there are variables that DON'T need to be modified, they should be included
    # in updated_variables unmodified
    # must return the updated variables map AND last_set_timestamps map
    return updated_variables, last_set_timestamps

  @classmethod
  def migrate_variables_down(cls, variables, last_set_timestamps, device_id=None):
    """
    Describes how to migrate the variables for example_peripheral to the version before from this
    version.
    """
    # NOTE: how we don't assume that the variable is in the map or that it is non-null. This is
    # because this function could be executed in any number of contexts (for example, we are
    # executing this one variable at a time, or the variable is being deleted so it's value is
    # None)
    updated_variables = {}
    if "temperature" in variables and variables["temperature"] is not None:
      # NOTE that all variable values are in string format, so they must be converted to the
      # proper data type and then converted back!
      temp = float(variables["temperature"])
      updated_variables["temperature"] = str(temp * 9 / 5 + 32)
    # Note: If you want to delete a variable, you should not include it in updated variables
    for var_name in variables:
      if not var_name == "variable_to_remove":
        updated_variables[var_name] = variables[var_name]
    # must return the updated variables map AND last_set_timestamps map
    # Note: If there are variables that DON'T need to be modified, they should be included
    # in updated_variables unmodified
    return updated_variables, last_set_timestamps


# Make sure to register ALL peripheral versions explicltly so we know they exist
register(ExamplePeripheralVersion20180221)
