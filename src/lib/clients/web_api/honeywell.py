import typing

import lib.clients.web_api.base


if typing.TYPE_CHECKING:
  import lib.clients.web_api.client


class WebAPIHoneywellClient(lib.clients.web_api.base.WebAPIBaseClient):

  async def get_honeywell_code(
      self,
      code: str,
      home_id: str,
  ) -> "lib.clients.web_api.client.WebAPIResponse":
    """GET from the /honeywell/code endpoint.

    Args:
      code: A string to exchange with Honeywell for an OAuth token.
      home_id: The ID of the home.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with the success page as content
    """
    return await self.get(path="/honeywell/code",
                          params={"state": home_id, "code": code},
                          cert_required=False)
