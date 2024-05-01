from lib.networking import interface
from lib.networking import utils
import thrift_types.message_bus.constants as message_bus_constants


class Authenticator:

  def __init__(self, authentication_policy):
    self._authentication_policy = authentication_policy

  @property
  def authentication_policy(self):
    return self._authentication_policy

  async def validate_certificate(self, device_id, home_id, certificate):
    if (home_id == message_bus_constants.UNASSIGNED_HOME_ID and
        self._authentication_policy.allow_unassigned_home_id):
      return True

    expected_fingerprint = await self._authentication_policy.get_expected_certificate_fingerprint(
        device_id=device_id,
        home_id=home_id,
    )

    if not expected_fingerprint:
      return False

    cert_fingerprint = utils.get_certificate_fingerprint(certificate)
    return cert_fingerprint == expected_fingerprint

  def get_authentication_method_for_peer(self, maybe_address, connection_params=None):
    method = self._authentication_policy.default_authentication_method
    if maybe_address:
      _, _, connection_args, secure = utils.parse_address(maybe_address)
      hostname = connection_args.get('host')
      if secure:
        if hostname:
          method = self._authentication_policy.get_authentication_method_for_host(hostname)
      else:
        method = interface.AuthenticationMethod.NONE
    elif connection_params and connection_params.get('authentication_token'):
      method = interface.AuthenticationMethod.JWT

    return method
