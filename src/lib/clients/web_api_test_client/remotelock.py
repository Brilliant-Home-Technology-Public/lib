import typing
import uuid

import lib.clients.web_api.client
import lib.clients.web_api_test_client.base
import lib.clients.web_api_test_client.utils
import lib.ulid


class WebAPIRemoteLockTestClient(lib.clients.web_api_test_client.base.WebAPIBaseTestClient):

  async def post_remotelock_code(self, code="a1b2c3d4e5", property_id=None, allow_redirects=True):
    property_id = property_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex
    return await self._session.post_remotelock_code(
        code=code,
        property_id=property_id,
        allow_redirects=allow_redirects,
    )

  async def post_update_remotelock_device_state(
      self,
      external_device_id: str = uuid.uuid4().hex,
      lock: bool = True,
      home_id: str = lib.ulid.generate(lib.ulid.IDType.HOME).hex,
      calling_device_id: str = lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    return await self._session.post_update_remotelock_device_state(
        external_device_id=external_device_id,
        calling_device_id=calling_device_id,
        lock=lock,
        home_id=home_id,
    )

  async def get_remotelock_devices_for_home(
      self,
      home_id: str = lib.ulid.generate(lib.ulid.IDType.HOME).hex,
      calling_device_id: str = lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    return await self._session.get_remotelock_devices_for_home(
        home_id=home_id,
        calling_device_id=calling_device_id,
    )

  async def post_remotelock_event(
      self,
      secret: str,
      data: typing.Dict[str, typing.Any]
  ):
    return await self._session.post_remotelock_event(
        secret=secret,
        data=data,
    )

  async def get_access_person(
      self,
      home_id: str,
      device_id: typing.Optional[str] = None,
      user_authorization_token: typing.Optional[str] = None,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    return await self._session.get_access_person(
        home_id=home_id,
        device_id=device_id,
        user_authorization_token=user_authorization_token,
    )
