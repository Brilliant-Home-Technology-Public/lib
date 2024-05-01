import datetime

import lib.br_jwt.br_jwt
import lib.clients.web_api_test_client.base
import lib.ulid


class WebAPIZendeskTestClient(lib.clients.web_api_test_client.base.WebAPIBaseTestClient):

  async def post_jwt(self, user_token=None):
    user_id = lib.ulid.generate(lib.ulid.IDType.USER)
    user_token = user_token or lib.br_jwt.br_jwt.encode_token(
        secret=self._web_api_jwt_secret,
        payload=dict(user_id=user_id),
        exp_timedelta=datetime.timedelta(hours=24),
    )
    return await self._session.post_jwt(user_token=user_token)

  async def zendesk_delete_user(
      self,
      email_address: str,
      user_to_delete_email_address: str,
      user_token: str,
      zendesk_user_token=None,
  ):
    return await self._session.zendesk_delete_user(
        email_address=email_address,
        user_to_delete_email_address=user_to_delete_email_address,
        user_token=user_token,
        zendesk_user_token=zendesk_user_token or lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_zendesk_jwt_secret,
            payload=dict(email_address=email_address),
            exp_timedelta=datetime.timedelta(minutes=1),
        ),
    )

  async def get_zendesk_graphql_token(self, email_address: str, token: str):
    return await self._session.get_zendesk_graphql_token(
        email_address=email_address,
        token=token or lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_zendesk_jwt_secret,
            payload=dict(email_address=email_address),
            exp_timedelta=datetime.timedelta(minutes=5),
        ),
    )
