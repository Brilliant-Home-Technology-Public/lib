import abc
import collections
import struct

import lib.networking.bluetooth.exceptions
import thrift_types.mesh_dfu.ttypes as mesh_dfu_ttypes


class DfuVersion(abc.ABC):

  @abc.abstractmethod
  def serialize(self):
    pass

  @abc.abstractmethod
  def is_newer_than(self, other):
    pass

  @classmethod
  @abc.abstractmethod
  def construct_from_raw_version_data(cls, raw_data):
    pass

  @classmethod
  @abc.abstractmethod
  def construct_from_ready_packet(cls, ready_packet):
    pass


class DfuSoftdeviceVersion(DfuVersion):

  SOFTDEVICE_PACKET_FORMAT = "<H"

  def __init__(self, softdevice_version):
    self.softdevice_version = softdevice_version

  def serialize(self):
    return struct.pack(
        DfuSoftdeviceVersion.SOFTDEVICE_PACKET_FORMAT,
        self.softdevice_version,
    )

  def is_newer_than(self, other):
    return self.softdevice_version > other.softdevice_version

  @classmethod
  def construct_from_raw_version_data(cls, raw_data):
    softdevice_version = struct.unpack(
        DfuSoftdeviceVersion.SOFTDEVICE_PACKET_FORMAT,
        raw_data[0:2],
    )
    return cls(softdevice_version)

  @classmethod
  def construct_from_ready_packet(cls, ready_packet):
    softdevice_version = struct.unpack(
        DfuSoftdeviceVersion.SOFTDEVICE_PACKET_FORMAT,
        ready_packet[6:8],
    )
    return cls(softdevice_version)


class DfuBootloaderVersion(DfuVersion):

  BOOTLOADER_PACKET_FORMAT = "<BB"

  def __init__(self, bootloader_type, bootloader_ver):
    self.bootloader_type = bootloader_type
    self.bootloader_ver = bootloader_ver

  def serialize(self):
    return struct.pack(
        DfuBootloaderVersion.DfuBootloaderVersion,
        self.bootloader_type,
        self.bootloader_ver,
    )

  def is_newer_than(self, other):
    return (self.bootloader_type == other.bootloader_type and
            self.bootloader_ver > other.bootloader_ver)

  @classmethod
  def construct_from_raw_version_data(cls, raw_data):
    bootloader_type, bootloader_ver = struct.unpack(
        DfuBootloaderVersion.BOOTLOADER_PACKET_FORMAT,
        raw_data[0:2],
    )
    return cls(bootloader_type, bootloader_ver)

  @classmethod
  def construct_from_ready_packet(cls, ready_packet):
    bootloader_type, bootloader_ver = struct.unpack(
        DfuBootloaderVersion.BOOTLOADER_PACKET_FORMAT,
        ready_packet[6:8],
    )
    return cls(bootloader_type, bootloader_ver)


class DfuApplicationVersion(DfuVersion):

  APPLICATION_PACKET_FORMAT = "<IHI"

  def __init__(self, company_id, application_id, application_version):
    self.company_id = company_id
    self.application_id = application_id
    self.application_version = application_version

  def serialize(self):
    return struct.pack(
        DfuApplicationVersion.APPLICATION_PACKET_FORMAT,
        self.company_id,
        self.application_id,
        self.application_version
    )

  def is_newer_than(self, other):
    return (self.company_id == other.company_id and
            self.application_id == other.application_id and
            self.application_version > other.application_version)

  @classmethod
  def construct_from_raw_version_data(cls, raw_data):
    company_id, application_id, application_version = struct.unpack(
        DfuApplicationVersion.APPLICATION_PACKET_FORMAT,
        raw_data[0:10],
    )
    return cls(company_id, application_id, application_version)

  @classmethod
  def construct_from_ready_packet(cls, ready_packet):
    company_id, application_id, application_version = struct.unpack(
        DfuApplicationVersion.APPLICATION_PACKET_FORMAT,
        ready_packet[6:16],
    )
    return cls(company_id, application_id, application_version)


class DfuDataInfo:

  def __init__(self, data):
    self.dfu_type, self.start_addr, self.firmware_len = struct.unpack("<BII", data[0:9])
    self.signature_len = data[9] if len(data) > 64 else 0
    raw_version_data_offset = 10 + self.signature_len
    self.signature = data[10:raw_version_data_offset] if len(data) > 64 else []
    raw_version_data = data[raw_version_data_offset:]
    if self.dfu_type == mesh_dfu_ttypes.MeshDfuHexType.SOFTDEVICE:
      self.dfu_version = DfuSoftdeviceVersion.construct_from_raw_version_data(raw_version_data)
    elif self.dfu_type == mesh_dfu_ttypes.MeshDfuHexType.BOOTLOADER:
      self.dfu_version = DfuBootloaderVersion.construct_from_raw_version_data(raw_version_data)
    elif self.dfu_type == mesh_dfu_ttypes.MeshDfuHexType.APPLICATION:
      self.dfu_version = DfuApplicationVersion.construct_from_raw_version_data(raw_version_data)
    else:
      raise lib.networking.bluetooth.exceptions.InvalidMeshDFUTypeError("Unknown Dfu type found.")


FirmwareVersion = collections.namedtuple("FirmwareVersion",
                                         ["softdevice", "bootloader", "application"])


def decode_firmware_version(firmware_version_str):
  ''' @brief This function decodes the firmware version string.

      @param firmware_version_str: The firmware version string that consists of the following
       components in little endian ->
       softdevice ver (2 bytes)|bootloader id (1 byte)|bootloader ver (1 byte)|app ver (4 bytes)

      @return FirmwareVersion
  '''
  softdevice_ver, bootloader_id, bootloader_ver, application_ver = struct.unpack(
      "<HBBI",
      bytes.fromhex(firmware_version_str),
  )
  return FirmwareVersion(softdevice_ver, bootloader_ver, application_ver)
