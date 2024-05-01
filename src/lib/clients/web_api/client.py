import json
import urllib.parse

import aiohttp

import lib.clients.web_api.art
import lib.clients.web_api.devices
import lib.clients.web_api.emails
import lib.clients.web_api.entrata
import lib.clients.web_api.genie
import lib.clients.web_api.graphql_homes
import lib.clients.web_api.homes
import lib.clients.web_api.honeywell
import lib.clients.web_api.login
import lib.clients.web_api.organizations
import lib.clients.web_api.provisioning
import lib.clients.web_api.registration
import lib.clients.web_api.remotelock
import lib.clients.web_api.software_support
import lib.clients.web_api.users
import lib.clients.web_api.zendesk
import lib.networking.utils as networking_utils


class WebAPIResponse:
  def __init__(self, http_status, body, headers):
    """
    Args:
      http_status: The response's HTTP status code as an integer.
      body: The body of the response as a string.
      headers: A multidict.MultiDict object containing all of the headers in the response.
    """
    self.http_status = http_status
    self.body = body
    self.headers = headers

  @classmethod
  async def convert_aiohttp_response(cls, aiohttp_resp):
    return WebAPIResponse(body=await aiohttp_resp.text(),
                          headers=aiohttp_resp.headers,
                          http_status=aiohttp_resp.status)

  def json(self):
    return json.loads(self.body)

  def __repr__(self):
    return ("WebAPIResponse(http_status={http_status}, body={body}, headers={headers})".format(
        http_status=self.http_status,
        body=self.body,
        headers=self.headers,
    ))

  def __eq__(self, other):
    return bool(self.http_status == other.http_status
                and self.body == other.body
                and self.headers == other.headers)


class WebAPIClientSession:

  def __init__(
      self,
      cert_dir,
      cert_file_prefix,
      web_api_server_prefix,
      cert_port,
      non_cert_port,
      loop=None,
      connect_timeout=30,
      use_ssl=True,
  ):
    self._cert_dir = cert_dir
    self._cert_file_prefix = cert_file_prefix
    self._server_prefix = web_api_server_prefix
    self._ssl_context = self._get_ssl_context() if use_ssl else None
    self.cert_port = cert_port
    self.non_cert_port = non_cert_port
    self._loop = loop

    ##########################
    # Implementation Clients #
    ##########################
    self.art = lib.clients.web_api.art.WebAPIArtClient(self)
    self.devices = lib.clients.web_api.devices.WebAPIDevicesClient(self)
    self.entrata = lib.clients.web_api.entrata.WebAPIEntrataClient(self)
    self.emails = lib.clients.web_api.emails.WebAPIEmailsClient(self)
    self.genie = lib.clients.web_api.genie.WebAPIGenieClient(self)
    self.graphql_homes = lib.clients.web_api.graphql_homes.WebAPIGraphQLHomesClient(self)
    self.homes = lib.clients.web_api.homes.WebAPIHomesClient(self)
    self.honeywell = lib.clients.web_api.honeywell.WebAPIHoneywellClient(self)
    self.login = lib.clients.web_api.login.WebAPILoginClient(self)
    self.organizations = lib.clients.web_api.organizations.WebAPIOrganizationsClient(self)
    self.provisioning = lib.clients.web_api.provisioning.WebAPIProvisioningClient(self)
    self.registration = lib.clients.web_api.registration.WebAPIRegistrationClient(self)
    self.remotelock = lib.clients.web_api.remotelock.WebAPIRemoteLockClient(self)
    self.software_support = lib.clients.web_api.software_support.WebAPISoftwareSupportClient(self)
    self.users = lib.clients.web_api.users.WebAPIUsersClient(self)
    self.zendesk = lib.clients.web_api.zendesk.WebAPIZendeskClient(self)

    # Hack for compatibility between different versions of aiohttp.
    if hasattr(aiohttp, "ClientTimeout"):
      self._session_timeout = aiohttp.ClientTimeout(connect=connect_timeout)
    else:
      self._session_timeout = connect_timeout

  def get_cert_files(self):
    key_file = "{}/{}.key".format(self._cert_dir, self._cert_file_prefix)
    cert_file = "{}/{}.cert".format(self._cert_dir, self._cert_file_prefix)
    return key_file, cert_file

  def _get_ssl_context(self):
    _, address_family, connection_args, _ = networking_utils.parse_address(self._server_prefix)
    return lib.networking.utils.get_ssl_context_for_host(
        address_family=address_family,
        host=connection_args["host"],
        cert_file_directory=self._cert_dir,
    )

  def _get_connector_and_url(self, path, cert_required):
    if cert_required and not self._ssl_context:
      raise ValueError("Cannot require certificates for a non-SSL client.")
    # The connector must be newly created for each ClientSession.
    # Set the `ssl` parameter to `False` to use HTTP.
    connector = aiohttp.TCPConnector(ssl=self._ssl_context or False, loop=self._loop)
    port = self.cert_port if cert_required else self.non_cert_port
    url = urllib.parse.urljoin("{}:{}".format(self._server_prefix, port), path)
    return connector, url

  async def request(self, method, path, extra_headers=None, cert_required=False, **kwargs):
    """Make an HTTP request with the specified method for the provided path.

    Any additional keyword argument is passed through to the `aiohttp` client request method. See
    https://docs.aiohttp.org/en/stable/client_reference.html#aiohttp.ClientSession.request for more
    details on which arguments are available.
    """
    connector, url = self._get_connector_and_url(path, cert_required)
    extra_headers = extra_headers or {}
    session_args = dict(connector=connector, loop=self._loop)
    if hasattr(aiohttp, "ClientTimeout"):
      session_args["timeout"] = self._session_timeout
    else:
      session_args["conn_timeout"] = self._session_timeout
    async with aiohttp.ClientSession(**session_args) as session:
      async with session.request(method=method, url=url, headers=extra_headers, **kwargs) as resp:
        return await WebAPIResponse.convert_aiohttp_response(aiohttp_resp=resp)

  async def get(self, path, extra_headers=None, cert_required=False, **kwargs):
    """Make a GET request for the provided path.

    Any additional keyword argument is passed through to the `aiohttp` client request method. See
    https://docs.aiohttp.org/en/stable/client_reference.html#aiohttp.ClientSession.request for more
    details on arguments are available.
    """
    return await self.request(
        method="GET",
        path=path,
        extra_headers=extra_headers,
        cert_required=cert_required,
        **kwargs
    )

  async def put(
      self,
      path,
      extra_headers=None,
      cert_required=False,
      **kwargs,
  ):
    """Make a PUT request for the provided path.

    Any additional keyword argument is passed through to the `aiohttp` client request method. See
    https://docs.aiohttp.org/en/stable/client_reference.html#aiohttp.ClientSession.request for more
    details on arguments are available. Some common keyword arguments here are `data` and `json`.
    """
    return await self.request(
        method="PUT",
        path=path,
        extra_headers=extra_headers,
        cert_required=cert_required,
        **kwargs
    )

  async def post(
      self,
      path,
      extra_headers=None,
      cert_required=False,
      **kwargs,
  ):
    """Make a POST request for the provided path.

    Any additional keyword argument is passed through to the `aiohttp` client request method. See
    https://docs.aiohttp.org/en/stable/client_reference.html#aiohttp.ClientSession.request for more
    details on arguments are available. Some common keyword arguments here are `data` and `json`.
    """
    return await self.request(
        method="POST",
        path=path,
        extra_headers=extra_headers,
        cert_required=cert_required,
        **kwargs
    )

  async def delete(
      self,
      path,
      extra_headers=None,
      cert_required=False,
      **kwargs,
  ):
    """Make a DELETE request for the provided path.

    Any additional keyword argument is passed through to the `aiohttp` client request method. See
    https://docs.aiohttp.org/en/stable/client_reference.html#aiohttp.ClientSession.request for more
    details on arguments are available. Some common keyword arguments here are `data` and `json`.
    """
    return await self.request(
        method="DELETE",
        path=path,
        extra_headers=extra_headers,
        cert_required=cert_required,
        **kwargs
    )
