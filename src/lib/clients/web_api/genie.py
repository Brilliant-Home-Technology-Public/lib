import lib.clients.web_api.base
import lib.networking.utils


class WebAPIGenieClient(lib.clients.web_api.base.WebAPIBaseClient):

  async def post_genie_code(self, code, home_id):
    """POST to the /genie/code endpoint.

    Args:
      code: A string to exchange with Genie for an OAuth token.
      home_id: The ID of the home.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with the success page as content
    """
    return await self.get(path="/genie/code",
                          params={"state": home_id, "code": code},
                          cert_required=False)
