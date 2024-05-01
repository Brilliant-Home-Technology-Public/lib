import base64
import datetime
import logging
import operator
import os
import typing

import cryptography.hazmat.primitives.asymmetric.ed25519 as cryptography_ed25519
import cryptography.hazmat.primitives.asymmetric.rsa as cryptography_rsa
import cryptography.hazmat.primitives.hashes
import cryptography.hazmat.primitives.serialization
import cryptography.hazmat.primitives.serialization.pkcs12
import cryptography.x509
import cryptography.x509.base

import lib.networking.utils as networking_utils
import lib.utils


log = logging.getLogger(__name__)


DEFAULT_EXPIRATION_DATETIME = datetime.datetime(2100, 1, 1, tzinfo=datetime.timezone.utc)


class CertificateGenerationError(Exception):
  pass


def _read_key(key_file):
  key_pem_data = lib.utils.read_file(key_file, 'rb')
  if not key_pem_data:
    return None

  return _deserialize_key(key_pem_data)


def _deserialize_key(key_data):
  try:
    return cryptography.hazmat.primitives.serialization.load_pem_private_key(
        key_data,
        password=None,
    )
  except Exception as e:
    log.error("Failed to read private key: %r", e)

  return None


def _generate_and_write_key(key_file):
  private_key = _generate_key()
  pem_data = private_key.private_bytes(
      encoding=cryptography.hazmat.primitives.serialization.Encoding.PEM,
      format=cryptography.hazmat.primitives.serialization.PrivateFormat.PKCS8,
      encryption_algorithm=cryptography.hazmat.primitives.serialization.NoEncryption(),
  )
  if not lib.utils.write_file(key_file, pem_data, mode='wb'):
    raise CertificateGenerationError("Failed to write private key!")

  return private_key


def _generate_key():
  return cryptography_rsa.generate_private_key(
      public_exponent=65537,  # Recommended by the cryptography docs
      key_size=2048,
  )


def _read_x509_certificate(certificate_file):
  certificate_pem_data = lib.utils.read_file(certificate_file, 'rb')
  if not certificate_pem_data:
    return None

  try:
    return cryptography.x509.load_pem_x509_certificate(certificate_pem_data)
  except Exception as e:
    log.error("Failed to read certificate: %r", e)

  return None


def _canonical_name(name):
  # Sort by short code (e.g. "CN" for commonName)
  return sorted(name, key=operator.attrgetter('rfc4514_attribute_name'))


def _get_subject_for_device_certificate(device_id) -> cryptography.x509.Name:
  common_name = "{}.device.brilliant.tech".format(device_id)
  rfc4514_subject = ",".join([
      "C=US",
      "ST=CA",
      "L=San Mateo",
      "O=Brilliant Home Technology",
      "OU=Engineering",
      f"CN={device_id}.device.brilliant.tech",
  ])
  subject_name = cryptography.x509.Name.from_rfc4514_string(rfc4514_subject)
  return subject_name


def make_certificate(
    subject_name: cryptography.x509.Name,
    issuer_name: cryptography.x509.Name,
    public_key: cryptography.x509.base.CERTIFICATE_PUBLIC_KEY_TYPES,  # Union of several types
    ca_key: cryptography.x509.base.CERTIFICATE_PRIVATE_KEY_TYPES,  # Union of several types
    serial_number: typing.Optional[int] = None,
    not_before_datetime: typing.Optional[datetime.datetime] = None,
    not_after_datetime: typing.Optional[datetime.datetime] = DEFAULT_EXPIRATION_DATETIME,
):
  hash_algorithm = None
  if not isinstance(ca_key, cryptography_ed25519.Ed25519PrivateKey):
    hash_algorithm = cryptography.hazmat.primitives.hashes.SHA256()
  certificate = cryptography.x509.CertificateBuilder().subject_name(
      subject_name
  ).issuer_name(
      issuer_name
  ).public_key(
      public_key
  ).serial_number(
      serial_number if serial_number is not None else cryptography.x509.random_serial_number()
  ).not_valid_before(
      not_before_datetime or datetime.datetime.utcnow()
  ).not_valid_after(
      not_after_datetime or DEFAULT_EXPIRATION_DATETIME
  ).sign(
      ca_key, hash_algorithm
  )
  return certificate


def blocking_generate_device_certificate(device_id, root_ca_file, root_ca_key, *,
                                         force_regenerate=False,
                                         directory_override=None):
  os.makedirs(directory_override or networking_utils.get_device_cert_dir(), exist_ok=True)
  key_file, csr_file, cert_file = networking_utils.get_device_cert_files(
      directory_override=directory_override)

  root_ca_cert = _read_x509_certificate(root_ca_file)
  if not root_ca_cert:
    raise CertificateGenerationError("Cannot generate certificate without CA certificate!")

  if force_regenerate:
    for file_path in (key_file, csr_file, cert_file):
      lib.utils.clear_file(file_path)

  key = _read_key(key_file)
  if not key:
    key = _generate_and_write_key(key_file)

  subject_name = _get_subject_for_device_certificate(device_id)

  certificate = _read_x509_certificate(cert_file)
  if (certificate and
      # Canonicalize names so they compare equal even if attributes are ordered differently
      _canonical_name(certificate.subject) == _canonical_name(subject_name) and
      _canonical_name(certificate.issuer) == _canonical_name(root_ca_cert.subject) and
      # cryptography's RSAPublicKey type doesn't implement logical equality
      key.public_key().public_numbers() == certificate.public_key().public_numbers()):
    log.info("Existing certificate is good. No need to regenerate.")
    return

  certificate = make_certificate(
      public_key=key.public_key(),
      subject_name=subject_name,
      ca_key=_deserialize_key(root_ca_key),
      issuer_name=root_ca_cert.issuer,
  )
  pem_certificate = certificate.public_bytes(
      cryptography.hazmat.primitives.serialization.Encoding.PEM
  )
  lib.utils.write_file(cert_file, pem_certificate, 'wb')


def _generate_private_key_and_device_certificate_for_device(
    device_id: str,
    root_ca: bytes,
    root_ca_key: bytes,
) -> tuple[cryptography.hazmat.primitives.asymmetric.rsa.RSAPrivateKey, cryptography.x509.Certificate]:
  ca_certificate = cryptography.x509.load_pem_x509_certificate(root_ca)
  private_key = _generate_key()
  certificate = make_certificate(
      public_key=private_key.public_key(),
      subject_name=_get_subject_for_device_certificate(device_id),
      ca_key=_deserialize_key(root_ca_key),
      issuer_name=ca_certificate.issuer,
  )

  return private_key, certificate


def generate_private_key_and_device_certificate_for_device(
    device_id: str,
    root_ca: bytes,
    root_ca_key: bytes,
) -> tuple[str, str]:
  private_key, certificate = _generate_private_key_and_device_certificate_for_device(
      device_id=device_id,
      root_ca=root_ca,
      root_ca_key=root_ca_key,
  )
  return (
      private_key.private_bytes(
          encoding=cryptography.hazmat.primitives.serialization.Encoding.PEM,
          format=cryptography.hazmat.primitives.serialization.PrivateFormat.PKCS8,
          encryption_algorithm=cryptography.hazmat.primitives.serialization.NoEncryption(),
      ).decode(),
      certificate.public_bytes(cryptography.hazmat.primitives.serialization.Encoding.PEM).decode(),
  )


def blocking_generate_pkcs12_certificate(
    device_id: str,
    root_ca: bytes,
    root_ca_key: bytes,
) -> str:
  private_key, certificate = _generate_private_key_and_device_certificate_for_device(
      device_id=device_id,
      root_ca=root_ca,
      root_ca_key=root_ca_key,
  )

  # iOS will fail to load unencrypted PKCS#12 blobs, so we force encryption with an empty
  # passphrase. This requires a bit of hackery because `cryptography` will raise an exception
  # when passed an empty passphrase through its encryption APIs.
  builder = cryptography.hazmat.primitives.serialization.PrivateFormat.PKCS12.encryption_builder()
  # Align parameters to those chosen by default by `openssl pkcs12`
  encryption = builder.kdf_rounds(
      2048
  ).key_cert_algorithm(
      cryptography.hazmat.primitives.serialization.pkcs12.PBES.PBESv1SHA1And3KeyTripleDESCBC
  ).hmac_hash(
      cryptography.hazmat.primitives.hashes.SHA1()
  ).build(b"dummy")  # Need to supply a non-empty passphrase here to avoid an exception
  # mypy doesn't know this property exists, but it does
  encryption.password = b''  # type: ignore[attr-defined]
  data = cryptography.hazmat.primitives.serialization.pkcs12.serialize_key_and_certificates(
      name=None,
      key=private_key,
      cert=certificate,
      cas=None,
      encryption_algorithm=encryption,
  )
  b64_data = base64.b64encode(data).decode()
  return b64_data


if __name__ == "__main__":
  import sys

  logging.basicConfig(level=logging.DEBUG)

  device_id = sys.argv[1]
  target_dir = sys.argv[2]
  ca_key_file = sys.argv[3]
  ca_cert_file = sys.argv[4]

  with open(ca_key_file, 'rb') as ca_key_data:
    ca_key_bytes = ca_key_data.read()

  blocking_generate_device_certificate(device_id,
                                       ca_cert_file,
                                       ca_key_bytes,
                                       directory_override=target_dir)

  with open(ca_cert_file, 'rb') as ca_cert_data:
    ca_cert_bytes = ca_cert_data.read()

  pkcs12_cert = blocking_generate_pkcs12_certificate(
      device_id,
      ca_cert_bytes,
      ca_key_bytes,
  )
  print(pkcs12_cert)
