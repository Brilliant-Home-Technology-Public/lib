from collections import defaultdict
import copy
import dataclasses
import hashlib
import logging
import typing

from lib import serialization
import lib.message_bus_api.device_utils
import thrift_types.message_bus.ttypes as mb_ttypes
import thrift_types.protocol.ttypes as protocol_ttypes


log = logging.getLogger(__name__)


class PeripheralCheckpointProtocol(typing.Protocol):
  timestamp: int
  integrity_checksum: bytes
  owning_device_id: str
  ownership_timestamp: int


class DeviceCheckpointProtocol(typing.Protocol):
  timestamp: int
  integrity_checksum: bytes
  peripheral_checkpoints_by_name: dict[str, PeripheralCheckpointProtocol]
  relaying_device_id: str
  relay_timestamp: int


@dataclasses.dataclass
class PeripheralCheckpointsDifference:
  """All of the differences between two sets of peripheral checkpoints.

  Attributes:
    peripherals_unknown_to_me: The set of peripheral names that the peer knows about, but I do not.
    peripherals_unknown_to_peer: The set of peripheral names that I know about, but the peer does
        not.
    divergent_peripherals: The set of peripheral names where the peer and I have different
        integrity_checksums but same timestamps.
    peripherals_out_of_sync: The set of peripheral names where the peer and I have different
        integrity_checksums and different timestamps.
  """
  peripherals_unknown_to_me: set[str] = dataclasses.field(default_factory=set)
  peripherals_unknown_to_peer: set[str] = dataclasses.field(default_factory=set)
  divergent_peripherals: set[str] = dataclasses.field(default_factory=set)
  peripherals_out_of_sync: set[str] = dataclasses.field(default_factory=set)
  # FIXME: Remove this after upgrading Cython. https://github.com/cython/cython/issues/2552
  __annotations__ = dict(
      peripherals_unknown_to_me=typing.Set[str],
      peripherals_unknown_to_peer=typing.Set[str],
      divergent_peripherals=typing.Set[str],
      peripherals_out_of_sync=typing.Set[str],
  )


@dataclasses.dataclass
class DeviceCheckpointsDifference:
  """
  Attributes:
    device_ids_unknown_to_me: The set of device IDs that the peer knows about, but I do not.
    device_ids_unknown_to_peer: The set of device IDs that I know about, but the peer does not.
    devices_out_of_sync_by_id: A mapping of device ID to PeripheralCheckpointsDifference for all
        devices where the peer and I have different integrity_checksums and different timestamps.
    divergent_devices: The set of device IDs where the peer and I have different
        integrity_checksums but same timestamps.
  """
  device_ids_unknown_to_me: set[str] = dataclasses.field(default_factory=set)
  device_ids_unknown_to_peer: set[str] = dataclasses.field(default_factory=set)
  devices_out_of_sync_by_id: defaultdict[str, PeripheralCheckpointsDifference] = dataclasses.field(
      default_factory=lambda: defaultdict(PeripheralCheckpointsDifference),
  )
  divergent_devices: set[str] = dataclasses.field(default_factory=set)
  # FIXME: Remove this after upgrading Cython. https://github.com/cython/cython/issues/2552
  __annotations__ = dict(
      device_ids_unknown_to_me=typing.Set[str],
      device_ids_unknown_to_peer=typing.Set[str],
      devices_out_of_sync_by_id=typing.Dict[str, PeripheralCheckpointsDifference],
      divergent_devices=typing.Set[str],
  )


def _encode_for_checksum(thrift_obj):
  return serialization.serialize(
      thrift_obj,
      protocol=protocol_ttypes.SerializationProtocol.THRIFT_BINARY,
  )


def calculate_peripheral_checksum(peripheral: mb_ttypes.Peripheral) -> bytes:
  """Calculates the peripheral's checksum.

  peripheral: The Peripheral for which to calculate the checksum.

  Returns: The peripheral's checksum as bytes.
  """
  bare_peripheral = copy.copy(peripheral)
  bare_peripheral.version = None  # ignore version for checksum calculation.
  # Remove variables before hashing because they may not be ordered consistently.
  bare_peripheral.variables = {}
  bare_peripheral.deleted_variables = []
  hasher = hashlib.md5()
  hasher.update(_encode_for_checksum(bare_peripheral))

  deleted_variables_map = {
      deleted_var.variable_name: deleted_var
      for deleted_var in peripheral.deleted_variables
  }

  all_known_var_names = deleted_variables_map.keys() | peripheral.variables.keys()

  for variable_name in sorted(all_known_var_names):
    if variable_name in peripheral.variables:
      to_hash = peripheral.variables[variable_name]
    else:
      to_hash = deleted_variables_map[variable_name]

    hasher.update(_encode_for_checksum(to_hash))
  return hasher.digest()


def calculate_device_checksum(
    device: mb_ttypes.Device,
    peripheral_checkpoints_by_name: typing.Dict[str, PeripheralCheckpointProtocol]
) -> bytes:
  """Calculate the device's checksum from the device's id, timestamp, device_type, and version
  fields and a concatenation of all the peripheral checksums.

  device: The Device for which to calculate the checksum.
  peripheral_checkpoints_by_name: A dictionary mapping peripheral names to peripheral checkpoints.

  Returns: The device's checksum as bytes.
  """
  bare_device = copy.copy(device)
  bare_device.peripherals = {}
  bare_device.version = None  # ignore version for checksum calculation.

  hasher = hashlib.md5()
  hasher.update(_encode_for_checksum(bare_device))
  for _, peripheral in sorted(peripheral_checkpoints_by_name.items()):
    hasher.update(peripheral.integrity_checksum)
  return hasher.digest()


def compare_device_checkpoints(
    my_device_checkpoints_by_id: typing.Dict[str, DeviceCheckpointProtocol],
    peer_device_checkpoints_by_id: typing.Dict[str, DeviceCheckpointProtocol],
) -> DeviceCheckpointsDifference:
  """Compares two sets of device checkpoints and returns a DeviceCheckpointsDifference object
  detailing the differences between the two sets of checkpoints.

  Args:
    my_device_checkpoints_by_id: A dictionary mapping the caller's set of known device ids to their
        corresponding device checkpoints.
    peer_device_checkpoints_by_id A dictionary mapping the peer's set of known device ids to their
        corresponding device checkpoints.

  Returns:
    A DeviceCheckpointsDifference object detailing the differences between the two sets of
    checkpoints.
  """
  device_checkpoints_difference = DeviceCheckpointsDifference()
  # Find relevant devices that the peer knows about, but are unknown to me.
  for device_id in peer_device_checkpoints_by_id:
    if device_id in my_device_checkpoints_by_id:
      continue

    if device_id in lib.message_bus_api.device_utils.KNOWN_VIRTUAL_DEVICE_IDS:
      # Ignore virtual devices. We don't support any type of deletion for virtual devices. Thus,
      # there is nothing to send to cause the peer to change its state.
      continue

    device_checkpoints_difference.device_ids_unknown_to_me.add(device_id)

  # Determine if a device is out of sync:
  for device_id, device_checkpoint in my_device_checkpoints_by_id.items():
    peer_device_checkpoint = peer_device_checkpoints_by_id.get(device_id, None)
    if not peer_device_checkpoint:
      device_checkpoints_difference.device_ids_unknown_to_peer.add(device_id)
      continue

    if device_checkpoint.integrity_checksum == peer_device_checkpoint.integrity_checksum:
      if device_checkpoint.timestamp != peer_device_checkpoint.timestamp:
        # This is probably only possible if there is a bug in the checksum calculation. After
        # validating the flow for a bit, we can probably delete this.
        log.error("Device %s has the same integrity_checksum, but different timestamps! Me: %s, "
                  "Peer: %s", device_id, device_checkpoint.timestamp,
                  peer_device_checkpoint.timestamp)
      continue

    # The device checksums do NOT match.
    if device_checkpoint.timestamp == peer_device_checkpoint.timestamp:
      # Since the checksums don't match but the timestamps do match, the timestamps are incorrect.
      device_checkpoints_difference.divergent_devices.add(device_id)

    # Find any peripherals that the peer knows about, but are unknown to me.
    for peripheral_name in peer_device_checkpoint.peripheral_checkpoints_by_name:
      if peripheral_name not in device_checkpoint.peripheral_checkpoints_by_name:
        device_checkpoints_difference.devices_out_of_sync_by_id[
            device_id
        ].peripherals_unknown_to_me.add(peripheral_name)

    for (peripheral_name,
         peripheral_checkpoint) in device_checkpoint.peripheral_checkpoints_by_name.items():
      peer_peripheral_checkpoint = peer_device_checkpoint.peripheral_checkpoints_by_name.get(
          peripheral_name, None
      )
      if not peer_peripheral_checkpoint:
        device_checkpoints_difference.devices_out_of_sync_by_id[
            device_id
        ].peripherals_unknown_to_peer.add(peripheral_name)
        continue

      if peripheral_checkpoint.integrity_checksum == peer_peripheral_checkpoint.integrity_checksum:
        if peripheral_checkpoint.timestamp != peer_peripheral_checkpoint.timestamp:
          # This is probably only possible if there is a bug in the checksum calculation. After
          # validating the flow for a bit, we can probably delete this.
          log.error("Peripheral %s in device %s has the same integrity_checksum, but different "
                    "timestamps! Me: %s, Peer: %s", peripheral_name, device_id,
                    peripheral_checkpoint.timestamp, peer_peripheral_checkpoint.timestamp)
        continue

      # The peripheral checksums do NOT match.
      if peripheral_checkpoint.timestamp == peer_peripheral_checkpoint.timestamp:
        # Since the checksums don't match but the timestamps do match, the timestamps are incorrect.
        device_checkpoints_difference.devices_out_of_sync_by_id[
            device_id
        ].divergent_peripherals.add(peripheral_name)
        continue

      # If the peer has a newer timestamp, then we probably don't need to do anything. The peer
      # could be directly connected to another device and have newer information.
      if peripheral_checkpoint.timestamp < peer_peripheral_checkpoint.timestamp:
        continue

      device_checkpoints_difference.devices_out_of_sync_by_id[
          device_id
      ].peripherals_out_of_sync.add(peripheral_name)

  return device_checkpoints_difference


def generate_modified_peripheral(
    peripheral: mb_ttypes.Peripheral,
    peer_peripheral_checkpoint_timestamp: int | None,
) -> mb_ttypes.ModifiedPeripheral:
  """Generate a ModifiedPeripheral that includes all of the variables and deleted_variables that
  have a newer timestamp than the peer's PeripheralCheckpoint timestamp.

  To generate a ModifiedPeripheral for a brand new Peripheral, set the
  peer_peripheral_checkpoint_timestamp to None.

  Args:
    peripheral: The full Peripheral from which to generate the ModifiedPeripheral.
    peer_peripheral_checkpoint_timestamp: The timestamp of the peer's PeripheralCheckpoint.

  Returns:
    A ModifiedPeripheral that includes all of the variables and deleted_variables that have a newer
    timestamp than the peer's PeripheralCheckpoint timestamp.
  """
  modified_variables = [
      mb_ttypes.ModifiedVariable(
          variable_name=variable_name,
          variable=variable,
      ) for variable_name, variable in peripheral.variables.items()
      if peer_peripheral_checkpoint_timestamp is None
      # Hack: account for Variables with `timestamp=None`, which unfortunately can still exist
      or (variable.timestamp or 0) > peer_peripheral_checkpoint_timestamp
  ]
  modified_peripheral = mb_ttypes.ModifiedPeripheral(
      deleted=False,
      dynamic_variable_prefix=peripheral.dynamic_variable_prefix,
      modified_variables=modified_variables,
      peripheral_id=peripheral.name,
      peripheral_type=peripheral.peripheral_type,
      peripheral_type_changed=True,
      peripheral_status_changed=True,
      prior_timestamp=peer_peripheral_checkpoint_timestamp,
      status=peripheral.status,
      timestamp=peripheral.timestamp,
  )
  for deleted_variable in peripheral.deleted_variables:
    if (peer_peripheral_checkpoint_timestamp is not None
        and deleted_variable.deletion_timestamp > peer_peripheral_checkpoint_timestamp):
      modified_peripheral.modified_variables.append(deleted_variable)
    else:
      modified_peripheral.prior_deleted_variables.append(deleted_variable)
  return modified_peripheral
