import lib.networking.interface
import lib.networking.utils


class AuthenticationPolicy(lib.networking.interface.AuthenticationPolicy):

  async def start(self):
    pass

  @property
  def strict(self):
    return False

  @property
  def default_authentication_method(self):
    return lib.networking.interface.AuthenticationMethod.CERTIFICATE_FINGERPRINT

  def get_authentication_method_for_host(self, hostname):
    return lib.networking.interface.AuthenticationMethod.CERTIFICATE_FINGERPRINT

  async def get_expected_certificate_fingerprint(self, device_id, home_id):
    return None

  def accept_client_certificate_as_header(self):
    return False
