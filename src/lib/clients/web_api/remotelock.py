import json
import typing

import lib.clients.web_api.base
import lib.networking.utils


if typing.TYPE_CHECKING:
  import lib.clients.web_api.client


class WebAPIRemoteLockClient(lib.clients.web_api.base.WebAPIBaseClient):

  async def post_remotelock_code(
      self,
      code: str,
      property_id: str,
      allow_redirects: bool = True,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """POST to the /remotelock/code endpoint.

    Args:
      code: A string to exchange with RemoteLock for an OAuth token.
      property_id: The ID of the property.
      allow_redirects: True, if this method should automatically redirect upon receiving a
          redirection response. False, otherwise.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with the success page as content
    """
    return await self.get(path="/remotelock/code",
                          params={"state": property_id, "code": code},
                          cert_required=False,
                          allow_redirects=allow_redirects)

  async def post_update_remotelock_device_state(
      self,
      external_device_id: str,
      lock: bool,
      home_id: str,
      calling_device_id: str,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """POST to the either the /remotelock/{external_device_id}/lock or
    /remotelock/{external_device_id}/unlock endpoint.

    Args:
      home_id: The ID of the calling device's home.
      calling_device_id: The ID of the device making this request.
    """
    headers = lib.networking.utils.format_headers({
        "home-id": home_id,
        "device-id": calling_device_id,
    })
    state = "lock" if lock else "unlock"
    return await self.post(
        cert_required=True,
        extra_headers=headers,
        path=f"/remotelock/{external_device_id}/{state}",
    )

  async def get_remotelock_devices_for_home(
      self,
      home_id: str,
      calling_device_id: str,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """GET from the /remotelock/{home_id}/devices endpoint.

    Args:
      home_id: The ID of the installing device's home.
      calling_device_id: The ID of the device making this request.
    """
    headers = lib.networking.utils.format_headers({
        "home-id": home_id,
        "device-id": calling_device_id,
    })
    return await self.get(
        cert_required=True,
        extra_headers=headers,
        path=f"/remotelock/{home_id}/devices",
    )

  async def post_remotelock_event(
      self,
      secret: str,
      data: typing.Dict[str, typing.Any],
  ):
    """POST to the /remotelock/event endpoint.

    Args:
      secret: The RemoteLock secret containing a property_id.
      data: JSON object representing a RemoteLock event.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with No Content
    """
    data_dump = json.dumps({
        "data": data,
    })
    headers = {
        "X-Secret": secret,
        "Content-Type": "application/json",
    }
    return await self.post(
        path="/remotelock/event",
        data=data_dump,
        extra_headers=headers,
    )

  async def get_access_person(
      self,
      home_id: str,
      device_id: typing.Optional[str] = None,
      user_authorization_token: typing.Optional[str] = None,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """GET to the /remotelock/{home_id}/access_person endpoint.

    Args:
      home_id: The home_id for which to get a RemoteLock access person.
      device_id: The ID of the device making this request.
      user_authorization_token: The JSON Web Token that authenticates the user's current session.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with the schema GetAccessPersonResponse
    """
    headers = {}
    if home_id and device_id:
      headers.update(lib.networking.utils.format_headers({
          "home-id": home_id,
          "device-id": device_id,
      }))
    if user_authorization_token:
      headers.update({"Authorization": f"Bearer {user_authorization_token}"})
    return await self.get(
        path=f"/remotelock/{home_id}/access_person",
        cert_required=True,
        extra_headers=headers,
    )
