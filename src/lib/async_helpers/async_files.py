import functools

from lib import utils


async def write_file(loop, file_path, data, tmp_file_suffix=None, mode="w"):
  return await loop.run_in_executor(
      executor=None,
      func=functools.partial(
          utils.write_file,
          file_path=file_path,
          data=data,
          mode=mode,
          use_fsync=True,
          create_dirs=True,
          tmp_file_suffix=tmp_file_suffix,
      ),
  )


async def atomic_relink(loop, link_source, link_destination, tmp_file_suffix):
  return await loop.run_in_executor(
      None,
      utils.atomic_relink,
      link_source,
      link_destination,
      tmp_file_suffix
  )


async def read_file(loop, file_path, mode="r"):
  return await loop.run_in_executor(None, utils.read_file, file_path, mode)


async def clear_file(loop, file_path):
  return await loop.run_in_executor(None, utils.clear_file, file_path)
