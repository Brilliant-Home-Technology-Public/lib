import copy
import typing

import thrift_types.message_bus.ttypes as mb_ttypes


PERIPHERAL_REGISTRY: typing.Dict[str, typing.Dict[str, type]] = {}


def register(cls):
  if cls.peripheral_name in PERIPHERAL_REGISTRY:
    peripheral_versions = PERIPHERAL_REGISTRY[cls.peripheral_name]
    if cls.version in peripheral_versions:
      if cls != peripheral_versions[cls.version]:
        # handle accidental duplicate version definitions
        raise ValueError("Peripheral {}, version {} defined twice!".format(
            cls.peripheral_name,
            cls.version
        ))
    else:
      peripheral_versions[cls.version] = cls
  else:
    PERIPHERAL_REGISTRY[cls.peripheral_name] = {cls.version: cls}

  if cls.peripheral_name:
    if cls.version in PERIPHERAL_REGISTRY.get(None, {}):
      raise ValueError("Peripheral {}, version {} conflicts with global version!".format(
          cls.peripheral_name,
          cls.version,
      ))
  else:
    for non_global_key in (k for k in PERIPHERAL_REGISTRY if k):
      if cls.version in PERIPHERAL_REGISTRY[non_global_key]:
        raise ValueError("Global version {} conflicts for peripheral {}!".format(
            non_global_key,
            cls.version,
        ))


class PeripheralVersion:
  """
  Peripheral versions are not like normal service versions in that they don't have multi-step
  migration functions and don't need to worry about args/responses. All peripheral migrations
  are responsible for doing is modifying the variables dictionary if necessary.
  """

  @classmethod
  def migrate_variables_up(cls, variables, last_set_timestamps, device_id=None):
    return variables, last_set_timestamps

  @classmethod
  def migrate_variables_down(cls, variables, last_set_timestamps, device_id=None):
    return variables, last_set_timestamps

  @classmethod
  def apply_migrations_to_variables(cls, direction, variables, device_id=None):
    """
    Given a set of variables, return a map of any changes to these variables as a result
    of this peripheral version's migrations. The keys to the map will be variable names, and
    the value will be a Variable struct if the variable was added or modified, and None if the
    variable was deleted. Omission from the map indicates that the variable was untouched.

    Args:
      - direction: "up" or "down" based on migration version
      - variables: A map of variable name to variable struct (could be None)
      - device_id: Optional, represents the device_id currently doing the migration.
    """
    updated_map = {}
    new_vars, new_ts = getattr(cls, "migrate_variables_{}".format(direction))(
        variables={name: v.value if v else None for name, v in variables.items()},
        last_set_timestamps={name: v.timestamp if v else None for name, v in variables.items()},
        device_id=device_id,
    )

    # First, handle any variables that were updated.
    new_existing_variables = {k: v for k, v in new_vars.items() if k in variables.keys()}
    for new_name, new_value in new_existing_variables.items():
      old_variable = variables[new_name]
      old_value = old_variable.value if old_variable else None
      old_timestamp = old_variable.timestamp if old_variable else None
      new_timestamp = new_ts.get(new_name)
      if new_value != old_value or new_timestamp != old_timestamp:
        if old_variable is None:
          # If this is a deleted variable, and the migration gave it a value, set some reasonable
          # defaults for the newly created variable.
          variable_to_set = mb_ttypes.Variable(
              name=new_name,
              value=new_value,
              timestamp=new_timestamp,
              externally_settable=True,
          )
        else:
          # Otherwise, make a deepcopy of the old variable (since it could be immutable), and
          # replace the appropriate values.
          variable_to_set = copy.deepcopy(old_variable)
          variable_to_set.value = new_value
          variable_to_set.timestamp = new_timestamp
        updated_map[new_name] = variable_to_set

    # Next, handle any removed variables.
    removed_variables = variables.keys() - new_vars.keys()
    for removed_variable_name in removed_variables:
      updated_map[removed_variable_name] = None

    # Finally, handle any added variables.
    added_variables = new_vars.keys() - variables.keys()
    for added_variable_name in added_variables:
      # TODO: do we need to handle a None value here?
      new_value = new_vars[added_variable_name]
      new_timestamp = new_ts.get(added_variable_name)
      variable = mb_ttypes.Variable(
          name=added_variable_name,
          value=new_value,
          timestamp=new_timestamp,
          externally_settable=True,
      )
      updated_map[added_variable_name] = variable

    return updated_map
