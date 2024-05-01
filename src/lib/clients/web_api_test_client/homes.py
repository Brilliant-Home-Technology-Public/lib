import datetime
import typing

import lib.br_jwt.br_jwt
import lib.clients.web_api.client
import lib.clients.web_api_test_client.base
import lib.clients.web_api_test_client.utils
import lib.serialization
from lib.test_helpers import data_helpers
import lib.ulid


class WebAPIHomesTestClient(lib.clients.web_api_test_client.base.WebAPIBaseTestClient):
  async def delete_home(
      self,
      control_id: str,
      email_address: str,
      home_id: str,
      verification_code: str,
  ):
    return await self._session.delete_home(
        control_id=control_id or lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
        email_address=email_address or lib.clients.web_api_test_client.utils.create_randomized_email_address(),
        home_id=home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        verification_code=verification_code or "123456",
    )

  async def delete_user_from_home(self, **kwargs):
    params = {
        "home_id": lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        "user_id": lib.ulid.generate(lib.ulid.IDType.USER).hex,
        "user_token": lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_jwt_secret,
            payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
            exp_timedelta=datetime.timedelta(hours=1),
        ),
    }
    params.update(kwargs)

    return await self._session.delete_user_from_home(**params)

  async def post_homes(self, client_cert=None, user_id=None, **kwargs):
    client_cert = client_cert or self._default_client_cert
    user_id = user_id or lib.ulid.generate(lib.ulid.IDType.USER).hex
    params = {
        "device_id": lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
        "token": lib.br_jwt.br_jwt.encode_device_token(client_cert=client_cert,
                                                       payload=dict(user_id=user_id),
                                                       exp_timedelta=datetime.timedelta(minutes=1),
                                                       secret=self._web_api_jwt_secret),
    }
    params.update(kwargs)

    return await self._session.post_homes(**params)

  async def post_homes_v2(self, client_cert=None, user_id=None, **kwargs):
    client_cert = client_cert or self._default_client_cert
    user_id = user_id or lib.ulid.generate(lib.ulid.IDType.USER).hex
    params = {
        "device_id": lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
        "home_name": "BrilliantHome",
        "token": lib.br_jwt.br_jwt.encode_device_token(client_cert=client_cert,
                                                       payload=dict(user_id=user_id),
                                                       exp_timedelta=datetime.timedelta(minutes=1),
                                                       secret=self._web_api_jwt_secret),
    }
    params.update(kwargs)

    return await self._session.post_homes_v2(**params)

  async def post_homes_complete_installation(
      self,
      device_id: typing.Optional[str] = None,
      home_id: typing.Optional[str] = None,
      honeywell_devices: typing.Optional[typing.List[typing.Dict[str, typing.Any]]] = None,
      switch_variables_per_control_id: typing.Optional[
          typing.Dict[str, typing.List[typing.Dict[str, str]]]
      ] = None,
      installed_devices: typing.Optional[typing.Dict[str, str]] = None,
      admin_jwt_token: str | None = None,
  ):
    home_id = home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex
    honeywell_devices = honeywell_devices or []
    switch_variables_per_control_id = switch_variables_per_control_id or {}
    installed_devices = installed_devices or {"D0": device_id} if device_id else {}

    return await self._session.post_homes_complete_installation(
        device_id=device_id,
        device_provision_state=data_helpers.get_device_provision_state(
            honeywell_devices=honeywell_devices,
            switch_variables_per_control_id=switch_variables_per_control_id,
        ),
        home_id=home_id,
        serialized_post_provision_state_config=lib.serialization.serialize(
            data_helpers.get_post_provision_state_config(
                device_id=device_id,
                state_config_id="",
            ),
        ),
        installed_devices=installed_devices,
        admin_jwt_token=admin_jwt_token,
    )

  async def post_send_delete_home_verification_email(
      self,
      control_id: typing.Optional[str] = None,
      home_id: typing.Optional[str] = None,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    return await self._session.post_send_delete_home_verification_email(
        control_id=control_id or lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
        home_id=home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex,
    )

  async def post_homes_devices(
      self,
      client_cert: bytes | None = None,
      payload: dict[str, typing.Any] | None = None,
      user_id: str | None = None,
      **kwargs,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    client_cert = client_cert or self._default_client_cert
    user_id = user_id or lib.ulid.generate(lib.ulid.IDType.USER).hex
    params = {
        "device_id": lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
        "home_id": lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        "token": lib.br_jwt.br_jwt.encode_device_token(
            client_cert=client_cert,
            payload=payload or dict(user_id=user_id),
            exp_timedelta=datetime.timedelta(minutes=1),
            secret=self._web_api_jwt_secret,
        ),
    }
    params.update(kwargs)

    return await self._session.post_homes_devices(**params)

  async def post_homes_configuration(
      self,
      configuration_id: typing.Optional[str] = None,
      date: typing.Optional[str] = None,
      home_id: typing.Optional[str] = None,
      token: typing.Optional[str] = None,
      time: typing.Optional[str] = None,
      user_id: typing.Optional[str] = None,
  ):
    user_id = user_id or lib.ulid.generate(lib.ulid.IDType.USER).hex
    token = token or lib.br_jwt.br_jwt.encode_device_token(
        client_cert=self._default_client_cert,
        exp_timedelta=datetime.timedelta(minutes=10),
        payload=dict(user_id=user_id),
        secret=self._web_api_jwt_secret,
    )
    params = {
        "configuration_id": configuration_id or lib.ulid.generate(lib.ulid.IDType.STATE_CONFIG).hex,
        "home_id": home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        "token": token,
        "date": date,
        "time": time,
    }
    return await self._session.post_homes_configuration(**params)

  async def get_homes_installation_template(
      self,
      home_id: typing.Optional[str] = None,
      user_id: typing.Optional[str] = None,
      user_token: typing.Optional[str] = None,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    home_id = home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex
    user_id = user_id or lib.ulid.generate(lib.ulid.IDType.USER).hex
    token = user_token or lib.br_jwt.br_jwt.encode_token(
        secret=self._web_api_login_jwt_secret,
        payload=dict(user_id=user_id),
        exp_timedelta=datetime.timedelta(hours=1),
    )

    return await self._session.get_homes_installation_template(home_id=home_id, user_token=token)

  async def get_homes_user_token(self, device_id=None, home_id=None):
    device_id = device_id or lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex
    home_id = home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex
    return await self._session.get_homes_user_token(device_id=device_id, home_id=home_id)

  async def post_homes_unicast_addresses(self,
                                         device_id=None,
                                         home_id=None,
                                         new_device_id=None,
                                         num_elements=None):
    device_id = device_id or lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex
    home_id = home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex
    new_device_id = new_device_id or lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex
    num_elements = num_elements or 2
    return await self._session.post_homes_unicast_addresses(
        device_id=device_id,
        home_id=home_id,
        new_device_id=new_device_id,
        num_elements=num_elements,
    )

  async def get_zendesk_user_token(self, user_token=None, home_id=None):
    home_id = home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex
    user_token = user_token or lib.br_jwt.br_jwt.encode_token(
        secret=self._web_api_jwt_secret,
        payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
        exp_timedelta=datetime.timedelta(hours=1),
    )
    return await self._session.get_zendesk_user_token(user_token=user_token, home_id=home_id)

  async def post_invite_user_to_home(self, **kwargs):
    params = {
        "email_address": lib.clients.web_api_test_client.utils.create_randomized_email_address(),
        "home_id": lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        "user_token": lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_jwt_secret,
            payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
            exp_timedelta=datetime.timedelta(hours=1),
        ),
    }
    params.update(kwargs)

    return await self._session.post_invite_user_to_home(**params)

  async def post_resend_invite_to_home(self, **kwargs):
    params = {
        "email_address": lib.clients.web_api_test_client.utils.create_randomized_email_address(),
        "home_id": lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        "user_token": lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_jwt_secret,
            payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
            exp_timedelta=datetime.timedelta(hours=1),
        ),
    }
    params.update(kwargs)

    return await self._session.post_resend_invite_to_home(**params)

  async def post_user_invite_users_to_home(self, **kwargs):
    params = {
        "email_addresses": [
            lib.clients.web_api_test_client.utils.create_randomized_email_address(),
        ],
        "home_id": lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        "user_token": lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_jwt_secret,
            payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
            exp_timedelta=datetime.timedelta(hours=1),
        ),
    }
    params.update(kwargs)

    return await self._session.post_user_invite_users_to_home(**params)

  async def post_user_accept_invite_to_home(self, **kwargs):
    params = {
        "home_id": lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        "user_token": lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_jwt_secret,
            payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
            exp_timedelta=datetime.timedelta(hours=1),
        ),
    }
    params.update(kwargs)

    return await self._session.post_user_accept_invite_to_home(**params)

  async def get_home_token(self, home_id, user_auth_token):
    return await self._session.get_home_token(
        home_id=home_id,
        token=user_auth_token,
    )

  async def delete_invite_to_home(self, **kwargs):
    params = {
        "email_address": lib.clients.web_api_test_client.utils.create_randomized_email_address(),
        "home_id": lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        "user_token": lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_jwt_secret,
            payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
            exp_timedelta=datetime.timedelta(hours=1),
        ),
    }
    params.update(kwargs)

    return await self._session.delete_invite_to_home(**params)

  async def post_send_root_ssh_verification_email(self, home_id: str, control_id: str):
    return await self._session.post_send_root_ssh_verification_email(
        home_id=home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        control_id=control_id or lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
    )

  async def get_homes_check_assets(
      self,
      home_id: str | None = None,
      device_id: str | None = None,
      user_token: str | None = None,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    return await self._session.get_homes_check_assets(
        home_id=home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        device_id=device_id or lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
        user_token=user_token or lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_jwt_secret,
            payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
            exp_timedelta=datetime.timedelta(hours=1),
        )
    )

  async def post_homes_new_asset(
      self,
      home_id: str | None = None,
      device_id: str | None = None,
      asset_data_dict: dict[str, bytes] | None = None,
      content_type: str | None = None,
      library_id: str | None = None,
      asset_title: str | None = None,
      user_token: str | None = None,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    return await self._session.post_homes_new_asset(
        home_id=home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        device_id=device_id or lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
        # The sample PNG is a 2x2 black image.
        asset_data_dict=asset_data_dict or {"asset_data": (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02\x08\x02\x00\x00\x00"
            b"\xfd\xd4\x9as\x00\x00\x00\x0bIDATx\x9cc`@\x06\x00\x00\x0e\x00\x01\xa9\x91s\xb1\x00\x00"
            b"\x00\x00IEND\xaeB`\x82"
        )},
        content_type=content_type or "image/png",
        library_id=library_id or "library:custom_art",
        asset_title=asset_title or "test.png",
        user_token=user_token or lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_jwt_secret,
            payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
            exp_timedelta=datetime.timedelta(hours=1),
        )
    )

  async def delete_homes_asset(
      self,
      home_id: str | None = None,
      device_id: str | None = None,
      library_id: str | None = None,
      s3_key: str | None = None,
      user_token: str | None = None,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    return await self._session.delete_homes_asset(
        home_id=home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        device_id=device_id or lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
        library_id=library_id or lib.ulid.generate(lib.ulid.IDType.USER_LIBRARY).hex,
        # Since this is just for testing purposes it's probably fine to use the USER_LIBRARY ID type
        # for the S3 key here.
        s3_key=s3_key or lib.ulid.generate(lib.ulid.IDType.USER_LIBRARY).hex,
        user_token=user_token or lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_jwt_secret,
            payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
            exp_timedelta=datetime.timedelta(hours=1),
        )
    )

  async def post_request_invite_for_home(
      self,
      home_id: str | None = None,
      device_id: str | None = None,
      email_address: str | None = None,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    return await self._session.post_request_invite_for_home(
        home_id=home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        device_id=device_id or lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
        email_address=email_address or lib.clients.web_api_test_client.utils.create_randomized_email_address(),
    )

  async def get_invite_status_for_home(
      self,
      home_id: str | None = None,
      device_id: str | None = None,
      email_address: str | None = None,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    return await self._session.get_invite_status_for_home(
        home_id=home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        device_id=device_id or lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
        email_address=email_address or lib.clients.web_api_test_client.utils.create_randomized_email_address(),
    )
