import functools
import itertools
import logging
import typing

from lib.home_layout import room_assignment
import thrift_types.configuration.constants as config_consts
import thrift_types.configuration.ttypes as config_ttypes
import thrift_types.message_bus.ttypes as mb_ttypes


log = logging.getLogger(__name__)


def scene_contains_action_matching_any_set_variables_action_for_peripherals(
    scene: config_ttypes.Scene,
    set_variables_actions: typing.List[config_ttypes.SetVariablesAction],
    peripherals_dict: typing.Dict[
        config_ttypes.UniquePeripheralID, mb_ttypes.Peripheral
    ]) -> bool:
  # NOTE: This function ignores multi-actions when checking for matching scene actions
  for set_variables_action in set_variables_actions:
    peripherals_dict_for_set_variables_action = {}
    for scene_action in scene.actions:
      unique_peripheral_id = config_ttypes.UniquePeripheralID(
          device_id=scene_action.device_id,
          peripheral_id=scene_action.peripheral_name
      )
      if unique_peripheral_id in peripherals_dict and (not set_variables_action.variables or
           set_variables_action.variables == scene_action.variables):
        peripherals_dict_for_set_variables_action[unique_peripheral_id] = \
            peripherals_dict[unique_peripheral_id]
    peripheral_filter_passed = peripherals_dict_for_set_variables_action and \
        resolve_peripheral_filter(
            peripheral_filter=set_variables_action.peripheral_filter,
            peripherals_dict=peripherals_dict_for_set_variables_action
        )
    if peripheral_filter_passed:
      return True
  return False


def resolve_peripheral_filter(
    peripheral_filter: config_ttypes.PeripheralFilter,
    peripherals_dict: typing.Optional[typing.Dict[
        config_ttypes.UniquePeripheralID, mb_ttypes.Peripheral
    ]],
    group_dict: typing.Optional[
        typing.Dict[str, typing.Set[config_ttypes.UniquePeripheralID]]
    ] = None
) -> typing.Set[config_ttypes.UniquePeripheralID]:
  '''Resolves a PeripheralFilter into set<UniquePeripheralID>

  Keyword arguments:
  peripheral_filter -- a PeripheralFilter
  peripherals_dict -- a map<UniquePeripheralID, Peripheral> of all peripherals to be considered.
      Can be None if not needed to resolve peripheral_filter.
  group_dict -- a map<str, set<UniquePeripheralID>> of device group ids to the set of associated
      peripherals. Can be None if not needed to resolve peripheral_filter.
  '''
  peripherals_iter: "typing.Iterable[config_ttypes.UniquePeripheralID]"
  if peripheral_filter.peripherals is not None:
    if peripherals_dict:
      # As a convenience, pre-filter for existence so downstream filters can assume existence
      peripherals_iter = (
          unique_peripheral_id
          for unique_peripheral_id in peripheral_filter.peripherals
          if unique_peripheral_id in peripherals_dict
      )
    else:
      peripherals_iter = peripheral_filter.peripherals
  elif peripherals_dict is not None:
    # Check all peripherals if peripherals list is not explicitly specified
    peripherals_iter = peripherals_dict.keys()
  else:
    raise ValueError(
        "Can't resolve filter if peripherals_dict and peripheral_filter.peripherals are both None"
    )
  if peripheral_filter.room_ids is not None:
    peripherals_iter = filter(
        functools.partial(
            _room_filter_func,
            accepted_room_ids=(
                config_consts.ALL_ROOM_IDS
                if peripheral_filter.room_ids == config_consts.ALL_ROOM_IDS
                else peripheral_filter.room_ids
            ),
            peripherals_dict=peripherals_dict,
            # NOTE: We treat explicitly specified (via peripheral_filter.peripherals),
            # unassignable (i.e. does not have the room_assignment variable) peripherals
            # as if they were in all rooms, as a convenience to the caller. Unassignable
            # peripherals that were NOT explicitly specified are treated as if they were in
            # no rooms (and thus would not pass the rooms filter), to safeguard against
            # accidentally accepting all unassignable peripherals in the home.
            accept_unassignable_peripherals=bool(peripheral_filter.peripherals)
        ),
        peripherals_iter
    )

  if peripheral_filter.expected_variable_states:
    # None and empty are equivalent for expected_variable_states; we need only check falsiness
    peripherals_iter = filter(
        functools.partial(
            _expected_variable_states_filter_func,
            expected_variable_states=peripheral_filter.expected_variable_states,
            peripherals_dict=peripherals_dict,
        ),
        peripherals_iter
    )

  if peripheral_filter.excluded_variable_states:
    # None and empty are equivalent for excluded_variable_states; we need only check falsiness
    peripherals_iter = filter(
        functools.partial(
            _excluded_variable_states_filter_func,
            excluded_variable_states=peripheral_filter.excluded_variable_states,
            peripherals_dict=peripherals_dict,
        ),
        peripherals_iter
    )
  if peripheral_filter.peripheral_types is not None:
    peripherals_iter = filter(
        functools.partial(
            _peripheral_type_filter_func,
            peripheral_types=peripheral_filter.peripheral_types,
            peripherals_dict=peripherals_dict,
        ),
        peripherals_iter
    )
  if peripheral_filter.group_ids is not None:
    valid_grouped_peripherals = set(
        itertools.chain.from_iterable(
            typing.cast(dict, group_dict).get(group_id, set())
            for group_id in peripheral_filter.group_ids
        )
    )
    peripherals_iter = filter(
        lambda unique_peripheral_id: unique_peripheral_id in valid_grouped_peripherals,
        peripherals_iter
    )
  resolved_peripherals = set(peripherals_iter)
  if not resolved_peripherals:
    log.debug("Peripheral filter %s resolved into no peripherals", peripheral_filter)
  return resolved_peripherals


def _room_filter_func(unique_peripheral_id: config_ttypes.UniquePeripheralID,
                      accepted_room_ids: typing.Set[str],
                      peripherals_dict: typing.Dict[
                          config_ttypes.UniquePeripheralID, mb_ttypes.Peripheral
                      ],
                      accept_unassignable_peripherals: bool) -> bool:
  variables = peripherals_dict[unique_peripheral_id].variables
  if not room_assignment.supports_room_assignment(variables):
    return accept_unassignable_peripherals
  return (
      room_assignment.has_room_assignment(variables)
      if accepted_room_ids == config_consts.ALL_ROOM_IDS
      # Accept the peripheral if it is in at least one of the accepted_room_ids
      else bool(accepted_room_ids.intersection(room_assignment.get_assigned_room_ids(variables)))
  )


def _expected_variable_states_filter_func(
    unique_peripheral_id: config_ttypes.UniquePeripheralID,
    expected_variable_states: typing.Dict[str, str],
    peripherals_dict: typing.Dict[config_ttypes.UniquePeripheralID, mb_ttypes.Peripheral]) -> bool:
  variables = peripherals_dict[unique_peripheral_id].variables
  all_variables_match_expected_state = not expected_variable_states or all(
      # Accept the peripheral if no expected_variable_states are missing
      key in variables and variables[key].value == expected_value
      for key, expected_value in expected_variable_states.items()
  )
  return all_variables_match_expected_state


def _excluded_variable_states_filter_func(
    unique_peripheral_id: config_ttypes.UniquePeripheralID,
    excluded_variable_states: typing.Dict[str, str],
    peripherals_dict: typing.Dict[config_ttypes.UniquePeripheralID, mb_ttypes.Peripheral],
) -> bool:
  variables = peripherals_dict[unique_peripheral_id].variables
  no_variables_match_excluded_state = not excluded_variable_states or all(
      # Accept the peripheral if no excluded_variable_states are present
      key not in variables or variables[key].value != excluded_value
      for key, excluded_value in excluded_variable_states.items()
  )
  return no_variables_match_excluded_state


def _peripheral_type_filter_func(
    unique_peripheral_id: config_ttypes.UniquePeripheralID,
    peripheral_types: typing.Set[mb_ttypes.PeripheralType],
    peripherals_dict: typing.Dict[config_ttypes.UniquePeripheralID, mb_ttypes.Peripheral]) -> bool:
  peripheral_type = peripherals_dict[unique_peripheral_id].peripheral_type
  return peripheral_type in peripheral_types
