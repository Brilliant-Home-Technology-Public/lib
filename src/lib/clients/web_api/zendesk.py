import lib.clients.web_api.base


class WebAPIZendeskClient(lib.clients.web_api.base.WebAPIBaseClient):

  async def post_jwt(self, user_token):
    """Post to the /zendesk/jwt endpoint.

    Args:
      user_token: The opaque user token we have provided to Zendesk.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
          {"jwt: <JSON Web Token encoded with the shared Zendesk secret>}
    """
    data = {
        "user_token": user_token,
    }
    return await self.post(path="/zendesk/jwt", data=data)

  async def zendesk_delete_user(
      self,
      email_address: str,
      user_to_delete_email_address: str,
      user_token: str,
      zendesk_user_token: str,
  ):
    """Sends a delete request to /zendesk/proxy/zendesk/users/{email_address}.
    Deletes the Zendesk user associated with the given email address.

    Args:
      email_address: The email address of the Zendesk user who is deleting a Brilliant user account
        (this will usually be a customer support agent or at least a Brilliant employee).
      user_to_delete_email_address: The email address of the user we want to delete.
      user_token: The user token for the user whose Zendesk user we want to delete.
      zendesk_user_token: The Zendesk user token for the user who is deleting a Brilliant user.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
          {"success": <True if the user was deleted, False otherwise>}
    """
    data = {
        "email_address": email_address,
        "token": zendesk_user_token,
        "Authorization": f"Bearer {user_token}",
    }
    return await self.delete(path=f"/zendesk/users/{user_to_delete_email_address}", json=data)

  async def get_zendesk_graphql_token(self, email_address: str, token: str):
    """Sends a GET request to /zendesk/graphql-token/{email_address}.
    Retrieves a JWT for the user with the given email address that allows them to hit
    our GraphQL endpoint at /graphql.

    Args:
      email_address: The email address of the user for whom we want to get the JWT.
      token: The Zendesk user token for the user who is requesting the JWT.
    """
    params = {
        "token": token,
    }
    return await self.get(
        path=f"/zendesk/graphql-token/{email_address}",
        params=params,
    )
