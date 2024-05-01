# pylint: disable=unbalanced-tuple-unpacking
from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
import enum
import logging
import typing

from lib.networking.bluetooth.mesh.mesh_types import FoundationModelOpCode
from lib.networking.bluetooth.mesh.mesh_types import LevelOpCode
from lib.networking.bluetooth.mesh.mesh_types import OnOffOpCode
from lib.networking.bluetooth.mesh.mesh_types import SIDModelID
from lib.networking.bluetooth.mesh.mesh_types import TransistionStepResolution
from lib.tools import bitstring_parser
import thrift_types.bluetooth.ttypes as bluetooth_ttypes


log = logging.getLogger(__name__)


class ModelOperation(enum.Enum):
  GET = 1
  SET = 2
  STATUS = 3


class PropertyCharacteristic(enum.Enum):
  # See https://brillianthome.atlassian.net/wiki/spaces/HI/pages/175210522/Brilliant+Switch+API
  VALUE = 1
  PUBLISH_CONFIG = 2


@dataclass(frozen=True)
class MeshPropertyCharacteristicID:
  """An identifier for a characteristic of a mesh property, such as on's value or motion
  detected's publish configuration.

  Note that this class does not include the value of the characteristic itself.
  """
  model_id: typing.Optional[SIDModelID]
  property_id: bluetooth_ttypes.SwitchPropertyID
  property_characteristic: PropertyCharacteristic

  # FIXME: Remove this after upgrading Cython. https://github.com/cython/cython/issues/2552
  __annotations__ = {
      "model_id": typing.Optional[SIDModelID],
      "property_id": bluetooth_ttypes.SwitchPropertyID,
      "property_characteristic": PropertyCharacteristic,
  }


MeshPropertyValue: typing.TypeAlias = int | bool | str


class MessagePayload:

  def __init__(
      self,
      operation: ModelOperation,
      node_address: int,
      mesh_property_characteristic_ids: typing.Set[MeshPropertyCharacteristicID],
      raw_data: bytes,
      transaction_id: typing.Optional[int] = None,
      values: dict[MeshPropertyCharacteristicID, MeshPropertyValue] | None = None,
  ):
    '''
    operation: A ModelOperation type.
    node_address: The node address of the mesh device.
    mesh_property_characteristic_ids: A set of MeshPropertyCharacteristicIDs corresponding to
                                      the values list (if applicable).
    raw_data: The PDU in bytes.
    transaction_id: Transaction ID for this particular message, if applicable.
    values: A mapping of MeshPropertyCharacteristicID to associated values for a
            ModelOperation.SET or ModelOperation.STATUS message. Typically None for
            ModelOperation.GET messages.
    '''
    self.operation = operation
    self.node_address = node_address
    self.mesh_property_characteristic_ids = mesh_property_characteristic_ids
    self.raw_data = raw_data
    self.transaction_id = transaction_id
    self.values = values or {}
    if self.operation != ModelOperation.GET:
      assert self.mesh_property_characteristic_ids == set(self.values.keys())
    model_ids = set(
        mesh_property_characteristic_id.model_id
        for mesh_property_characteristic_id in mesh_property_characteristic_ids
    )
    assert len(model_ids) <= 1
    self.model_id = next(iter(model_ids)) if model_ids else None

  def __str__(self):
    s = ['%s=%r' % (key, value)
      for key, value in self.__dict__.items()]
    return '%s(%s)' % (self.__class__.__name__, ', '.join(s))

  def __eq__(self, other):
    return isinstance(other, self.__class__) and self.__dict__ == other.__dict__

  def get_transaction_key(self):
    """Returns an id to index MessagePayload and match it to its exact request/response.

    Returns None if this cannot be mapped to a transaction.

    This is intended to be an opaque key. If you want to access fields of the key, access them
    through the MessagePayload object itself and not through this key.
    """
    if self.transaction_id is None or self.model_id is None:
      return None

    return (self.model_id, self.transaction_id)

  def get_match_key(
      self,
      mesh_property_characteristic_id: MeshPropertyCharacteristicID,
  ) -> typing.Tuple[int, MeshPropertyCharacteristicID]:
    """Returns an id to index a MessagePayload and match it to an appropriate request/response.

    mesh_property_characteristic_id should probably come from
    self.mesh_property_characteristic_ids.

    Unlike get_transaction_key, different requests/responses for the same node address and mesh
    property can all have the same match key. Conceptually, this provides a key that can group
    requests that are asking for the same thing and can map any response that answers the question
    to those requests.

    This is intended to be an opaque key. If you want to access fields of the key, access them
    through the MessagePayload object itself and not through this key.
    """

    return (self.node_address, mesh_property_characteristic_id)

  def get_match_keys(self) -> typing.Set[typing.Tuple[int, MeshPropertyCharacteristicID]]:
    return set(
        self.get_match_key(mesh_property_characteristic_id)
        for mesh_property_characteristic_id in self.mesh_property_characteristic_ids
    )


class AbstractMeshModel(ABC):

  @property
  @abstractmethod
  def model_id(self):
    '''
    Returns the SIDModelID for this model
    '''

  @abstractmethod
  def opcodes_handled(self):
    ''' returns a list of opcodes (1-3 bytes) that are bound to this model '''

  @abstractmethod
  def receive_message(self, src, pdu):
    '''
    src: number, 2 bytes, [0,65535]
    pdu: mesh access payload
    '''


class OnOffClientModel(AbstractMeshModel):

  MODEL_ID = SIDModelID.ONOFF_CLIENT
  SET_PDU_PARSER = bitstring_parser.BitstringParser("uint:16, uint:8, uint:8")
  SET_PDU_TRANSITION_PARSER = bitstring_parser.BitstringParser("uint:2, uint:6, uint:8")
  GET_PDU_PARSER = bitstring_parser.BitstringParser("uint:16, uint:8")

  def __init__(self):
    self.trans_id = 0

  @property
  def model_id(self):
    return self.MODEL_ID

  def _get_next_trans_id(self):
    return (self.trans_id + 1) % 256

  def opcodes_handled(self):
    return [OnOffOpCode.ONOFF_STATUS]

  def create_set_onoff_message(self, on, node_address, transition_ms=0, delay=0):
    ''' on: True or False '''
    pdu = self.SET_PDU_PARSER.pack(OnOffOpCode.ONOFF_SET, on, self.trans_id)
    transition_units = transition_ms // 100
    if transition_units > 0:
      pdu += self.SET_PDU_TRANSITION_PARSER.pack(
          TransistionStepResolution.HUNDRED_MILLISECONDS,
          transition_units,
          delay,
      )
    mesh_property_characteristic_id = MeshPropertyCharacteristicID(
        model_id=self.model_id,
        property_id='on',
        property_characteristic=PropertyCharacteristic.VALUE,
    )
    message_payload = MessagePayload(
        operation=ModelOperation.SET,
        node_address=node_address,
        mesh_property_characteristic_ids={mesh_property_characteristic_id},
        raw_data=pdu,
        transaction_id=self.trans_id,
        values={mesh_property_characteristic_id: on},
    )
    self.trans_id = self._get_next_trans_id()
    return message_payload

  def create_get_onoff_message(self, node_address):
    pdu = self.GET_PDU_PARSER.pack(OnOffOpCode.ONOFF_GET, self.trans_id)
    message_payload = MessagePayload(
        operation=ModelOperation.GET,
        node_address=node_address,
        mesh_property_characteristic_ids={
            MeshPropertyCharacteristicID(
                model_id=self.model_id,
                property_id='on',
                property_characteristic=PropertyCharacteristic.VALUE,
            ),
        },
        raw_data=pdu,
        transaction_id=self.trans_id,
    )
    self.trans_id = self._get_next_trans_id()
    return message_payload


class LevelClientModel(AbstractMeshModel):

  MODEL_ID = SIDModelID.LEVEL_CLIENT
  SET_PDU_PARSER = bitstring_parser.BitstringParser("uint:16, uintle:16, uint:8")
  SET_PDU_TRANSITION_PARSER = bitstring_parser.BitstringParser("uint:2, uint:6, uint:8")
  GET_PDU_PARSER = bitstring_parser.BitstringParser("uint:16, uint:8")

  def __init__(self):
    self.trans_id = 0

  @property
  def model_id(self):
    return self.MODEL_ID

  def _get_next_trans_id(self):
    return (self.trans_id + 1) % 256

  def opcodes_handled(self):
    return [LevelOpCode.LEVEL_STATUS]

  def create_set_level_message(self, level, node_address, transition_ms=0, delay=0):
    ''' level: number, 2 bytes, [0,65535] '''
    pdu = self.SET_PDU_PARSER.pack(LevelOpCode.LEVEL_SET, level, self.trans_id)
    transition_units = transition_ms // 100
    if transition_units > 0:
      pdu += self.SET_PDU_TRANSITION_PARSER.pack(
          TransistionStepResolution.HUNDRED_MILLISECONDS,
          transition_units,
          delay,
      )
    mesh_property_characteristic_id = MeshPropertyCharacteristicID(
        model_id=self.model_id,
        property_id='level',
        property_characteristic=PropertyCharacteristic.VALUE,
    )
    message_payload = MessagePayload(
        operation=ModelOperation.SET,
        node_address=node_address,
        mesh_property_characteristic_ids={mesh_property_characteristic_id},
        raw_data=pdu,
        transaction_id=self.trans_id,
        values={mesh_property_characteristic_id: level},
    )
    self.trans_id = self._get_next_trans_id()
    return message_payload

  def create_get_level_message(self, node_address):
    pdu = self.GET_PDU_PARSER.pack(LevelOpCode.LEVEL_GET, self.trans_id)
    message_payload = MessagePayload(
        operation=ModelOperation.GET,
        node_address=node_address,
        mesh_property_characteristic_ids={
            MeshPropertyCharacteristicID(
                model_id=self.model_id,
                property_id='level',
                property_characteristic=PropertyCharacteristic.VALUE,
            ),
        },
        raw_data=pdu,
        transaction_id=self.trans_id,
    )
    self.trans_id = self._get_next_trans_id()
    return message_payload


class ConfigurationClientModel(AbstractMeshModel):
  ''' Configuration server does not expect trans_id in messages '''

  MODEL_ID = SIDModelID.CONFIGURATION_CLIENT
  NODE_RESET_PDU_PARSER = bitstring_parser.BitstringParser("uint:16")

  @property
  def model_id(self):
    return self.MODEL_ID

  def opcodes_handled(self):
    return [FoundationModelOpCode.CONFIG_MODEL_NODE_RESET_STATUS]

  def receive_message(self, src, pdu):
    ''' Node reset status message has no parameters '''
    # TODO: Include the mesh_property_characteristic_id once status message for reset is sent
    # back reliably
    message_payload = MessagePayload(
        operation=ModelOperation.STATUS,
        node_address=src,
        mesh_property_characteristic_ids=set(),
        raw_data=pdu,
    )
    log.debug("Mesh Access RX: %s", message_payload)
    return message_payload

  def create_node_reset_message(self):
    # TODO: Wrap in a MessagePayload once status message for reset is sent back reliably
    return self.NODE_RESET_PDU_PARSER.pack(FoundationModelOpCode.CONFIG_MODEL_NODE_RESET)
