"""
This module provides a stub authentication policy that can be used with a lib.protocol.processor.
"""

import lib.networking.interface


class AuthenticationPolicy(lib.networking.interface.AuthenticationPolicy):

  def __init__(self, strict=False):
    self._strict = strict

  async def start(self):
    pass

  @property
  def strict(self):
    return self._strict

  @property
  def default_authentication_method(self):
    return lib.networking.interface.AuthenticationMethod.CERTIFICATE_FINGERPRINT

  def get_authentication_method_for_host(self, hostname):
    return lib.networking.interface.AuthenticationMethod.NONE

  async def get_expected_certificate_fingerprint(self, device_id, home_id):
    return None

  def accept_client_certificate_as_header(self):
    return False
