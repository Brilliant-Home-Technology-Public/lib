import logging

from lib.networking.bluetooth.mesh.mesh_types import ProxyMessageType
from lib.networking.bluetooth.mesh.mesh_types import ProxySARType
from lib.tools import bitstring_parser


log = logging.getLogger(__name__)


class ProxySARHandler:
  '''
  Specifies segmentation and reassembly of messages as part of the Proxy Protocol

     send_message            receive_network_pdu_callback OR
            V               receive_network_beacon_callback
            V                                ^
          |-------------------------------------|
          |            ProxySARHandler          |
          |_____________________________________|
            V                                ^
    send_packet_callback              receive_packet
  '''
  PROXY_PDU_PARSER = bitstring_parser.BitstringParser("uint:2, uint:6, bytes")

  def __init__(
      self,
      send_packet_callback,
      receive_network_pdu_callback,
      receive_network_beacon_callback,
      att_mtu,
  ):
    '''
    send_packet_callback: Callback for sending proxy pdus. Takes 1 argument, the pdu
    receive_network_pdu_callback: callback for netowrk pdus: Takes 1 argument, the pdu
    receive_network_beacon_callback: callback for network beacons. Takes 1 argument, the beacon
    att_mtu: Attribute Protocol Maximum Transmission Unit (bytes)
    '''
    self.send_packet_callback = send_packet_callback
    self.receive_network_pdu_callback = receive_network_pdu_callback
    self.receive_network_beacon_callback = receive_network_beacon_callback
    self.data_mtu = att_mtu - 1
    self.packet_buff = None

  def send_network_pdu(self, pdu):
    self.send_message(ProxyMessageType.NETWORK_PDU, pdu)

  def send_mesh_beacon(self, pdu):
    self.send_message(ProxyMessageType.MESH_BEACON, pdu)

  def send_proxy_config(self, pdu):
    self.send_message(ProxyMessageType.PROXY_CONFIGURATION, pdu)

  def send_message(self, message_type, message):
    '''
    Takes a network message and segments it if ncessary before transmission via proxy protocol

    message_type: ProxyMessageType
    message: beacon or network pdu
    '''
    log.debug("Mesh Bearer TX: message %s", message)
    proxy_pdus = []
    if len(message) <= self.data_mtu:
      # no segmentation required
      pdu = self.PROXY_PDU_PARSER.pack(ProxySARType.COMPLETE, message_type, message)
      proxy_pdus.append(pdu)
    else:
      # segmentation is required
      packets = [message[i:i + self.data_mtu] for i in range(0, len(message), self.data_mtu)]

      # label first packet with proper header
      first_packet = self.PROXY_PDU_PARSER.pack(ProxySARType.FIRST, message_type, packets[0])
      proxy_pdus.append(first_packet)

      # label middle packets (if any) with proper header
      for packet in packets[1:-1]:
        continuation_packet = self.PROXY_PDU_PARSER.pack(
            ProxySARType.CONTINUATION,
            message_type,
            packet,
        )
        proxy_pdus.append(continuation_packet)

      # label last packet with proper header
      last_packet = self.PROXY_PDU_PARSER.pack(ProxySARType.LAST, message_type, packets[-1])
      proxy_pdus.append(last_packet)

    for proxy_pdu in proxy_pdus:
      self.send_packet_callback(proxy_pdu)

  def receive_packet(self, packet):
    '''
    packet: proxy pdu
    '''
    unpacked = self.PROXY_PDU_PARSER.unpack(packet)
    sar_type, message_type, data = unpacked  # pylint: disable=unbalanced-tuple-unpacking

    log.debug(
        'Mesh Bearer (Proxy SAR) RX Type: %s %s for data: %s',
        ProxySARType(sar_type),
        ProxyMessageType(message_type),
        data,
    )

    if sar_type == ProxySARType.COMPLETE:
      self.packet_buff = data
      self.receive_message(message_type, self.packet_buff)
      self.packet_buff = None
    elif sar_type == ProxySARType.FIRST:
      self.packet_buff = data
    elif sar_type == ProxySARType.CONTINUATION:
      self.packet_buff += data
    elif sar_type == ProxySARType.LAST:
      self.packet_buff += data
      self.receive_message(message_type, self.packet_buff)
      self.packet_buff = None
    else:
      log.warning('Unexpected Proxy SAR Type: %s for proxy pdu: %s', sar_type, packet)

  def receive_message(self, message_type, message):
    if message_type == ProxyMessageType.NETWORK_PDU:
      self.receive_network_pdu_callback(message)
    elif message_type == ProxyMessageType.MESH_BEACON:
      self.receive_network_beacon_callback(message)
    elif message_type == ProxyMessageType.PROXY_CONFIGURATION:
      log.warning("Mesh Proxy Message proxy configuration type not handled")
    elif message_type == ProxyMessageType.PROVISIONING_PDU:
      log.warning("Mesh Proxy Message provisioning pdu type not handled")
    else:
      log.warning("Invalid proxy message type: %s", message_type)
