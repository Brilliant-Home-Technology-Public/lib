import base64
import hashlib
import logging
import os

from cryptography.hazmat import backends
from cryptography.hazmat.primitives import serialization


log = logging.getLogger(__name__)


def get_public_key(pem_file_path):
  try:
    with open(pem_file_path, 'rb') as pem_file:
      return serialization.load_pem_public_key(
          data=pem_file.read(),
          backend=backends.default_backend(),
      )
  except FileNotFoundError:
    log.warning("No file at %s to load public key from", pem_file_path)
    return None


def get_key_id(key_bytes: bytes) -> str:
  # First 8 bytes of SHA-256 hash
  return hashlib.sha256(key_bytes).hexdigest()[:16]


def get_random_secret(num_bytes=32):
  secret = os.urandom(num_bytes)
  return secret


def get_random_secret_string(num_bytes=24):
  secret = get_random_secret(num_bytes)
  return base64.b64encode(secret).decode('utf-8')
