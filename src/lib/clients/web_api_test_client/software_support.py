import lib.br_jwt.br_jwt
import lib.clients.web_api_test_client.base
import lib.clients.web_api_test_client.utils


class WebAPISoftwareSupportTestClient(lib.clients.web_api_test_client.base.WebAPIBaseTestClient):

  async def get_mobile_software_update(self, **kwargs):
    params = {
        "revision_id": "18.12.04"
    }
    params.update(kwargs)
    return await self._session.get_mobile_software_update(**params)

  async def get_switch_software_update(self, **kwargs):
    params = {
        "revision_id": "a332fef7b69bed583d8f653a4c85565f317c46c23eb821541dd2a7418d8eb711"
    }
    params.update(kwargs)
    return await self._session.get_switch_software_update(**params)
