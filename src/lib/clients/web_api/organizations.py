import lib.clients.web_api.base


class WebAPIOrganizationsClient(lib.clients.web_api.base.WebAPIBaseClient):
  async def delete_invitation_to_home_property(
      self,
      email_address: str,
      property_id: str,
      user_token: str,
  ):
    """DELETE /organizations/homes/{property_id}/invitations/{email_address} endpoint.

    Args:
      email_address: The email address of the invitee.
      property_id: The ID of the home property for the invitation.
      user_token: The requester's authorization token.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with no content.
    """
    return await self.delete(
        path="/organizations/homes/{}/invitations/{}".format(property_id, email_address),
        extra_headers={"Authorization": "Bearer {}".format(user_token)},
    )

  async def post_add_user_to_home(
      self,
      property_id: str,
      user_id: str,
      token: str,
  ):
    """POST to the /organizations/homes/{property_id}/users endpoint.

    Args:
      property_id: The property ID of the home.
      user_id: The ID of the user being added to the home property.
      token: A JSON Web Token for admin portal registration.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 200
        body: {"building_name": <building name>, "home_property_name": <home property name>}
    """
    return await self.post(
        path="/organizations/homes/{}/users".format(property_id),
        json={"token": token, "user_id": user_id},
    )

  async def post_add_user_to_organization(
      self,
      property_id,
      user_id,
      token,
  ):
    """POST to the /organizations/{property_id}/user endpoint.

    Args:
      property_id: The property ID of the organization.
      user_id: The ID of the user being added to the organization.
      token: A JSON Web Token for admin portal registration.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 200
        body: {"token": <token>}
    """
    return await self.post(
        path="/organizations/{}/users".format(property_id),
        json={"user_id": user_id, "token": token},
    )

  async def delete_user_from_organization(
      self,
      property_id: str,
      user_id: str,
      user_token: str,
  ):
    """DELETE to the /organizations/{property_id}/users endpoint.

    Args:
      property_id: The property ID of the organization.
      user_id: The ID of the user being removed from the organization.
      user_token: The portal user's authorization token.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with no content.
    """
    headers = {
        "Authorization": "Bearer {}".format(user_token),
        "Content-Type": "application/json",
    }
    return await self.delete(
        path="/organizations/{}/users/{}".format(property_id, user_id),
        extra_headers=headers,
    )

  async def delete_portal_user_invitation_to_organization(
      self,
      email_address: str,
      property_id: str,
      user_token: str,
  ):
    """DELETE to the /organizations/{property_id}/invitations/{email_address} endpoint.

    Args:
      email_address: The email address of the invitee.
      property_id: The property ID of the organization.
      user_token: The portal user's authorization token.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with no content.
    """
    headers = {
        "Authorization": "Bearer {}".format(user_token),
        "Content-Type": "application/json",
    }
    return await self.delete(
        path="/organizations/{}/invitations/{}".format(property_id, email_address),
        extra_headers=headers,
    )

  async def post_invite_portal_user_to_organization(
      self,
      email_address: str,
      organization_id: str,
      user_token: str,
  ):
    """POST to the /organizations/{property_id}/invitations endpoint.

    Args:
      email_address: The invitee's email address.
      organization_id: The property ID of the organization.
      user_token: The portal user's authorization token.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 204
    """
    return await self.post(
        path="/organizations/{}/invitations".format(organization_id),
        extra_headers={
            "Authorization": "Bearer {}".format(user_token),
            "Content-Type": "application/json",
        },
        json={"email_address": email_address},
    )

  async def post_reset_home_for_home_property(
      self,
      property_id: str,
      user_token: str,
  ):
    """POST to the /organizations/homes/{property_id}/reset-home endpoint.

    Args:
      property_id: The ID of the property to reset.
      user_token: The requester's authorization token.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with:
        status: 200
        body: {"home_id": <home_id>}
    """
    return await self.post(
        path=f"/organizations/homes/{property_id}/reset-home",
        extra_headers={
            "Authorization": "Bearer {}".format(user_token),
            "Content-Type": "application/json",
        }
    )

  async def post_invite_user_to_home(self, email_address: str, property_id: str, user_token: str):
    """POST to the /organizations/homes/{property_id}/invitations endpoint.

    Args:
      email_address: The email address of the invitee.
      property_id: The ID of the home property to which the invitee is invited.
      user_token: The authorization token of the inviter.
    """
    return await self.post(
        path=f"/organizations/homes/{property_id}/invitations",
        json={"email_address": email_address},
        extra_headers={
            "Authorization": "Bearer {}".format(user_token),
            "Content-Type": "application/json",
        },
    )

  async def post_resend_invite_to_home(self, email_address: str, property_id: str, user_token: str):
    """POST to the /organizations/homes/{property_id}/invitations/resend endpoint.

    Args:
      email_address: The email address of the invitee.
      home_id: The ID of the home to which the invitee is invited.
      user_token: The authorization token of the inviter.
    """
    return await self.post(
        path=f"/organizations/homes/{property_id}/invitations/resend",
        json={"email_address": email_address},
        extra_headers={
            "Authorization": f"Bearer {user_token}",
            "Content-Type": "application/json",
        },
    )
