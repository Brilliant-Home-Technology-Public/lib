from lib import serialization
import thrift_types.configuration.ttypes as configuration_ttypes


def get_assigned_room_ids(peripheral_variables):
  room_assignment_var = peripheral_variables.get("room_assignment")
  room_ids = []
  if room_assignment_var and room_assignment_var.value:
    room_assignment = serialization.deserialize(
        configuration_ttypes.RoomAssignment,
        room_assignment_var.value,
    )
    room_ids = room_assignment.room_ids or []

  return room_ids


def get_primary_room_id(peripheral_variables):
  room_ids = get_assigned_room_ids(peripheral_variables)
  return room_ids[0] if room_ids else None


def has_room_assignment(peripheral_variables):
  return bool(get_assigned_room_ids(peripheral_variables))


def supports_room_assignment(peripheral_variables):
  return "room_assignment" in peripheral_variables
