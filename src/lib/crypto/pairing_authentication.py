import base64
import hashlib
import hmac


def compute_authentication_commitment(
    code,
    random_secret,
    home_id,
    certificate_fingerprint_base64,
):
  code_hasher = hmac.new(
      key=random_secret,
      msg=code.to_bytes(4, byteorder="big"),
      digestmod=hashlib.sha256,
  )
  commitment_key = code_hasher.digest()
  commitment_hasher = hmac.new(commitment_key, digestmod=hashlib.sha256)
  commitment_hasher.update(home_id.encode('utf-8'))
  commitment_hasher.update(base64.b64decode(certificate_fingerprint_base64))
  return base64.b64encode(commitment_hasher.digest()).decode()


def compare_commitments(commitment1, commitment2):
  return hmac.compare_digest(commitment1, commitment2)
