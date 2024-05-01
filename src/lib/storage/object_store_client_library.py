from abc import ABCMeta
import asyncio
import base64
import logging
import ssl
import urllib.parse

import aiohttp
import gflags

from lib.networking import aiohttp_compat
from lib.networking import interface as networking_interface
from lib.networking import utils
from lib.storage import interface


log = logging.getLogger(__name__)

# In production and staging, we connect to a specific port on the Object Store host that does not
# require a client certificate as part of the request. Instead, we pass the client's certificate to
# the Object Store using a header.
gflags.DEFINE_string("internal_object_store_endpoint", "http://localhost:6455",
                     "The endpoint for communicating with object store. This specific endpoint "
                     "does not require a client certificate to be set, but rather expects it as a "
                     "header.")
gflags.DEFINE_string("object_store_authorization_secret", "test_secret",
                     "The secret that internal clients use to authenticate to object store.")


FLAGS = gflags.FLAGS


def get_object_store_authorization_secret():
  return FLAGS.object_store_authorization_secret


class BaseObjectStoreInterface(metaclass=ABCMeta):

  async def _make_get_request(self, url, params, **client_session_kwargs):
    async with aiohttp.ClientSession(**client_session_kwargs) as session:
      resp = await session.get(url=url, params=params)
      if resp.status != 200:
        log.error("Got non 200 response status %d for %s GET: %s", resp.status, url,
                  await resp.text())
        resp.close()
        return None, None
      return await resp.read(), interface.ObjectMetadata.from_headers(resp.headers)

  async def _make_put_request(self, base_url, data, metadata, **client_session_args):
    url = "{}/post".format(base_url)

    if not metadata:
      metadata = interface.ObjectMetadata(size=len(data))
    async with aiohttp.ClientSession(**client_session_args) as session:
      resp = await session.post(url=url, data=data, headers=metadata.to_headers())
      result = None
      if resp.status != 200:
        log_lvl = self._get_log_level(resp.status)
        log.log(log_lvl, "Got non 200 response status %d for %s PUT request: %s", resp.status, url,
          await resp.text())
        resp.close()
      else:
        result = await resp.json()
      return resp.status, result

  async def _make_head_request(self, url, params, **client_session_kwargs):
    async with aiohttp.ClientSession(**client_session_kwargs) as session:
      resp = await session.head(url=url, params=params)
      await resp.read()  # Should be empty, but forcing a read() suppresses annoying unclosed error
      if resp.status != 200:
        log_lvl = self._get_log_level(resp.status)
        log.log(log_lvl, "Got non 200 response status %d for %s HEAD: %s", resp.status, url,
                await resp.text())
        return None
      return interface.ObjectMetadata.from_headers(resp.headers)

  async def _make_delete_request(self, url, params, **client_session_kwargs):
    async with aiohttp.ClientSession(**client_session_kwargs) as session:
      resp = await session.delete(url=url, params=params)
      await resp.read()  # Should be empty, but forcing a read() suppresses annoying unclosed error
      if resp.status != 204:
        log.error("Got non 204 response status %d for %s DELETE: %s", resp.status, url,
                  await resp.text())
        return None
      return "OK"

  def _get_log_level(self, resp_status):
    server_error = 500 <= resp_status < 600
    acceptable_client_error = resp_status in (429, 404)
    if not (server_error or acceptable_client_error):
      return logging.ERROR
    return logging.INFO


class LocalObjectStoreInterface(BaseObjectStoreInterface):

  def __init__(self, local_listen_port):
    self.local_listen_port = local_listen_port

  async def make_get_request(self, key, owner):
    return await super()._make_get_request(
        url=self._get_local_address(),
        params={'key': key, 'owner': owner}
    )

  async def make_put_request(self, data, metadata=None):
    # The local put request will only put on the current device (and eventually upload to cloud)
    return await super()._make_put_request(
        base_url=self._get_local_address(),
        data=data,
        metadata=metadata,
    )

  async def make_head_request(self, key, owner):
    return await super()._make_head_request(
        url=self._get_local_address(),
        params=dict(key=key, owner=owner)
    )

  async def make_delete_request(self, key, owner):
    return await super()._make_delete_request(
        url=self._get_local_address(),
        params=dict(key=key, owner=owner),
    )

  def get_url(self, key, query_params=None):
    final_query_params = query_params or {}
    if 'key' in final_query_params:
      raise ValueError("'key' cannot be specified as a query parameter!")
    final_query_params.update(key=key)

    query_str = urllib.parse.urlencode(final_query_params)
    return "{}/?{}".format(self._get_local_address(), query_str)

  def _get_local_address(self):
    return "http://localhost:{}".format(self.local_listen_port)


class RemoteObjectStoreInterface(BaseObjectStoreInterface):

  def __init__(self, device_id, home_id, authentication_policy=None, cert_file_directory=None):
    self.device_id = device_id
    self.home_id = home_id
    self._authentication_policy = authentication_policy
    self._cert_file_directory = cert_file_directory
    # TODO: start/shutdown - kill any open connections?

  async def make_get_request(self, key, owner, owner_address):
    """Get the data and metadata identified by the given key from the given Object Store server.

    Args:
      key: The key that identifies the data to retrieve.
      owner: The ID of the device that owns the data.
      owner_address: The URL of the Object Store server.

    Returns:
      If the request was successful, a tuple in the form:
          (data, lib.storage.interface.ObjectMetadata).
      If the request was not successful, the tuple will be (None, None).
    """
    connector, headers = await self._get_connection_params(owner, owner_address)
    return await super()._make_get_request(
        url=owner_address,
        params={'key': key},
        connector=connector,
        headers=headers,
    )

  async def make_put_request(self, data, owner, owner_address, metadata=None):
    """Put data and metadata into the given Object Store server.

    Args:
      data: The bytes to store in the Object Store server.
      metadata: The lib.storage.interface.ObjectMetadata corresponding to the given `data`.
      owner: The ID of the device that owns the data.
      owner_address: The URL of the Object Store server.

    Returns:
      If the request was successful, a tuple in the form:
          (HTTP response code, dict(key=<newly_created_key>, owner=<data_owner_name>).
      If the request was not successful, a tuple in the form (HTTP response code, None).
    """
    connector, headers = await self._get_connection_params(owner, owner_address)
    return await super()._make_put_request(
        base_url=owner_address,
        data=data,
        connector=connector,
        headers=headers,
        metadata=metadata,
    )

  async def make_head_request(self, key, owner, owner_address):
    """Request the metadata corresponding to the given key from the given Object Store server.

    Args:
      key: The key that identifies the metadata to retrieve.
      owner: The ID of the device that owns the data.
      owner_address: The URL of the Object Store server.

    Returns:
      If the request is successful, returns the lib.storage.interface.ObjectMetadata object.
      If the request is not successful, returns None.
    """
    connector, headers = await self._get_connection_params(owner, owner_address)
    return await super()._make_head_request(
        url=owner_address,
        params=dict(key=key),
        connector=connector,
        headers=headers,
    )

  async def make_delete_request(self, key, owner, owner_address):
    """Delete the data corresponding to the given key from the given Object Store server.

    Args:
      key: The key that identifies the metadata to retrieve.
      owner: The ID of the device that owns the data.
      owner_address: The URL of the Object Store server.

    Returns:
      If the request is successful, returns "OK".
      If the request is not successful, returns None.
    """
    connector, headers = await self._get_connection_params(owner, owner_address)
    return await super()._make_delete_request(
        url=owner_address,
        params=dict(key=key),
        connector=connector,
        headers=headers,
    )

  async def _get_connection_params(self, owner, owner_address):
    ssl_context = None
    server_fingerprint = None
    _, address_family, connection_args, secure = utils.parse_address(owner_address)
    if secure:
      ssl_context = utils.get_ssl_context_for_host(
          address_family=address_family,
          host=connection_args['host'],
          cert_file_directory=self._cert_file_directory,
      )
      if self._authentication_policy:
        authentication_method = self._authentication_policy.get_authentication_method_for_host(
            hostname=connection_args['host'],
        )
      else:
        authentication_method = networking_interface.AuthenticationMethod.NONE

      if authentication_method == networking_interface.AuthenticationMethod.CERTIFICATE_FINGERPRINT:
        fingerprint_b64 = await self._authentication_policy.get_expected_certificate_fingerprint(
            home_id=self.home_id,
            device_id=owner,
        )
        if fingerprint_b64:
          server_fingerprint = base64.b64decode(fingerprint_b64)
        elif self._authentication_policy.strict:
          raise ssl.CertificateError("No known fingerprint for {}".format(owner))
        else:
          server_fingerprint = None

    connector = aiohttp_compat.FingerprintCheckingTCPConnector(
        ssl_context=ssl_context,
        fingerprint=server_fingerprint,
    )
    headers = utils.format_headers({
        "home-id": self.home_id,
        "device-id": self.device_id,
    })
    return connector, headers


class InternalObjectStoreInterface(BaseObjectStoreInterface):
  """Interface to make Object Store calls within the VPC on behalf of a specific client."""

  def __init__(self, device_id, home_id, client_certificate_header, authorization_header=None):
    self.device_id = device_id
    self.home_id = home_id
    self.client_certificate_header = client_certificate_header
    self.authorization_header = authorization_header

  async def make_get_request(self, key, remote_address=None):
    headers = self._get_headers()
    return await super()._make_get_request(
        url=self._get_url(remote_address),
        params={"key": key},
        headers=headers,
    )

  async def make_put_request(self, data, remote_address=None, metadata=None):
    headers = self._get_headers()
    return await super()._make_put_request(
        base_url=self._get_url(remote_address),
        data=data,
        metadata=metadata,
        headers=headers,
    )

  async def make_head_request(self, key, remote_address=None):
    headers = self._get_headers()
    return await super()._make_head_request(
        url=self._get_url(remote_address),
        params={"key": key},
        headers=headers,
    )

  async def make_delete_request(self, key, remote_address=None):
    headers = self._get_headers()
    return await super()._make_delete_request(
        url=self._get_url(remote_address),
        params={"key": key},
        headers=headers,
    )

  def _get_url(self, remote_address):
    return remote_address or FLAGS.internal_object_store_endpoint

  def _get_headers(self):
    to_format = {"home-id": self.home_id}
    if self.device_id:
      to_format["device-id"] = self.device_id
    if self.client_certificate_header:
      to_format["client-cert-pem"] = self.client_certificate_header
    headers = utils.format_headers(to_format)
    if self.authorization_header:
      headers["authorization"] = self.authorization_header
    return headers


if __name__ == '__main__':
  event_loop = asyncio.get_event_loop()
  remote_interface = RemoteObjectStoreInterface("Den", "1")
  test_data = bytes("test_data_100", "utf-8")
  event_loop.run_until_complete(remote_interface.make_put_request(
      data=test_data,
      owner="cloud",
      owner_address="https://object-store.brilliant.tech:443",
  ))
  get_result = event_loop.run_until_complete(remote_interface.make_get_request(
      key="f07aa694445bc5c7a8425773ec506951fc63ccd6",
      owner="cloud",
      owner_address="https://object-store.brilliant.tech:443"
  ))
  print("Result:", get_result)
