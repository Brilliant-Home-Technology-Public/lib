import json
import typing

import lib.clients.web_api.base
import lib.networking.utils
import thrift_types.bootstrap.constants as bootstrap_constants


if typing.TYPE_CHECKING:
  import lib.clients.web_api.client


class WebAPIHomesClient(lib.clients.web_api.base.WebAPIBaseClient):

  async def post_homes(self,
                       device_id,
                       token):
    """Post to the /homes endpoint.

    Args:
      device_id: The ID of the device to add to the home.
      token: A JSON Web Token containing the user's ID and signed with the server's secret. The
          token is usually received in the post /emails/<email_address>/verify-device response.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
        {"home_id": <The ID of the newly created home>}
    """
    data = {
        "device_id": device_id,
    }
    return await self.post(path="/homes",
                           data=data,
                           extra_headers={bootstrap_constants.AUTHENTICATION_TOKEN_HEADER: token},
                           cert_required=True)

  async def post_homes_v2(self,
                          device_id,
                          home_name,
                          token,
                          occupied: typing.Optional[int] = None,
                          parent_property_id: typing.Optional[str] = None,
                          is_user_jwt_token: bool = False):
    """Post to the /v2/homes endpoint.

    Args:
      device_id: The ID of the device to add to the home.
      home_name: The name of the home.
      token: A JSON Web Token containing the user's ID and signed with the server's secret. The
          token is usually received in the post /emails/<email_address>/verify-device response.
      occupied: (optional) Whether the home is occupied or not.
      parent_property_id: (optional) The ID of the home's parent property (i.e. that of a Building
          or Organization).
      is_user_jwt_token: Whether the token is a user authorization token.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
        {"home_id": <The ID of the newly created home>}
    """
    data = {
        "device_id": device_id,
        "home_name": home_name,
    }
    if occupied is not None:
      data["occupied"] = occupied
    if parent_property_id is not None:
      data["parent_property_id"] = parent_property_id

    token_header = bootstrap_constants.AUTHENTICATION_TOKEN_HEADER
    if is_user_jwt_token:
      token_header = "Authorization"
      token = f"Bearer {token}"

    return await self.post(path="/v2/homes",
                           data=data,
                           extra_headers={token_header: token},
                           cert_required=True)

  async def post_homes_complete_installation(
      self,
      device_id: str,
      device_provision_state: typing.List[typing.Dict[str, str]],
      home_id: str,
      serialized_post_provision_state_config: str,
      installed_devices: typing.List[typing.Dict[str, str]],
      admin_jwt_token: str | None,
  ):
    """POST the /homes/{home_id}/complete-installation endpoint.

    Args:
      device_id: The ID of the device sending the request.
      device_provision_state: A list of dictionaries containing variable names and corresponding
          serialized PeripheralInfos.
      home_id: The ID of the home for which to complete the installation.
      serialized_post_provision_state_config: The post-provision StateConfig sent up from mobile,
          serialized.
      installed_devices: A dictionary mapping from installation template ID to installed control
          device ID.
      admin_jwt_token: The JWT token of the MDU operator for a MF home, if available. If this is
          provided, the request will use this token as authorization instead of the client cert.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with no content.
    """

    if admin_jwt_token:
      headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    else:
      headers = lib.networking.utils.format_headers({
          "home-id": home_id,
          "device-id": device_id,
      })
    return await self.post(
        path="/homes/{home_id}/complete-installation".format(home_id=home_id),
        extra_headers=headers,
        json=dict(
            device_provision_state=device_provision_state,
            post_provision_state=serialized_post_provision_state_config,
            installation_template_id="ed0bce3b836f4eadb53be80866c6717c",
            installed_devices=installed_devices,
        ),
        cert_required=True,
    )

  async def post_send_delete_home_verification_email(
      self,
      control_id: str,
      home_id: str,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """POST to the /homes/{home_id}/delete-home-verification endpoint.

    Args:
    - control_id: The ID of the Control issuing the delete request.
    - home_id: The ID of the home to be deleted.
    - user_id: The ID of the user to whom the home belongs.

    Returns:
      A response body with the email address to which the verification email was sent.
    """
    return await self.post(
        cert_required=True,
        extra_headers=lib.networking.utils.format_headers({
            "home-id": home_id,
            "device-id": control_id,
        }),
        path=f"/homes/{home_id}/delete-home-verification",
    )

  async def post_homes_devices(
      self,
      device_id: str,
      home_id: str,
      token: str,
      is_user_jwt_token: bool = False,
  ):
    """Post to the /homes/{home_id}/devices endpoint.

    Args:
      device_id: The ID of the device to add to the home.
      home_id: The ID of the home to which to add the device.
      token: Either
        - A JSON Web Token containing the user's ID and signed with the server's secret. The
          token is usually received in the post /emails/<email_address>/verify-device response.
        - A JSON Web Token containing the user's ID and signed using the user login secret.
      is_user_jwt_token: Whether the token is a user authorization token.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
        {"home_id": <The ID of the home>}
    """
    data = {
        "device_id": device_id,
    }
    token_header = bootstrap_constants.AUTHENTICATION_TOKEN_HEADER
    if is_user_jwt_token:
      token_header = "Authorization"
      token = f"Bearer {token}"
    return await self.post(
        path=f"/homes/{home_id}/devices",
        data=data,
        extra_headers={
            token_header: token
        },
        cert_required=True
    )

  async def post_homes_configuration(self,
                                     home_id: str,
                                     configuration_id: str,
                                     token: str,
                                     date: typing.Optional[str] = None,
                                     time: typing.Optional[str] = None):
    """POST to the /homes/{home_id}/configurations endpoint.

    Args:
      configuration_id: The ID of the configuration that will be applied.
      home_id: The ID of the home to which the new configuration should be applied.
      token: A JSON Web Token containing the user's ID and signed with the server's secret. Usually
          received in the POST /emails/<email_address>/verify-device response.
      date: (optional) The date on which the configuration should be applied in "MM/DD/YYYY" format.
      time: (optional) The time at which the configuration should be applied in "h:mm AM" format.
    """
    return await self.post(
        path="/homes/{home_id}/configurations".format(home_id=home_id),
        json={
            "configuration_id": configuration_id,
            "date": date,
            "time": time,
        },
        extra_headers={
            "Authorization": "Bearer {}".format(token),
            "Content-Type": "application/json",
        },
    )

  async def get_homes_installation_template(
      self,
      home_id: str,
      user_token: str,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """GET the /homes/{home_id}/installation-template endpoint.

    Args:
      home_id: The ID of the home for which to retrieve the installation template.
      user_token: The authorization token of the user retrieving the template.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing the installation
      template.
    """
    return await self.get(
        path="/homes/{home_id}/installation-template".format(home_id=home_id),
        extra_headers={"Authorization": "Bearer {}".format(user_token)},
    )

  async def get_homes_user_token(self, device_id, home_id):
    """GET the /homes/{home_id}/user-token endpoint.

    Args:
      device_id: The ID of the device issuing the request.
      home_id: The ID of the home to retrieve the user token for.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
        {"user_token": <The user token>,
         "expiration_timestamp": <The timestamp (in ms) at which the token expires>}
    """
    headers = lib.networking.utils.format_headers({
        "home-id": home_id,
        "device-id": device_id,
    })
    return await self.get(path="/homes/{home_id}/user-token".format(home_id=home_id),
                          extra_headers=headers,
                          cert_required=True)

  async def get_zendesk_user_token(self, user_token, home_id):
    """GET the /homes/{home_id}/zendesk-user-token endpoint.

    Args:
      user_token: A JSON Web Token containing the user's ID and signed with the server's secret.
      home_id: The ID of the home to retrieve the user token for.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
        {"user_token": <The user token>,
         "expiration_timestamp": <The timestamp (in ms) at which the token expires>}
    """
    headers = {
        "Authorization": "Bearer {}".format(user_token),
    }
    return await self.get(
        path="/homes/{home_id}/zendesk-user-token".format(home_id=home_id),
        extra_headers=headers,
    )

  async def post_homes_unicast_addresses(self, device_id, home_id, new_device_id, num_elements):
    """POST the /homes/{home_id}/unicast-addresses endpoint.

    Args:
      device_id: The ID of the device issuing the request.
      home_id: The ID of the home to which the device belongs.
      new_device_id: The ID of the device to provision an unicast address for.
      num_elements: The number of mesh elements the device has (and thus the number of unicast
        addresses to assign).

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
        {"unicast_addresses": [<unicast_address_1>, <unicast_address_2>]}
    """
    headers = lib.networking.utils.format_headers({
        "home-id": home_id,
        "device-id": device_id,
    })
    headers["Content-Type"] = "application/json"
    data = json.dumps({"device_id": new_device_id, "num_elements": num_elements})
    return await self.post(path="/homes/{home_id}/unicast-addresses".format(home_id=home_id),
                           data=data,
                           extra_headers=headers,
                           cert_required=True)

  async def get_homes_check_assets(
      self,
      home_id: str,
      device_id: str,
      user_token: str | None = None,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """GET the /homes/{home_id}/assets endpoint.

    Args:
      home_id: The ID of the home to check for assets.
      device_id: The ID of the device issuing the request.
      user_token: A JSON Web Token containing the user's ID and signed with the server's secret.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing a list of assets.
    """
    headers = lib.networking.utils.format_headers({
        "home-id": home_id,
        "device-id": device_id,
    })
    if user_token:
      headers |= {"Authorization": f"Bearer {user_token}"}
    return await self.get(
        path=f"/homes/{home_id}/assets",
        extra_headers=headers,
        cert_required=True,
    )

  async def post_homes_new_asset(
      self,
      home_id: str,
      device_id: str,
      asset_data_dict: dict[str, str],
      content_type: str,
      library_id: str,
      asset_title: str | None = None,
      user_token: str | None = None,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """POST the /homes/{home_id}/assets endpoint.

    Args:
      home_id: The ID of the home to which the asset belongs.
      device_id: The ID of the device issuing the request.
      asset_data_dict: A dictionary containing the asset data to upload.
      content_type: The content type of the asset.
      library_id: The ID of the library to which the asset belongs.
      asset_title: The title of the asset.
      user_token: A JSON Web Token containing the user's ID and signed with the server's secret.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing the asset ID.
    """
    headers = lib.networking.utils.format_headers({
        "home-id": home_id,
        "device-id": device_id
    })
    if user_token:
      headers |= {"Authorization": f"Bearer {user_token}"}
    path = f"/homes/{home_id}/assets?content_type={content_type}&library_id={library_id}"
    if asset_title:
      path += f"&title={asset_title}"
    return await self.post(
        path=path,
        data=asset_data_dict["asset_data"],
        extra_headers=headers,
        cert_required=True,
    )

  async def delete_home(
      self,
      control_id: str,
      email_address: str,
      home_id: str,
      verification_code: str,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """DELETE /homes/{home_id}.

    Args:
    - control_id: The ID of the Control issuing the delete home request.
    - email_address: The email address of the user deleting the home.
    - home_id: The ID of the home being deleted.
    - verification_code: The code used to verify the delete home request.
    """
    return await self.delete(
        cert_required=True,
        extra_headers=lib.networking.utils.format_headers({
            "home-id": home_id,
            "device-id": control_id,
        }),
        json=dict(
            email_address=email_address,
            verification_code=verification_code,
        ),
        path=f"/homes/{home_id}",
    )

  async def delete_homes_asset(
      self,
      home_id: str,
      device_id: str,
      library_id: str,
      s3_key: str,
      user_token: str | None = None,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """DELETE the /homes/{home_id}/assets/{library_id}/{s3_key} endpoint.

    Args:
      home_id: The ID of the home to which the asset belongs.
      device_id: The ID of the device issuing the request.
      library_id: The ID of the library to which the asset belongs.
      s3_key: The S3 key of the asset to delete.
      user_token: A JSON Web Token containing the user's ID and signed with the server's secret.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing the asset ID.
    """
    headers = lib.networking.utils.format_headers({
        "home-id": home_id,
        "device-id": device_id
    })
    if user_token:
      headers |= {"Authorization": f"Bearer {user_token}"}
    return await self.delete(
        path=f"/homes/{home_id}/assets/{library_id}/{s3_key}",
        extra_headers=headers,
        cert_required=True,
    )

  async def delete_user_from_home(self, home_id: str, user_id: str, user_token: str):
    """DELETE /homes/{home_id}/users/{user_id}.

    Args:
      home_id: The ID of the home from which the user is being removed.
      user_id: The ID of the user being removed.
      user_token: The authorization token of the admin who is removing them.
    """
    return await self.delete(
        path="/homes/{}/users/{}".format(home_id, user_id),
        extra_headers={"Authorization": "Bearer {}".format(user_token)}
    )

  async def post_invite_user_to_home(self, email_address: str, home_id: str, user_token: str):
    """POST to the /homes/{home_id}/invitations endpoint.

    Args:
      email_address: The email address of the invitee.
      home_id: The ID of the home to which the invitee is invited.
      user_token: The authorization token of the inviter.
    """
    return await self.post(
        path="/homes/{}/invitations".format(home_id),
        json={"email_address": email_address},
        extra_headers={
            "Authorization": "Bearer {}".format(user_token),
            "Content-Type": "application/json",
        },
    )

  async def post_resend_invite_to_home(self, email_address: str, home_id: str, user_token: str):
    """POST to the /homes/{home_id}/invitations/resend endpoint.

    Args:
      email_address: The email address of the invitee.
      home_id: The ID of the home to which the invitee is invited.
      user_token: The authorization token of the inviter.
    """
    return await self.post(
        path=f"/homes/{home_id}/invitations/resend",
        json={"email_address": email_address},
        extra_headers={
            "Authorization": f"Bearer {user_token}",
            "Content-Type": "application/json",
        },
    )

  async def post_user_invite_users_to_home(
      self,
      email_addresses: typing.List[str],
      home_id: str,
      user_token: str
  ):
    """POST to the /homes/{home_id}/user-invitations endpoint.

    Args:
      email_addresses: The list of email addresses to invite.
      home_id: The ID of the home to which the invitee is invited.
      user_token: The authorization token of the inviter.
    """
    return await self.post(
        path=f"/homes/{home_id}/user-invitations",
        json={"email_addresses": email_addresses},
        extra_headers={
            "Authorization": "Bearer {}".format(user_token),
            "Content-Type": "application/json",
        },
    )

  async def post_user_accept_invite_to_home(self, home_id: str, user_token: str):
    """POST to the /homes/{home_id}/users endpoint.

    Args:
      home_id: The ID of the home to which the user is invited.
      user_token: The authorization token of the user accepting the invite.
    """
    return await self.post(
        path=f"/homes/{home_id}/users",
        extra_headers={
            "Authorization": "Bearer {}".format(user_token),
            "Content-Type": "application/json",
        },
    )

  async def get_home_token(self, home_id, token):
    """Get the /homes/{home_id}/join-home-token endpoint.

    Args:.
      home_id: The ID of the home to get the home authentication token for.
      token: A JSON Web Token containing the user's ID and signed with the server's secret. The
          token is usually received in the post login/admin/verify-mfa-code response.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
        {"token": <The home auth token>}
    """
    return await self.get(
        path="/homes/{home_id}/join-home-token".format(home_id=home_id),
        extra_headers={"Authorization": "Bearer {}".format(token)},
    )

  async def delete_invite_to_home(
      self,
      user_token: str,
      home_id: str,
      email_address: str,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """DELETE from the /homes/{home_id}/user-invitations/{email_address} endpoint.

    Args:
      home_id: The ID of the home to delete the invite for.
      email_address: The email to which the invite was sent.
      user_token: A JWT containing the user's ID and signed with the server's secret.
    """
    return await self.delete(
        path=f"/homes/{home_id}/user-invitations/{email_address}",
        json={"email_address": email_address},
        extra_headers={"Authorization": "Bearer {}".format(user_token)},
    )

  async def post_send_root_ssh_verification_email(
      self,
      home_id: str,
      control_id: str,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """POST to the /homes/{home_id}/send-root-ssh-verification-email endpoint.

    Args:
      home_id: The ID of the home that is enabling Root SSH.
      control_id: The ID of the control making the request.
    """
    return await self.post(
        path=f"/homes/{home_id}/send-root-ssh-verification-email",
        extra_headers=lib.networking.utils.format_headers({
            "home-id": home_id,
            "device-id": control_id,
        }),
    )

  async def post_request_invite_for_home(
      self,
      home_id: str,
      device_id: str,
      email_address: str,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """POST to the /homes/{home_id}/request-invite/{email_address} endpoint.

    Args:
      home_id: The ID of the home for which to request an invite.
      device_id: The ID of the device making the request.
      email_address: The email address to send the invite to.
    """
    headers = lib.networking.utils.format_headers({
        "home-id": home_id,
        "device-id": device_id,
    })
    return await self.post(
        path=f"/homes/{home_id}/invite-requests/{email_address}",
        extra_headers=headers,
        cert_required=True,
    )

  async def get_invite_status_for_home(
      self,
      home_id: str,
      device_id: str,
      email_address: str,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """GET from the /homes/{home_id}/invite-status/{email_address} endpoint.

    Args:
      home_id: The ID of the home for which to request an invite.
      device_id: The ID of the device making the request.
      email_address: The email address to send the invite to.
    """
    headers = lib.networking.utils.format_headers({
        "home-id": home_id,
        "device-id": device_id,
    })
    return await self.get(
        path=f"/homes/{home_id}/invite-status/{email_address}",
        extra_headers=headers,
        cert_required=True,
    )
