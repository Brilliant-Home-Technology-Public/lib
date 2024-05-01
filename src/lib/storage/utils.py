import hashlib


def gen_sha(data):
  sha = hashlib.sha1()
  sha.update(data)
  return sha.hexdigest()
