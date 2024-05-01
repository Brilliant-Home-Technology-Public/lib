import enum


class NonceType(enum.IntEnum):
  ''' Mesh Profile 3.8.5 '''
  NETWORK = 0x00
  APPLICATION = 0x01
  DEVICE = 0x02
  PROXY = 0x03


class ProxySARType(enum.IntEnum):
  ''' Mesh Profile 6.3.1 '''
  COMPLETE = 0b00
  FIRST = 0b01
  CONTINUATION = 0b10
  LAST = 0b11


class ProxyMessageType(enum.IntEnum):
  ''' Mesh Profile 6.3.1 '''
  NETWORK_PDU = 0x00
  MESH_BEACON = 0x01
  PROXY_CONFIGURATION = 0x02
  PROVISIONING_PDU = 0x03


class OnOffOpCode(enum.IntEnum):
  ''' Mesh Models 7.1  '''
  ONOFF_GET = 0x8201
  ONOFF_SET = 0x8202
  ONOFF_SET_UNACK = 0x8203
  ONOFF_STATUS = 0x8204


class LevelOpCode(enum.IntEnum):
  ''' Mesh Models 7.1 '''
  LEVEL_GET = 0x8205
  LEVEL_SET = 0x8206
  LEVEL_SET_UNACK = 0x8207
  LEVEL_STATUS = 0x8208
  LEVEL_DELTA_SET = 0x8209
  LEVEL_DELTA_SET_UNACK = 0x820A
  MOVE_SET = 0x820B
  MOVE_SET_UNACK = 0x820C


class SIDModelID(enum.IntEnum):
  ''' Mesh Models 7.3 '''
  CONFIGURATION_SERVER = 0x0000
  CONFIGURATION_CLIENT = 0x0001
  ONOFF_SERVER = 0x1000
  ONOFF_CLIENT = 0x1001
  LEVEL_SERVER = 0x1002
  LEVEL_CLIENT = 0x1003
  SWITCH_CONFIG_CLIENT = 0x2008


class ProxyConfigurationOpCode(enum.IntEnum):
  ''' Mesh Profile 6.5 '''
  SET_FILTER_TYPE = 0x00
  ADD_ADDRESS = 0x01
  REMOVE_ADDRESS = 0x02
  FILTER_STATUS = 0x03


class ProxyFilterType(enum.IntEnum):
  ''' Mesh Profile 6.5.1 '''
  WHITE_LIST = 0x00
  BLACK_LIST = 0x01


class BeaconTypes(enum.IntEnum):
  ''' Mesh Models 3.9 '''
  UNPROVISIONED_DEVICE = 0x00
  SECURE_NETWORK = 0x01


class FoundationModelOpCode(enum.IntEnum):
  ''' Mesh Profile 4.3.4.1 '''
  CONFIG_MODEL_APP_BIND = 0x803D
  CONFIG_MODEL_APP_STATUS = 0x803E
  CONFIG_MODEL_APP_UNBIND = 0X803F
  CONFIG_MODEL_PUBLICATION_GET = 0X8018
  CONFIG_MODEL_PUBLICATION_STATUS = 0X8019
  CONFIG_MODEL_PUBLICATION_VIRTUAL_ADDRESS_SET = 0X801A
  CONFIG_MODEL_SUBSCRIPTION_ADD = 0X801B
  CONFIG_MODEL_SUBSCRIPTION_DELETE = 0X801C
  CONFIG_MODEL_SUBSCRIPTION_DELETE_ALL = 0X801D
  CONFIG_MODEL_SUBSCRIPTION_OVERWRITE = 0X801E
  CONFIG_MODEL_SUBSCRIPTION_STATUS = 0X801F
  CONFIG_MODEL_SUBSCRIPTION_VIRTUAL_ADDRESS_ADD = 0X8020
  CONFIG_MODEL_SUBSCRIPTION_VIRTUAL_ADDRESS_DELETE = 0X8021
  CONFIG_MODEL_SUBSCRIPTION_VIRTUAL_ADDRESS_OVERWRITE = 0X8022
  CONFIG_MODEL_NODE_RESET = 0x8049
  CONFIG_MODEL_NODE_RESET_STATUS = 0x804A


class AddressType(enum.Enum):
  '''
  Mesh Profile 3.4.2
  0b0000000000000000: Unassigned Address
  0b0xxxxxxxxxxxxxxx: Unicast Address (excluding 0b0000000000000000)
  0b10xxxxxxxxxxxxxx: Virtual Address
  0b11xxxxxxxxxxxxxx: Group Address
  '''
  UNASSIGNED = 0
  UNICAST = 1
  VIRTUAL = 2
  GROUP = 3


def address_to_type(address):
  ''' number, 2 bytes, [0,65535] '''
  if address == 0:
    return AddressType.UNASSIGNED
  if address < 32768:
    return AddressType.UNICAST
  if address < 49152:
    return AddressType.VIRTUAL
  return AddressType.GROUP


class TransistionStepResolution(enum.IntEnum):
  ''' Mesh Models 3.1.3 '''
  HUNDRED_MILLISECONDS = 0b00
  SECONDS = 0b01
  TEN_SECONDS = 0b10
  TEN_MINUTES = 0b11
