import platform
import re
import sys


# Platform identification constants.
UNKNOWN = 0
RASPBERRY_PI = 1
BEAGLEBONE_BLACK = 2


class OperatingSystem:
  LINUX = 'linux'
  OSX = 'osx'
  WINDOWS = 'windows'


PLATFORM_INFO_PATH = '/proc/cpuinfo'


def platform_detect():
  """Detect if running on the Raspberry Pi or Beaglebone Black"""
  try:
    with open(PLATFORM_INFO_PATH, 'r', encoding="utf-8") as infile:
      for line in infile:
        # Match a line of the form "Revision : 0002" while ignoring extra
        # info in front of the revsion (like 1000 when the Pi was over-volted).
        match = re.match(r'Hardware\s+:\s+BCM(\w{4})$', line, flags=re.IGNORECASE)
        if match:
          return RASPBERRY_PI
      return BEAGLEBONE_BLACK
  except Exception:
    return UNKNOWN


def os_detect():
  """ returns the operating system enum we are running on """
  if sys.platform == 'darwin':
    return OperatingSystem.OSX
  if sys.platform in ('linux', 'linux2'):
    return OperatingSystem.LINUX
  if sys.platform == 'win32':
    raise OSError("y r u use OperatingSystem.WINDOWS?")
  raise OSError("unknown operating system")


def _get_distro_name():
  os_type = os_detect()
  if os_type == OperatingSystem.OSX:
    return "osx"
  with open("/etc/os-release", "r", encoding="utf-8") as f:
    os_name = f.read().strip()

  matches = {
      "b2qt": "poky",
      "Brilliant": "poky",
      "Debian": "debian",
      "Amazon Linux": "amazonlinux",
  }
  for match, distro in matches.items():
    if match in os_name:
      return distro

  raise OSError("Unknown distro")


def platform_name():
  distro = _get_distro_name()
  machine = platform.machine()
  return "{}_{}".format(distro, machine)
