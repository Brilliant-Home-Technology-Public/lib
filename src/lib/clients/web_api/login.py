import json

import lib.clients.web_api.base


class WebAPILoginClient(lib.clients.web_api.base.WebAPIBaseClient):

  async def post_login_admin(self,
                             email_address,
                             password):
    """Post to the /login/admin endpoint.

    Args:
      email_address: The user's email address.
      password: The user's password.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
          {"mfa_sent": True/False}
    """
    data = json.dumps({
        "email_address": email_address,
        "password": password,
    })
    headers = {"Content-Type": "application/json"}
    return await self.post(path="/login/admin", data=data, extra_headers=headers)

  async def post_login_user(self,
                             email_address,
                             password):
    """Post to the /login/user endpoint.

    Args:
      email_address: The user's email address.
      password: The user's password.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
          {"mfa_code_sent": True/False}
    """
    data = json.dumps({
        "email_address": email_address,
        "password": password,
    })
    headers = {"Content-Type": "application/json"}
    return await self.post(path="/login/user", data=data, extra_headers=headers)

  async def post_login_admin_refresh(self,
                                     token):
    """Post to the /login/admin/refresh endpoint.

    Args:
      token: The user's login token.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
          {"token": <token>}
    """
    headers = {
        "Authorization": "Bearer {}".format(token),
    }
    return await self.post(path="/login/admin/refresh", data="", extra_headers=headers)

  async def post_login_verify_mfa_code(self, email_address, code, token):
    """Post to the /login/admin/verify-mfa-code endpoint.

    Args:
      email_address: The email address of the user.
      code: The verification code sent to the user.
      token: The JWT used to verify the user's email when verifying MFA.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
          {"token": <token>}
    """
    data = json.dumps({
        "email_address": email_address,
        "code": code,
        "token": token,
    })
    headers = {"Content-Type": "application/json"}
    return await self.post(path="/login/admin/verify-mfa-code", data=data, extra_headers=headers)

  async def post_login_user_verify_mfa_code(
      self,
      email_address: str,
      code: str,
      token: str,
  ):
    """Post to the /login/user/verify-mfa-code endpoint.

    Args:
      email_address: The email address of the user.
      code: The verification code sent to the user.
      token: The JWT used to verify the user's email when verifying MFA.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
          {"token": <token>}
    """
    data = json.dumps({
        "email_address": email_address,
        "code": code,
        "token": token,
    })
    headers = {"Content-Type": "application/json"}
    return await self.post(path="/login/user/verify-mfa-code", data=data, extra_headers=headers)

  async def post_login_user_refresh(
      self,
      token: str,
  ):
    """Post to the /login/user/refresh endpoint.

    Args:
      token: The User's login token.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
          {"token": <token>}
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    return await self.post(path="/login/user/refresh", extra_headers=headers)
