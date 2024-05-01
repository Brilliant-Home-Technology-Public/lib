# pylint: disable=unbalanced-tuple-unpacking,not-callable
import logging

import cryptography

from lib.networking.bluetooth.mesh import crypto
from lib.networking.bluetooth.mesh import mesh_types
from lib.networking.bluetooth.mesh.mesh_types import NonceType
from lib.tools import bitstring_parser


log = logging.getLogger(__name__)


class MessageSarState:
  '''
  This class maintains the state of a partially sent or received Transport Messages.
  The behavior is specified in Mesh Profiles 3.5.3.4: Reassembly behavior
  The LowerTransportHandler may hold instances of this class
  '''

  def __init__(
      self,
      netkey,
      access_payload_key,
      akf,
      iv_index,
      seq,
      szmic,
      seq_zero,
      seg_n,
      src,
      dst,
      ctl,
      ttl,
      segments,
      ack_callback,
      drop_sar_state_callback,
      timer_queue,
  ):
    self.netkey = netkey
    self.access_payload_key = access_payload_key
    self.akf = akf
    self.iv_index = iv_index
    self.szmic = szmic
    self.seq = seq
    self.seq_zero = seq_zero
    self.seg_n = seg_n
    self.src = src
    self.dst = dst
    self.ctl = ctl
    self.ttl = ttl
    self.segments = segments
    self.ack_callback = ack_callback
    self.drop_sar_state_callback = drop_sar_state_callback
    self.timer_queue = timer_queue

    self.ack_timer_ms = 150 + 50 * self.ttl
    self.incomplete_timer_ms = 10 * 1000
    self.ack_timer = None
    self.incomplete_timer = None

    self.restart_ack_timer()
    self.restart_incomplete_timer()

  def stop_timers(self):
    # Prevent timers from cancelling themselves mid-execution
    if self.ack_timer and not self.ack_timer.is_firing():
      self.ack_timer.cancel()
    if self.incomplete_timer and not self.incomplete_timer.is_firing():
      self.incomplete_timer.cancel()

  def restart_ack_timer(self):
    if self.ack_timer:
      self.ack_timer.cancel()

    self.ack_timer = self.timer_queue.set_timer(
        timeout_ms=self.ack_timer_ms,
        callback_func=self.ack_callback,
        args=(self,),
    )

  def add_segment(self, seg_o, segment):
    self.segments[seg_o] = segment

    # memory leak guard
    segment_count = self.seg_n + 1
    if len(self.segments) > segment_count:
      self.drop_sar_state_callback(self)

  def restart_incomplete_timer(self):
    if self.incomplete_timer:
      self.incomplete_timer.cancel()

    self.incomplete_timer = self.timer_queue.set_timer(
        timeout_ms=self.incomplete_timer_ms,
        callback_func=self.drop_sar_state_callback,
        args=(self,),
    )

  def is_reassembly_complete(self):
    segment_count = self.seg_n + 1
    for seg_o in range(segment_count):
      if seg_o not in self.segments:
        return False
    return True

  def reassembled_message(self):
    # make sure is_reassembly_complete returns True before calling this
    pdu = b''
    segment_count = self.seg_n + 1
    for seg_o in range(segment_count):
      pdu += self.segments[seg_o]
    return pdu

  def construct_block_ack(self):
    block_ack = 0
    for seq_o, _ in self.segments.items():
      block_ack |= (1 << seq_o)
    return block_ack


class TransportHandler:

  def __init__(self, datastore, mesh_manager):
    self.datastore = datastore
    self.mesh_manager = mesh_manager

  def get_access_payload_key(self, node, akf):
    '''
    Returns 16-byte key for encrypting/decrypting access messages sent to/received from node
    with address node and with app key field akf (or None if key not found)
    '''
    return (
        self.datastore.get_appkey()
        if akf
        else self.datastore.get_device_key(node)
    )


class UpperTransportHandler(TransportHandler):
  '''
  Handles Upper Transport Layer encryption and decryption

  send_message                     receive_message_callback
          V                                ^
        |-------------------------------------|
        |         UpperTransportHandler       |
        |_____________________________________|
          V                                ^
  send_upper_transport_pdu_callback   receive_upper_transport_pdu
  '''

  TRANSPORT_NONCE_PARSER = bitstring_parser.BitstringParser(
      "uint:8, uint:1, pad:7, uintbe:24, uintbe:16, uintbe:16, uintbe:32",
  )

  def __init__(
      self,
      datastore,
      mesh_manager,
      send_upper_transport_pdu_callback,
      receive_message_callback,
  ):
    super().__init__(datastore, mesh_manager)
    self.send_upper_transport_pdu_callback = send_upper_transport_pdu_callback
    self.receive_message_callback = receive_message_callback

  def get_nonce(self, nonce_type, aszmic, iv_index, seq, src, dst):
    '''
    Mesh Profile 3.8.5

    nonce_type: NonceType (APPLICATION or DEVICE)
    aszmic: szmic if a segmented access message or 0 for all other message formats
    iv_index: number, 4 bytes [0,4294967295]
    seq: number, 3 bytes, [0,16777215]
    src: number, 2 bytes, [0,65535]
    dst: number, 2 bytes, [0,65535]

    returns:
      13 byte application or device nonce
    '''
    return self.TRANSPORT_NONCE_PARSER.pack(nonce_type, aszmic, seq, src, dst, iv_index)

  def encrypt(self, access_payload_key, nonce, message, tag_length):
    '''
    Mesh Profile 3.8.7.1

    Takes an Access Layer message and ecrypts it for the transport pdu

    access_payload_key: 16 byte string used to encrypt message
    nonce: 13 byte application nonce
    message: byte string, upper transport message
    tag_length: specifies size of TransMIC. 4 and 8 are valid options depending on message

    returns:
      encrypted transport pdu
    '''
    return crypto.ccm_encrypt(access_payload_key, nonce, message, tag_length)

  def decrypt(self, access_payload_key, nonce, encrypted_data, tag_length):
    '''
    Mesh Profile 3.8.7.1

    Takes transport pdu data and decrypts it

    access_payload_key: 16 byte string used to decrypt message
    nonce: 13 byte application nonce
    encrypted_data: byte string, encrypted upper transport message
    tag_length: specifies size of TransMIC. 4 and 8 are valid options depending on message

    returns:
      decrypted upper transport message

    raises cryptography.exceptions.InvalidTag
    '''
    return crypto.ccm_decrypt(access_payload_key, nonce, encrypted_data, tag_length)

  def send_message(self, netkey, akf, src, dst, ctl, message):
    '''

    Takes an access layer message, encypts it and sends it to the network
    layer. The message is segmented if necessary.

    Currently only supports access messages encrypted with application key

    netkey: byte string, 16 bytes
    akf: 1 for non-configuration messages, 0 for configuration messages
    src: number, 2 bytes, [0,65535]
    dst: number, 2 bytes, [0,65535]
    ctl: 0: access message, 32 bit NetMIC
         1: control message, 64 bit NetMIC

    message: acess message
    '''
    nonce_initializers = self.mesh_manager.get_nonce_initializers()
    if nonce_initializers is None:
      log.error("Mesh Transport TX: Failed to send message message because IV index is None.")
      return
    log.debug("Mesh Transport TX: src %s dst %s ctl %s message %s", src, dst, ctl, message)

    nonce_type = NonceType.APPLICATION if akf else NonceType.DEVICE
    nonce = self.get_nonce(
        nonce_type=nonce_type,
        aszmic=0,
        iv_index=nonce_initializers.iv_index,
        seq=nonce_initializers.seq_num,
        src=src,
        dst=dst,
    )
    tag_length = 4  # 8 if ctl else 4
    access_payload_key = self.get_access_payload_key(dst, akf)
    encrypted_message = self.encrypt(
        access_payload_key=access_payload_key,
        nonce=nonce,
        message=message,
        tag_length=tag_length,
    )
    self.send_upper_transport_pdu_callback(
        netkey=netkey,
        access_payload_key=access_payload_key,
        akf=akf,
        iv_index=nonce_initializers.iv_index,
        ttl=None,  # use default
        seq=nonce_initializers.seq_num,
        src=src,
        dst=dst,
        ctl=ctl,
        pdu=encrypted_message,
    )

  def receive_upper_transport_pdu(self, netkey, access_payload_key, akf, iv_index, seg, seq, szmic, src, dst, ctl, pdu):
    tag_length = 8 if ctl else 4
    nonce_type = NonceType.APPLICATION if akf else NonceType.DEVICE
    aszmic = szmic if seg else 0
    nonce = self.get_nonce(
        nonce_type=nonce_type,
        aszmic=aszmic,
        iv_index=iv_index,
        seq=seq,
        src=src,
        dst=dst,
    )
    try:
      message = self.decrypt(
          access_payload_key=access_payload_key,
          nonce=nonce,
          encrypted_data=pdu,
          tag_length=tag_length,
      )
    except cryptography.exceptions.InvalidTag as e:
      log.warning('Invalid Bluetooth Mesh Upper Transport packet:%s', pdu)
    else:
      self.receive_message_callback(src, message)


class LowerTransportHandler(TransportHandler):
  '''
  Handles Lower Transport Layer segmentation and reassembly

  send_upper_transport_pdu        receive_upper_transport_pdu_callback
            V                                ^
          |-------------------------------------|
          |         LowerTransportHandler       |
          |_____________________________________|
            V                                ^
   send_lower_transport_pdu_callback  receive_lower_transport_pdu
  '''
  UNSEGMENTED_ACCESS_PDU_PARSER = bitstring_parser.BitstringParser(
      "uint:1, uint:1, uint:6, bytes",
  )
  SEGMENTED_ACCESS_PDU_PARSER = bitstring_parser.BitstringParser(
      "uint:1, uint:1, uint:6, uint:1, uint:13, uint:5, uint:5, bytes",
  )
  SEGMENTED_ACK_PDU_PARSER = bitstring_parser.BitstringParser(
      "uint:1, pad:7, uint:1, uint:13, pad:2, uint:32",
  )
  SEGMENTATION_FIELD_PARSER = bitstring_parser.BitstringParser("uint:1, pad:7")
  UNSEGMENTED_CONTROL_PDU_PARSER = bitstring_parser.BitstringParser("uint:1, uint:7, bytes")
  SEGMENTED_CONTROL_PDU_PARSER = bitstring_parser.BitstringParser(
      "uint:1, uint:7, uint:1, uint:13, uint:5, uint:5, bytes",
  )
  SEQUENCE_NUMBER_UPPER_BITMASK = 0xffe000
  SEQUENCE_ZERO_NUM_BITS = 13

  ACCESS_PDU_UNSEGMENTED_LENGTH = 15
  ACCESS_PDU_SEGMENTED_LENGTH = 12
  CONTROL_PDU_SEGMENTED_LENGTH = 8

  SAR_SEGACK_TTL = 8

  def __init__(
      self,
      datastore,
      mesh_manager,
      timer_queue,
      send_lower_transport_pdu_callback,
      receive_upper_transport_pdu_callback,
  ):
    super().__init__(datastore, mesh_manager)
    self.timer_queue = timer_queue
    self.send_lower_transport_pdu_callback = send_lower_transport_pdu_callback
    self.receive_upper_transport_pdu_callback = receive_upper_transport_pdu_callback
    # NOTE: We include access message-related callbacks at the transport layer so that we can
    # surface segmentation information
    self.access_message_packet_handled_callback = None
    self.complete_access_message_handled_callback = None
    self.receive_packet_buffers = {}  # key: seq_zero, value: MessageSarState
    self.transmit_packet_buffers = {}  # key: seq_zero, value: MessageSarState

  def send_upper_transport_pdu(self, netkey, access_payload_key, akf, iv_index, ttl, seq, src, dst, ctl, pdu):
    # TODO: handle control messages
    aid = crypto.k4(access_payload_key) if akf else 0
    transport_pdus = []
    segmented = len(pdu) > self.ACCESS_PDU_UNSEGMENTED_LENGTH
    if segmented:
      # access message requires segmentation
      segments = [
          pdu[i:i + self.ACCESS_PDU_SEGMENTED_LENGTH]
          for i in range(0, len(pdu), self.ACCESS_PDU_SEGMENTED_LENGTH)
      ]
      seq_zero = seq & 0x1fff
      seg_n = len(segments) - 1
      szmic = 0
      for seg_o, segment in enumerate(segments):
        pdu = self.SEGMENTED_ACCESS_PDU_PARSER.pack(
            1,  # SEG = 1
            akf,
            aid,
            szmic,
            seq_zero,
            seg_o,
            seg_n,
            segment,
        )
        transport_pdus.append(pdu)
    else:
      # no segmentation required
      pdu = self.UNSEGMENTED_ACCESS_PDU_PARSER.pack(
          0,  # SEG = 0,
          akf,
          aid,
          pdu,
      )
      transport_pdus.append(pdu)

    # take segmented pdus and pass them on for further processing
    self.send_lower_transport_pdu_callback(
        netkey=netkey,
        iv_index=iv_index,
        ttl=None,  # use default
        seq=seq,
        src=src,
        dst=dst,
        ctl=ctl,
        pdu=transport_pdus[0],
    )
    self.on_access_message_packet_handled(False, segmented, src, dst)

    for transport_pdu in transport_pdus[1:]:
      nonce_initializers = self.mesh_manager.get_nonce_initializers()
      self.send_lower_transport_pdu_callback(
          netkey=netkey,
          iv_index=nonce_initializers.iv_index,
          ttl=None,  # use default
          seq=nonce_initializers.seq_num,
          src=src,
          dst=dst,
          ctl=ctl,
          pdu=transport_pdu,
      )
      self.on_access_message_packet_handled(False, segmented, src, dst)

    self.on_complete_access_message_handled(False, segmented, src, dst)

  def on_access_message_packet_handled(self, inbound, segmented, src_address, dst_address):
    """ Called any time an access message packet is sent or received.

    @param inbound: True if control is receiving the packet, otherwise False
    @param segmented: True if the packet is part of a segmented message, otherwise False
    @param src_address: Unicast address of the device that sent the message
    @param dst_address: Unicast address of the device that the message was sent to
    """
    if self.access_message_packet_handled_callback is not None:
      self.access_message_packet_handled_callback(
          inbound=inbound,
          segmented=segmented,
          src_address=src_address,
          dst_address=dst_address,
      )

  def on_complete_access_message_handled(self, inbound, segmented, src_address, dst_address):
    """ Called any time a complete access message is sent or received.

    See on_access_message_packet_handled for parameter details.
    """
    if self.complete_access_message_handled_callback is not None:
      self.complete_access_message_handled_callback(
          inbound=inbound,
          segmented=segmented,
          src_address=src_address,
          dst_address=dst_address,
      )

  def receive_lower_transport_pdu(self, netkey, iv_index, ttl, seq, src, dst, ctl, packet):
    log.debug('Mesh Transport RX: seq %s src %s dst %s ctl %s: %s', seq, src, dst, ctl, packet)
    seg = self.SEGMENTATION_FIELD_PARSER.unpack(packet[:1])[0]
    if ctl == 0:
      self.on_access_message_packet_handled(True, seg == 1, src, dst)
      if seg == 0:
        self.on_complete_access_message_handled(True, False, src, dst)

    if seg == 1:
      self.receive_segmented_packet(netkey, iv_index, seq, src, dst, ctl, packet)
    elif ctl == 0:
      self.receive_unsegmented_access_packet(netkey, iv_index, seq, src, dst, packet)
    elif ctl == 1:
      self.receive_unsegmented_control_packet(netkey, iv_index, seq, src, dst, packet)

  def receive_segmented_packet(self, netkey, iv_index, seq, src, dst, ctl, packet):
    seq_zero = 0
    seg_o = 0
    seg_n = 0
    akf = 1
    szmic = 0
    if ctl:
      # Mesh Profile 3.5.2.4: Segmented Control Message
      seg, opcode, rfu, seq_zero, seg_o, seg_n, segment = (
          self.SEGMENTED_CONTROL_PDU_PARSER.unpack(packet)
      )
      log.debug(
          "Mesh Transport RX segmented control: "
          "src:%s seg:%s opcode:0x%x rfu:%s seq_zero:%s seg_o:%s seg_n:%s segment:%s",
          src, seg, opcode, rfu, seq_zero, seg_o, seg_n, segment,
      )
    else:
      # Mesh Profile 3.5.2.2: Segmented Access Message
      seg, akf, aid, szmic, seq_zero, seg_o, seg_n, segment = (
          self.SEGMENTED_ACCESS_PDU_PARSER.unpack(packet)
      )
      log.debug(
          "Mesh Transport RX segmented access: "
          "src:%s seg:%s akf:%s aid:%s szmic:%s seq_zero:%s seg_o:%s seg_n:%s segment:%s",
          src, seg, akf, aid, szmic, seq_zero, seg_o, seg_n, segment,
      )

    if seq_zero in self.receive_packet_buffers:
      first_src = self.receive_packet_buffers[seq_zero].src
      if src != first_src:
        log.warning('Mesh Transport RX segmented message from different sources: %s, %s', first_src, src)
        return

      sar_state = self.receive_packet_buffers[seq_zero]
      sar_state.segments[seg_o] = segment

      # maybe restart ack_timer
      if not sar_state.ack_timer.is_alive():
        sar_state.restart_ack_timer()
      # restart incomplete timer
      sar_state.restart_incomplete_timer()
    else:
      segments = {seg_o: segment}
      sar_state = MessageSarState(
          netkey=netkey,
          access_payload_key=self.get_access_payload_key(src, akf),
          akf=akf,
          iv_index=iv_index,
          seq=seq,
          szmic=szmic,
          seq_zero=seq_zero,
          seg_n=seg_n,
          src=src,
          dst=dst,
          ctl=ctl,
          ttl=self.SAR_SEGACK_TTL,
          segments=segments,
          ack_callback=self.ack_segmented_message,
          drop_sar_state_callback=self.drop_sar_state,
          timer_queue=self.timer_queue,
      )
      self.receive_packet_buffers[seq_zero] = sar_state

    self.check_if_segmented_message_is_complete(sar_state)

  def drop_sar_state(self, sar_state):
    sar_state.stop_timers()
    self.receive_packet_buffers.pop(sar_state.seq_zero, None)
    if not sar_state.is_reassembly_complete():
      log.warning("Dropping incomplete SAR state: "
                  "src:%s dst:%s seq_zero:%s seg_n:%s received:%s",
                  sar_state.src,
                  sar_state.dst,
                  sar_state.seq_zero,
                  sar_state.seg_n,
                  sorted(sar_state.segments.keys()))

  def receive_unsegmented_access_packet(self, netkey, iv_index, seq, src, dst, packet):
    seg, akf, aid, pdu = self.UNSEGMENTED_ACCESS_PDU_PARSER.unpack(packet)
    log.debug(
        'Mesh Transport RX unsegmented access: src:%s seg:%s akf:%s aid:%d pdu:%s',
        src,
        seg,
        akf,
        aid,
        pdu,
    )
    self.receive_upper_transport_pdu_callback(
        netkey=netkey,
        access_payload_key=self.get_access_payload_key(src, akf),
        akf=akf,
        iv_index=iv_index,
        seg=0,
        seq=seq,
        szmic=0,
        src=src,
        dst=dst,
        ctl=0,
        pdu=pdu,
    )

  def receive_unsegmented_control_packet(self, netkey, iv_index, seq, src, dst, packet):
    # Mesh Profile 3.5.2.3
    # TODO: implement
    seg, opcode, params = self.UNSEGMENTED_CONTROL_PDU_PARSER.unpack(packet)
    if opcode == 0:
      self.handle_segmented_ack_message(netkey, iv_index, seq, src, dst, packet)
    else:
      log.info('Mesh Transport RX unsegmented control: opcode 0x%x params %s', opcode, params)

  def check_if_segmented_message_is_complete(self, sar_state):
    if not sar_state.is_reassembly_complete():
      return

    # segmented pdu is complete
    self.drop_sar_state(sar_state)
    self.ack_segmented_message(sar_state)
    pdu = sar_state.reassembled_message()
    # Reconstruct the sequence number used for upper transport encryption.
    # Lower 13 bits are in seq_zero; higher 11 bits can be taken from sequence number from any
    # received segment
    seq = (self.SEQUENCE_NUMBER_UPPER_BITMASK & sar_state.seq) | sar_state.seq_zero
    if seq > sar_state.seq:
      # Handle case where upper bits have just been incremented by a rollover
      seq -= (1 << self.SEQUENCE_ZERO_NUM_BITS)

    self.receive_upper_transport_pdu_callback(
        netkey=sar_state.netkey,
        access_payload_key=sar_state.access_payload_key,
        akf=sar_state.akf,
        iv_index=sar_state.iv_index,
        seg=1,
        seq=seq,
        szmic=sar_state.szmic,
        src=sar_state.src,
        dst=sar_state.dst,
        ctl=sar_state.ctl,
        pdu=pdu,
    )
    if sar_state.ctl == 0:
      self.on_complete_access_message_handled(True, True, sar_state.src, sar_state.dst)

  def ack_segmented_message(self, sar_state):
    ''' sar_state: MessageSarState namedtuple '''
    if mesh_types.address_to_type(sar_state.dst) != mesh_types.AddressType.UNICAST:
      # Per section 3.5.3.3 of Mesh Profile spec, acknowledgements should not be sent when the
      # segmented message is directed to a virtual/group address
      log.debug("Not sending ack for message sent to non-unicast address: %#0x", sar_state.dst)
      return

    nonce_initializers = self.mesh_manager.get_nonce_initializers()
    block_ack = sar_state.construct_block_ack()
    pdu = self.SEGMENTED_ACK_PDU_PARSER.pack(
        0,  # SEG = 0
        0,  # OBO = 0
        sar_state.seq_zero,
        block_ack,
    )

    self.send_lower_transport_pdu_callback(
        netkey=sar_state.netkey,
        iv_index=nonce_initializers.iv_index,
        ttl=self.SAR_SEGACK_TTL,
        seq=nonce_initializers.seq_num,
        src=sar_state.dst,  # swap src and dst
        dst=sar_state.src,  # swap src and dst
        ctl=1,
        pdu=pdu,
    )

  def handle_segmented_ack_message(self, netkey, iv_index, seq, src, dst, packet):
    # TODO: implement
    seg, obo, seq_zero, block_ack = self.SEGMENTED_ACK_PDU_PARSER.unpack(packet)

    log.info('Mesh Transport ack RX: seg %s obo %s seq_zero %s block_ack %s',
        seg,
        obo,
        seq_zero,
        block_ack,
    )
