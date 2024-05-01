# pylint: disable=unbalanced-tuple-unpacking
import logging

import cryptography

import lib.crypto.block_ciphers
from lib.networking.bluetooth.mesh import crypto
from lib.networking.bluetooth.mesh.mesh_types import NonceType
from lib.tools import bitstring_parser


log = logging.getLogger(__name__)


class NetworkHandler:
  '''
  Handles the netkey encryption and decryption specified as part of the Network Layer

 send_transport_pdu     receive_transport_pdu_callback
            V                                ^
          |-------------------------------------|
          |            NetworkHandler           |
          |_____________________________________|
            V                                ^
 send_network_pdu_callback         receive_network_pdu

  '''

  NETWORK_PDU_PARSER = bitstring_parser.BitstringParser("uint:1, uint:7, bytes:6, bytes")
  NETWORK_HEADER_PARSER = bitstring_parser.BitstringParser("uint:1, uint:7, uintbe:24, uintbe:16")
  PRIVACY_RANDOM_PARSER = bitstring_parser.BitstringParser("pad:40, uintbe:32, bytes:7")
  NETWORK_NONCE_PARSER = bitstring_parser.BitstringParser(
      "uint:8, uint:1, uint:7, uintbe:24, uintbe:16, pad:16, uintbe:32",
  )
  PROXY_NONCE_PARSER = bitstring_parser.BitstringParser(
      "uint:8, pad:8, uintbe:24, uintbe:16, pad:16, uintbe:32",
  )
  TRANSORT_ENCRYPTION_MESSAGE_PARSER = bitstring_parser.BitstringParser("uintbe:16, bytes")

  TTL = 4  # [0,127]
  UNASSIGNED_ADDRESS = 0x0000
  BROADCAST_ADDRESS = 0xFFFF

  def __init__(
      self,
      datastore,
      mesh_manager,
      send_network_pdu_callback,
      send_proxy_config_pdu_callback,
      receive_transport_pdu_callback,
  ):
    self.datastore = datastore
    self.mesh_manager = mesh_manager
    self.send_network_pdu_callback = send_network_pdu_callback
    self.send_proxy_config_pdu_callback = send_proxy_config_pdu_callback
    self.receive_transport_pdu_callback = receive_transport_pdu_callback

  def get_privacy_random(self, iv_index, pdu):
    '''
    Mesh Profile 3.8.7.3

    iv_index: number, 4 bytes [0,4294967295]
    pdu: transport pdu (encrypted)

    returns:
      0x0000000000 || IV Index || Privacy Random
    '''
    return self.PRIVACY_RANDOM_PARSER.pack(iv_index, pdu[:7])

  def get_proxy_nonce(self, iv_index, ttl, seq, src, ctl):
    '''
    Mesh Profile 3.8.5.4

    iv_index: number, 4 bytes [0,4294967295]
    ttl: number, 7 bits [0,127]
    seq: number, 3 bytes, [0,16777215]
    src: number, 2 bytes, [0,65535]
    ctl: number, 1 bit [0,1]

    returns:
      13 byte proxy nonce
    '''
    return self.PROXY_NONCE_PARSER.pack(NonceType.PROXY, seq, src, iv_index)

  def get_nonce(self, iv_index, ttl, seq, src, ctl):
    '''
    Mesh Profile 3.8.5.1

    iv_index: number, 4 bytes [0,4294967295]
    ttl: number, 7 bits [0,127]
    seq: number, 3 bytes, [0,16777215]
    src: number, 2 bytes, [0,65535]
    ctl: number, 1 bit [0,1]
    returns:
      13 byte network nonce
    '''
    return self.NETWORK_NONCE_PARSER.pack(NonceType.NETWORK, ctl, ttl, seq, src, iv_index)

  def get_PECB(self, netkey, iv_index, pdu):
    '''
    PECB: value specified by Mesh Profile 3.8.7.3

    netkey: 16 byte string
    iv_index: number, 4 bytes [0,4294967295]
    pdu: transport pdu (encrypted)

    returns:
      PECB
    '''
    nid, encryption_key, privacy_key = crypto.k2(netkey, b'\x00')
    privacy_random = self.get_privacy_random(iv_index, pdu)
    PECB = lib.crypto.block_ciphers.aes_ecb_encrypt(plaintext=privacy_random, key=privacy_key)
    return PECB

  def obfuscate_header(self, netkey, iv_index, ttl, seq, src, ctl, pdu):
    '''
    Mesh Profile 3.8.7.3

    netkey: 16 byte string
    iv_index: number, 4 bytes [0,4294967295]
    ttl: number, 7 bits [0,127]
    seq: number, 3 bytes, [0,16777215]
    src: number, 2 bytes, [0,65535]
    ctl: number, 1 bit [0,1]
    pdu: transport pdu (encrypted)

    returns:
      6 bytes of obfuscated network header
    '''
    PECB = self.get_PECB(netkey, iv_index, pdu)
    network_header = self.NETWORK_HEADER_PARSER.pack(ctl, ttl, seq, src)
    obfuscated_data = crypto.xor(network_header, PECB[:6])
    return obfuscated_data

  def unobfuscate_header(self, netkey, iv_index, obfuscated_data, pdu):
    '''
    Mesh Profile 3.8.7.3

    netkey: 16 byte string
    iv_index: number, 4 bytes [0,4294967295]
    obfuscated_data: 6 bytes of network header
    pdu: transport pdu (encrypted)

    returns:
      ctl, ttl, seq, src
    '''
    PECB = self.get_PECB(netkey, iv_index, pdu)
    data = crypto.xor(obfuscated_data, PECB[:6])
    ctl, ttl, seq, src = self.NETWORK_HEADER_PARSER.unpack(data)
    return ctl, ttl, seq, src

  def encrypt(self, encryption_key, nonce, dst, pdu, tag_length):
    '''
    Mesh Profile 3.8.7.2

    encryption_key: 16 bytes, from k2 derivation function
    nonce: 13 bytes, network nonce
    dst: number, 2 bytes, [0,65535]
    pdu: lower transport pdu
    tag_length: 4 for access message, 8 for control

    return:
      encrypted component of network pdu
    '''
    plaintext = self.TRANSORT_ENCRYPTION_MESSAGE_PARSER.pack(dst, pdu)
    return crypto.ccm_encrypt(encryption_key, nonce, plaintext, tag_length)

  def decrypt(self, encrypted_data, encryption_key, nonce, tag_length):
    '''
    Mesh Profile 3.8.7.2

    Takes the encrypted portion of the network pdu and decrypts it into lower transport pdu

    return:
      dst: number: 2 bytes
      pdu: transport pdu

    raises cryptography.exceptions.InvalidTag
    '''
    plaintext = crypto.ccm_decrypt(encryption_key, nonce, encrypted_data, tag_length)
    dst, pdu = self.TRANSORT_ENCRYPTION_MESSAGE_PARSER.unpack(plaintext)
    return dst, pdu

  def send_proxy_configuration_pdu(self, netkey, iv_index, ttl, seq, src, dst, ctl, pdu):
    '''
    Mesh Profile 6.5

    The proxy configuration pdu has the same format as a regular network pdu, but
    with a different nonce and proxy bearer opcode.

    netkey: byte string, 16 bytes
    iv_index: number, 4 bytes [0,4294967295]
    ttl: should be 0
    seq: number, 3 bytes, [0,16777215]
    src: number, 2 bytes, [0,65535]
    dst: should be 0
    ctl: should be 1
    pdu: lower lower transport pdu 8-128 bits
    returns:
      NID || Obfuscated Header (7 bytes) || Encrypted Transport PDU
    '''
    log.debug("Mesh Network TX: src %s dst %s ctl %s pdu %s seq %s", src, dst, ctl, pdu, seq)
    if dst != self.UNASSIGNED_ADDRESS or ctl != 1 or ttl != 0:
      log.error("Invalid proxy configuration pdu")
    nid, encryption_key, privacy_key = crypto.k2(netkey, b'\x00')
    nonce = self.get_proxy_nonce(
        iv_index=iv_index,
        ttl=ttl,
        seq=seq,
        src=src,
        ctl=ctl,
    )
    tag_length = 8 if ctl else 4
    encrypted_data = self.encrypt(
        encryption_key=encryption_key,
        nonce=nonce,
        dst=dst,
        pdu=pdu,
        tag_length=tag_length,
    )
    obfuscated_header = self.obfuscate_header(
        netkey=netkey,
        iv_index=iv_index,
        ttl=ttl,
        seq=seq,
        src=src,
        ctl=ctl,
        pdu=encrypted_data,
    )
    network_pdu = self.NETWORK_PDU_PARSER.pack(iv_index & 1, nid, obfuscated_header, encrypted_data)

    self.send_proxy_config_pdu_callback(network_pdu)

  def send_transport_pdu(self, netkey, iv_index, ttl, seq, src, dst, ctl, pdu):
    '''
    Mesh Profile 3.4.4

    Takes all relavent information for the network pdu and constructs it.

    netkey: byte string, 16 bytes
    iv_index: number, 4 bytes [0,4294967295]
    ttl: number, 7 bits [0,127]. If None, a default is used
    seq: number, 3 bytes, [0,16777215]
    src: number, 2 bytes, [0,65535]
    dst: number, 2 bytes, [0,65535]
    ctl: 0: access message, 32 bit NetMIC
         1: control message, 64 bit NetMIC
    pdu: lower lower transport pdu 8-128 bits

    returns:
      NID || Obfuscated Header (7 bytes) || Encrypted Transport PDU
    '''
    log.debug("Mesh Network TX: src %s dst %s ctl %s pdu %s seq %s", src, dst, ctl, pdu, seq)
    if ttl is None:
      ttl = self.TTL
    nid, encryption_key, privacy_key = crypto.k2(netkey, b'\x00')
    nonce = self.get_nonce(
        iv_index=iv_index,
        ttl=ttl,
        seq=seq,
        src=src,
        ctl=ctl,
    )
    tag_length = 8 if ctl else 4
    encrypted_data = self.encrypt(
        encryption_key=encryption_key,
        nonce=nonce,
        dst=dst,
        pdu=pdu,
        tag_length=tag_length,
    )
    obfuscated_header = self.obfuscate_header(
        netkey=netkey,
        iv_index=iv_index,
        ttl=ttl,
        seq=seq,
        src=src,
        ctl=ctl,
        pdu=encrypted_data,
    )
    network_pdu = self.NETWORK_PDU_PARSER.pack(iv_index & 1, nid, obfuscated_header, encrypted_data)

    self.send_network_pdu_callback(network_pdu)

  def receive_network_pdu(self, pdu):
    '''
    Mesh Profile 3.4.4

    Reverse of build_packet: takes a network pdu and unencrypts it.
    conditionally returns a transport pdu

    raises cryptography.exceptions.InvalidTag
    '''
    netkey = self.datastore.get_netkey()
    nid, encryption_key, privacy_key = crypto.k2(netkey, b'\x00')
    ivi, nid, obfuscated_header, encrypted_data = self.NETWORK_PDU_PARSER.unpack(pdu)
    iv_index = self.mesh_manager.get_iv_index_for_ivi(ivi)
    if iv_index is None:
      log.warning("Device not part of a network, unable to process PDU.")
      return

    ctl, ttl, seq, src = self.unobfuscate_header(
        netkey=netkey,
        iv_index=iv_index,
        obfuscated_data=obfuscated_header,
        pdu=encrypted_data,
    )

    # Message Replay Protection: Mesh Profile 3.8.8
    seqauth = (iv_index << 24) + seq

    log.debug("Bluetooth Mesh Network Packet src:%s seqauth: %s, %s, %s ",
              src, iv_index, seq, seqauth)
    last_seqauth = self.datastore.get_max_seqauth_for_source(src)
    if last_seqauth is not None and seqauth <= last_seqauth:
      log.warning("Bluetooth Mesh Network Packet src:%s lower seqauth: %s <= %s",
                  src, seqauth, last_seqauth)
      return

    tag_length = 8 if ctl else 4
    nonce = self.get_nonce(
        iv_index=iv_index,
        ttl=ttl,
        seq=seq,
        src=src,
        ctl=ctl,
    )

    try:
      dst, transport_pdu = self.decrypt(
          encrypted_data=encrypted_data,
          encryption_key=encryption_key,
          nonce=nonce,
          tag_length=tag_length,
      )
    except cryptography.exceptions.InvalidTag as e:
      log.warning("Invalid Bluetooth Mesh Network Packet from src:%s pdu:%s", src, pdu)
      return

    self.datastore.set_max_seqauth_for_source(src, seqauth)

    if dst == self.UNASSIGNED_ADDRESS and ctl == 1 and ttl == 0:
      log.info("Mesh Network RX configuration message")
      return

    node_address = self.datastore.get_node_address()
    if dst not in (node_address, self.BROADCAST_ADDRESS):
      log.debug("Mesh Packet meant for dst: %s node address: %s", dst, node_address)
      return

    self.receive_transport_pdu_callback(netkey, iv_index, ttl, seq, src, dst, ctl, transport_pdu)
