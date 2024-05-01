import json

import lib.clients.web_api.base


class WebAPIGraphQLHomesClient(lib.clients.web_api.base.WebAPIBaseClient):

  async def post_graphql_homes(self,
                               user_token,
                               query):
    """Post to the /graphql endpoint.

    Args:
      user_token: The user's authorization token.
      query: The graphql query to execute as a string.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing the graphQL response.
    """
    data = json.dumps({"query": query})
    headers = {
        "Authorization": "Bearer {}".format(user_token),
        "Content-Type": "application/json",
    }
    return await self.post(path="/graphql",
                           data=data,
                           extra_headers=headers)
