import datetime

import lib.br_jwt.br_jwt
import lib.clients.web_api_test_client.base
import lib.clients.web_api_test_client.utils
import lib.ulid


class WebAPILoginTestClient(lib.clients.web_api_test_client.base.WebAPIBaseTestClient):

  async def post_login_admin(self, **kwargs):
    email_address = kwargs.get(
        "email_address",
        lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    params = {
        "email_address": email_address,
        "password": "password",
    }
    params.update(kwargs)
    return await self._session.post_login_admin(**params)

  async def post_login_user(self, **kwargs):
    email_address = kwargs.get(
        "email_address",
        lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    params = {
        "email_address": email_address,
        "password": "password",
    }
    params.update(kwargs)
    return await self._session.post_login_user(**params)

  async def post_login_admin_refresh(self, user_token=None):
    user_token = user_token or lib.br_jwt.br_jwt.encode_token(
        secret=self._web_api_login_jwt_secret,
        payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER)),
        exp_timedelta=datetime.exp_timedelta(hours=24),
    )
    return await self._session.post_login_admin_refresh(token=user_token)

  async def post_login_verify_mfa_code(self, email_address, code, token):
    return await self._session.post_login_verify_mfa_code(
        email_address=email_address,
        code=code,
        token=token,
    )

  async def post_login_user_verify_mfa_code(self, email_address, code, token):
    return await self._session.post_login_user_verify_mfa_code(
        email_address=email_address,
        code=code,
        token=token,
    )

  async def post_login_user_refresh(self, user_token=None):
    user_token = user_token or lib.br_jwt.br_jwt.encode_token(
        secret=self._web_api_user_login_jwt_secret,
        payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER)),
        exp_timedelta=datetime.exp_timedelta(days=30),
    )
    return await self._session.post_login_user_refresh(token=user_token)
