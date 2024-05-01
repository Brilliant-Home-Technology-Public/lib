import asyncio
import copy


def handle_rate_limit(func):
  """A decorator that will handle requests that have been rejected due to hitting the rate limit. If
  the WebAPIBaseClass has the `retry_rate_limit` field set to True, this decorator will attempt hte
  request up to three times after a brief sleep. If `retry_rate_limit` is set to False, then this
  decorator will immediately return the rate limited response.
  """
  async def _handle_rate_limit(self, *args, **kwargs):
    attempts = 3 if self.retry_rate_limit else 1
    while attempts:
      attempts -= 1
      resp = await func(self, *args, **kwargs)
      if resp.http_status == 429:
        await asyncio.sleep(.5)
      else:
        break
    return resp
  return _handle_rate_limit


class WebAPIBaseClient:
  """The base client from which all other WebAPIClients should inherit."""

  def __init__(self, session, retry_rate_limit=True):
    """
    retry_rate_limit: True if any rate limited requests should be retried. False if rate limited
        requests should not be retried.
    session: The WebAPIClientSession to use to make requests.
    """
    self.retry_rate_limit = retry_rate_limit
    self.session = session

  @handle_rate_limit
  async def get(self, *args, **kwargs):
    return await self.session.get(*args, **kwargs)

  @handle_rate_limit
  async def post(self, *args, **kwargs):
    return await self.session.post(*args, **kwargs)

  @handle_rate_limit
  async def put(self, *args, **kwargs):
    return await self.session.put(*args, **kwargs)

  @handle_rate_limit
  async def delete(self, *args, **kwargs):
    return await self.session.delete(*args, **kwargs)

  @staticmethod
  def get_headers(default_headers, header_updates=None):
    """Create a dictionary of headers. Any dictionary values that are set to None will be removed
    from the resulting headers dictionary.

    Args:
      default_headers: A dictionary of default header values.
      header_updates: A dictionary containing updates to apply to the the default_headers.
    """
    # Copy the default headers to avoid modifying the input dictionary.
    headers = copy.deepcopy(default_headers) if default_headers else {}
    header_updates = header_updates or {}
    headers.update(header_updates)

    return dict((key, value) for key, value in headers.items() if value is not None)
