import pkgutil

from lib.versioning.peripheral_version.base import PERIPHERAL_REGISTRY
from lib.versioning.peripheral_version.base import PeripheralVersion


__path__ = pkgutil.extend_path(__path__, __name__)
for importer, modname, ispkg in pkgutil.walk_packages(path=__path__, prefix=__name__ + "."):
  if not modname.endswith("_test"):
    __import__(modname)


def get_peripheral_version(device_id, peripheral_name, version):
  # NOTE: device_id is unused for now, but will provide a lot of flexibility in the future
  # in case we want to make device specific peripheral migrations
  registry = PERIPHERAL_REGISTRY

  peripheral_specific_version = registry.get(peripheral_name, {}).get(version)
  global_version = registry.get(None, {}).get(version)

  # return the base class if the specified peripheral or version doesn't exist
  return peripheral_specific_version or global_version or PeripheralVersion
