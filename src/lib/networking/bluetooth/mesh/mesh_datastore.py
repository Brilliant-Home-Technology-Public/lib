from abc import ABC
from abc import abstractmethod
import collections


MeshNetworkIVIndex = collections.namedtuple(
    "MeshNetworkIVIndex",
    ["iv_index", "iv_index_update_trigger_time_ms"],
)


class AbstractMeshDatastore(ABC):

  @abstractmethod
  def get_next_seq(self):
    ''' seq: number, 3 bytes, [0,16777215] '''

  @abstractmethod
  def set_seq(self, seq):
    ''' seq: number, 3 bytes, [0,16777215] '''

  @abstractmethod
  def get_mesh_network_iv_index_update_time(self):
    ''' time from epoch, milliseconds '''

  @abstractmethod
  def set_mesh_network_iv_index(self, iv_index):
    ''' iv_index: number, 4 bytes [0,4294967295] '''

  @abstractmethod
  def set_mesh_network_iv_index_recovery_time(self):
    ''' set the current epoch time in milliseconds as iv_index recovery time '''

  @abstractmethod
  def get_mesh_network_iv_index_recovery_time(self):
    ''' time from epoch, milliseconds '''

  @abstractmethod
  def get_netkey(self):
    ''' byte string, 16 bytes '''

  @abstractmethod
  def set_netkey(self, netkey):
    ''' byte string, 16 bytes '''

  @abstractmethod
  def get_appkey(self):
    ''' byte string, 16 bytes '''

  @abstractmethod
  def set_appkey(self, appkey):
    ''' byte string, 16 bytes '''

  @abstractmethod
  def get_node_address(self):
    ''' number, 2 bytes, [0,65535] '''

  @abstractmethod
  def get_max_seqauth_for_source(self, node):
    ''' node: number, 2 bytes, [0,65535] '''

  @abstractmethod
  def set_max_seqauth_for_source(self, node, seqauth):
    '''
    seqauth: combination of iv_index and sequence number 8 bytes [0, 2^56]
    '''

  @abstractmethod
  def get_device_key(self, node):
    ''' byte string, 16 bytes '''

  @abstractmethod
  async def get_mesh_network_iv_index(self):
    pass

  @abstractmethod
  async def update_mesh_network_iv_index(self, new_iv_index):
    pass

  @abstractmethod
  async def finish_mesh_network_iv_index_update(self):
    pass

  @abstractmethod
  def get_node_iv_index(self):
    pass

  @abstractmethod
  async def roll_over_node_nonce_parameters(self):
    pass
