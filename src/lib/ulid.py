import enum
import uuid

import ulid


class InvalidIDTypeError(Exception):
  pass


class IDType(enum.IntEnum):
  '''The type of object that the ULID will be used to represent (e.g. a user, a home, etc.).

  Currently, 255 values are reserved for the type. If this enum exceeds 255, we will need to use
  more of the Brilliant reserved bits to represent the type.

  WARNING: Once an ID has been generated with an enum defined here, DO NOT change the value assigned
  to the enum!
  '''
  USER = 1
  HOME = 2
  FACEPLATE = 3
  GANGBOX = 4
  FINISHED_GOOD = 5
  RETURN = 6
  SWITCH = 7
  PLUG = 8
  ORGANIZATION_PROPERTY = 9
  STATE_CONFIG = 10
  USER_ASSET = 11
  USER_LIBRARY = 12
  PROPERTY_ALARM = 13
  ALERT_NOTIFICATION = 14
  LOADLESS_BASE = 15
  VIRTUAL_CONTROL = 16


def generate(id_type):
  '''Generate a Universally Unique Lexicographically Sortable Identifier (ULID).

  Unlike a UUIDv1, the ULID orders the timestamp from the highest order bits to the smallest.
  Since the timestamp uses millisecond granularity, each time a ULID is generated in a separate
  millisecond, it will be lexicographically ordered after the previously generated ULID. If two
  ULIDs for the same type are generated within the same millisecond, then there is no guarentee
  on the ordering of the ULIDs.

  Note that when multiple machines generate ULIDs of the same id_type, there is a risk of clock
  skew. Thus, the ordered properties are only valid on a single instance generating ULIDs.

  ULID properties:
  * Network byte order, big-endian, most significant bit first.
  * 128 bits in binary format in the following format:
    * The first 48 bits are the timestamp.
      * Won't run out of space until the year 10895 AD.
    * The next 16 bits are reserved for Brilliant's use:
      * First 8 bits are currently unused.
      * The final 8 bits store the type that is representened by the ULID..
    * The final 64 bits are random.

  When represented as a 32 character hex string, the ULID will have the following format:

      TTTTTTTT-TTTT-UUYY-RRRR-RRRRRRRRRRRR

  - T = Timestamp
  - U = Unused (should always be 0).
  - Y = Type
  - R = Random

  NOTE: The base ulid.ULID's randomness function still includes the 16 bytes reserved for
  Brilliant.

  Args:
    id_type: An IDType enum.

  Returns:
    A ULID converted to a python uuid.UUID.
  '''
  if not isinstance(id_type, IDType):
    raise InvalidIDTypeError("{id_type} is not a valid member of the IDType enum.".format(
        id_type=id_type,
    ))

  # The default ulid implementation uses 48 bits for the timestamp and 80 bits for
  # randomness. Instead of the 80 bits of randomness, we reserve the last 16 bits for Brilliant's
  # use.
  new_ulid = ulid.new()
  timestamp_bytes = new_ulid.timestamp().bytes
  id_type_bytes = bytes([0x00, id_type])
  randomness_bytes = new_ulid.randomness().bytes[2:]

  return ulid.ULID(timestamp_bytes + id_type_bytes + randomness_bytes).uuid


def validate(identifier, id_type):
  '''
  Returns True if the identifier is a UUID matching this type. Otherwise, returns False.

  ULID properties:
    * Network byte order, big-endian, most significant bit first.
    * 128 bits in binary format in the following format:
      * The first 48 bits are the timestamp.
        * Won't run out of space until the year 10895 AD.
      * The next 16 bits are reserved for Brilliant's use:
        * First 8 bits are currently unused.
        * The final 8 bits store the type that is representened by the ULID..
      * The final 64 bits are random.
  '''
  try:
    converted = ulid.from_uuid(uuid.UUID(identifier))
    id_type_bytes = converted.randomness().bytes[0:2]
    if int.from_bytes(id_type_bytes, byteorder='big') != id_type:
      return False
  except ValueError:
    return False
  return True
