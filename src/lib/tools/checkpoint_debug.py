import io
import typing

from lib.tools import indenting_printer
import thrift_types.remote_bridge.ttypes as remote_bridge_ttypes


def format_checkpoints(
    device_checkpoints_by_id: typing.Dict[str, remote_bridge_ttypes.DeviceCheckpoint],
) -> str:
  results = io.StringIO()
  printer = indenting_printer.IndentingPrinter(tab='\t', outfile=results)
  for device_id in sorted(device_checkpoints_by_id):
    device_checkpoint = device_checkpoints_by_id[device_id]
    printer.write(f"Device: {device_id}")
    with printer.indented():
      printer.write(f"Timestamp: {device_checkpoint.timestamp}")
      printer.write(f"Checksum: {device_checkpoint.integrity_checksum.hex()}")
      if device_checkpoint.relaying_device_id:
        printer.write(f"Relaying Device: {device_checkpoint.relaying_device_id}")
        printer.write(f"Relay Timestamp: {device_checkpoint.relay_timestamp}")

      for name in sorted(device_checkpoint.peripheral_checkpoints_by_name):
        printer.write()
        peripheral_checkpoint = device_checkpoint.peripheral_checkpoints_by_name[name]
        printer.write(f"Peripheral: {name}")
        with printer.indented():
          printer.write(f"Timestamp: {peripheral_checkpoint.timestamp}")
          printer.write(f"Checkpoint: {peripheral_checkpoint.integrity_checksum.hex()}")
          if peripheral_checkpoint.owning_device_id:
            printer.write(f"Owning Device: {peripheral_checkpoint.owning_device_id}")
            printer.write(f"Ownership Timestamp: {peripheral_checkpoint.ownership_timestamp}")

    printer.write()

  return results.getvalue().removesuffix("\n")  # Drop the extra newline added by the last device
