import datetime
import typing

import lib.br_jwt.br_jwt
import lib.clients.web_api.client
import lib.clients.web_api_test_client.base
import lib.clients.web_api_test_client.utils
import lib.ulid


class WebAPIUsersTestClient(lib.clients.web_api_test_client.base.WebAPIBaseTestClient):

  async def post_users(self, **kwargs):
    email_address = kwargs.get(
        "email_address",
        lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    params = {
        "birthdate": "01/01/1980",
        "email_address": email_address,
        "family_name": "Isprettygreat",
        "given_name": "Olaf",
        "password": "password",
        "token": lib.br_jwt.br_jwt.encode_email_token(
            email_address=email_address,
            secret=self._web_api_jwt_secret,
            allowed_paths=["/users"],
        ),
    }
    params.update(kwargs)
    return await self._session.post_users(**params)

  async def delete_users(
      self,
      user_id: typing.Optional[str] = None,
      user_token: typing.Optional[str] = None,
      token: typing.Optional[str] = None,
      **kwargs,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    user_id = user_id or lib.ulid.generate(lib.ulid.IDType.USER).hex
    token = token or lib.br_jwt.br_jwt.encode_email_token(
        email_address=lib.clients.web_api_test_client.utils.create_randomized_email_address(),
        secret=self._web_api_jwt_secret,
        allowed_paths=["/users/{user_id}", "/users/{email_address}/homes"],
    )
    user_token = user_token or lib.br_jwt.br_jwt.encode_token(
        secret="TEST_USER_LOGIN_SECRET",
        payload=dict(
            user_id=user_id or lib.ulid.generate(lib.ulid.IDType.USER).hex,
            property_id=None,
            allowed_paths=["/users/{user_id}", "/users/{email_address}/homes"]
        ),
        issued_at=datetime.datetime.now(datetime.timezone.utc),
    )
    params = {
        "user_id": user_id,
        "token": token,
        "user_token": user_token,
    }
    params.update(kwargs)
    return await self._session.delete_users(**params)

  async def get_users_homes(
      self,
      email_address: typing.Optional[str] = None,
      token: typing.Optional[str] = None,
      user_token: typing.Optional[str] = None,
      **kwargs,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    email_address = (
        email_address or lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    token = token or lib.br_jwt.br_jwt.encode_email_token(
        email_address=email_address,
        secret=self._web_api_jwt_secret,
        allowed_paths=["/users/{user_id}", "/users/{email_address}/homes"],
    )
    user_token = user_token or lib.br_jwt.br_jwt.encode_token(
        secret="TEST_USER_LOGIN_SECRET",
        payload=dict(
            user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex,
            property_id=None,
            allowed_paths=["/users/{email_address}/homes"]
        ),
        issued_at=datetime.datetime.now(datetime.timezone.utc),
    )
    params = {
        "email_address": email_address,
        "token": token,
        "user_token": user_token,
    }
    params.update(kwargs)
    return await self._session.get_users_homes(**params)

  async def post_users_mfa_devices_phone_number_new(self, email_address=None, **kwargs):
    email_address = (
        email_address or lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    params = {
        "user_id": lib.ulid.generate(lib.ulid.IDType.USER).hex,
        "phone_number": "(123) 456-7890",
        "token": lib.br_jwt.br_jwt.encode_admin_registration_token(
            email_address=email_address,
            property_id=lib.ulid.generate(lib.ulid.IDType.ORGANIZATION_PROPERTY).hex,
            route_name="users_mfa_devices_phone_number_new",
            secret=self._web_api_admin_registration_jwt_secret,
        ),
    }
    params.update(kwargs)
    return await self._session.post_users_mfa_devices_phone_number_new(**params)

  async def post_users_verify_delete_user_code(
      self,
      email_address: typing.Optional[str] = None,
      token: typing.Optional[str] = None,
      user_token: typing.Optional[str] = None,
      verification_code: typing.Optional[str] = None,
      **kwargs,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    email_address = (
        email_address or lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    token = token or lib.br_jwt.br_jwt.encode_email_token(
        email_address=email_address,
        secret=self._web_api_jwt_secret,
        allowed_paths=["/users/{email_address}/verify-delete-user-code"],
    )
    user_token = user_token or lib.br_jwt.br_jwt.encode_token(
        secret="TEST_USER_LOGIN_SECRET",
        payload=dict(
            user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex,
            property_id=None,
            allowed_paths=["/users/{email_address}/verify-delete-user-code"]
        ),
        issued_at=datetime.datetime.now(datetime.timezone.utc),
    )
    verification_code = verification_code or "123456"
    params = {
        "email_address": email_address,
        "token": token,
        "user_token": user_token,
        "verification_code": verification_code,
    }
    params.update(kwargs)
    return await self._session.post_users_verify_delete_user_code(**params)

  async def delete_revoke_users_tokens(
      self,
      token: typing.Optional[str] = None,
      user_id: typing.Optional[str] = None,
      **kwargs,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    user_id = user_id or lib.ulid.generate(lib.ulid.IDType.USER).hex
    token = token or lib.br_jwt.br_jwt.encode_token(
        payload=dict(
            user_id=user_id,
            allowed_paths=["/users/{user_id}/tokens"],
        ),
        secret=self._web_api_login_jwt_secret,
        exp_timedelta=datetime.timedelta(days=30),
        issued_at=datetime.datetime.now(datetime.timezone.utc)
    )
    params = {
        "user_id": user_id,
        "token": token,
    }
    params.update(kwargs)
    return await self._session.delete_revoke_users_tokens(**params)
