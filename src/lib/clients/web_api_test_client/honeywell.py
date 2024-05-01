import uuid

import lib.clients.web_api.client
import lib.clients.web_api_test_client.base
import lib.clients.web_api_test_client.utils


class WebAPIHoneywellTestClient(lib.clients.web_api_test_client.base.WebAPIBaseTestClient):

  async def get_honeywell_code(
      self,
      code=None,
      home_id=None,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    home_id = home_id or lib.ulid.generate(lib.ulid.IDType.HOME).hex
    code = code or uuid.uuid4().hex.upper()
    return await self._session.get_honeywell_code(code=code, home_id=home_id)
