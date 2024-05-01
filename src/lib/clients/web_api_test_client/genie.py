import lib.clients.web_api_test_client.base
import lib.clients.web_api_test_client.utils


class WebAPIGenieTestClient(lib.clients.web_api_test_client.base.WebAPIBaseTestClient):

  async def post_genie_code(self, code, home_id=None):
    home_id = home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex
    return await self._session.post_genie_code(code=code, home_id=home_id)
