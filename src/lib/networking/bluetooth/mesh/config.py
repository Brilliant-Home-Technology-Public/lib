# pylint: disable=unbalanced-tuple-unpacking
import bitstring

from lib.networking.bluetooth.mesh.mesh_types import FoundationModelOpCode


class FoundationModel:

  MODEL_APP_BIND_PDU = 'uint:16, uint:16, uint:16, uint:16'

  def create_bind_command(self, element, appkey_idx, model_id):
    pdu = bitstring.pack(
        self.MODEL_APP_BIND_PDU,
        FoundationModelOpCode.CONFIG_MODEL_APP_BIND,
        element,
        appkey_idx,
        model_id,
    ).bytes
    return pdu
