import asyncio
import logging
import ssl
import typing

from aiohttp import web
from multidict import MultiDict

from lib.networking import authentication
from lib.networking import utils
import lib.networking.interface as networking_interface
import lib.storage.interface as storage_interface


log = logging.getLogger(__name__)


class BadRequestError(Exception):
  pass


class ObjectStoreRPCHandler:

  REQUEST_PAYLOAD_MAX_SIZE = 8 * 1024 * 1024

  authenticator: typing.Optional[authentication.Authenticator]

  def __init__(
      self,
      loop: asyncio.AbstractEventLoop,
      host: str,
      listen_port: int,
      object_store: storage_interface.ObjectStoreBase,
      enable_ssl: bool = True,
      validate_certs: bool = True,
      enable_access_logs: bool = True,
      authentication_policy: typing.Optional[networking_interface.AuthenticationPolicy] = None,
      pass_through_request: bool = False,
      extra_middlewares: typing.Optional[typing.List[typing.Callable]] = None,
      cert_file_directory: typing.Optional[str] = None,
      validate_home_auth_jwt: bool = False,
  ):
    self.loop = loop
    self.enable_ssl = enable_ssl
    self.validate_certs = validate_certs
    self.validate_home_auth_jwt = validate_home_auth_jwt
    self.host = host
    self.listen_port = listen_port
    self.object_store = object_store
    self.app = None
    self.protocol_handler = None
    self.server = None
    self.enable_access_logs = enable_access_logs
    if authentication_policy:
      self.authenticator = authentication.Authenticator(
          authentication_policy=authentication_policy,
      )
    else:
      self.authenticator = None
    self.pass_through_request = pass_through_request
    self.extra_middlewares = extra_middlewares or []
    self.cert_file_directory = cert_file_directory

  async def start(self):
    self.app = web.Application(
        middlewares=[*self.extra_middlewares, self.certificate_middleware_factory],
        client_max_size=self.REQUEST_PAYLOAD_MAX_SIZE,
    )
    self._register_routes()
    if self.enable_access_logs:
      self.protocol_handler = self.app.make_handler()
    else:
      self.protocol_handler = self.app.make_handler(access_log=None)

    ssl_context = (utils.get_ssl_context(purpose=ssl.Purpose.CLIENT_AUTH,
                                         cert_file_directory=self.cert_file_directory)
                   if self.enable_ssl else None)
    self.server = await self.loop.create_server(
        protocol_factory=self.protocol_handler,
        host=self.host,
        port=self.listen_port,
        ssl=ssl_context
    )

  async def reload(self):
    # TODO is there a simple way to just reload the SSLContext?
    if self.app is None:  # web.Application subclasses dict, so it has some odd truthiness...
      log.error("This handler is not currently running! Skipping reload %s %s",
                self.app,
                len(self.app))
      return

    await self.shutdown()
    await self.start()

  async def certificate_middleware_factory(self, app, handler):  # pylint: disable=unused-argument
    async def middleware(request):
      if request.get("global_authorization"):  # For internal requests.
        return await handler(request)

      if ((self.validate_certs or self.validate_home_auth_jwt)
          and self.authenticator
          and handler != self._handle_ping):  # pylint: disable=comparison-with-callable
        auth_method = self.authenticator.get_authentication_method_for_peer(
            maybe_address=None,
            connection_params={
                "authentication_token": request.headers.get("x-brilliant-authentication-token"),
            },
        )
        valid = False
        if (self.validate_home_auth_jwt
            and auth_method == networking_interface.AuthenticationMethod.JWT):
          valid = await self._is_home_auth_token_authorized(request=request)
        elif self.validate_certs:
          valid = await self._is_client_cert_authorized(request=request)

        if not valid:
          if self.authenticator.authentication_policy.strict:
            return web.Response(status=401)
          log.warning("Failed to validate client")
      return await handler(request)
    return middleware

  async def shutdown(self):
    if self.server:
      self.server.close()
      await self.server.wait_closed()

    if self.app is not None:  # See comment above
      await self.app.shutdown()
      if self.protocol_handler is not None:
        await self.protocol_handler.shutdown()
      await self.app.cleanup()

  def _register_routes(self):
    self.app.router.add_route(method='GET', path='/', handler=self._handle_get)
    self.app.router.add_route(method='GET', path='/ping', handler=self._handle_ping)
    self.app.router.add_route(method='POST', path='/post', handler=self._handle_put)
    self.app.router.add_route(method='HEAD', path='/', handler=self._handle_head)
    self.app.router.add_route(method="DELETE", path="/", handler=self._handle_delete)

  async def _is_client_cert_authorized(self, request):
    if self.authenticator.authentication_policy.accept_client_certificate_as_header():
      peer_certificate = utils.get_certificate_from_headers(request.headers)
    else:
      ssl_object = request.transport.get_extra_info('ssl_object')
      peer_certificate = ssl_object.getpeercert(binary_form=True)

    try:
      device_id = request.headers['x-brilliant-device-id']
      home_id = request.headers['x-brilliant-home-id']
    except KeyError:
      log.info("Failed to retrieve device_id/home_id from headers")
      return False

    valid = await self.authenticator.validate_certificate(
        device_id=device_id,
        home_id=home_id,
        certificate=peer_certificate,
    )
    return valid

  async def _is_home_auth_token_authorized(self, request):
    try:
      device_id = request.headers["x-brilliant-device-id"]
      home_id = request.headers["x-brilliant-home-id"]
      token = request.headers["x-brilliant-authentication-token"]
    except KeyError:
      log.info("Failed to retrieve device_id/home_id/token from headers")
      return False

    # If the Authentication Policy does not support home-auth JWTs, then return False.
    try:
      validity_interval_seconds = await self.authenticator.authentication_policy.get_token_validity_interval_seconds(
          home_id=home_id,
          peer_device_id=device_id,
          home_auth_token=token,
      )
      valid_home_auth_jwt = (validity_interval_seconds or 0) > 0
    except NotImplementedError:
      valid_home_auth_jwt = False

    return valid_home_auth_jwt

  def _parse_parameters(self, request):
    required = ("key",)
    optional = ("owner",)

    result = {}
    for parameter in required + optional:
      try:
        value = request.query.getone(parameter)
        result[parameter] = value
      except KeyError as e:
        if parameter in required:
          raise web.HTTPBadRequest(reason="%s must be specified" % parameter) from e

    return result

  async def _handle_get(self, request):
    resp_data = None
    params = self._parse_parameters(request)
    key = params['key']
    owner = params.get('owner')
    base_args = (key, owner)
    if self.pass_through_request:
      base_args += (request,)
    resp_data, metadata = await self.object_store.get(*base_args)

    if not resp_data or not metadata:
      return web.Response(status=404)
    status = 200
    headers = metadata.to_headers()
    body = resp_data
    if resp_data:
      bytes_lower = 0
      bytes_upper = len(resp_data) - 1
      bytes_total = len(resp_data)
      if 'RANGE' in request.headers:
        lower, upper = request.headers['RANGE'].split("=")[1].split("-")
        if not upper:
          upper = bytes_total - 1
        if int(lower) >= 0 and int(lower) < int(upper) and int(upper) <= bytes_total:
          bytes_lower = int(lower)
          bytes_upper = int(upper)
          body = resp_data[bytes_lower:bytes_upper + 1]  # End range is exclusive
          status = 206
        else:
          log.error("Received out of bounds range request: %s", request.headers['RANGE'])
      content_range = "bytes {}-{}/{}".format(bytes_lower, bytes_upper, bytes_total)
      headers['Accept-Ranges'] = 'bytes'
      headers['Content-Length'] = str(bytes_upper - bytes_lower + 1)
      headers['Content-Range'] = str(content_range)
    return web.Response(
        body=body,
        headers=MultiDict(headers),
        status=status,
    )

  async def _handle_ping(self, request):  # pylint: disable=unused-argument
    return web.Response(body="PONG", status=200)

  async def _handle_put(self, request):
    resp_data = None
    data = await request.read()
    if data:
      metadata = storage_interface.ObjectMetadata.from_headers(request.headers)
      base_args = (data, metadata)
      if self.pass_through_request:
        base_args += (request,)
      resp_data = await self.object_store.put(*base_args)
    return web.json_response(resp_data)

  async def _handle_head(self, request):
    params = self._parse_parameters(request)
    key = params['key']
    owner = params.get('owner')
    base_args = (key, owner)
    if self.pass_through_request:
      base_args += (request,)
    info = await self.object_store.head(*base_args)
    if not info:
      raise web.HTTPNotFound()

    headers = info.to_headers()
    # Need to do a little dance to get the headers set properly with an empty body
    resp = web.Response(body=None, status=200)
    resp.headers.update(headers)
    return resp

  async def _handle_delete(self, request):
    params = self._parse_parameters(request)
    key = params["key"]
    owner = params.get("owner")
    base_args = (key, owner)
    if self.pass_through_request:
      base_args += (request,)
    resp = await self.object_store.delete(*base_args)
    if resp is None:
      # This happens when the delete could not be executed because the caller did not have
      # permission.
      raise web.HTTPForbidden()
    return web.Response(body=None, status=204)
