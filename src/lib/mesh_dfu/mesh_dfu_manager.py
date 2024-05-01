import collections
import json
import logging
import math
import os.path
import random
import struct

import aiofiles

from lib.mesh_dfu import dfu_version
import lib.mesh_dfu.exceptions as mesh_dfu_exceptions
import thrift_types.mesh_dfu.ttypes as mesh_dfu_ttypes


ManifestInfoKey = collections.namedtuple(
    "ManifestInfoKey",
    ["hex_type", "id"]
)

ManifestInfo = collections.namedtuple(
    "ManifestInfo",
    ["bin_filepath", "dat_filepath", "dfu_data_info"],
)

MIN_TRANSACTION_ID_VALUE = 0
MAX_TRANSACTION_ID_VALUE = 0xFFFFFFFF

# Packet structure definitions
# For more information, please go to:
# https://brillianthome.atlassian.net/wiki/spaces/HI/pages/277250227/Mesh+DFU
#
# Ready packet structure
# [PREFIX][TYPE][AUTHORITY][TRANSACTION_ID][COMPANY_ID][APP_ID][APP_VER][NETWORK_ID]
READY_PACKET_FORMAT = "<HBBIIHII"
READY_PACKET_AUTHORITY = 0x0F  # Bootloader and Application
# The type data in bitpacked as follows:
# [Softdevice | Bootloader | Application | BL info | RFU]
SOFTDEVICE_BITMASK = 1
BOOTLOADER_BITMASK = 2
APPLICATION_BITMASK = 4

# Start packet structure
# [PREFIX][INDEX][TRANSACTION_ID][START_ADDR][FIRMWARE_LEN/4][SIGNATURE_LEN][START_FLAG]
START_PACKET_FORMAT = "<HHIIIHB"
START_PACKET_INDEX = 0
START_PACKET_FLAG = 0x0C

# Data packet structure
# [PREFIX][SEGMENT_INDEX][TRANSACTION_ID][DATA_SEGMENT]
DATA_PACKET_PREFIX_FORMAT = "<HHI"

# FWID packet structure
# [PREFIX][SD_VERSION][BOOTLOADER_TYPE][BOOTLOADER_VER][COMPANY_ID][APPLICATION_ID][APPLICATION_VER][NETWORK_ID]
FWID_PACKET_FORMAT = "<HHBBIHII"

# Data request packet structure
# [PREFIX][SEGMENT_INDEX][TRANSACTION_ID]
DATA_REQUEST_PACKET_FORMAT = "<HHI"

# Data response prefix packet structure
# [PREFIX][SEGMENT_INDEX][TRANSACTION_ID]
DATA_RESPONSE_PREFIX_FORMAT = "<HHI"

# Header used by data/data request/data response packets
# [SEGMENT_INDEX][TRANSACTION_ID]
DATA_PACKET_COMMON_HEADER_FORMAT = "<HI"

# Firmware segment definitions
FW_SEGMENT_ALIGNMENT_ADDR = 0xFFFFFFFF

# Max packet size that we can advertise
DFU_PACKET_MAX_SIZE = 16

# For DFU, we have 2 ready and 1 start packet that is required for DFU
NUM_PREREQUISITE_PACKETS_FOR_DFU = 3

log = logging.getLogger(__name__)


class MeshDfuManager:
  '''
  Manager responsible for:
    1) Parsing the firmware manifest and binaries into update packets.s
    2) Decoding the incoming broadcast packets from mesh devices.
  '''

  # Dfu type information
  MESH_DFU_PACKET_FWID = 0xFFFE
  MESH_DFU_PACKET_STATE = 0xFFFD
  MESH_DFU_PACKET_DATA = 0xFFFC
  MESH_DFU_PACKET_DATA_REQ = 0xFFFB
  MESH_DFU_PACKET_DATA_RSP = 0xFFFA

  def __init__(self, loop):
    self._loop = loop
    self.hex_type_and_id_to_manifest_map = {}
    self.transaction_id_to_hextype_and_id_map = {}
    self.network_id = 0
    self.file_cache = {}

  async def get_file_data(self, filepath):
    if filepath not in self.file_cache:
      async with aiofiles.open(filepath, "rb", loop=self._loop) as fh:
        self.file_cache[filepath] = await fh.read()

    return self.file_cache[filepath]

  async def load_manifest_info_from_firmware_section(self, firmware_dirpath, firmware_info):
    dat_filepath = os.path.join(firmware_dirpath, firmware_info["dat_file"])
    dfu_init_packet_data = await self.get_file_data(dat_filepath)
    return ManifestInfo(
        bin_filepath=os.path.join(firmware_dirpath, firmware_info["bin_file"]),
        dat_filepath=dat_filepath,
        dfu_data_info=dfu_version.DfuDataInfo(dfu_init_packet_data),
    )

  async def register_firmware_manifest(self, firmware_dirpath):
    manifest_filepath = os.path.join(firmware_dirpath, "manifest.json")

    async with aiofiles.open(manifest_filepath, "r", loop=self._loop) as manifest_fh:
      manifest_data = await manifest_fh.read()
      manifest = json.loads(manifest_data).get("manifest")
      if not manifest:
        return

      application_firmware_info = manifest.get("application")
      if application_firmware_info:
        manifest_info = await self.load_manifest_info_from_firmware_section(
            firmware_dirpath,
            application_firmware_info,
        )
        manifest_info_key = ManifestInfoKey(
            mesh_dfu_ttypes.MeshDfuHexType.APPLICATION,
            manifest_info.dfu_data_info.dfu_version.application_id,
        )
        self.hex_type_and_id_to_manifest_map[manifest_info_key] = manifest_info

      bootloader_firmware_info = manifest.get("bootloader")
      if bootloader_firmware_info:
        manifest_info = await self.load_manifest_info_from_firmware_section(
            firmware_dirpath,
            bootloader_firmware_info,
        )
        manifest_info_key = ManifestInfoKey(
            mesh_dfu_ttypes.MeshDfuHexType.BOOTLOADER,
            manifest_info.dfu_data_info.dfu_version.bootloader_type,
        )
        self.hex_type_and_id_to_manifest_map[manifest_info_key] = manifest_info

  def get_manifest_info(self, hex_type, target_id):
    return self.hex_type_and_id_to_manifest_map.get(
        ManifestInfoKey(hex_type, target_id),
        None,
    )

  def generate_transaction_id(self, hex_type, target_id):
    '''
    Generates a new transaction ID for update.

    @hex_type: The type of update
    @id: The ID for the corresponding type
    '''
    new_transaction_id = random.randint(MIN_TRANSACTION_ID_VALUE, MAX_TRANSACTION_ID_VALUE)
    self.transaction_id_to_hextype_and_id_map[new_transaction_id] = ManifestInfoKey(
        hex_type,
        target_id,
    )
    return new_transaction_id

  def get_ready_packet(self, dfu_data_info, transaction_id):
    return struct.pack(
        READY_PACKET_FORMAT,
        MeshDfuManager.MESH_DFU_PACKET_STATE,
        dfu_data_info.dfu_type,
        READY_PACKET_AUTHORITY,
        transaction_id,
        dfu_data_info.dfu_version.company_id,
        dfu_data_info.dfu_version.application_id,
        dfu_data_info.dfu_version.application_version,
        self.network_id
    )

  def get_start_packet(self, dfu_data_info, transaction_id):
    return struct.pack(
        START_PACKET_FORMAT,
        MeshDfuManager.MESH_DFU_PACKET_DATA,
        START_PACKET_INDEX,
        transaction_id,
        dfu_data_info.start_addr,
        dfu_data_info.firmware_len // 4,
        dfu_data_info.signature_len,
        START_PACKET_FLAG,
    )

  @staticmethod
  def get_firmware_segment(dfu_data_info, firmware, firmware_section_index):
    '''
    This retrieves the correct segment based on the segment index

    @dfu_data_info: lib.mesh_dfu.dfu_version.DfuDataInfo for this update
    @firmware: The actual firmware data that was read from disk
    @firmware_section_index: The firmware is chunked into sections for
                             broadcast and this is the section index
                             to return to the caller of the function

    @return: Bytes for the firmware segment
    '''
    firmware_offset = firmware_section_index * DFU_PACKET_MAX_SIZE

    if firmware_offset >= len(firmware):
      raise mesh_dfu_exceptions.InvalidMeshDfuPacketError(
          "Firmware offset is larger than the actual size of firmware."
      )

    packet_size = DFU_PACKET_MAX_SIZE
    if firmware_section_index == 0 and dfu_data_info.start_addr != FW_SEGMENT_ALIGNMENT_ADDR:
      # If the segment is the first segment and the start address is at an offset from the
      # default start address, we need to return firmware segment at the correct offset.
      packet_size = DFU_PACKET_MAX_SIZE - (dfu_data_info.start_addr % DFU_PACKET_MAX_SIZE)
    elif firmware_offset + DFU_PACKET_MAX_SIZE > len(firmware):
      # If the last packet is smaller than DFU_PACKET_MAX_SIZE, compute the sizes correctly
      packet_size = len(firmware) - firmware_offset

    return firmware[firmware_offset:firmware_offset + packet_size]

  def is_signature_index(self, transaction_id, index):
    manifest_info_key = self.transaction_id_to_hextype_and_id_map.get(transaction_id)
    if not manifest_info_key:
      return False
    manifest_info = self.get_manifest_info(manifest_info_key.hex_type, manifest_info_key.id)
    if not manifest_info:
      return False

    firmware_segment_count = math.ceil(
        manifest_info.dfu_data_info.firmware_len / DFU_PACKET_MAX_SIZE
    )
    return index >= NUM_PREREQUISITE_PACKETS_FOR_DFU + firmware_segment_count

  async def get_regular_update_packet(self, transaction_id, index):
    ''' The purpose of this function is to return regular update packets based on the index
        The regular packets consists of:
          0) Ready packet
          1) Ready packet
          2) Start packet
          3...n) Firmware packets
          n+1...m) Signature packets

        Please note that the following is intentional, 2 ready packets are needed
        get the mesh device into the correct state.
        Go to https://brillianthome.atlassian.net/wiki/spaces/HI/pages/277250227/Mesh+DFU
        for more information and there is a state machine diagram in there.
    '''
    manifest_info_key = self.transaction_id_to_hextype_and_id_map.get(transaction_id)
    if not manifest_info_key:
      return None

    manifest_info = self.get_manifest_info(manifest_info_key.hex_type, manifest_info_key.id)
    if not manifest_info:
      return None

    dfu_data_info = manifest_info.dfu_data_info

    if index in (0, 1):
      # Return ready packet
      return self.get_ready_packet(dfu_data_info, transaction_id)

    if index == 2:
      # Return start packet
      return self.get_start_packet(dfu_data_info, transaction_id)

    # Return either firmware or signature packet depending on the index
    firmware = await self.get_file_data(manifest_info.bin_filepath)
    total_firmware_segments = math.ceil(len(firmware) / DFU_PACKET_MAX_SIZE)
    total_signature_segments = math.ceil(dfu_data_info.signature_len / DFU_PACKET_MAX_SIZE)
    # We consider the "body" to be the firmware + signature portion of the packets to send (i.e. we
    # exclude the ready and start packets)
    body_packet_index = index - NUM_PREREQUISITE_PACKETS_FOR_DFU
    if body_packet_index < total_firmware_segments:
      # Firmware packet
      firmware_index = body_packet_index
      data_packet = struct.pack(
          DATA_PACKET_PREFIX_FORMAT,
          MeshDfuManager.MESH_DFU_PACKET_DATA,
          firmware_index + 1,  # The segment index start from 1 for data segments
          transaction_id,
      )
      data_packet += MeshDfuManager.get_firmware_segment(dfu_data_info, firmware, firmware_index)
      return data_packet

    if body_packet_index < total_firmware_segments + total_signature_segments:
      # Signature packet
      signature_index = body_packet_index - total_firmware_segments
      signature_packet = struct.pack(
          DATA_PACKET_PREFIX_FORMAT,
          MeshDfuManager.MESH_DFU_PACKET_DATA,
          total_firmware_segments + signature_index + 1,  # The segment index continues from data seg
          transaction_id,
      )
      signature_offset = signature_index * DFU_PACKET_MAX_SIZE
      signature_packet += \
          dfu_data_info.signature[signature_offset:signature_offset + DFU_PACKET_MAX_SIZE]
      return signature_packet

    # We have no more packets to send ergo, return None
    return None

  @staticmethod
  def get_network_id_from_dfu_fwid_packet(fwid_packet):
    '''
    This returns none if the fwid_packet does not contain the mesh_network_id.
    Otherwise, this will return the network ID that was returned from the fwid packet
    '''
    if len(fwid_packet) < 18:
      return None
    *_, network_id = struct.unpack(FWID_PACKET_FORMAT, fwid_packet[0:18])

    return network_id

  @staticmethod
  def decode_packet_type(data):
    return struct.unpack("<H", data[0:2])[0]

  @staticmethod
  def decode_data_packet_common_header(data):
    return struct.unpack(
        DATA_PACKET_COMMON_HEADER_FORMAT,
        data[:6],
    )

  def decode_data_request_packet(self, data):
    return (self.decode_packet_type(data), *self.decode_data_packet_common_header(data[2:]))

  def get_manifest_info_key(self, transaction_id):
    return self.transaction_id_to_hextype_and_id_map.get(transaction_id)

  async def get_dfu_data_request_packet(self, data):
    # This is to support backward compatibility with the
    # old switch embedded code
    _, firmware_segment_index, transaction_id = self.decode_data_request_packet(data)
    return await self.get_dfu_data_request_packet_from_segment_and_transaction_id(
        firmware_segment_index,
        transaction_id,
    )

  async def get_dfu_data_request_packet_from_segment_and_transaction_id(self,
      firmware_segment_index,
      transaction_id):
    if firmware_segment_index == 0:
      # We've received a packet that is invalid,
      # we should simply return none here instead
      # of raising an error because the incoming
      # packet is a broadcast and could be either
      # malformed or problematic as a result of
      # malicious activity.
      log.debug("Mesh DFU: Invalid segment index.")
      return None
    if transaction_id not in self.transaction_id_to_hextype_and_id_map:
      # If the control receives a transaction ID that
      # it is unfamiliar with, return None to signify
      log.debug("Mesh DFU: Unknown transaction ID.")
      return None

    manifest_info_key = self.transaction_id_to_hextype_and_id_map[transaction_id]
    manifest_info = self.hex_type_and_id_to_manifest_map[manifest_info_key]
    firmware = await self.get_file_data(manifest_info.bin_filepath)
    # Please note that that the firmware segment index starts from 1
    # i.e: The update packet at index 0 corresponds to segment index 1.
    # As a result, when passing into get_firmware_segment, we should subtract 1
    # from firmware_segment_index
    #
    # Additionally, we assume that all data request packets will be for a firmware segment packet as
    # opposed to a signature packet (which we won't intentionally skip), though it's not clear if
    # this is actually a valid assumption to make. If it isn't, we'd need to allow this function to
    # return signature packets (similar to how get_regular_update_packet works).
    firmware_segment_packet = MeshDfuManager.get_firmware_segment(
        manifest_info.dfu_data_info,
        firmware,
        firmware_segment_index - 1,
    )
    data_request_response_packet = struct.pack(
        DATA_RESPONSE_PREFIX_FORMAT,
        MeshDfuManager.MESH_DFU_PACKET_DATA_RSP,
        firmware_segment_index,
        transaction_id,
    )
    data_request_response_packet += firmware_segment_packet
    return data_request_response_packet

  def get_update_version(self, hex_type, update_type_id):
    manifest_info_key = ManifestInfoKey(
        hex_type,
        update_type_id,
    )

    if manifest_info_key not in self.hex_type_and_id_to_manifest_map:
      return None

    manifest_info = self.hex_type_and_id_to_manifest_map[manifest_info_key]
    return manifest_info.dfu_data_info.dfu_version

  async def get_total_firmware_packet_count(self, transaction_id):
    ''' @brief This returns the total number of firmware packets

        @param transaction_id: The transaction ID for which the information is required

        @return: None if the transaction id is not recognized. The number of packets otherwise
    '''
    manifest_info_key = self.transaction_id_to_hextype_and_id_map.get(transaction_id)
    if not manifest_info_key:
      return None

    manifest_info = self.get_manifest_info(manifest_info_key.hex_type, manifest_info_key.id)
    if not manifest_info:
      return None

    dfu_data_info = manifest_info.dfu_data_info
    firmware = await self.get_file_data(manifest_info.bin_filepath)
    total_firmware_segments = math.ceil(len(firmware) / DFU_PACKET_MAX_SIZE)
    total_signature_segments = math.ceil(dfu_data_info.signature_len / DFU_PACKET_MAX_SIZE)
    # We have to add 3 to account for the 2 ready and 1 start packet
    return total_firmware_segments + total_signature_segments + NUM_PREREQUISITE_PACKETS_FOR_DFU


class DfuReadyPacketInfo:

  DFU_READY_DECODER_PREFIX = "<BBI"

  def __init__(self, ready_packet):
    raw_type, _, self.transaction_id = struct.unpack(
        DfuReadyPacketInfo.DFU_READY_DECODER_PREFIX,
        ready_packet[0:6],
    )
    self.dfu_type = DfuReadyPacketInfo.decode_ready_packet_type(raw_type)
    self.dfu_version = None
    self.network_id = None
    if self.dfu_type == mesh_dfu_ttypes.MeshDfuHexType.APPLICATION:
      self.dfu_version = dfu_version.DfuApplicationVersion.construct_from_ready_packet(
          ready_packet
      )
      if len(ready_packet) >= 20:
        self.network_id = struct.unpack("<I", ready_packet[16:20])[0]
    elif self.dfu_type == mesh_dfu_ttypes.MeshDfuHexType.BOOTLOADER:
      self.dfu_version = dfu_version.DfuBootloaderVersion.construct_from_ready_packet(
          ready_packet
      )
      if len(ready_packet) >= 12:
        self.network_id = struct.unpack("<I", ready_packet[8:12])[0]

  @staticmethod
  def decode_ready_packet_type(raw_type):
    if raw_type & APPLICATION_BITMASK:
      return mesh_dfu_ttypes.MeshDfuHexType.APPLICATION

    if raw_type & BOOTLOADER_BITMASK:
      return mesh_dfu_ttypes.MeshDfuHexType.BOOTLOADER

    return None


class DfuFWIDPacketInfo:

  FWID_DECODER_PREFIX = "<HBBIHI"

  def __init__(self, fwid_packet):
    # We first generate teh unpacked data tuple before assigning the individual property
    # their values because the list of data to unpack is long and there isn't really
    # a good way to not exceed the 100 word count limit
    unpacked_data = struct.unpack(DfuFWIDPacketInfo.FWID_DECODER_PREFIX, fwid_packet[0:14])
    self.softdevice_version = unpacked_data[0]
    self.bootloader_type = unpacked_data[1]
    self.bootloader_version = unpacked_data[2]
    self.company_id = unpacked_data[3]
    self.application_id = unpacked_data[4]
    self.application_version = unpacked_data[5]
    self.network_id = None
    if len(fwid_packet) >= 18:
      self.network_id = struct.unpack("<I", fwid_packet[14:18])[0]
    self.dfu_bootloader_version = dfu_version.DfuBootloaderVersion(
        self.bootloader_type,
        self.bootloader_version,
    )
    self.dfu_application_version = dfu_version.DfuApplicationVersion(
        self.company_id,
        self.application_id,
        self.application_version,
    )

  def as_version_string(self):
    ''' @brief Returns the version string.

        @return Hexstring of the following bytes in little endian ->
        softdevice ver (2 bytes)|bootloader id (1 byte)|bootloader ver (1 byte)|app ver (4 bytes)
    '''
    version_bytes = struct.pack(
        "<HBBI",
        self.softdevice_version,
        self.bootloader_type,
        self.bootloader_version,
        self.application_version,
    )
    return version_bytes.hex()
