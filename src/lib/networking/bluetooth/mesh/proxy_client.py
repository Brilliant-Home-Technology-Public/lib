import logging

from lib.networking.bluetooth.mesh import access
from lib.networking.bluetooth.mesh import beacon
from lib.networking.bluetooth.mesh import bearer
from lib.networking.bluetooth.mesh import crypto
from lib.networking.bluetooth.mesh import mesh_manager
from lib.networking.bluetooth.mesh import network
from lib.networking.bluetooth.mesh import transport
from lib.networking.bluetooth.mesh.mesh_types import ProxyConfigurationOpCode
from lib.networking.bluetooth.mesh.mesh_types import ProxyFilterType
from lib.queueing import timer_queue
from lib.tools import bitstring_parser


log = logging.getLogger(__name__)


class ProxyMeshClient:
  '''
  This class manages message passing between the various Bluetooth Mesh Layers

  The following functions can be called to transmit light and level model access messages
    message = self.access_handler.onoff_model.create_set_onoff_message(on)
        (OR)
    message = self.access_handler.level_model.create_set_level_message(level)
    self.send_access_message(dst, message)

  Light and level model updates from the mesh come in the form of a callback:
    - receive_message_callback(MessagePayload)

  Sending and receiving Mesh packets happen through the following functions:
    - send_pdu_callback(pdu)
    - receive_pdu(pdu)


        send_message                  receive_message_callback
            V                                ^
          |-------------------------------------|
          |        AccessMessageHandler         |
          |_____________________________________|
            V                                ^
            V                                ^
          |-------------------------------------|
          |        UpperTransportHandler        | --> control messages
          |_____________________________________|
            V                                ^
            V                                ^
          |-------------------------------------|
          |         LowerTransportHandler       |
          |_____________________________________|
            V                                ^
            V                                ^
          |-------------------------------------|
          |            NetworkHandler           | --> network configuration messages
          |_____________________________________|
            V                                ^
            V                                ^
          |-------------------------------------|
          |            ProxySARHandler          | --> proxy configuration + beacons
          |_____________________________________|
            V                                ^
       send_pdu_callback                  receive_pdu
            V                                ^
    [send blueooth packet]    [receive blueooth packet]

  '''

  def __init__(
      self,
      loop,
      send_pdu_callback,
      receive_message_callback,
      datastore,
      enable_iv_update_test_mode=False,
  ):
    '''
      send_pdu_callback: call this with a byte string to transmit a bluetooth packet to a network
      receive_message_callback: called with any state changes from nodes in the mesh network,
          taking a MessagePayload argument
      datastore: object that implements the AbstractMeshDatastore interface
    '''
    self.send_pdu_callback = send_pdu_callback
    self.receive_message_callback = receive_message_callback

    self.timer_queue = timer_queue.ThreadSafeTimerQueue(loop=loop)

    self.datastore = datastore
    self.beacon_handler = beacon.BeaconHandler()

    self.access_handler = access.AccessMessageHandler(
        mesh_update_callback=self.receive_message_callback,
    )
    self.mesh_manager = mesh_manager.MeshManager(
        loop=loop,
        datastore=self.datastore,
        beacon_handler=self.beacon_handler,
        send_network_beacon_callback=None,
        enable_iv_update_test_mode=enable_iv_update_test_mode,
    )
    self.upper_transport_handler = transport.UpperTransportHandler(
        datastore=self.datastore,
        mesh_manager=self.mesh_manager,
        send_upper_transport_pdu_callback=None,
        receive_message_callback=None,
    )
    self.lower_transport_handler = transport.LowerTransportHandler(
        timer_queue=self.timer_queue,
        datastore=self.datastore,
        mesh_manager=self.mesh_manager,
        send_lower_transport_pdu_callback=None,
        receive_upper_transport_pdu_callback=None,
    )
    self.network_handler = network.NetworkHandler(
        datastore=self.datastore,
        mesh_manager=self.mesh_manager,
        send_network_pdu_callback=None,
        send_proxy_config_pdu_callback=None,
        receive_transport_pdu_callback=None,
    )

    self.proxy_config_handler = ProxyConfigurationHandler(
        datastore=self.datastore,
        mesh_manager=self.mesh_manager,
        send_proxy_configuration_pdu_callback=None,
    )

    self.proxy_sar_handler = bearer.ProxySARHandler(
        send_packet_callback=self.send_pdu_callback,
        receive_network_pdu_callback=None,
        receive_network_beacon_callback=None,
        att_mtu=33,
    )

    # hook up input/outputs after classes have been instantiated
    self.upper_transport_handler.send_upper_transport_pdu_callback = self.lower_transport_handler.send_upper_transport_pdu
    self.upper_transport_handler.receive_message_callback = self.access_handler.receive_access_message

    self.lower_transport_handler.send_lower_transport_pdu_callback = self.network_handler.send_transport_pdu
    self.lower_transport_handler.receive_upper_transport_pdu_callback = self.upper_transport_handler.receive_upper_transport_pdu

    self.network_handler.send_network_pdu_callback = self.proxy_sar_handler.send_network_pdu
    self.network_handler.send_proxy_config_pdu_callback = self.proxy_sar_handler.send_proxy_config
    self.network_handler.receive_transport_pdu_callback = self.lower_transport_handler.receive_lower_transport_pdu

    self.proxy_sar_handler.receive_network_pdu_callback = self.network_handler.receive_network_pdu
    self.proxy_sar_handler.receive_network_beacon_callback = self.mesh_manager.receive_network_beacon

    self.mesh_manager.send_network_beacon_callback = self.proxy_sar_handler.send_mesh_beacon

    self.proxy_config_handler.send_proxy_configuration_pdu_callback = self.network_handler.send_proxy_configuration_pdu

  async def start(self):
    await self.timer_queue.start()
    await self.mesh_manager.start()

  async def shutdown(self):
    await self.timer_queue.shutdown()
    await self.mesh_manager.shutdown()

  def setup(self):
    pass

  def receive_pdu(self, pdu):
    '''
    called when a bluetooth packet is received
    pdu: bluetooth packet
    '''
    self.proxy_sar_handler.receive_packet(pdu)

  def _send_access_message(self, dst, message, app_key_field, send_count=1):
    '''
    dst: number, 2 bytes, [0,65535]
    message: ble mesh access message
    app_key_field: 1 for configuration messages, else 0
    send_count: for important messages, increasing send_count will increase
                delivery reliability
    '''

    log.info(
        "Sending access message. dst: %s, message: 0x%s, send_count: %s",
        dst,
        message.hex(),
        send_count,
    )
    netkey = self.datastore.get_netkey()
    src = self.datastore.get_node_address()
    ctl = 0  # 0 for access messages, 0 for control
    for _ in range(send_count):
      self.upper_transport_handler.send_message(
          netkey=netkey,
          akf=app_key_field,
          src=src,
          dst=dst,
          ctl=ctl,
          message=message,
      )

  def send_access_message(self, dst, message, send_count=1):
    '''
    For sending non-configuration access messages
    dst: number, 2 bytes, [0,65535]
    message: ble mesh access message (non-configuration message)
    send_count: for important messages, increasing send_count will increase
                delivery reliability
    '''
    self._send_access_message(
        dst=dst,
        message=message,
        app_key_field=1,
        send_count=send_count,
    )

  def send_configuration_access_message(self, dst, message, send_count=1):
    '''
    For sending configuration access messages
    dst: number, 2 bytes, [0,65535]
    message: ble mesh access message (configuration message)
    send_count: for important messages, increasing send_count will increase
                delivery reliability
    '''
    self._send_access_message(
        dst=dst,
        message=message,
        app_key_field=0,
        send_count=send_count,
    )

  def get_network_id(self):
    ''' Mesh Profile 3.8.6.3.2 Network Id is public information '''
    netkey = self.datastore.get_netkey()
    return crypto.k3(netkey)

  def initialize_broadcast_filter(self):
    '''
    Call this after connecting to a proxy server to get state updates on the
    broadcast address for mesh devices.
    '''
    self.proxy_config_handler.send_set_filter_type_pdu(ProxyFilterType.WHITE_LIST)
    self.proxy_config_handler.send_add_address_to_filter_pdu(0xFFFF)  # broadcast address


class ProxyConfigurationHandler:

  FILTER_TYPE_PDU_PARSER = bitstring_parser.BitstringParser("uint:8, uint:8")
  ADD_ADDRESS_PDU_PARSER = bitstring_parser.BitstringParser("uint:8, uintbe:16")

  def __init__(
      self,
      datastore,
      mesh_manager,
      send_proxy_configuration_pdu_callback,
  ):
    self.datastore = datastore
    self.mesh_manager = mesh_manager
    self.send_proxy_configuration_pdu_callback = send_proxy_configuration_pdu_callback

  def send_add_address_to_filter_pdu(self, address):
    '''
    address: unicast, group or virtual address
    '''
    pdu = self.ADD_ADDRESS_PDU_PARSER.pack(ProxyConfigurationOpCode.ADD_ADDRESS, address)
    self.send_proxy_configuration(pdu)

  def send_set_filter_type_pdu(self, filter_type):
    '''
    filter_type: ProxyFilterType
    '''
    pdu = self.FILTER_TYPE_PDU_PARSER.pack(ProxyConfigurationOpCode.SET_FILTER_TYPE, filter_type)
    self.send_proxy_configuration(pdu)

  def send_proxy_configuration(self, pdu):
    netkey = self.datastore.get_netkey()
    nonce_initializers = self.mesh_manager.get_nonce_initializers()
    if nonce_initializers is None:
      log.error("Proxy Client: Unable to send proxy configuration because IV index is None.")
      return
    ttl = 0
    src = self.datastore.get_node_address()
    dst = 0
    ctl = 1

    self.send_proxy_configuration_pdu_callback(
        netkey=netkey,
        iv_index=nonce_initializers.iv_index,
        ttl=ttl,
        seq=nonce_initializers.seq_num,
        src=src,
        dst=dst,
        ctl=ctl,
        pdu=pdu,
    )
