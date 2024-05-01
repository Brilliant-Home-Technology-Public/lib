import logging
import secrets
import typing

import lib.utils


log = logging.getLogger(__name__)


class EncryptedKeyStore:

  def __init__(self, storage_path: str, cipher, expected_length: int = 64):
    """Initialize the key store

    storage_path: Filesystem path at which the encrypted key data should be stored
    cipher: A symmetric cipher used to encrypt/decrypt the key stored on the filesystem
    expected_length: Key length (in bytes)
    """
    self._storage_path = storage_path
    self._cipher = cipher
    self._expected_length = expected_length

  def get_key(self) -> bytes:
    """Read the key, generating and storing a new key as necessary.

    Returns the raw key in bytes.
    """
    key = self._read_and_decrypt_key()
    if not key:
      # Didn't exist yet, or couldn't be read. Try to make a new key.
      self._store_new_key()
      key = self._read_and_decrypt_key()
      if not key:
        raise Exception("Failed to load or generate a valid key!")

    return key

  def _read_and_decrypt_key(self) -> typing.Optional[bytes]:
    try:
      ciphertext_hex = lib.utils.read_file(self._storage_path, mode='r')
      if ciphertext_hex:
        plaintext = self._cipher.decrypt(ciphertext_hex)
        if plaintext and len(plaintext) == self._expected_length:
          return plaintext
    except Exception as e:
      log.error("Error reading key material: %r", e)

    log.warning("Failed to read valid key material. Attempting wipe.")
    # Something wrong with the file. Try to start fresh.
    lib.utils.clear_file(self._storage_path)
    return None

  def _store_new_key(self):
    with lib.utils.temporary_umask(0o077):
      lib.utils.write_file(
          file_path=self._storage_path,
          data=self._cipher.encrypt(secrets.token_bytes(self._expected_length)),
          use_fsync=True,
      )
