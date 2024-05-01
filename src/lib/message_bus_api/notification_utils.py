import copy
import logging
import typing

from lib.message_bus_api import device_utils
from lib.message_bus_api import peripheral_utils
import thrift_types.message_bus.constants as mb_consts
import thrift_types.message_bus.ttypes as message_bus_ttypes


log = logging.getLogger(__name__)


def merge_modified_peripherals(
    newer: message_bus_ttypes.ModifiedPeripheral | None,
    older: message_bus_ttypes.ModifiedPeripheral | None,
) -> message_bus_ttypes.ModifiedPeripheral:
  if not newer and not older:
    raise ValueError("newer and older cannot both be None")
  if not newer:
    return older
  if not older:
    return newer

  newer.prior_timestamp = older.prior_timestamp

  if not newer.deleted:
    newer.prior_deleted_variables = older.prior_deleted_variables
    newer.peripheral_type_changed = bool(newer.peripheral_type_changed or
                                         older.peripheral_type_changed)
    newer.peripheral_status_changed = bool(newer.peripheral_status_changed or
                                           older.peripheral_status_changed)
    modified_variables_by_name = {mv.variable_name: mv for mv in (newer.modified_variables or [])}
    for older_modified_variable in (older.modified_variables or []):
      if older_modified_variable.variable_name not in modified_variables_by_name:
        modified_variables_by_name[older_modified_variable.variable_name] = older_modified_variable

    newer.modified_variables = list(modified_variables_by_name.values())

  return newer


def apply_modified_variables(
    target_peripheral: message_bus_ttypes.Peripheral,
    modified_variables: typing.List[message_bus_ttypes.ModifiedVariable] | None,
) -> typing.List[message_bus_ttypes.ModifiedVariable]:
  modified_peripheral, _ = _apply_modified_variables(target_peripheral, modified_variables)
  return modified_peripheral.modified_variables


def _apply_modified_variables(
    target_peripheral: message_bus_ttypes.Peripheral,
    modified_variables: typing.List[message_bus_ttypes.ModifiedVariable] | None,
    *,
    updated_device: message_bus_ttypes.Device | None = None,
) -> tuple[message_bus_ttypes.ModifiedPeripheral, bool]:
  # Gracefully handle cases where peripheral timestamp is unset
  peripheral_timestamp = target_peripheral.timestamp or 0
  applied = []
  deleted_variables = {mv.variable_name: mv for mv in target_peripheral.deleted_variables}
  for modified_variable in sorted(
      modified_variables or [],
      # Processing in timestamp order ensures more correct handling of cases where the same variable
      # name shows up more than once in modified_variables. It affects the return value of what was
      # applied, ensuring we do not skip over ModifiedVariables that would be applied if processed
      # in order (this may not currently matter to downstream logic). More importantly, it ensures
      # modified_variable_has_change behaves as expected even if we do not fully update
      # target_peripheral in the middle of the for loop execution. Specifically, we currently do not
      # update target_peripheral.deleted_variables until after all modified_variable_has_change
      # calls (same for target_peripheral.timestamp though this may or may not matter less). By
      # processing in order, we can avoid scenarios where we delete a variable, but because we did
      # not update target_peripheral.deleted_variables, we end up adding it back due to a stale
      # update being processed out of order. It is not clear whether we currently actually see calls
      # to this function that both update/add and delete the same variable.
      key=lambda mv: peripheral_utils.get_variable_modification_timestamp(mv) or 0,
  ):
    if not peripheral_utils.modified_variable_has_change(
        old_peripheral=target_peripheral,
        modified_variable=modified_variable,
        include_unset=True,
    ):
      continue

    var_name = modified_variable.variable_name
    if modified_variable.variable:
      target_peripheral.variables[var_name] = modified_variable.variable
      peripheral_timestamp = max((peripheral_timestamp, modified_variable.variable.timestamp or 0))
      deleted_variables.pop(var_name, None)
    else:
      target_peripheral.variables.pop(var_name, None)
      peripheral_timestamp = max(peripheral_timestamp, modified_variable.deletion_timestamp)
      if (target_peripheral.dynamic_variable_prefix is not None and
          var_name.startswith(target_peripheral.dynamic_variable_prefix)):
        deleted_variables[var_name] = (
            current_deleted_var
            if ((current_deleted_var := deleted_variables.get(var_name)) and
                current_deleted_var.deletion_timestamp >= modified_variable.deletion_timestamp)
            else modified_variable
        )
    applied.append(modified_variable)

  new_deleted_variables_full = sorted(
      deleted_variables.values(),
      key=lambda dv: (dv.deletion_timestamp, dv.variable_name)
  )
  if (updated_device and
      target_peripheral.name in updated_device.peripherals and
      # checks if it has an unchangeable owner: being either cloud owned or not a virtual device
      updated_device.id not in device_utils.NON_CLOUD_OWNED_KNOWN_VIRTUAL_DEVICE_IDS
   ):
    # When we receive full Device notifications from devices with unchangeable owners, force sync
    # deleted_variables by dropping any deleted variables that the owner is not aware of. We should
    # not be running into cases where we drop deleted variables with timestamps newer than ~January
    # 2024, but we may encounter historical cases with older timestamps where we did not properly
    # keep the owner's deleted_variables updated at the time. If we encounter non-historical cases,
    # they should be investigated and addressed such that the owner does not lose track of
    # deleted_variables information.
    # NOTE: One case where we may run into this is when a control is reset without leaving the home,
    # and then rejoins the same home. This should hopefully be rare and it may be simpler just to
    # let this logic handle those cases.
    # NOTE: This deleted_variables syncing logic happens AFTER applying modified_variables.
    # Consequently, this logic implicitly expects that updated_device has likewise already applied
    # modified_variables in order to avoid false hits. Also, even though this logic does not
    # directly interact with modified_variables, we put it in this function to keep all
    # deleted_variables mutation logic in one place.
    deleted_variables_recognized_by_owner = \
        set(updated_device.peripherals[target_peripheral.name].deleted_variables)
    deleted_variables_unrecognized_by_owner = set()
    kept_deleted_variables_count = 0
    # Owner may not be aware of some deleted variables because it already pruned them due to
    # DEFAULT_MAX_CACHED_DELETED_VARIABLES. Only force sync (and log) the deleted variables that
    # would still be present and unrecognized after applying DEFAULT_MAX_CACHED_DELETED_VARIABLES.
    for new_deleted_variable in reversed(new_deleted_variables_full):
      if new_deleted_variable in deleted_variables_recognized_by_owner:
        kept_deleted_variables_count += 1
        if kept_deleted_variables_count == mb_consts.DEFAULT_MAX_CACHED_DELETED_VARIABLES:
          break
      else:
        deleted_variables_unrecognized_by_owner.add(new_deleted_variable)
    if deleted_variables_unrecognized_by_owner:
      log.error(
          "Encountered deleted_variables on peripheral %s that the owner is not aware of: %s",
          target_peripheral.name,
          deleted_variables_unrecognized_by_owner
      )
      for deleted_variable in deleted_variables_unrecognized_by_owner:
        new_deleted_variables_full.remove(deleted_variable)
  new_deleted_variables = \
      new_deleted_variables_full[-mb_consts.DEFAULT_MAX_CACHED_DELETED_VARIABLES:]
  metadata_changed = (
      target_peripheral.deleted_variables != new_deleted_variables or
      target_peripheral.timestamp != peripheral_timestamp
  )
  modified_peripheral = message_bus_ttypes.ModifiedPeripheral(
      peripheral_id=target_peripheral.name,
      deleted=False,
      modified_variables=applied,
      status=target_peripheral.status,
      peripheral_type=target_peripheral.peripheral_type,
      dynamic_variable_prefix=target_peripheral.dynamic_variable_prefix,
      timestamp=peripheral_timestamp,
      prior_timestamp=target_peripheral.timestamp,
      prior_deleted_variables=[],  # FIXME: fill this in if we intend to make use of this field.
      peripheral_type_changed=False,
      peripheral_status_changed=False,
  )
  target_peripheral.deleted_variables = new_deleted_variables
  target_peripheral.timestamp = peripheral_timestamp
  return modified_peripheral, metadata_changed


def apply_modified_peripheral(
    target_peripheral: message_bus_ttypes.Peripheral,
    modified_peripheral: message_bus_ttypes.ModifiedPeripheral,
) -> message_bus_ttypes.ModifiedPeripheral | None:
  return _apply_modified_peripheral(target_peripheral, modified_peripheral)


def _apply_modified_peripheral(
    target_peripheral: message_bus_ttypes.Peripheral,
    modified_peripheral: message_bus_ttypes.ModifiedPeripheral,
    *,
    force_status: message_bus_ttypes.PeripheralStatus | None = None,
    updated_device: message_bus_ttypes.Device | None = None,
) -> message_bus_ttypes.ModifiedPeripheral | None:
  original_peripheral = copy.copy(target_peripheral)
  if force_status is not None:
    target_peripheral.status = force_status

  original_timestamp = target_peripheral.timestamp
  # Prefer modified peripheral over existing if both are unset, or if timestamps are the same
  if (target_peripheral.timestamp or -1) <= (modified_peripheral.timestamp or 0):
    target_peripheral.peripheral_type = modified_peripheral.peripheral_type
    target_peripheral.dynamic_variable_prefix = modified_peripheral.dynamic_variable_prefix
    target_peripheral.timestamp = modified_peripheral.timestamp
    if force_status is None:
      target_peripheral.status = modified_peripheral.status

  metadata_changed = original_peripheral != target_peripheral
  new_modified_peripheral, metadata_changed_from_applying_vars = _apply_modified_variables(
      target_peripheral,
      modified_peripheral.modified_variables,
      updated_device=updated_device,
  )
  metadata_changed |= metadata_changed_from_applying_vars

  if not metadata_changed and not new_modified_peripheral.modified_variables:
    return None
  # FIXME: deleted probably should be False since this function does not handle Peripheral
  # deleted updates, but some existing code may actually expect to call this function for
  # peripheral deletions. This is potentially dangerous since this function can in theory return
  # None thinking there is nothing to apply to the Peripheral, but in reality the caller should
  # handle the Peripheral deletion behavior through other means.
  new_modified_peripheral.deleted = modified_peripheral.deleted
  new_modified_peripheral.prior_timestamp = original_timestamp
  # Should these be recomputed?
  new_modified_peripheral.prior_deleted_variables = modified_peripheral.prior_deleted_variables
  new_modified_peripheral.peripheral_type_changed = modified_peripheral.peripheral_type_changed
  new_modified_peripheral.peripheral_status_changed = modified_peripheral.peripheral_status_changed
  return new_modified_peripheral


def _apply_modified_peripheral_to_device(
    target_device: message_bus_ttypes.Device,
    modified_peripheral: message_bus_ttypes.ModifiedPeripheral,
    force_status: message_bus_ttypes.PeripheralStatus | None,
    updated_device: message_bus_ttypes.Device,
) -> message_bus_ttypes.ModifiedPeripheral | None:
  if modified_peripheral.deleted:
    prior = target_device.peripherals.pop(modified_peripheral.peripheral_id, None)
    if prior:
      return modified_peripheral
    return None

  if modified_peripheral.peripheral_id not in target_device.peripherals:
    to_create = message_bus_ttypes.Peripheral(
        name=modified_peripheral.peripheral_id,
        timestamp=None,
        peripheral_type=modified_peripheral.peripheral_type,
        dynamic_variable_prefix=modified_peripheral.dynamic_variable_prefix,
        variables={},
    )
    target_device.peripherals[modified_peripheral.peripheral_id] = to_create

  return _apply_modified_peripheral(
      target_peripheral=target_device.peripherals[modified_peripheral.peripheral_id],
      modified_peripheral=modified_peripheral,
      force_status=force_status,
      updated_device=updated_device,
  )


def apply_notification_modifications(
    target_device: message_bus_ttypes.Device,
    updated_device: message_bus_ttypes.Device,
    *,
    device_deleted: bool = False,
    modified_peripherals: typing.List[message_bus_ttypes.ModifiedPeripheral] | None = None,
    force_peripheral_status: message_bus_ttypes.PeripheralStatus | None = None,
    enable_implicit_dynamic_variable_deletion: bool = True
) -> typing.List[message_bus_ttypes.ModifiedPeripheral]:
  resulting_modified_peripherals_from_application = []
  untouched_target_peripheral_ids = set(target_device.peripherals)
  for modified_peripheral in (modified_peripherals or []):
    maybe_applied = _apply_modified_peripheral_to_device(
        target_device=target_device,
        modified_peripheral=modified_peripheral,
        force_status=force_peripheral_status,
        updated_device=updated_device,
    )
    untouched_target_peripheral_ids.discard(modified_peripheral.peripheral_id)
    if maybe_applied:
      resulting_modified_peripherals_from_application.append(maybe_applied)

  if updated_device.peripherals or modified_peripherals is None or device_deleted:
    implicit_modifications_to_apply = peripheral_utils.get_modified_peripherals(
        old_device=target_device,
        new_device=updated_device,
        enable_implicit_dynamic_variable_deletion=enable_implicit_dynamic_variable_deletion,
    )
    for implicit_modified_peripheral in implicit_modifications_to_apply:
      implicit_change = _apply_modified_peripheral_to_device(
          target_device=target_device,
          modified_peripheral=implicit_modified_peripheral,
          # NOTE: force_peripheral_status is NOT applied on peripherals that neither had a
          # ModifiedPeripheral passed in via the modified_peripherals param nor had an implicit
          # ModifiedPeripheral generated from get_modified_peripherals. It is unclear whether this
          # is intentional.
          force_status=force_peripheral_status,
          updated_device=updated_device,
      )
      untouched_target_peripheral_ids.discard(implicit_modified_peripheral.peripheral_id)
      if implicit_change:
        resulting_modified_peripherals_from_application.append(implicit_change)
      else:
        log.warning("Computed modified peripheral %s, but no change applied on device %s!",
                    implicit_modified_peripheral,
                    target_device.id)
    for peripheral_id in untouched_target_peripheral_ids:
      # Ensure we call _apply_modified_variables passing in updated_device on all peripherals in
      # target_device.peripherals. As of 2/4/24, this is solely to ensure that we execute the
      # deleted_variables syncing logic if necessary (see how _apply_modified_variables makes use
      # of updated_device).
      modified_peripheral, metadata_changed = _apply_modified_variables(
          target_peripheral=target_device.peripherals[peripheral_id],
          modified_variables=[],
          updated_device=updated_device,
      )
      if metadata_changed:
        resulting_modified_peripherals_from_application.append(modified_peripheral)

  device_type_updated = False
  older_updated_timestamp = updated_device.timestamp < target_device.timestamp
  update_clears_set_target_device_type = (target_device.device_type is not None
                                          and updated_device.device_type is None)

  if not (older_updated_timestamp or update_clears_set_target_device_type):
    device_type_updated = target_device.device_type != updated_device.device_type
    target_device.device_type = updated_device.device_type

  merged_by_peripheral_id: dict[str, message_bus_ttypes.ModifiedPeripheral] = {}
  for modified_peripheral in resulting_modified_peripherals_from_application:
    merged_by_peripheral_id[modified_peripheral.peripheral_id] = merge_modified_peripherals(
        older=merged_by_peripheral_id.get(modified_peripheral.peripheral_id),
        newer=modified_peripheral,
    )
  merged_resulting_modified_peripherals = list(merged_by_peripheral_id.values())
  if merged_resulting_modified_peripherals or device_type_updated:
    target_device.timestamp = max(
        target_device.timestamp,
        updated_device.timestamp,
        *(
            modified_peripheral.timestamp
            for modified_peripheral in merged_resulting_modified_peripherals
            if modified_peripheral.timestamp
        ),
    )
  return merged_resulting_modified_peripherals


def get_updated_variable(
    peripheral_id: str,
    variable_name: str,
    device: message_bus_ttypes.Device,
    modified_peripherals: typing.List[message_bus_ttypes.ModifiedPeripheral] | None = None
) -> message_bus_ttypes.Variable | None:
  variable = None

  peripheral = device.peripherals.get(peripheral_id)
  if peripheral:
    variable = peripheral.variables.get(variable_name)

  if modified_peripherals and not variable:
    for modified_peripheral in modified_peripherals:
      if modified_peripheral.peripheral_id == peripheral_id:
        for modified_variable in (modified_peripheral.modified_variables or []):
          if modified_variable.variable_name == variable_name:
            variable = modified_variable.variable
            break
        break

  return variable
