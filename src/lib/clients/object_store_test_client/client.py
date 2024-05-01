"""The ObjectStoreTestClient provides a default interface for interacting with the server's Object
Store service. The test client is intended to be used for manual testing and integration tests and
should not be directly used in production code.
"""

import os

from lib.clients.object_store_test_client.authentication_policy import AuthenticationPolicy
import lib.storage.object_store_client_library


class ObjectStoreTestClient:
  def __init__(self,
               device_id,
               home_id,
               object_store_address,
               cert_file_directory):
    """
    Args:
      cert_file_directory: The absolute directory in which the client's certificates are stored.
          Test certificates are provided in the top-level `certs/object_store_test_client`
          directory.
      device_id: The ID of the device from which the requests will originate.
      home_id: The ID of the home to which the device belongs.
      object_store_address: The URL used to communicate with the server's Object Store service.
    """
    self._device_id = device_id
    self._object_store_address = object_store_address

    self._interface = lib.storage.object_store_client_library.RemoteObjectStoreInterface(
        authentication_policy=AuthenticationPolicy(),
        cert_file_directory=cert_file_directory,
        device_id=device_id,
        home_id=home_id,
    )

  async def make_get_request(self, key):
    """Get the data and metadata identified by the given key from the given Object Store server.

    Args:
      key: The key that identifies the data to retrieve.

    Returns:
      If the request was successful, a tuple in the form:
          (data, lib.storage.interface.ObjectMetadata).
      If the request was not successful, the tuple will be (None, None).
    """
    return await self._interface.make_get_request(
        key=key,
        owner=self._device_id,
        owner_address=self._object_store_address,
    )

  async def make_put_request(self, data, metadata=None):
    """Put data and metadata into the given Object Store server.

    Args:
      data: The bytes to store in the Object Store server.
      metadata: The lib.storage.interface.ObjectMetadata corresponding to the given `data`.

    Returns:
      If the request was successful, a tuple in the form:
          (HTTP response code, dict(key=<newly_created_key>, owner=<data_owner_name>).
      If the request was not successful, a tuple in the form (HTTP response code, None).
    """
    return await self._interface.make_put_request(
        data=data,
        metadata=metadata,
        owner=self._device_id,
        owner_address=self._object_store_address,
    )

  async def make_head_request(self, key):
    """Request the metadata corresponding to the given key from the given Object Store server.

    Args:
      key: The key that identifies the metadata to retrieve.

    Returns:
      If the request is successful, returns the lib.storage.interface.ObjectMetadata object.
      If the request is not successful, returns None.
    """
    return await self._interface.make_head_request(
        key=key,
        owner=self._device_id,
        owner_address=self._object_store_address,
    )

  async def make_delete_request(self, key):
    """Delete the data corresponding to the given key from the given Object Store server.

    Args:
      key: The key that identifies the metadata to retrieve.

    Returns:
      If the request is successful, returns "OK".
      If the request is not successful, returns None.
    """
    return await self._interface.make_delete_request(
        key=key,
        owner=self._device_id,
        owner_address=self._object_store_address,
    )
