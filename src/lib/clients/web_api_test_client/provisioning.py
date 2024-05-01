import base64
import datetime
import typing
import uuid

import lib.br_jwt.br_jwt
import lib.clients.web_api.base


class WebAPIProvisioningTestClient(lib.clients.web_api_test_client.base.WebAPIBaseTestClient):

  async def get_challenge(self) -> bytes:
    resp = await self._session.get_challenge()
    challenge_b64 = resp.json()["challenge"]
    return base64.b64decode(challenge_b64)

  async def post_register_app(
      self,
      mobile_device_id: typing.Optional[str] = None,
      mobile_device_model: typing.Optional[str] = None,
  ):
    params = dict(
        mobile_device_id=mobile_device_id or uuid.uuid4().hex,
        mobile_device_model=mobile_device_model or "iPhone 5"
    )

    return await self._session.post_register_app(**params)

  async def get_virtual_control_self_bootstrap(
      self,
      home_property_id: str | None = None,
      token: str | None = None,
  ):
    if not token:
      token = lib.br_jwt.br_jwt.encode_token(
          payload=dict(
              allowed_paths=["/provisioning/virtual-control-self-bootstrap"],
              property_id=home_property_id,
          ),
          secret="SECRET",
          exp_timedelta=datetime.timedelta(days=7),
      )
    params = dict(
        home_property_id=home_property_id if home_property_id else uuid.uuid4().hex,
        token=token,
    )

    return await self._session.get_virtual_control_self_bootstrap(**params)
