import typing

import lib.clients.web_api.base


if typing.TYPE_CHECKING:
  import lib.clients.web_api.client


class WebAPIUsersClient(lib.clients.web_api.base.WebAPIBaseClient):
  DELETE_USER_TOKEN_HEADER = "x-brilliant-delete-user-token"

  async def post_users(self,
                       birthdate,
                       email_address,
                       family_name,
                       given_name,
                       password,
                       token):
    """Post to the /users endpoint.

    Args:
      birthdate: The users birthdate as a string in the formate MM-DD-YY.
      email_address: The user's email address.
      family_name: The user's last name.
      given_name: The user's first name.
      password: The user's new password.
      token: A JSON Web Token containing the user's email address and signed with the server's
          secret. The token is usually received in an email triggered by the POST /emails endpoint.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
          {"given_name": <given_name>,
           "verification_code": <verification_code>}
    """
    data = {
        "birthdate": birthdate,
        "email_address": email_address,
        "family_name": family_name,
        "given_name": given_name,
        "password": password,
        "token": token,
    }
    return await self.post(path="/users",
                           data=data)

  async def delete_users(
      self,
      user_id: str,
      token: str,
      user_token: str | None = None,
      cert_required: typing.Optional[bool] = True,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """Delete on the /users/{user_id} endpoint.

    Args:
      user_id: The ID of the user account to delete.
      token: A JSON Web Token returned by the `POST
          /users/{email_address}/verify-delete-user-code` endpoint.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 204
    """
    extra_headers = {self.DELETE_USER_TOKEN_HEADER: token}
    if user_token:
      extra_headers["Authorization"] = f"Bearer {user_token}"
    return await self.delete(
        path=f"/users/{user_id}",
        extra_headers=extra_headers,
        cert_required=cert_required,
    )

  async def get_users_homes(
      self,
      email_address: str,
      token: str,
      user_token: str | None = None,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """Get from the /users/{email_address}/homes endpoint.

    Args:
      email_address: The email address of the account from which to retrieve all associated homes.
      token: A JSON Web Token returned by the `POST
          /users/{email_address}/verify-delete-user-code` endpoint.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 200
        body: {"homes": [<home_details>, ...], "user_id": <user_id>}
    """
    extra_headers = {self.DELETE_USER_TOKEN_HEADER: token}
    if user_token:
      extra_headers["Authorization"] = f"Bearer {user_token}"
    return await self.get(
        path=f"/users/{email_address}/homes",
        extra_headers=extra_headers,
        cert_required=True,
    )

  async def post_users_mfa_devices_phone_number_new(
      self,
      user_id,
      phone_number,
      token
  ):
    """Post to the /users/{user_id}/mfa-devices/phone-number endpoint.

    Args:
      user_id: The user's id.
      phone_number: The phone number to be added.
      token: A JSON Web Token for admin portal registration.

    Returns:
      A lib.clients.web_api_client.WebAPIResponse with no content.
    """
    return await self.post(
        path="/users/{}/mfa-devices/phone-number".format(user_id),
        json={"phone_number": phone_number, "token": token},
    )

  async def post_users_verify_delete_user_code(
      self,
      email_address: str,
      token: str,
      verification_code: str,
      user_token: str | None = None,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """Post to the /users/{email_address}/verify-delete-user-code endpoint.

    Args:
      email_address: The email address of the account to delete.
      token: A JSON Web Token returned by the `POST
          /emails/{email_address}/delete-user-verification-code` endpoint.
      verification_code: The verification code sent to the email address.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 200
        body: {"token": <token>}
    """
    extra_headers = {self.DELETE_USER_TOKEN_HEADER: token}
    if user_token:
      extra_headers["Authorization"] = f"Bearer {user_token}"
    return await self.post(
        path=f"/users/{email_address}/verify-delete-user-code",
        json={"verification_code": verification_code},
        extra_headers=extra_headers,
        cert_required=True,
    )

  async def delete_revoke_users_tokens(
      self,
      token: str,
      user_id: str,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """DELETE to the /users/{user_id}/tokens endpoint.

    Args:
      token: A JSON Web Token for a user.
      verification_code: The verification code sent to the email address.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 204
    """
    return await self.delete(
        path=f"/users/{user_id}/tokens",
        extra_headers={"Authorization": f"Bearer {token}"},
        cert_required=True,
    )
