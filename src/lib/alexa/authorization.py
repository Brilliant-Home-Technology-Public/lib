import asyncio
import inspect
import json
import logging
import ssl
import typing
import urllib.parse

import aiohttp

import lib.networking.utils


log = logging.getLogger(__name__)


class AmazonError(Exception):
  def __init__(self, response_status, response_text):
    super().__init__("Alexa auth error (status: {}): {}".format(response_status, response_text))
    self.response_status = response_status
    self.response_text = response_text


class RefreshTokenError(AmazonError):
  """
  Raised when Amazon tells us we have used a bad token to make a request.
  """


CLIENT_ID = 'amzn1.application-oa2-client.863cf538324c4ca1bf1739195fbc6dce'


class AVSOauth:
  '''
  Alexa Voice Services Authentication Class

  Access to the AVS API requires an access token, which expires hourly.
  New access tokens (and refresh tokens) are obtained through a refresh token
  '''
  USER_AUTHORIZATION_URL = "https://www.amazon.com/ap/oa"
  TOKEN_EXCHANGE_URL = "https://api.amazon.com/auth/o2/token"
  # changing this will invalidate existing refresh tokens
  REDIRECT_URI = "https://web-api.brilliant.tech/alexa/code"

  def __init__(self, client_id=None, client_secret=None):
    self.client_id = client_id or CLIENT_ID
    self.client_secret = client_secret

  @classmethod
  def get_user_authorization_endpoint(cls, serial_number):
    scope_dict = {
        "alexa:all": {
            "productID": "brilliant",
            "productInstanceAttributes": {
                "deviceSerialNumber": serial_number,
            },
        }
    }

    scope_data = json.dumps(scope_dict, separators=(',', ':'))  # compact json with no whitespace
    query_params = {
        "client_id": CLIENT_ID,
        "scope_data": scope_data,
        "redirect_uri": cls.REDIRECT_URI,
        "response_type": "code",
        "scope": "alexa:all",
    }
    return "%s?%s" % (cls.USER_AUTHORIZATION_URL, urllib.parse.urlencode(query_params))

  async def exchange_code_for_token(self,
                                    code: str,
                                    loop: typing.Optional[asyncio.AbstractEventLoop] = None,
                                    include_redirect_uri: bool = True,
                                    return_expires_in: bool = False,
                                    client_id: str = ''):
    query_args = self._get_code_exchange_query_args(
        code=code,
        client_id=client_id or self.client_id,
        # client_secret is not necessary if a non-default client_id has been passed in from mobile
        client_secret=None if client_id else self.client_secret,
        include_redirect_uri=include_redirect_uri,
    )
    async with self.create_session(loop=loop) as session:
      async with session.request(
          method="POST",
          url=self.TOKEN_EXCHANGE_URL,
          headers=self._get_oauth_headers(),
          data=urllib.parse.urlencode(query_args).encode('ascii'),
      ) as resp:
        data = await self._handle_access_token_response(resp)
    if return_expires_in:
      return (data["access_token"], data["refresh_token"], data["expires_in"])
    return (data["access_token"], data["refresh_token"])

  async def refresh_token(self,
                          refresh_token: str,
                          loop: typing.Optional[asyncio.AbstractEventLoop] = None,
                          include_redirect_uri: bool = True,
                          return_expires_in: bool = False,
                          client_id: str = '',
                          override_token_url: str = '',
                          override_headers: typing.Optional[dict[str, str]] = None):
    ''' takes a refresh_token and returns new access_token and refresh_token in a tuple '''
    query_args = self._get_token_exchange_query_args(
        refresh_token=refresh_token,
        client_id=client_id or self.client_id,
        # client_secret is not necessary if a non-default client_id has been passed in from mobile
        client_secret=None if client_id else self.client_secret,
        include_redirect_uri=include_redirect_uri,
    )
    url = override_token_url if override_token_url else self.TOKEN_EXCHANGE_URL
    headers = override_headers if override_headers else self._get_oauth_headers()
    async with self.create_session(loop=loop) as session:
      async with session.request(
          method="POST",
          url=url,
          headers=headers,
          data=urllib.parse.urlencode(query_args).encode('ascii'),
      ) as resp:
        data = await self._handle_access_token_response(resp)
    if return_expires_in:
      return (data["access_token"], data["refresh_token"], data["expires_in"])
    return (data["access_token"], data["refresh_token"])

  def create_session(self, loop=None):
    # We must specify our ssl context when using OPENSSL 1.0.2
    sslcontext = lib.networking.utils.get_ssl_context(
        purpose=ssl.Purpose.SERVER_AUTH,
        load_cert_chain=False,
    )
    if "ssl" in inspect.getfullargspec(aiohttp.TCPConnector).kwonlyargs:
      # Maintain compatibility with older versions of aiohttp that do not have "ssl" as a kwarg.
      conn = aiohttp.TCPConnector(
          ssl=sslcontext,
          loop=loop,
      )  # pylint: disable=unexpected-keyword-arg
    else:
      conn = aiohttp.TCPConnector(ssl_context=sslcontext, loop=loop)
    return aiohttp.ClientSession(connector=conn, loop=loop)

  async def _handle_access_token_response(self, response):
    if 200 <= response.status <= 299:
      return await response.json()
    if 400 <= response.status <= 499:
      # This is a known error if you try to get an access token with another access token.
      raise RefreshTokenError(response_status=response.status,
                              response_text=await response.text())
    raise AmazonError(response_status=response.status, response_text=await response.text())

  def _get_oauth_headers(self):
    return {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Cache-Control': 'no-cache',
    }

  def _get_token_exchange_query_args(
      self,
      refresh_token,
      client_id,
      client_secret,
      include_redirect_uri,
  ):
    params = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    if include_redirect_uri:
      params["redirect_uri"] = self.REDIRECT_URI
    return params

  def _get_code_exchange_query_args(
      self,
      code,
      client_id,
      client_secret,
      include_redirect_uri,
  ):
    params = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
    }
    if include_redirect_uri:
      params["redirect_uri"] = self.REDIRECT_URI
    return params
