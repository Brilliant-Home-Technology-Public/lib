import logging
import typing

import lib.time
import thrift_types.message_bus.ttypes as mb_ttypes


log = logging.getLogger(__name__)


def get_modified_peripherals(
    old_device: mb_ttypes.Device | None,
    new_device: mb_ttypes.Device,
    *,
    enable_implicit_dynamic_variable_deletion: bool = True,
) -> typing.List[mb_ttypes.ModifiedPeripheral]:
  modified_peripherals = []
  new_peripherals = new_device.peripherals
  old_peripherals = old_device.peripherals if old_device else {}
  for peripheral_name in new_peripherals.keys() | old_peripherals.keys():
    modified_peripheral = get_modified_peripheral(
        old_peripherals.get(peripheral_name),
        new_peripherals.get(peripheral_name),
        implicit_peripheral_deletion_timestamp=new_device.timestamp,
        enable_implicit_dynamic_variable_deletion=enable_implicit_dynamic_variable_deletion,
    )
    if modified_peripheral:
      modified_peripherals.append(modified_peripheral)

  return modified_peripherals


def get_modified_peripheral(
    old_peripheral: mb_ttypes.Peripheral | None,
    new_peripheral: mb_ttypes.Peripheral | None,
    *,
    implicit_peripheral_deletion_timestamp: int | None = None,
    enable_implicit_dynamic_variable_deletion: bool = True,
    require_newer_peripheral_to_add_brand_new_variables: bool = False
) -> mb_ttypes.ModifiedPeripheral | None:
  if old_peripheral == new_peripheral:
    return None

  if not new_peripheral:
    if not old_peripheral:
      # This shouldn't be reachable due to the check above, but mypy can't figure that out.
      raise ValueError("Prior peripheral from which to generate deletion was not provided!")
    if implicit_peripheral_deletion_timestamp is None:
      raise ValueError(
          "implicit_peripheral_deletion_timestamp must be specified for peripheral deletion"
      )

    # This peripheral has been deleted
    return mb_ttypes.ModifiedPeripheral(
        peripheral_id=old_peripheral.name,
        deleted=True,
        timestamp=implicit_peripheral_deletion_timestamp,
        prior_timestamp=old_peripheral.timestamp,
        peripheral_type_changed=False,
        peripheral_status_changed=False,
        peripheral_type=old_peripheral.peripheral_type,
    )

  modified_variables = get_modified_variables(
      old_peripheral,
      new_peripheral,
      enable_implicit_dynamic_variable_deletion=enable_implicit_dynamic_variable_deletion,
      require_newer_peripheral_to_add_brand_new_variables=require_newer_peripheral_to_add_brand_new_variables,
  )
  # The "new" peripheral might only have stale changes that we won't apply, or trivial changes
  # e.g. to the prior_deleted_variables field. We only want to generate a ModifiedPeripheral
  # if there are nontrivial changes.
  if old_peripheral and not modified_variables:
    # Short-circuits once an input evaluates True
    have_metadata_change = any(
        getattr(old_peripheral, attr) != getattr(new_peripheral, attr)
        for attr in ("status", "peripheral_type", "dynamic_variable_prefix")
    )
    have_newer_timestamp = (old_peripheral.timestamp or 0) < (new_peripheral.timestamp or 0)
    if not have_metadata_change and not have_newer_timestamp:
      return None

  peripheral_type_changed = (
      old_peripheral.peripheral_type != new_peripheral.peripheral_type
      if old_peripheral
      else False
  )
  peripheral_status_changed = (
      old_peripheral.status != new_peripheral.status
      if old_peripheral
      else False
  )
  return mb_ttypes.ModifiedPeripheral(
      peripheral_id=new_peripheral.name,
      deleted=False,
      modified_variables=modified_variables,
      status=new_peripheral.status,
      peripheral_type=new_peripheral.peripheral_type,
      peripheral_type_changed=peripheral_type_changed,
      peripheral_status_changed=peripheral_status_changed,
      dynamic_variable_prefix=new_peripheral.dynamic_variable_prefix,
      timestamp=new_peripheral.timestamp,
      prior_timestamp=old_peripheral.timestamp if old_peripheral else None,
      prior_deleted_variables=(
          (old_peripheral.deleted_variables or None) if old_peripheral else None
      ),
  )


def get_modified_variables(
    old_peripheral: mb_ttypes.Peripheral | None,
    new_peripheral: mb_ttypes.Peripheral,
    *,
    include_unset: bool = True,
    enable_implicit_dynamic_variable_deletion: bool = True,
    require_newer_peripheral_to_add_brand_new_variables: bool = False
) -> typing.List[mb_ttypes.ModifiedVariable]:
  implicit_deletion_timestamp = new_peripheral.timestamp
  if new_peripheral.timestamp is None:
    if (new_peripheral.peripheral_type in {mb_ttypes.PeripheralType.MOBILE_CONFIGURATION,
                                           mb_ttypes.PeripheralType.REMOTE_MEDIA}):
      # Whitelist mobile peripheral types until android fixes its Peripherals to have a timestamp.
      # See CQ-9621.
      implicit_deletion_timestamp = lib.time.get_current_time_ms()
    else:
      raise ValueError(f"Peripheral {new_peripheral.name} timestamp should not be None")
  modified_variables = []
  if not old_peripheral:
    # Construct a dummy peripheral. This makes peripheral metadata available to callees and
    # eliminates some None-checks
    old_peripheral = mb_ttypes.Peripheral(
        name=new_peripheral.name,
        peripheral_type=new_peripheral.peripheral_type,
        dynamic_variable_prefix=new_peripheral.dynamic_variable_prefix,
        variables={},
        deleted_variables=[],
    )

  explicit_deleted_variables = {
      dv.variable_name: dv for dv in new_peripheral.deleted_variables
  }

  var_names = set(old_peripheral.variables) | explicit_deleted_variables.keys()
  if ((not require_newer_peripheral_to_add_brand_new_variables) or
      (new_peripheral.timestamp or 0) > (old_peripheral.timestamp or 0)):
    # NOTE: new variables may be added with timestamp 0. So when
    # require_newer_peripheral_to_add_brand_new_variables is True, only comparing the new variable
    # timestamp to the old peripheral timestamp may be overly restrictive. We could check that
    # either the new variable timestamp OR the new peripheral timestamp exceeds the old peripheral
    # timestamp, but here we are assuming that the new peripheral timestamp will always be greater
    # than or equal to each of its variable's timestamps, so checking just the new peripheral
    # timestamp would be sufficient.
    # It could make sense to always require this timestamp check rather than having the param
    # require_newer_peripheral_to_add_brand_new_variables enable it, but it's unclear if this breaks
    # any previous assumptions made around this code. So for now, have this behavior be opt in.
    var_names.update(new_peripheral.variables)

  for var_name in var_names:
    deletion_timestamp = None
    is_implicit_static_variable_deletion = False
    if var_name not in new_peripheral.variables:
      # This variable has been deleted between old and new, either explicitly or implicitly
      if var_name in explicit_deleted_variables:
        deletion_timestamp = explicit_deleted_variables[var_name].deletion_timestamp
      else:
        is_dynamic_variable = old_peripheral.dynamic_variable_prefix and \
            var_name.startswith(old_peripheral.dynamic_variable_prefix)
        is_implicit_static_variable_deletion = not is_dynamic_variable
        if not is_dynamic_variable or enable_implicit_dynamic_variable_deletion:
          deletion_timestamp = implicit_deletion_timestamp

    # We want to consider unset variables as modified if they are new variables
    modified_variable = mb_ttypes.ModifiedVariable(
        variable_name=var_name,
        variable=new_peripheral.variables.get(var_name),
        deletion_timestamp=deletion_timestamp,
    )
    if modified_variable_has_change(old_peripheral, modified_variable, include_unset=include_unset):
      if is_implicit_static_variable_deletion:
        log.info(
            "Generated ModifiedVariable for implicit static variable deletion. Peripheral: %s,"
            " ModifiedVariable: %s, old variable timestamp: %s, old peripheral timestamp: %s,"
            " new peripheral timestamp: %s",
            new_peripheral.name,
            modified_variable,
            old_peripheral.variables[var_name].timestamp,
            old_peripheral.timestamp,
            new_peripheral.timestamp,
        )
      modified_variables.append(modified_variable)

  return modified_variables


def modified_variable_has_change(
    old_peripheral: mb_ttypes.Peripheral,
    modified_variable: mb_ttypes.ModifiedVariable,
    include_unset: bool = False
) -> bool:
  variable_name = modified_variable.variable_name
  new_variable = modified_variable.variable
  new_variable_timestamp = get_variable_modification_timestamp(modified_variable)
  is_dynamic_variable = (
      old_peripheral.dynamic_variable_prefix and
      variable_name.startswith(old_peripheral.dynamic_variable_prefix)
  )
  is_unset = new_variable and (new_variable_timestamp is None)
  if is_unset and not include_unset:
    # No timestamp means the variable is 'unset' => assume no changes
    return False

  old_variable = None
  old_deleted_variable = None
  old_variable_timestamp = None
  if variable_name in old_peripheral.variables:
    old_variable = old_peripheral.variables[variable_name]
    old_variable_timestamp = old_variable.timestamp
  else:
    # Only need to consider old deleted variable if the variable doesn't exist
    # It is safe to assume that if old_deleted_variable is set, this implies old_variable is None.
    for mv in old_peripheral.deleted_variables:
      if variable_name == mv.variable_name:
        old_deleted_variable = mv
        old_variable_timestamp = mv.deletion_timestamp
        break

  if is_dynamic_variable and new_variable and old_deleted_variable and is_unset:
    # Special case for dynamic variables that we'll preserve in order to not break any previous
    # assumptions made around this code: Treat unset variables as no different from deleted
    return False

  new_variable_timestamp_is_newer = \
      (new_variable_timestamp or 0) > (old_variable_timestamp or 0)

  # All are None case
  if not new_variable and not old_variable and not old_deleted_variable:
    # Special case for dynamic variables that we'll preserve in order to not break any previous
    # assumptions made around this code: report implicitly deleted variables as changed
    return is_dynamic_variable

  # new_variable is truthy cases
  if new_variable and not old_variable and not old_deleted_variable:
    # Brand new variable is being added
    # NOTE: this case seems to get hit a lot when starting up to initialize state
    return True
  if new_variable and old_variable:
    # Existing variable is being changed
    if old_variable_timestamp is not None and new_variable_timestamp is not None:
      # If both versions have timestamps, compare them
      return new_variable_timestamp_is_newer
    return old_variable != new_variable
  if new_variable and old_deleted_variable:
    # Previously deleted variable is being re-added
    return (not is_dynamic_variable) or new_variable_timestamp_is_newer

  # new_variable is None cases
  if old_variable:
    # Existing variable is being deleted
    if not is_dynamic_variable and old_variable_timestamp == 0:
      # Sometimes we are deleting a static readonly variable. These variables may not set timestamp,
      # in which case it is meaningless to compare against old_variable_timestamp. In these cases,
      # use peripheral timestamp as a proxy.
      # NOTE: We accept equal timestamps here, primarily due to how
      # notification_utils.apply_modified_peripheral will update old_peripheral.timestamp before
      # calling this, which may or may not be desired behavior, but that's how the code works
      # right now. It's worth noting that notification_utils.apply_modified_peripheral prefers
      # modifications in the case of equivalent timestamps as well, though a lot of the code in
      # this file does not.
      return (new_variable_timestamp or 0) >= (old_peripheral.timestamp or 0)
    return new_variable_timestamp_is_newer
  # else old_deleted_variable is truthy
  # Previously deleted variable is being deleted
  return is_dynamic_variable and new_variable_timestamp_is_newer


def get_variable_modification_timestamp(
    modified_variable: mb_ttypes.ModifiedVariable,
) -> int | None:
  if modified_variable.variable:
    return modified_variable.variable.timestamp

  return modified_variable.deletion_timestamp
