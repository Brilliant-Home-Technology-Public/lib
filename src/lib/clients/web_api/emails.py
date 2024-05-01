import aiohttp.web

import lib.clients.web_api.base
import lib.networking.utils
import thrift_types.bootstrap.constants as bootstrap_constants


class WebAPIEmailsClient(lib.clients.web_api.base.WebAPIBaseClient):
  async def post_emails_admin_portal_verify_email(
      self,
      email_address: str,
      token: str,
      force: bool = False,
  ):
    """POST to the /emails/{email_address}/verify-admin-email endpoint.

    Args:
      email_address: The receiver's email address.
      token: A JSON Web Token for admin portal registration.
      force: Whether or not this is a force request for the verification email.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 200
        body: {"token": <token>}
    """
    return await self.post(
        path="/emails/{}/verify-admin-email".format(email_address),
        json={"token": token, "force": force},
    )

  async def post_emails_v2(self,
                           device_name,
                           device_type,
                           email_address):
    """Post to the /v2/emails endpoint.

    Args:
      device_name: The name of the device for which a verification code is being requested.
      device_type: The configuration.ttypes.BrilliantDeviceType of the device for which a
          verification code is being requested.
      email_address: The user's email address.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with the following:
          headers:
            {"X-Brilliant-Auth-Token": <JSON Web Token for posting to /homes or
                                        /emails/<email_address>/verify_device}
          body:
            {"links": {"verify_device": {"href": <verify-device URL>}}}
    """
    data = {
        "device_name": device_name,
        "device_type": device_type,
        "email_address": email_address,
    }
    return await self.post(path="/v2/emails",
                           data=data,
                           cert_required=True)

  async def post_emails_verify_device(self,
                                      code,
                                      email_address,
                                      token):
    """Post to the /emails/<email_address>/verify-device endpoint.

    Args:
      code: The verification code received when creating the user or received in the verification
          code email.
      email_address: The user's email address.
      token: A JSON Web Token that is signed with the server's secret. The token is usually received
          in the post /emails response.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with the following:
          headers:
            {"X-Brilliant-Auth-Token": <JSON Web Token for posting to /homes or
                                        /homes/<home_id>/devices}
          body:
            {"available_homes": <A list of homes with which the device can attach>}
    """
    data = {
        "code": code,
    }
    return await self.post(path="/emails/{}/verify-device".format(email_address),
                           data=data,
                           extra_headers={bootstrap_constants.AUTHENTICATION_TOKEN_HEADER: token},
                           cert_required=True)

  async def post_send_tenant_verification_email(self, email_address: str, token: str, force: bool):
    """POST to the /emails/{email_address}/send-tenant-verification-email endpoint.

    Args:
      email_address: The invitee's email address.
      token: The admin registration token from the invitation link.
      force: Whether this is a force to get a new verification code.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 200
        body: {"token": <token>}
    """
    return await self.post(
        path="/emails/{}/send-tenant-verification-email".format(email_address),
        json={"token": token, "force": force},
    )

  async def post_send_delete_user_verification_email(self,
      email_address: str,
      token: str | None = None,
  ):
    """POST to the /emails/{email_address}/delete-user-verification-code endpoint.

    Args:
      email_address: The user's email address.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 200
        body: {"token": <token>}
    """
    extra_headers = {"Authorization": f"Bearer {token}"} if token else {}
    return await self.post(
        path=f"/emails/{email_address}/delete-user-verification-code",
        cert_required=True,
        extra_headers=extra_headers,
    )

  async def get_create_user_link(self, email_address: str) -> aiohttp.web.Response:
    """GET to the /emails/{email_address}/create-user-link endpoint.

    Args:
      email_address: The user's email address.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 200
        body: {"create_user_link": <url>}
    """
    return await self.get(
        path=f"/emails/{email_address}/create-user-link",
    )

  async def post_verify_user_email(
      self,
      code: str,
      email_address: str,
      token: str,
  ) -> aiohttp.web.Response:
    """POST to the /emails/{email_address}/verify-user-email endpoint.

    Args:
      code: The verification code for the email address.
      email_address: The user's email address.
      token: A JSON Web Token used to authenticate the email verification.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 200
        body:
          {
              "token": <token>,
              "user_id": <optional user-id>,
          }
    """
    return await self.post(
        path=f"/emails/{email_address}/verify-user-email",
        json={"code": code, "token": token},
    )

  async def post_send_user_verification_email(
      self,
      email_address: str,
      token: str,
      force: bool,
  ) -> aiohttp.web.Response:
    """POST to the /emails/{email_address}/send-user-verification-email endpoint.

    Args:
      email_address: The user's email address.
      token: The user registration token.
      force: Whether the request is to force a verification email.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 200
        body: {"token": <token>}
    """
    return await self.post(
        path=f"/emails/{email_address}/send-user-verification-email",
        json={"token": token, "force": force},
    )

  async def post_verify_root_ssh(
      self,
      email_address: str,
      code: str,
      control_id: str,
      home_id: str,
  ) -> aiohttp.web.Response:
    """POST to the /emails/{email_address}/verify-root-ssh endpoint.

    Args:
      email_address: The email address that received the verification email.
      code: The verification code received in the email.
      control_id: The ID of the control making the request.
      home_id: The ID of the home requesting to enable Root SSH.

    Returns `204: No Content` on success.
    """
    return await self.post(
        path=f"/emails/{email_address}/verify-root-ssh",
        json={"code": code},
        extra_headers=lib.networking.utils.format_headers({
            "home-id": home_id,
            "device-id": control_id,
        }),
    )
