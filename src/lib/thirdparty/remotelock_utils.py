import enum


class EventType(enum.Enum):
  ACCESS_DENIED = "access_denied"
  ACCESS_GUEST_LATE_SYNC = "access_guest_late_sync"
  ACCESS_PERSON_SYNCED = "access_person_synced"
  ACCESS_PERSON_SYNC_FAILED = "access_person_sync_failed"
  ACCESS_PERSON_USED = "access_person_used"
  ACS_DOOR_CLOSED = "acs_door_closed"
  ACS_DOOR_HELD_OPEN = "acs_door_held_open"
  ACS_DOOR_OPENED = "acs_door_opened"
  BATTERY_REPLACED = "battery_replaced"
  CONNECTIVITY = "connectivity"
  HUMIDITY_CHANGED = "humidity_changed"
  JAMMED = "jammed"
  KORE_READY_PIN_USED = "kore_ready_pin_used"
  LOCKED = "locked"
  POWER_LEVEL_LOW = "power_level_low"
  RELAY_ENABLED = "relay_enabled"
  RELAY_DISABLED = "relay_disabled"
  RESET = "reset"
  TEMPERATURE_CHANGED = "temperature_changed"
  UNLOCKED = "unlocked"
  UNLOCKEDLOCKED = "unlockedlocked"


SUPPORTED_EVENT_TYPES = [
    EventType.BATTERY_REPLACED,
    EventType.CONNECTIVITY,
    EventType.JAMMED,
    EventType.LOCKED,
    EventType.POWER_LEVEL_LOW,
    EventType.RESET,
    EventType.UNLOCKED,
]


LOW_POWER_THRESHOLD = 30


def get_peripheral_info_id(
    accessible_id: str,
    access_device_type: str,
) -> str:
  return f"{accessible_id}:{access_device_type}"


def get_accessible_id_from_peripheral_info_id(
    peripheral_info_id: str,
) -> str:
  return peripheral_info_id.rsplit(":", 1)[0]
