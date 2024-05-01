# pylint: disable=unbalanced-tuple-unpacking
import logging

from lib.networking.bluetooth.mesh.brilliant_model import AckedLevelClientModel
from lib.networking.bluetooth.mesh.brilliant_model import AckedOnOffClientModel
from lib.networking.bluetooth.mesh.brilliant_model import SwitchClientModel
from lib.networking.bluetooth.mesh.model import ConfigurationClientModel
from lib.tools import bitstring_parser


log = logging.getLogger(__name__)


class AccessMessageHandler:

  OPCODE_PREFIX_PARSER = bitstring_parser.BitstringParser("uint:2, pad:6")
  OPCODE_PREFIX_TO_LENGTH = {
      0b00: 1,
      0b01: 1,
      0b10: 2,
      0b11: 3,
  }

  def __init__(self, mesh_update_callback):
    self.mesh_update_callback = mesh_update_callback

    # TODO: We may occasionally drop a set message using the same model for different devices
    self.onoff_model = AckedOnOffClientModel()
    self.level_model = AckedLevelClientModel()
    self.switch_model = SwitchClientModel()
    # Configuration server does not expect transaction IDs in client messages so we do not
    # use an acked model
    self.configuration_model = ConfigurationClientModel()

    models = (
        self.onoff_model,
        self.level_model,
        self.switch_model,
        self.configuration_model,
    )

    # construct a lookup table of opcode to model
    self._opcode_mapping = {}
    for model in models:
      for opcode in model.opcodes_handled():
        self._opcode_mapping[opcode] = model

  def receive_access_message(self, src, message):
    opcode_prefix = self.OPCODE_PREFIX_PARSER.unpack(message[:1])[0]
    opcode_length = self.OPCODE_PREFIX_TO_LENGTH[opcode_prefix]
    opcode = int(message[:opcode_length].hex(), 16)
    payload = message[opcode_length:].hex()

    log.info('Mesh Access RX access message: src: %s (%#0x), 0x%x: 0x%s',
             src, src, opcode, payload)

    if opcode not in self._opcode_mapping:
      log.warning("No model to handle mesh model opcode: 0x%x", opcode)
      return

    model = self._opcode_mapping[opcode]
    message_payload = model.receive_message(src, message)
    if message_payload:
      self.mesh_update_callback(message_payload)
