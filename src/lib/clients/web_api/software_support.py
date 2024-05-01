import lib.clients.web_api.base


class WebAPISoftwareSupportClient(lib.clients.web_api.base.WebAPIBaseClient):

  async def get_mobile_software_update(self, revision_id):
    """Get to the /mobile_software_update endpoint.

    Args:
      revision_id: Calendar version (zero-padded) of the mobile release to validate
          (e.g. "181206").

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
          {"status": <status>}
          Where status is "OK", "INVALID" or "UNSUPPORTED"
    """
    return await self.get(
        path="/mobile_software_update/{revision_id}".format(revision_id=revision_id),
    )

  async def get_switch_software_update(self, revision_id):
    """Get to the /software_update endpoint.

    Args:
      revision_id: SHA of the version to validate
          (e.g. "8898d02c389408c9d20a902f82825eb6096ab135886272237b74f01179bfd134").

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
          {"status": <status>}
          Where status is "OK" or "UNSUPPORTED"
    """
    return await self.get(
        path="/software_update/{revision_id}".format(revision_id=revision_id),
    )
