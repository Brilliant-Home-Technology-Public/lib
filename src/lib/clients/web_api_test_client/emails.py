import datetime
import typing

import aiohttp

import lib.br_jwt.br_jwt
import lib.clients.web_api.client
import lib.clients.web_api_test_client.base
import lib.clients.web_api_test_client.utils
import lib.ulid


class WebAPIEmailsTestClient(lib.clients.web_api_test_client.base.WebAPIBaseTestClient):
  async def post_emails_admin_portal_verify_email(self, organization_id=None, **kwargs):
    organization_id = (
        organization_id or lib.ulid.generate(lib.ulid.IDType.ORGANIZATION_PROPERTY).hex
    )

    email_address = kwargs.get(
        "email_address",
        lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    params = {
        "email_address": email_address,
        "token": lib.br_jwt.br_jwt.encode_admin_registration_token(
            email_address=email_address,
            route_name="emails_admin_portal_verify_email",
            property_id=organization_id,
            secret=self._web_api_admin_registration_jwt_secret,
        ),
        "force": False,
    }
    params.update(kwargs)

    return await self._session.post_emails_admin_portal_verify_email(**params)

  async def post_send_tenant_verification_email(self, home_property_id=None, **kwargs):
    home_property_id = (
        home_property_id or lib.ulid.generate(lib.ulid.IDType.ORGANIZATION_PROPERTY).hex
    )
    email_address = kwargs.get(
        "email_address",
        lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    params = {
        "email_address": email_address,
        "token": lib.br_jwt.br_jwt.encode_admin_registration_token(
            email_address=email_address,
            route_name="emails_send_tenant_verification_email",
            property_id=home_property_id,
            secret=self._web_api_admin_registration_jwt_secret,
        ),
        "force": False,
    }
    params.update(kwargs)

    return await self._session.post_send_tenant_verification_email(**params)

  async def post_emails_verify_device(self, client_cert=None, **kwargs):
    client_cert = client_cert or self._default_client_cert
    params = {
        "code": "123456",
        "email_address": lib.clients.web_api_test_client.utils.create_randomized_email_address(),
        "token": lib.br_jwt.br_jwt.encode_device_token(client_cert=client_cert,
                                                       exp_timedelta=datetime.timedelta(hours=1),
                                                       secret=self._web_api_jwt_secret),
    }
    params.update(kwargs)

    return await self._session.post_emails_verify_device(**params)

  async def post_send_delete_user_verification_email(
      self,
      email_address: typing.Optional[str] = None,
      user_token: typing.Optional[str] = None,
      **kwargs,
  ):
    email_address = (
        email_address or lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    params = {
        "email_address": email_address,
        "token": user_token or lib.br_jwt.br_jwt.encode_token(
            secret="TEST_USER_LOGIN_SECRET",
            payload=dict(
                user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex,
                property_id=None,
                allowed_paths=["/emails/{email_address}/delete-user-verification-code"]
            ),
            issued_at=datetime.datetime.now(datetime.timezone.utc),
        ),
    }
    params.update(kwargs)

    return await self._session.post_send_delete_user_verification_email(**params)

  async def get_create_user_link(
      self,
      email_address: typing.Optional[str] = None,
  ) -> aiohttp.web.Response:
    email_address = (
        email_address or lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    params = {
        "email_address": email_address,
    }
    return await self._session.get_create_user_link(**params)

  async def post_verify_user_email(
      self,
      code: str = "123456",
      token: typing.Optional[str] = None,
      email_address: typing.Optional[str] = None,
  ) -> aiohttp.web.Response:
    email_address = email_address or lib.clients.web_api_test_client.utils.create_randomized_email_address()
    token = token or lib.br_jwt.br_jwt.encode_token(
        secret="TEST_USER_REGISTRATION_SECRET",
        payload=dict(
            email_address=email_address,
            property_id=None,
            allowed_paths=["registration_user_verify_email"]
        )
    )

    return await self._session.post_verify_user_email(
        code=code,
        email_address=email_address,
        token=token,
    )

  async def post_send_user_verification_email(
      self,
      token: typing.Optional[str] = None,
      email_address: typing.Optional[str] = None,
      force: bool = False,
  ) -> aiohttp.web.Response:
    email_address = email_address or lib.clients.web_api_test_client.utils.create_randomized_email_address()
    token = token or lib.br_jwt.br_jwt.encode_token(
        secret="TEST_USER_REGISTRATION_SECRET",
        payload=dict(
            email_address=email_address,
            property_id=None,
            allowed_paths=["emails_send_user_verification_email"]
        )
    )
    return await self._session.post_send_user_verification_email(
        email_address=email_address,
        token=token,
        force=force,
    )

  async def post_verify_root_ssh(
      self,
      email_address: typing.Optional[str] = None,
      code: str = "123456",
      control_id: typing.Optional[str] = None,
      home_id: typing.Optional[str] = None,
  ) -> aiohttp.web.Response:
    email_address = email_address or lib.clients.web_api_test_client.utils.create_randomized_email_address()
    home_id = home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex
    control_id = control_id or lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex

    return await self._session.post_verify_root_ssh(
        email_address=email_address,
        code=code,
        control_id=control_id,
        home_id=home_id,
    )
