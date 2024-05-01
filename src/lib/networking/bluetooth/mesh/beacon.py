# pylint: disable=unbalanced-tuple-unpacking
import logging

from lib.networking.bluetooth.mesh import crypto
from lib.networking.bluetooth.mesh.mesh_types import BeaconTypes
from lib.tools import bitstring_parser


log = logging.getLogger(__name__)


class InvalidBeaconError(Exception):
  pass


class BeaconHandler:

  SECURE_NETWORK_BEACON_PARSER = bitstring_parser.BitstringParser(
      "uint:8, uint:8, bytes:8, uintbe:32, bytes:8",
  )
  AUTHENTICATION_VALUE_INPUT_PARSER = bitstring_parser.BitstringParser("uint:8, bytes:8, uintbe:32")

  def get_beacon_key(self, netkey):
    ''' Mesh Profile 3.8.6.3.4 '''
    salt = crypto.s1(b'nkbk')
    P = b'id128\x01'
    beacon_key = crypto.k1(netkey, salt, P)
    return beacon_key

  def parse_network_beacon(self, netkey, pdu):
    '''
    Mesh Profile 3.9.3

    This handler only works with a single net key

    returns:
       iv_update: is network in an iv_index update procedure
       key_refresh: is network in a key refresh procedure
       iv_index:  broadcasted iv_index

    raises InvalidBeaconError
    '''
    beacon_type, flags, network_id, iv_index, auth_value = (
        self.SECURE_NETWORK_BEACON_PARSER.unpack(pdu)
    )

    network_id_check = crypto.k3(netkey)
    if network_id != network_id_check:
      raise InvalidBeaconError('Beacon network_id does not match network_key')

    key_refresh = bool(flags & 1 << 0)
    iv_update = bool(flags & 1 << 1)
    log.info(
        'Mesh Beacon RX type:%s iv_update:%s key_refresh:%s network_id:%s iv_index:%s',
        beacon_type,
        iv_update,
        key_refresh,
        network_id,
        iv_index,
    )

    beacon_key = self.get_beacon_key(netkey)
    auth_value_check = crypto.cmac(beacon_key, pdu[1:14])[:8]
    if auth_value != auth_value_check:
      raise InvalidBeaconError('Beacon auth_value does not match network_key')

    return iv_update, key_refresh, iv_index

  def build_network_beacon(self, netkey, iv_update, key_refresh, iv_index):
    '''
    Mesh Profile 3.9.3

    iv_index: number, 4 bytes [0,4294967295]
    key_refresh: [0, 1]
    iv_update: [0, 1]

    returns:
      secure network beacon packet
    '''

    beacon_type = BeaconTypes.SECURE_NETWORK
    network_id = crypto.k3(netkey)

    flags = 0
    flags |= key_refresh << 0
    flags |= iv_update << 1

    beacon_key = self.get_beacon_key(netkey)
    beacon_body = self.AUTHENTICATION_VALUE_INPUT_PARSER.pack(flags, network_id, iv_index)
    auth_value = crypto.cmac(beacon_key, beacon_body)[:8]

    log.info(
        'Mesh Beacon TX type:%s iv_update:%s key_refresh:%s network_id:%s iv_index:%s',
        beacon_type,
        iv_update,
        key_refresh,
        network_id,
        iv_index,
    )

    return self.SECURE_NETWORK_BEACON_PARSER.pack(
        beacon_type,
        flags,
        network_id,
        iv_index,
        auth_value,
    )
