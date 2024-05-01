import logging

import cryptography.exceptions
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers import aead
from cryptography.hazmat.primitives.kdf import hkdf

import lib.crypto.utils as crypto_utils
import thrift_types.crypto.ttypes as crypto_ttypes


log = logging.getLogger(__name__)


class EphemeralAsymmetricKeyCipher:

  def __init__(self):
    self._private_key = None
    self._key_id = None

  def generate_key(self):
    self._private_key = x25519.X25519PrivateKey.generate()
    public_bytes = self._private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    self._key_id = self._get_key_id(public_bytes)
    return crypto_ttypes.PublicKey(
        key_id=self._key_id,
        key_type=crypto_ttypes.AsymmetricKeyType.X25519,
        public_bytes=public_bytes,
    )

  def decrypt(self, encrypted_message):
    if not self._private_key:
      # TODO raise error?
      return None

    if encrypted_message.peer_key_id != self._key_id:
      log.error("Key mismatch: message was encrypted for key %s; currently have %s",
                encrypted_message.peer_key_id, self._key_id)
      return None

    peer_public_key = x25519.X25519PublicKey.from_public_bytes(
        encrypted_message.public_key.public_bytes)
    shared_secret = self._private_key.exchange(peer_public_key)

    # Discard key so it can't be used again
    self._private_key = None

    # Run Diffie-Hellman secret through a Key Derivation Function (KDF) to compute symmetric key
    kdf = hkdf.HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b'')
    symmetric_key = kdf.derive(shared_secret)

    try:
      plaintext = aead.AESGCM(symmetric_key).decrypt(
          nonce=encrypted_message.nonce,
          data=encrypted_message.ciphertext,
          associated_data=None,
      )
    except cryptography.exceptions.InvalidTag:  # Raised when decryption fails for whatever reason
      log.warning("Failed to decrypt ciphertext!")
      return None

    return plaintext

  @classmethod
  def _get_key_id(cls, public_bytes):
    return crypto_utils.get_key_id(public_bytes)
