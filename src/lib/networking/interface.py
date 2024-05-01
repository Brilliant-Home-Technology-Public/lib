import abc
import enum


class PeerInterface(metaclass=abc.ABCMeta):

  @abc.abstractmethod
  async def start(self):
    pass

  @abc.abstractmethod
  async def shutdown(self):
    pass

  @abc.abstractmethod
  def incoming_message_iterator(self):
    pass

  @abc.abstractmethod
  def get_peer_common_name(self):
    pass

  @abc.abstractmethod
  def get_peer_certificate(self):
    pass

  @abc.abstractmethod
  def get_peer_connection_parameters(self):
    pass

  @abc.abstractmethod
  def is_validated(self):
    pass

  @property
  @abc.abstractmethod
  def serialization_protocol(self):
    pass

  @property
  @abc.abstractmethod
  def negotiated_api_version(self):
    pass


class UnauthorizedError(Exception):
  pass


AuthenticationMethod = enum.Enum(
    "AuthenticationMethod",
    ("NONE", "CERTIFICATE_SUBJECT", "CERTIFICATE_FINGERPRINT", "JWT"),
)


class AuthenticationPolicy(metaclass=abc.ABCMeta):

  @property
  @abc.abstractmethod
  def strict(self):
    pass

  @property
  @abc.abstractmethod
  def default_authentication_method(self):
    pass

  @abc.abstractmethod
  def get_authentication_method_for_host(self, hostname):
    pass

  @abc.abstractmethod
  async def get_expected_certificate_fingerprint(self, device_id, home_id):
    pass

  @abc.abstractmethod
  def accept_client_certificate_as_header(self):
    pass

  @property
  def allow_unassigned_home_id(self):
    return False

  async def get_token_validity_interval_seconds(self, home_id, peer_device_id, home_auth_token):
    raise NotImplementedError("get_token_validity_interval_seconds not implemented")
