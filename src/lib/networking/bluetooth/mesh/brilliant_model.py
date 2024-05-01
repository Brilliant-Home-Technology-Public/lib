# pylint: disable=unbalanced-tuple-unpacking
import collections
import logging
import threading
import typing

from lib.networking.bluetooth.mesh import mesh_types
from lib.networking.bluetooth.mesh import model
import lib.time
from lib.tools import bitstring_parser
import thrift_types.bluetooth.constants as bluetooth_consts
import thrift_types.bluetooth.ttypes as bluetooth_ttypes


log = logging.getLogger(__name__)


GestureEvent = collections.namedtuple("GestureEvent", ["gesture", "value"])
RequestEvent = collections.namedtuple("RequestEvent", ["timestamp", "handled"])


class TransactionCache:
  """Utility class to help de-duplicate messages based on transaction id."""

  TRANSACTION_CACHE_DURATION_MS = 12 * 1000

  def __init__(self):
    self.cache_ttl = self.TRANSACTION_CACHE_DURATION_MS
    self._cache = {}
    self._cache_lock = threading.RLock()

  def track_message(self, message_payload):
    now_ms = lib.time.get_current_time_ms()
    with self._cache_lock:
      self._flush_expired(now_ms)
      self._cache[message_payload.get_transaction_key()] = RequestEvent(
          timestamp=now_ms,
          # No need to handle responses to set requests
          handled=message_payload.operation == model.ModelOperation.SET,
      )

  def ingest_message_and_check_if_already_handled(self, message_payload):
    """Ingests a MessagePayload and returns whether it has been handled already."""
    transaction_key = message_payload.get_transaction_key()
    if transaction_key is None:
      return False

    with self._cache_lock:
      self._flush_expired(now_ms=lib.time.get_current_time_ms())
      request_event = self._cache.get(transaction_key, None)
      if request_event:
        if request_event.handled:
          return True
        self._cache[transaction_key] = RequestEvent(
            timestamp=request_event.timestamp,
            handled=True,
        )
      return False

  def _flush_expired(self, now_ms):
    # Lock should be held
    outstanding_transactions = list(self._cache.keys())
    for transaction_id in outstanding_transactions:
      elapsed = now_ms - self._cache[transaction_id].timestamp
      if elapsed > self.cache_ttl:
        self._cache.pop(transaction_id)


class AckedOnOffClientModel(model.OnOffClientModel):
  '''
  This client is backwards compatible with the Mesh Specification OnOffClientModel
  It handles an optional transaction id field at the end of the onoff status message:
    uint8_t present_on_off;
    uint8_t target_on_off;
    uint8_t remaining_time;
    uint8_t transaction_id;

  If the transaction id is defined, we try to match it up against a message we created.
  '''
  EXTENDED_STATUS_PDU_PARSER = bitstring_parser.BitstringParser(
      "uint:16, uint:8, uint:8, uint:8, uint:8",
  )
  EXTENDED_STATUS_PDU_BYTES = 6
  STATUS_PDU_PARSER = bitstring_parser.BitstringParser("uint:16, uint:8")

  def receive_message(self, src, pdu):
    transaction_id = None
    if len(pdu) != self.EXTENDED_STATUS_PDU_BYTES:
      # This is a regular format status message
      _, on = self.STATUS_PDU_PARSER.unpack(pdu)
    else:
      # Handle the extended format status message with trans_id
      _, on, _, _, transaction_id = self.EXTENDED_STATUS_PDU_PARSER.unpack(pdu)

    # This status update does not match up with our own request: trigger an update
    mesh_property_characteristic_id = model.MeshPropertyCharacteristicID(
        model_id=self.model_id,
        property_id='on',
        property_characteristic=model.PropertyCharacteristic.VALUE,
    )
    message_payload = model.MessagePayload(
        operation=model.ModelOperation.STATUS,
        node_address=src,
        mesh_property_characteristic_ids={mesh_property_characteristic_id},
        raw_data=pdu,
        transaction_id=transaction_id,
        values={mesh_property_characteristic_id: on},
    )
    log.debug("Mesh Access RX: %s", message_payload)
    return message_payload


class AckedLevelClientModel(model.LevelClientModel):
  '''
  This client is backwards compatible with the Mesh Specification LevelClientModel
  It handles an optional transaction id field at the end of the level status message:
    int16_t present_level;
    int16_t target_level;
    uint8_t remaining_time;
    uint8_t transaction_id;

  If the transaction id is defined, we try to match it up against a message we created.
  '''
  EXTENDED_STATUS_PDU_PARSER = bitstring_parser.BitstringParser(
      "uint:16, uintle:16, uintle:16, uint:8, uint:8",
  )
  EXTENDED_STATUS_PDU_BYTES = 8
  STATUS_PDU_PARSER = bitstring_parser.BitstringParser("uint:16, uintle:16")

  def receive_message(self, src, pdu):
    transaction_id = None
    if len(pdu) != self.EXTENDED_STATUS_PDU_BYTES:
      # This is a regular format status message
      _, level = self.STATUS_PDU_PARSER.unpack(pdu)
    else:
      # Handle the extended format status message with trans_id
      _, level, _, _, transaction_id = self.EXTENDED_STATUS_PDU_PARSER.unpack(pdu)

    # This status update does not match up with our own request: trigger an update
    mesh_property_characteristic_id = model.MeshPropertyCharacteristicID(
        model_id=self.model_id,
        property_id='level',
        property_characteristic=model.PropertyCharacteristic.VALUE,
    )
    message_payload = model.MessagePayload(
        operation=model.ModelOperation.STATUS,
        node_address=src,
        mesh_property_characteristic_ids={mesh_property_characteristic_id},
        raw_data=pdu,
        transaction_id=transaction_id,
        values={mesh_property_characteristic_id: level},
    )
    log.debug("Mesh Access RX: %s", message_payload)
    return message_payload


class SwitchClientModel(model.AbstractMeshModel):
  ACCESS_PAYLOAD_MAXIMUM_SIZE = 376  # Mesh Profile 3.7.3
  # TODO: Move footer size fields to thrift
  COMPACT_PROPERTY_FOOTER_SIZE_BYTES = 1
  NON_COMPACT_PROPERTY_FOOTER_SIZE_BYTES = 8
  MESH_PROPERTY_DATA_TYPE_TO_BITSTRING_PARSER = {
      bluetooth_consts.MeshPropertyDataType.BOOL:
          bitstring_parser.BitstringParser("uint:8"),
      bluetooth_consts.MeshPropertyDataType.UINT8:
          bitstring_parser.BitstringParser("uint:8"),
      bluetooth_consts.MeshPropertyDataType.UINT16:
          bitstring_parser.BitstringParser("uintle:16"),
      bluetooth_consts.MeshPropertyDataType.UINT32:
          bitstring_parser.BitstringParser("uintle:32"),
      bluetooth_consts.MeshPropertyDataType.UINT64:
          bitstring_parser.BitstringParser("uintle:64"),
      bluetooth_consts.MeshPropertyDataType.INT8:
          bitstring_parser.BitstringParser("int:8"),
      bluetooth_consts.MeshPropertyDataType.INT16:
          bitstring_parser.BitstringParser("intle:16"),
      bluetooth_consts.MeshPropertyDataType.INT32:
          bitstring_parser.BitstringParser("intle:32"),
      bluetooth_consts.MeshPropertyDataType.INT64:
          bitstring_parser.BitstringParser("intle:64"),
      # Convert array fields into hexstrings for the message bus as bytes do not handle well in
      # all formats
      bluetooth_consts.MeshPropertyDataType.UINT8_ARRAY:
          bitstring_parser.BitstringParser("hex"),
  }
  SET_PUBLISH_CONFIG_PARAMETERS_PARSER = bitstring_parser.BitstringParser(
      "uint:8, uint:8, uint:8, uint:8",
  )
  SWITCH_OPCODE_PARSER = bitstring_parser.BitstringParser("uint:24, uint:8")

  def __init__(self):
    # initialize a lookup table for status opcodes to their specifications
    self.property_specs = bluetooth_consts.SWITCH_PROPERTY_SPECS

    # initialize a lookup table for gesture opcodes to their specifications
    self.gesture_specs = bluetooth_consts.SWITCH_GESTURE_SPECS

    # initialize mapping of switch opcode to handler
    self.SWITCH_OPCODE_TO_HANDLER = {
        bluetooth_ttypes.SwitchOpCode.PROPERTIES_STATUS: self._handle_property_status,
        bluetooth_ttypes.SwitchOpCode.GESTURE_DETECTED: self._handle_gesture_detected,
        bluetooth_ttypes.SwitchOpCode.GET_PUBLISH_CONFIG: self._handle_publish_config_response,
        bluetooth_ttypes.SwitchOpCode.SET_PUBLISH_CONFIG: self._handle_publish_config_response,
        bluetooth_ttypes.SwitchOpCode.COMPACT_PROPERTIES_STATUS:
            self._handle_compact_property_status,
    }
    # NOTE: We currently only use transaction IDs for publish config messages. If we start using
    # them for property messages too, we may need to either share the transaction ID between both
    # message types or update MessagePayload's get_transaction_key to include the opcode.
    self.publish_config_trans_id = 0

  @property
  def model_id(self):
    return mesh_types.SIDModelID.SWITCH_CONFIG_CLIENT

  def opcodes_handled(self):
    return [bluetooth_consts.BrilliantOpCode.SWITCH_OPCODE]

  def _get_next_publish_config_trans_id(self):
    return (self.publish_config_trans_id + 1) % 256

  def _create_get_properties_message_generic(
      self,
      properties: typing.List[bluetooth_ttypes.SwitchPropertyID],
      node_address: int,
      opcode: bluetooth_ttypes.SwitchOpCode,
  ) -> model.MessagePayload:
    sorted_properties = sorted(properties)
    property_bytes = [p.to_bytes(1, byteorder='little', signed=False) for p in sorted_properties]
    opcode_and_switch_opcode = self.SWITCH_OPCODE_PARSER.pack(
        bluetooth_consts.BrilliantOpCode.SWITCH_OPCODE,
        opcode,
    )
    parameters = b''.join(property_bytes)
    raw_data = opcode_and_switch_opcode + parameters
    mesh_property_characteristic_ids = {
        model.MeshPropertyCharacteristicID(
            model_id=self.model_id,
            property_id=property_id,
            property_characteristic=model.PropertyCharacteristic.VALUE,
        )
        for property_id in sorted_properties
    }
    message_payload = model.MessagePayload(
        operation=model.ModelOperation.GET,
        node_address=node_address,
        mesh_property_characteristic_ids=mesh_property_characteristic_ids,
        raw_data=raw_data,
    )
    return message_payload

  def create_compact_get_properties_message(
      self,
      properties: typing.List[bluetooth_ttypes.SwitchPropertyID],
      node_address: int,
  ) -> model.MessagePayload:
    return self._create_get_properties_message_generic(
        properties=properties,
        node_address=node_address,
        opcode=bluetooth_ttypes.SwitchOpCode.COMPACT_GET_PROPERTIES,
    )

  def create_get_properties_message(
      self,
      properties: typing.List[bluetooth_ttypes.SwitchPropertyID],
      node_address: int,
  ) -> model.MessagePayload:
    return self._create_get_properties_message_generic(
        properties=properties,
        node_address=node_address,
        opcode=bluetooth_ttypes.SwitchOpCode.GET_PROPERTIES,
    )

  def _create_set_properties_message_generic(
      self,
      properties: dict[bluetooth_ttypes.SwitchPropertyID, model.MeshPropertyValue],
      node_address: int,
      opcode: bluetooth_ttypes.SwitchOpCode,
      property_footer: bytes,
  ) -> model.MessagePayload:
    # Note: Values with the "UINT8_ARRAY" property data type must be formatted as a hexstring.
    params = []
    values_by_mesh_property_characteristic_id = {}
    for property_id in sorted(properties):
      if property_id not in self.property_specs:
        log.warning("SwitchClientModel unrecognized property: %s", property_id)
        continue

      property_size = self.property_specs[property_id].property_size
      property_type = self.property_specs[property_id].property_type
      property_value = properties[property_id]
      params.append(bytes([property_id]))
      parser = self.MESH_PROPERTY_DATA_TYPE_TO_BITSTRING_PARSER[property_type]
      params.append(parser.pack(property_value))
      params.append(property_footer)
      mesh_property_characteristic_id = model.MeshPropertyCharacteristicID(
          model_id=self.model_id,
          property_id=property_id,
          property_characteristic=model.PropertyCharacteristic.VALUE,
      )
      values_by_mesh_property_characteristic_id[mesh_property_characteristic_id] = property_value

    opcode_and_switch_opcode = self.SWITCH_OPCODE_PARSER.pack(
        bluetooth_ttypes.BrilliantOpCode.SWITCH_OPCODE,
        opcode,
    )
    parameters = b''.join(params)

    if len(parameters) > self.ACCESS_PAYLOAD_MAXIMUM_SIZE:
      log.error("Access message: %s exceeds maximum payload size", parameters)

    raw_data = opcode_and_switch_opcode + parameters
    message_payload = model.MessagePayload(
        operation=model.ModelOperation.SET,
        node_address=node_address,
        mesh_property_characteristic_ids=set(values_by_mesh_property_characteristic_id.keys()),
        raw_data=raw_data,
        values=values_by_mesh_property_characteristic_id,
    )
    return message_payload

  def create_set_properties_message(
      self,
      properties: dict[bluetooth_ttypes.SwitchPropertyID, model.MeshPropertyValue],
      node_address: int,
  ) -> model.MessagePayload:
    property_footer = lib.time.get_current_time_ms().to_bytes(
        self.NON_COMPACT_PROPERTY_FOOTER_SIZE_BYTES,
        byteorder='little',
        signed=False,
    )
    return self._create_set_properties_message_generic(
        properties=properties,
        node_address=node_address,
        opcode=bluetooth_ttypes.SwitchOpCode.SET_PROPERTIES,
        property_footer=property_footer,
    )

  def create_compact_set_properties_message(
      self,
      properties: dict[bluetooth_ttypes.SwitchPropertyID, model.MeshPropertyValue],
      node_address: int,
  ):
    return self._create_set_properties_message_generic(
        properties=properties,
        node_address=node_address,
        opcode=bluetooth_ttypes.SwitchOpCode.COMPACT_SET_PROPERTIES,
        # Mesh devices do not currently check against the footer sequence number, but it does still
        # expect the field to exist, so we use a dummy sequence number of zero
        property_footer=bytes(1),
    )

  def _publish_config_valid(self, publish_config):
    if publish_config.type not in bluetooth_ttypes.PublishConfigType._VALUES_TO_NAMES:
      return False
    # Currently, all publish configs should have profile 0
    return publish_config.profile == 0

  def create_get_publish_config_message(self, property_id, node_address):
    if property_id not in self.property_specs:
      raise ValueError("SwitchClientModel unrecognized property: %s" % property_id)
    opcode_and_switch_opcode = self.SWITCH_OPCODE_PARSER.pack(
        bluetooth_consts.BrilliantOpCode.SWITCH_OPCODE,
        bluetooth_consts.SwitchOpCode.GET_PUBLISH_CONFIG,
    )
    parameters = bytes([property_id])
    raw_data = opcode_and_switch_opcode + parameters
    message_payload = model.MessagePayload(
        operation=model.ModelOperation.GET,
        node_address=node_address,
        mesh_property_characteristic_ids={
            model.MeshPropertyCharacteristicID(
                model_id=self.model_id,
                property_id=property_id,
                property_characteristic=model.PropertyCharacteristic.PUBLISH_CONFIG,
            ),
        },
        raw_data=raw_data,
    )
    return message_payload

  def create_set_publish_config_message(
      self,
      property_id: bluetooth_ttypes.SwitchPropertyID,
      publish_config: bluetooth_ttypes.PublishConfig,
      node_address: int,
  ) -> model.MessagePayload:
    if property_id not in self.property_specs:
      raise ValueError("SwitchClientModel unrecognized property: %s" % property_id)
    if not self._publish_config_valid(publish_config):
      raise ValueError("SwitchClientModel invalid publish config %s" % publish_config)
    opcode_and_switch_opcode = self.SWITCH_OPCODE_PARSER.pack(
        bluetooth_consts.BrilliantOpCode.SWITCH_OPCODE,
        bluetooth_consts.SwitchOpCode.SET_PUBLISH_CONFIG,
    )
    parameters = self.SET_PUBLISH_CONFIG_PARAMETERS_PARSER.pack(
        property_id,
        publish_config.type,
        publish_config.profile,
        self.publish_config_trans_id,
    )
    raw_data = opcode_and_switch_opcode + parameters
    mesh_property_characteristic_id = model.MeshPropertyCharacteristicID(
        model_id=self.model_id,
        property_id=property_id,
        property_characteristic=model.PropertyCharacteristic.PUBLISH_CONFIG,
    )
    message_payload = model.MessagePayload(
        operation=model.ModelOperation.SET,
        node_address=node_address,
        mesh_property_characteristic_ids={mesh_property_characteristic_id},
        raw_data=raw_data,
        transaction_id=self.publish_config_trans_id,
        values={mesh_property_characteristic_id: publish_config},
    )
    self.publish_config_trans_id = self._get_next_publish_config_trans_id()
    return message_payload

  def receive_message(self, src, pdu):
    _, switch_opcode = self.SWITCH_OPCODE_PARSER.unpack(pdu)
    handler = self.SWITCH_OPCODE_TO_HANDLER.get(switch_opcode, None)
    if handler is None:
      log.warning("SwitchClientModel doesnt handle switch-opcode: 0x%x", switch_opcode)
      return None

    return handler(src, pdu)

  def _handle_property_status_generic(
      self,
      src: int,
      pdu: bytes,
      property_footer_size: int,
  ) -> model.MessagePayload | None:
    parameter_bytes = pdu[4:]  # drop the first 3 bytes (opcode) and byte 4 (switch opcode)
    properties = {}

    while parameter_bytes:
      property_id = int(parameter_bytes[0])
      if property_id not in self.property_specs:
        # Stop parsing if we get to an unknown id
        log.warning("SwitchClientModel doesn't support property type: 0x%x", property_id)
        break

      property_spec = self.property_specs[property_id]
      value_cutoff = 1 + property_spec.property_size
      property_footer_cutoff = value_cutoff + property_footer_size
      if property_footer_cutoff > len(parameter_bytes):
        log.warning("SwitchClientModel status too short: %s", parameter_bytes)
        break

      value_bytes = parameter_bytes[1: value_cutoff]
      value = typing.cast(
          model.MeshPropertyValue,
          self.MESH_PROPERTY_DATA_TYPE_TO_BITSTRING_PARSER[property_spec.property_type].unpack(
              value_bytes,
          )[0],
      )
      # TODO: Use the footer (parameter_bytes[value_cutoff: property_footer_cutoff]) to determine
      # staleness

      mesh_property_characteristic_id = model.MeshPropertyCharacteristicID(
          model_id=self.model_id,
          property_id=property_id,
          property_characteristic=model.PropertyCharacteristic.VALUE,
      )
      properties[mesh_property_characteristic_id] = value

      # Move forward to next property to parse
      parameter_bytes = parameter_bytes[property_footer_cutoff:]

    if properties:
      message_payload = model.MessagePayload(
          operation=model.ModelOperation.STATUS,
          node_address=src,
          mesh_property_characteristic_ids=set(properties.keys()),
          raw_data=pdu,
          values=properties,
      )
      log.debug("SwitchClientModel RX: %s", message_payload)
      return message_payload
    return None

  def _handle_property_status(self, src: int, pdu: bytes) -> model.MessagePayload | None:
    ''' Handle the PROPERTIES_STATUS (0x03) subopcode '''
    return self._handle_property_status_generic(
        src=src,
        pdu=pdu,
        property_footer_size=self.NON_COMPACT_PROPERTY_FOOTER_SIZE_BYTES,
    )

  def _handle_compact_property_status(self,
      src: int,
      pdu: bytes,
  ) -> model.MessagePayload | None:
    ''' Handle the COMPACT_PROPERTIES_STATUS (0x13) subopcode '''
    return self._handle_property_status_generic(
        src=src,
        pdu=pdu,
        property_footer_size=self.COMPACT_PROPERTY_FOOTER_SIZE_BYTES,
    )

  def _handle_gesture_detected(self, src, pdu):
    ''' Handle the PROPERTIES_STATUS (0x04) subopcode '''
    parameter_bytes = pdu[4:]  # drop the first 3 bytes (opcode) and byte 4 (switch opcode)

    # figure out the gesture type, and the format of potential additional data
    gesture_type = int(parameter_bytes[0])
    gesture_info = parameter_bytes[1:]
    if gesture_type not in self.gesture_specs:
      log.warning("SwitchClientModel doesn't support gesture type: 0x%x", gesture_type)
      return None
    gesture_spec = self.gesture_specs[gesture_type]
    if len(gesture_info) != gesture_spec.property_size:
      log.warning("SwitchClientModel gesture with mismatched data: %s", parameter_bytes)
      return None

    gesture_value = None
    if gesture_spec.property_size:
      gesture_value = int.from_bytes(gesture_info, byteorder='little', signed=True)
    mesh_property_characteristic_id = model.MeshPropertyCharacteristicID(
        model_id=self.model_id,
        property_id=bluetooth_consts.GESTURE_PROPERTY_ID,
        property_characteristic=model.PropertyCharacteristic.VALUE,
    )
    message_payload = model.MessagePayload(
        operation=model.ModelOperation.STATUS,
        node_address=src,
        mesh_property_characteristic_ids={mesh_property_characteristic_id},
        raw_data=pdu,
        values={mesh_property_characteristic_id: GestureEvent(gesture_type, gesture_value)},
    )

    log.debug("SwitchClientModel RX: %s", message_payload)
    return message_payload

  def _get_message_payload_for_publish_config_response(self, src, pdu):
    parameter_bytes = pdu[4:]  # drop the first 3 bytes (opcode) and byte 4 (switch opcode)
    property_id = int(parameter_bytes[0])
    if property_id not in self.property_specs:
      log.warning("SwitchClientModel unrecognized property: %s", property_id)
      return None
    publish_config = bluetooth_ttypes.PublishConfig(
        type=int(parameter_bytes[1]),
        profile=int(parameter_bytes[2]),
    )
    if not self._publish_config_valid(publish_config):
      log.warning("SwitchClientModel invalid publish config %s", publish_config)
      return None
    transaction_id = int(parameter_bytes[3])
    mesh_property_characteristic_id = model.MeshPropertyCharacteristicID(
        model_id=self.model_id,
        property_id=property_id,
        property_characteristic=model.PropertyCharacteristic.PUBLISH_CONFIG,
    )
    message_payload = model.MessagePayload(
        operation=model.ModelOperation.STATUS,
        node_address=src,
        mesh_property_characteristic_ids={mesh_property_characteristic_id},
        raw_data=pdu,
        transaction_id=transaction_id,
        values={mesh_property_characteristic_id: publish_config},
    )
    return message_payload

  def _handle_publish_config_response(self, src, pdu):
    ''' SET_PUBLISH_CONFIG (0x05) and GET_PUBLISH_CONFIG (0x06) subopcodes '''
    message_payload = self._get_message_payload_for_publish_config_response(
        pdu=pdu,
        src=src,
    )
    if message_payload:
      log.debug("SwitchClientModel RX: %s", message_payload)
    return message_payload
