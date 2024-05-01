import contextlib
import copy
import json
import logging
import os
import pathlib
import random
import string
import sys
import tempfile

import gflags

import lib.immutable.utils as immutable_utils


gflags.DEFINE_string("release_info_filepath", "/tmp/fake-ostree/release_info.json",
                     "The OTA json filepath.")
gflags.DEFINE_string("tracking_branch_filepath", "/var/lib/update_manager/tracking_branch",
                     "The tracking branch filepath")

FLAGS = gflags.FLAGS


log = logging.getLogger(__name__)


def read_file(file_path, mode='r'):
  data = None
  try:
    with open(file_path, mode, encoding=_encoding_from_mode(mode)) as file:
      data = file.read()
  except FileNotFoundError:
    log.info("File %s not found", file_path)
  except Exception as e:
    log.error("Error reading file %s: %s", file_path, str(e))
  return data


def shred_file(file_path):
  try:
    num_bytes = os.stat(file_path).st_size
    write_file(file_path, data=b"\0" * num_bytes, mode='wb', use_fsync=True)
    return True
  except Exception as e:
    log.error("Error shredding file %s: %r", file_path, e)

  return False


def clear_file(file_path, *, overwrite=False):
  try:
    if os.path.isfile(file_path):
      if overwrite:
        shred_file(file_path)

      os.remove(file_path)
    return True
  except Exception as e:
    log.error("Error removing file %s: %s", file_path, str(e))
    return False


def write_file(file_path, data, mode='w', use_fsync=False, create_dirs=False, tmp_file_suffix=None):
  '''
  Write data out to a file at file_path

  @file_path: Destination file path.
  @data: The data to be written out.
  @mode: The open mode to use.
  @use_fsync: Whether to call os.fsync to force the file to be written to disk.
  @create_dirs: Createe the directory for the destination file if it does not exists.
  @tmp_file_suffix: If this non None or non "", it would use a temporary file to first
                    write the data to. Then rename the temporary file to the desired
                    filepath.
  '''
  success = False
  file = None
  try:
    dir_path = os.path.dirname(file_path)
    if create_dirs:
      os.makedirs(dir_path, exist_ok=True)

    if tmp_file_suffix:
      file = tempfile.NamedTemporaryFile(  # pylint: disable=consider-using-with
          mode=mode,
          suffix=tmp_file_suffix,
          dir=dir_path,
          delete=False,
      )
    else:
      file = open(  # pylint: disable=consider-using-with
          file_path,
          mode,
          encoding=_encoding_from_mode(mode),
      )

    file.write(data)
    if use_fsync:
      file.flush()
      os.fsync(file.fileno())

    if tmp_file_suffix:
      os.replace(file.name, file_path)

    success = True
  except Exception as e:
    if tmp_file_suffix and file:
      clear_file(file.name)

    log.error("Error writing to file %s: %s", file_path, str(e))
  finally:
    if file is not None:
      file.close()
  return success


def get_base_dir():
  '''
  Returns the absolute path to the base directory of the repository containing the python executable
  '''
  return pathlib.Path(sys.executable).parents[2].as_posix()


def get_release_info_filepath():
  return FLAGS.release_info_filepath


def get_release_tag(release_info_filepath):
  if not release_info_filepath:
    return None

  data = read_file(release_info_filepath)
  if not data:
    return None
  data = data.strip()
  release_info = json.loads(data)
  if not release_info:
    return None
  release_tag = release_info.get("release_tag")
  return release_tag


def get_tracking_branch_filepath():
  return FLAGS.tracking_branch_filepath


def get_sentry_environment(tracking_branch_filepath):
  if not tracking_branch_filepath:
    return None

  data = read_file(tracking_branch_filepath)
  if not data:
    return None
  return os.path.basename(data.strip())


def write_flagfile(file_path, flags):
  file = None
  try:
    with open(file_path, 'w', encoding="utf-8") as file:
      for k, v in flags.items():
        val_str = ",".join(elem for elem in v) if isinstance(v, list) else v
        flag = "--%s=%s\n" % (k, val_str)
        file.write(flag)
  except Exception as e:
    log.error("Error writing to file %s: %s", file_path, str(e))


@contextlib.contextmanager
def temporary_umask(new_umask):
  previous_umask = os.umask(new_umask)
  try:
    yield
  finally:
    os.umask(previous_umask)


def convert_fahrenheit_to_celsius(temperature, round_to_int=True):
  temperature_c = (temperature - 32) / 1.8
  return round(temperature_c) if round_to_int else temperature_c


def convert_celsius_to_fahrenheit(temperature, round_to_int=True):
  temperature_f = (temperature * 1.8) + 32
  return round(temperature_f) if round_to_int else temperature_f


def fast_copy(obj, deep=True):
  if deep:
    # Pickling/unpickling is significantly faster than copy.deepcopy
    return immutable_utils.ImmutableCompatiblePickleCopier.deepcopy(obj)
  return copy.copy(obj)


def atomic_relink(link_source, link_destination, tmp_file_suffix):
  if (os.path.exists(link_destination) and
      os.path.exists(link_source) and
      os.path.realpath(link_source) == os.path.realpath(link_destination)):
    return True

  link_tmp_file_path = "{}-{}-{}".format(
      link_destination,
      "".join(random.sample(string.digits + string.ascii_letters, 10)),
      tmp_file_suffix,
  )
  try:
    os.symlink(link_source, link_tmp_file_path)
    os.replace(link_tmp_file_path, link_destination)
    return True
  except Exception as e:
    log.error("Error symlinking %s to %s: %s", link_source, link_destination, str(e))
    return False


def _encoding_from_mode(mode):
  return None if "b" in mode else "utf-8"
