import base64
import binascii

from lib.crypto import block_ciphers


# the encryption key used by the server is in server/configs/alexa_home_skill.py

def alexa_home_id_to_access_token(home_id, encryption_key):
  ''' returns access_token '''
  if isinstance(home_id, str):
    home_id = str.encode(home_id)
  encrypted = block_ciphers.des_encrypt(home_id, encryption_key)
  return base64.b64encode(encrypted)


def alexa_access_token_to_home_id(access_token, encryption_key):
  ''' returns home_id '''
  unencoded = base64.b64decode(access_token)
  return block_ciphers.des_decrypt(unencoded, encryption_key).decode("utf-8")


def alexa_home_id_to_code(home_id, encryption_key):
  '''
  truncate and base 64 encoded an access_token, roughly a 4 character passcode
  '''
  if isinstance(home_id, str):
    home_id = str.encode(home_id)
  access_token = alexa_home_id_to_access_token(home_id, encryption_key)
  truncated = access_token[:3]
  return base64.b64encode(truncated).decode("utf-8")


def verify_alexa_code(code, home_id, encryption_key):
  ''' check if home_id and code match '''
  if isinstance(home_id, str):
    home_id = str.encode(home_id)
  access_token = alexa_home_id_to_access_token(home_id, encryption_key)
  try:
    decoded = base64.b64decode(code)
  except binascii.Error:
    return False
  return access_token.startswith(decoded)
