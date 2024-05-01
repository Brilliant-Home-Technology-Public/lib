import datetime

import lib.br_jwt.br_jwt
import lib.clients.web_api_test_client.base
import lib.clients.web_api_test_client.utils
import lib.ulid


class WebAPIGraphQLHomesTestClient(lib.clients.web_api_test_client.base.WebAPIBaseTestClient):

  async def post_graphql_homes(self, query, user_token=None):
    user_token = user_token or lib.br_jwt.br_jwt.encode_token(
        secret=self._web_api_login_jwt_secret,
        payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER)),
        exp_timedelta=datetime.exp_timedelta(hours=24),
    )
    return await self._session.post_graphql_homes(
        user_token=user_token,
        query=query,
    )
