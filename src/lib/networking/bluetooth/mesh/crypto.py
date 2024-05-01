import functools

from cryptography.hazmat import backends
from cryptography.hazmat.primitives import ciphers
from cryptography.hazmat.primitives.ciphers import aead
from cryptography.hazmat.primitives.cmac import CMAC

import lib.crypto.block_ciphers
from lib.tools import bitstring_parser


ZERO = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
_K2_PARSER = bitstring_parser.BitstringParser("pad:1, uint:7, bytes:16, bytes:16")
_K4_PARSER = bitstring_parser.BitstringParser("pad:122, uint:6")


def xor(msg, key):
  '''
  msg: bytes, same length as key
  key: bytes, same length as message

  xor is a poor standalone cipher
  the following property holds for xor used in encryption
    encrypted_msg = xor(msg, key)
    decrypted_msg = xor(encrypted_msg, key)

  returns:
    msg XOR key
  '''
  return bytes(a ^ b for a, b in zip(msg, key))


def cmac(key, msg):
  '''
  Mesh Profile 3.8.2.2: CMAC function

  key: 16 byte key
  m: byte string message

  return:
    16 byte message hash
  '''
  cipher = CMAC(
      ciphers.algorithms.AES(key),
      backend=backends.default_backend(),
  )
  cipher.update(msg)
  return cipher.finalize()


def ccm_encrypt(key, nonce, msg, tag_length, aad=b''):
  '''
  Mesh Profile 3.8.2.3 CCM function

  key: 16 byte key
  nonce: 13 byte nonce
  msg: plaintext, secret message
  tag_length: authentication tag length in bytes
  aad: additional data, authenticated but unecrypted data
  '''
  cipher = aead.AESCCM(key, tag_length)
  return cipher.encrypt(nonce, msg, aad)


def ccm_decrypt(key, nonce, ciphertext, tag_length, aad=b''):
  '''
  Mesh Profile 3.8.2.3 CCM function

  key: 16 byte key
  nonce: 13 byte nonce
  ciphertext: secret message
  tag_length: authentication tag length in bytes
  aad: authenticated but unecrypted data

  raises cryptography.exceptions.InvalidTag
  '''
  cipher = aead.AESCCM(key, tag_length)
  return cipher.decrypt(nonce, ciphertext, aad)


def e(key, plaintext):
  '''
  Bluetooth Core Spec: 2.2.1 security function e

  key: 16 byte key
  plaintext: 16 byte plaintextData

  returns:
    16 byte encryptedData
  '''
  return lib.crypto.block_ciphers.aes_ecb_encrypt(plaintext, key)


@functools.lru_cache
def s1(M):
  '''
  Mesh Profile 3.8.2.4: s1 SALT generation function

  M: byte string

  return:
    16 byte message hash
  '''
  return cmac(ZERO, M)


@functools.lru_cache
def k1(N, SALT, P):
  '''
  Mesh Profile 3.8.2.5: k1 derivation function

  Used to generate instances of IdentityKey and BeaconKey

  N: 0 or more bytes, Key
  SALT: 16 bytes
  P: 0 or more bytes, String like "prdk" or "prsk"

  return:
    16 bytes, Derived Key
  '''
  T = cmac(SALT, N)
  return cmac(T, P)


@functools.lru_cache
def k2(N, P):
  '''
  Mesh Profile 3.8.2.6: k2 network key material derivation function

  Generates EncryptionKey, PrivacyKey, and NID

  N: 16 bytes, Network Key
  P: 1 or more bytes

  return:
    NIP: 7 bit integer
    Encryption Key: 16 bytes
    Privacy Key: 16 bytes
  '''
  SALT = s1(b'smk2')
  T = cmac(SALT, N)

  T0 = b''
  T1 = cmac(T, T0 + P + b'\x01')
  T2 = cmac(T, T1 + P + b'\x02')
  T3 = cmac(T, T2 + P + b'\x03')

  k = (T1 + T2 + T3)[-33:]  # mod 2^263, throw away most significant bit later

  unpacked = _K2_PARSER.unpack(k)
  nid, encryption_key, privacy_key = unpacked  # pylint: disable=unbalanced-tuple-unpacking
  return nid, encryption_key, privacy_key


@functools.lru_cache
def k3(N):
  '''
  Mesh Profile 3.8.2.7: k3 derivation function

  Used to generate a  public value derived from a private key

  N: 16 bytes, Network Key

  return:
    8 bytes, Network ID
  '''
  SALT = s1(b'smk3')
  T = cmac(SALT, N)

  return cmac(T, b'id64\x01')[-8:]  # mod 2^64


@functools.lru_cache
def k4(N):
  '''
  Mesh Profile 3.8.2.8: k4 derivation function

  Used to generate a public value of 6 bits derived from a private key.

  N: 16 bytes
  return:
    6 bit integer
  '''
  SALT = s1(b'smk4')
  T = cmac(SALT, N)
  cmac_id6 = cmac(T, b'id6\x01')
  aid = _K4_PARSER.unpack(cmac_id6)[0]  # mod 2^6
  return aid
