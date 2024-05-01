import lib.clients.web_api.base


class WebAPIRegistrationClient(lib.clients.web_api.base.WebAPIBaseClient):
  async def post_registration_admin_verification_phone(
      self,
      email_address,
      phone_number,
      token,
  ):
    """POST to the /admin-portal/verification/{email_address}/phone endpoint.

    Args:
      email_address: The email address of the user.
      phone_number: The phone number to which the verification code should be sent.
      token: A JSON Web Token for admin portal registration.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 200
        body: {"token": <token>}
    """
    return await self.post(
        path="/admin-portal/verification/{}/phone".format(email_address),
        json={"phone_number": phone_number, "token": token},
    )

  async def post_registration_admin_verification_verify_phone(
      self,
      email_address,
      code,
      token,
  ):
    """POST to the /admin-portal/verification/{email_address}/verify-phone endpoint.

    Args:
      email_address: The email address of the user.
      code: The verification code for the user's phone number.
      token: A JSON Web Token for admin portal registration.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 200
        body: {"token": <token>}
    """
    return await self.post(
        path="/admin-portal/verification/{}/verify-phone".format(email_address),
        json={"code": code, "token": token},
    )

  async def post_registration_admin_verify_email(
      self,
      code,
      email_address,
      token,
  ):
    """POST to the /admin-portal/{email_address}/verify-email endpoint.

    Args:
      code: The verification code for the email address.
      email_address: The user's email address.
      token: A JSON Web Token for admin portal registration.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 200
        body:
          {
              "birthdate": <birthdate>,
              "email_address": <email-address>,
              "family_name": <family-name>,
              "given_name": <given-name>,
              "organization_id": <organization-id>,
              "organization_name": <organization-name>,
              "token": <token>,
              "user_id": <user-id>,
          }
    """
    return await self.post(
        path="/admin-portal/{}/verify-email".format(email_address),
        json={"code": code, "token": token},
    )

  async def post_verify_tenant_email(
      self,
      code: str,
      email_address: str,
      token: str,
  ):
    """POST to the /admin-portal/{email_address}/verify-tenant-email endpoint.

    Args:
      code: The verification code for the email address.
      email_address: The invited tenant's email address.
      token: A JSON Web Token used to authenticate the email verification.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 200
        body:
          {
              "token": <token>,
              "user_id": <user-id>,
          }
    """
    return await self.post(
        path="/admin-portal/{}/verify-tenant-email".format(email_address),
        json={"code": code, "token": token},
    )
