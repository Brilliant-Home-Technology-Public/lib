from lib.versioning.base_version import BaseVersion
from thrift_types.version import constants


class BaseDeviceProvisioningVersion(BaseVersion):
  service = "DeviceProvisioning"


class DeviceProvisioningVersion20181018(BaseDeviceProvisioningVersion):
  prev_version = None
  version = constants.VERSION_20181018
  next_version = None


ALL_API_VERSIONS = [
    DeviceProvisioningVersion20181018,
]


CURRENT_API_VERSION = DeviceProvisioningVersion20181018
