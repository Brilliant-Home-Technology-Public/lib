import json

import lib.clients.web_api.base


class WebAPIEntrataClient(lib.clients.web_api.base.WebAPIBaseClient):

  async def post_entrata_code(self,
                              auth_code,
                              token):
    """Post to the /entrata/code endpoint.

    Args:
      auth_code: The Entrata auth code.
      token: The user's login token.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with no JSON body.
    """
    data = json.dumps({
        "auth_code": auth_code,
    })
    headers = {
        "Authorization": "Bearer {}".format(token),
        "Content-Type": "application/json",
    }
    return await self.post(path="/entrata/code", data=data, extra_headers=headers)
