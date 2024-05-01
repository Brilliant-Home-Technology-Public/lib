import logging

from cryptography.hazmat import backends
from cryptography.hazmat.primitives import ciphers
from cryptography.hazmat.primitives.ciphers import algorithms as cipher_algorithms
from cryptography.hazmat.primitives.ciphers import modes as cipher_modes

import lib.crypto.utils as crypto_utils


log = logging.getLogger(__name__)

AES_BLOCK_SIZE = cipher_algorithms.AES.block_size // 8


def des_encrypt(plaintext, key, pad=True):
  '''
  plaintext: byte string, multiple of 8 in length.
  key: 16 or 24 byte key
  pad: if true, plaintext will be padded to right length

  returns encrypted message

  if you need a random key, you can do
      > lib.crypto.utils.get_random_secret(16)
  '''
  padtext = plaintext
  if pad:
    padding_len = 8 - (len(plaintext) % 8)
    padtext += b'\0' * padding_len
  return _cipher_encrypt(_get_des3_ecb_cipher(key), padtext)


def des_decrypt(ciphertext, key, pad=True):
  '''
  ciphertext: symetrically encrypted message from des_encrypt
  key: 16 or 24 byte key
  pad: if true, padding bytes will be dropped from end of string

  returns decrypted message
  '''
  padtext = _cipher_decrypt(_get_des3_ecb_cipher(key), ciphertext)
  plaintext = padtext
  if pad:
    plaintext = plaintext.rstrip(b'\0')
  return plaintext


def aes_encrypt(plaintext, key, pad=True):
  '''
  plaintext: byte string, multiple of 16 in length.
  key: 16, 24, or 32 byte key
  pad: if true, plaintext will be padded to right length

  returns encrypted message

  if you need a random key, you can do
      > lib.crypto.utils.get_random_secret(16)
  '''
  padtext = plaintext
  if pad:
    padding_len = 16 - (len(plaintext) % 16)
    padtext += b'\0' * padding_len

  iv = crypto_utils.get_random_secret(AES_BLOCK_SIZE)
  return iv + _cipher_encrypt(_get_aes_cbc_cipher(key=key, iv=iv), padtext)


def aes_decrypt(ciphertext, key, pad=True):
  '''
  ciphertext: symetrically encrypted message from aes_encrypt
  key: 16, 24 or 32 byte key
  pad: if true, padding bytes will be dropped from end of string

  returns decrypted message
  '''
  iv = ciphertext[:AES_BLOCK_SIZE]
  padtext = _cipher_decrypt(_get_aes_cbc_cipher(key=key, iv=iv), ciphertext[AES_BLOCK_SIZE:])
  plaintext = padtext
  if pad:
    plaintext = plaintext.rstrip(b'\0')
  return plaintext


def aes_ecb_encrypt(plaintext, key):
  '''
  plaintext: 16 byte string
  key: 16 byte key

  ECB mode of AES, not recommended for repeated use without a nonce.

  returns encrypted message
  '''
  return _cipher_encrypt(_get_aes_ecb_cipher(key=key), plaintext)


def aes_ecb_decrypt(ciphertext, key):
  '''
  ciphertext: 16 byte string, symetrically encrypted message from aes_encrypt
  key: 16 byte key

  ECB mode of AES, not recommended for repeated use without a nonce.

  returns decrypted message
  '''
  return _cipher_decrypt(_get_aes_ecb_cipher(key=key), ciphertext)


def _get_symmetric_cipher(algorithm_cls, key, mode):
  cipher = ciphers.Cipher(
      algorithm_cls(key),
      mode=mode,
      backend=backends.default_backend(),
  )
  return cipher


def _get_aes_ecb_cipher(key):
  cipher = _get_symmetric_cipher(
      algorithm_cls=ciphers.algorithms.AES,
      key=key,
      mode=cipher_modes.ECB(),
  )
  return cipher


def _get_aes_cbc_cipher(key, iv):
  cipher = _get_symmetric_cipher(
      algorithm_cls=ciphers.algorithms.AES,
      key=key,
      mode=cipher_modes.CBC(iv),
  )
  return cipher


def _get_des3_ecb_cipher(key):
  cipher = _get_symmetric_cipher(
      algorithm_cls=ciphers.algorithms.TripleDES,
      key=key,
      mode=cipher_modes.ECB(),
  )
  return cipher


def _cipher_encrypt(cipher, plaintext):
  encryptor = cipher.encryptor()
  ciphertext = encryptor.update(plaintext) + encryptor.finalize()
  return ciphertext


def _cipher_decrypt(cipher, ciphertext):
  decryptor = cipher.decryptor()
  plaintext = decryptor.update(ciphertext) + decryptor.finalize()
  return plaintext
