import aiofiles

import lib.networking.bluetooth.exceptions


SYSFS_ADV_MIN_INTERVAL_FILE_PATH = '/sys/class/bluetooth/hci0/adv_min_interval'
SYSFS_ADV_MAX_INTERVAL_FILE_PATH = '/sys/class/bluetooth/hci0/adv_max_interval'


class BluezConfigSysfsHelper:
  '''
  Asyncio wrapper for our calls to config Bluez through sysfs.
  '''

  def __init__(self, loop):
    self._loop = loop

  async def _get_interval(self, filepath):
    async with aiofiles.open(filepath, "r", loop=self._loop) as fh:
      data = await fh.read()
      return int(data)

  async def _set_interval(self, filepath, interval):
    async with aiofiles.open(filepath, "w", loop=self._loop) as fh:
      await fh.write(str(interval))

  async def set_advertising_interval(self, min_interval_tick, max_interval_tick):
    if min_interval_tick > max_interval_tick:
      raise lib.networking.bluetooth.exceptions.BluezConfigError(
          "Error setting advertising intervals: "
          "The minimum interval must be less than the maximum interval."
      )
    current_max_interval_tick = await self._get_interval(SYSFS_ADV_MAX_INTERVAL_FILE_PATH)
    if max_interval_tick <= current_max_interval_tick:
      await self._set_interval(SYSFS_ADV_MIN_INTERVAL_FILE_PATH, min_interval_tick)
      await self._set_interval(SYSFS_ADV_MAX_INTERVAL_FILE_PATH, max_interval_tick)
    else:
      await self._set_interval(SYSFS_ADV_MAX_INTERVAL_FILE_PATH, max_interval_tick)
      await self._set_interval(SYSFS_ADV_MIN_INTERVAL_FILE_PATH, min_interval_tick)
