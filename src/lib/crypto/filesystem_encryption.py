import dataclasses
import gzip
import logging
import os
import shutil
import subprocess
import typing


log = logging.getLogger(__name__)


class ParseError(Exception):
  pass


class KeyMismatchError(Exception):
  pass


@dataclasses.dataclass
class CryptPolicy:
  directory: str
  policy_version: str = dataclasses.field(metadata={'text_name': 'Policy version'})
  key_identifier: str = dataclasses.field(metadata={'text_name': 'Master key identifier'})
  contents_algorithm: str = dataclasses.field(metadata={'text_name': 'Contents encryption mode'})
  filenames_algorithm: str = dataclasses.field(metadata={'text_name': 'Filenames encryption mode'})
  flags: str = dataclasses.field(metadata={'text_name': 'Flags'})

  # FIXME: Remove this after upgrading Cython. https://github.com/cython/cython/issues/2552
  __annotations__ = {
      'directory': str,
      'policy_version': str,
      'key_identifier': str,
      'contents_algorithm': str,
      'filenames_algorithm': str,
      'flags': str,
  }

  @classmethod
  def _fields_by_text_name(cls):
    fields = {}
    for field in dataclasses.fields(cls):
      text_name = field.metadata.get("text_name")
      if not text_name:
        continue
      fields[text_name.lower()] = field

    return fields

  @classmethod
  def parse(cls, policy_text: str):
    lines = policy_text.strip().split('\n')
    first_line = lines.pop(0).strip(":")
    if not first_line.startswith("Encryption policy"):
      raise ParseError(f"Invalid starting line: {first_line}")

    directory = first_line.split()[-1]

    attrs = {}
    fields_by_text_name = cls._fields_by_text_name()
    for line in lines:
      try:
        key, value = line.strip().split(": ")
        field = fields_by_text_name[key.lower()]
        attrs[field.name] = field.type(value)
      except (KeyError, ValueError) as e:
        raise ParseError(f"Failed to parse line {line!r}: {e!r}") from e

    policy = cls(directory=directory, **attrs)
    return policy


class FSCryptManager:

  def __init__(self):
    self._key_handle = None

  @classmethod
  def is_supported(cls):
    try:
      with gzip.open("/proc/config.gz", 'rt') as config:  # 'rt' => read as text
        for l in config:
          if l.strip() == "CONFIG_FS_ENCRYPTION=y":
            return True
    except Exception as e:
      log.error("Failed to read kernel config! Assuming no encryption support. %r", e)

    return False

  def is_enabled_for_filesystem(self, fs_device: str):
    tune2fs_output = self._call_util("tune2fs", "-l", fs_device)
    for line in tune2fs_output.decode().strip().split('\n'):
      if not line.startswith("Filesystem features:"):
        continue
      features = line[len("Filesystem features:"):].split()
      return "encrypt" in features

    raise ParseError("Failed to parse filesystem features!")

  def enable_for_filesystem(self, fs_device: str):
    self._call_util("tune2fs", "-O", "encrypt", fs_device)

  def _call_util(self, util: str, *args, input_data: typing.Optional[bytes] = None):
    completed = subprocess.run(
        [util, *args],
        input=input_data,
        check=True,
        capture_output=True,
    )
    return completed.stdout

  def _call(self, *args, input_data: typing.Optional[bytes] = None):
    return self._call_util("fscryptctl", *args, input_data=input_data)

  def load_key(self, key: bytes, mount_point: str = "/"):
    self._key_handle = self._call("add_key", mount_point, input_data=key).strip().decode()

  def _get_policy(self, path: str):
    try:
      policy = self._call("get_policy", path)
    except subprocess.CalledProcessError as e:
      if b"not encrypted" in e.stderr:
        return None
      raise

    return CryptPolicy.parse(policy.decode())

  def is_encrypted(self, directory: str):
    policy = self._get_policy(directory)
    if not policy:
      return False

    if policy.key_identifier != self._key_handle:
      raise KeyMismatchError(
          f"Required key does not match ({policy.key_identifier} != {self._key_handle})")

    return True

  def make_encrypted(self, directory: str):
    # The directory needs to be empty before we can enable encryption, so we move it aside
    # temporarily and then back in after encryption has been applied.
    temp_dir_name = directory + ".tmp"
    if os.path.exists(temp_dir_name):
      # Copy any existing files
      log.warning("Previous temporary directory exists! Overwriting.")
      shutil.rmtree(temp_dir_name)

    os.rename(directory, temp_dir_name)
    os.makedirs(directory)

    log.info("Setting encryption policy for %s!", directory)
    self._call("set_policy", self._key_handle, directory)

    for entry in os.listdir(temp_dir_name):
      # Move back into now-encrypted directory. This is suprisingly tricky because this actually
      # needs to be a copy operation, and Python's built-in helpers for this won't properly
      # preserve ownership of the files as it's copying. `mv` will do everything we want.
      self._call_util("mv", os.path.join(temp_dir_name, entry), directory)

    shutil.rmtree(temp_dir_name)
