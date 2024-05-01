import contextlib
import logging
import subprocess
import threading
import typing
import uuid

import asn1crypto.core
import pkcs11
import pkcs11.util.x509

import lib.crypto.utils as crypto_utils
import lib.utils
import thrift_types.crypto.ttypes as crypto_ttypes


log = logging.getLogger(__name__)


class TokenUnavailableError(Exception):
  pass


class NoAvailableSlotError(Exception):
  pass


class NoPINError(TokenUnavailableError):
  pass


class PKCS11Token:
  """Encapsulates a PKCS#11 token.

  PKCS#11 is a standard for delegating cryptographic operations to a token, e.g. a Hardware
  Security Module (HSM) or Smart Card (SC), like a YubiKey. These tokens support standard
  cryptographic operations (encryption/decryption, signing/verification, etc.) without
  revealing sensitive key data to the calling application/host device.

  https://en.wikipedia.org/wiki/PKCS_11
  """

  def __init__(self,
               token_label: str,
               pkcs11_module: str,
               pin: typing.Optional[str] = None,
               pin_path: typing.Optional[str] = None,
  ):
    """Initialize the token.

    token_label: The label identifying the token to be used
    pin: The user & security officer login PIN (mutually exclusive with pin_path)
    pin_path: Path to binary data from which to derive PIN (mutually exclusive with pin)
    pkcs11_module: The path to a shared object implementing the desired backend PKCS#11 API
    """
    if not bool(pin) ^ bool(pin_path):
      raise ValueError("Exactly one of pin & pin_path must be specified!")
    self._token_label = token_label
    self._pin = pin
    self._pin_path = pin_path
    self._pkcs11_module = pkcs11_module
    self._pkcs11_lib = pkcs11.lib(pkcs11_module)
    # Serialize all operations with a lock
    self._lock = threading.RLock()

  def ready(self) -> bool:
    """Returns True if the token exists, False otherwise."""
    try:
      with self._lock:
        return self._get_token() is not None
    except TokenUnavailableError:
      return False

  def _get_available_slot(self):
    for slot in self._pkcs11_lib.get_slots():
      if slot.flags & pkcs11.SlotFlag.TOKEN_PRESENT:
        token = slot.get_token()
        # Uninitialized OP-TEE tokens are labeled with a string of asterisks
        if token and token.label and set(token.label) != {'*'}:
          continue

      return slot.slot_id

    raise NoAvailableSlotError("Couldn't find an open slot!")

  def initialize(self):
    """Create the token and set its PINs."""
    with self._lock:
      return self._initialize_with_lock()

  def _initialize_with_lock(self):
    # python-pkcs11 doesn't support initializing tokens, so we'll need to shell out for this.
    slot_id = self._get_available_slot()
    self._tool_cmd(
        "--init-token",
        "--label", self._token_label,
        "--so-pin", self._pin,
        "--slot", str(slot_id),
    )
    # Pick up the newly-created token
    self._pkcs11_lib.reinitialize()

    # Don't bother with separate PINs for the user vs. security officer
    self._tool_cmd(
        "--init-pin",
        "--label", self._token_label,
        "--login", "--so-pin", self._pin,
        "--pin", self._pin,
        # Pass the slot ID (which may change after initialization); otherwise this randomly fails
        "--slot", str(self._get_token().slot.slot_id),
    )
    # Reinitialize to pick up the PIN change
    self._pkcs11_lib.reinitialize()

  @contextlib.contextmanager
  def session(self, rw: bool = False) -> pkcs11.Session:
    """Context manager which authenticates to yield a pkcs11.Session instance

    rw: True if the session should allow writes to the token state.
    """
    with self._lock:
      with self._get_token().open(rw=rw, user_pin=self._pin) as session:
        yield session

  def destroy_all_objects(self):
    with self.session(rw=True) as session:
      for obj in session.get_objects():
        obj.destroy()

  def _get_token(self):
    if not self._pin:
      # Allow binary data
      pin_raw = lib.utils.read_file(self._pin_path, 'rb')
      if not pin_raw:
        raise NoPINError("Unlock PIN is not available")

      self._pin = pin_raw.hex()

    try:
      return self._pkcs11_lib.get_token(token_label=self._token_label)
    except pkcs11.exceptions.NoSuchToken as e:
      raise TokenUnavailableError(f"Cannot find token '{self._token_label}'") from e

  def _tool_cmd(self, *args):
    completed = subprocess.run(
        ["pkcs11-tool", "--module", self._pkcs11_module, *args],
        check=True,
        capture_output=True,
    )
    return completed.stdout


class PKCS11AESCipher:
  """Implements encrypt() and decrypt() methods backed by a (virtual) PKCS#11 token"""

  IV_LEN_BYTES = 16

  def __init__(self, token_label: str, key_label: str, pin: str, pkcs11_module: str):
    """Initialize the cipher

    token_label: The label identifying the token to be used
    key_label: The label identifying the AES key to be used
    pin: The user & security officer login PIN
    pkcs11_module: The path to a shared object implementing the desired backend PKCS#11 API
    """
    self._key_label = key_label
    self._token = PKCS11Token(
        token_label=token_label,
        pin=pin,
        pkcs11_module=pkcs11_module,
    )

  def prepare_key(self):
    """Prepare the cipher for operation.

    The key and token will be initialized according to the parameters supplied to __init__() if
    they do not yet exist.
    """
    if not self._token.ready():
      log.info("Initializing token.")
      self._token.initialize()

    with self._token.session(rw=True) as session:
      try:
        key = session.get_key(label=self._key_label)
        log.debug("Key %s:%s is available on %s.", key, self._key_label, session)
        return
      except pkcs11.exceptions.NoSuchKey:
        pass
      session.generate_key(
          key_type=pkcs11.KeyType.AES,
          key_length=256,
          id=uuid.uuid4().bytes,  # Need some unique value here
          label=self._key_label,
          template={
              # Don't allow callers to read the key data
              pkcs11.Attribute.SENSITIVE: True,
              pkcs11.Attribute.EXTRACTABLE: False,
          },
          store=True,  # Key should be persistent
      )

  def encrypt(self, plaintext: bytes) -> str:
    """Encrypt the supplied plaintext.

    plaintext: Bytestring to be encrypted

    Returns a hex-encoded IV||Ciphertext string.
    """
    with self._token.session() as session:
      mechanism = self._get_encryption_mechanism(session)
      if mechanism != pkcs11.Mechanism.AES_CBC_PAD and len(plaintext) % 16 != 0:
        raise ValueError("Padding not available; plaintext must be aligned to block size!")

      key = session.get_key(label=self._key_label)
      iv = session.generate_random(self.IV_LEN_BYTES * 8)
      ciphertext = key.encrypt(
          plaintext,
          mechanism=mechanism,
          mechanism_param=iv,
      )
      hex_data = (iv + ciphertext).hex()
      return hex_data

  def decrypt(self, ciphertext_hex: str) -> bytes:
    """Decrypt the supplied ciphertext with a prepended IV.

    ciphertext_hex: Hex-encoded string of IV||Ciphertext

    Returns the deciphered plaintext.
    """
    ciphertext_and_iv = bytes.fromhex(ciphertext_hex)
    iv = ciphertext_and_iv[:self.IV_LEN_BYTES]
    ciphertext = ciphertext_and_iv[self.IV_LEN_BYTES:]

    with self._token.session() as session:
      key = session.get_key(label=self._key_label)
      plaintext = key.decrypt(
          ciphertext,
          mechanism=self._get_encryption_mechanism(session),
          mechanism_param=iv,
      )
      return plaintext

  def _get_encryption_mechanism(self, session):
    available_mechanisms = session.token.slot.get_mechanisms()
    # AES GCM would be better but it's not supported by python-pkcs11
    return (
        pkcs11.Mechanism.AES_CBC_PAD
        if pkcs11.Mechanism.AES_CBC_PAD in available_mechanisms
        # Some implementations (e.g. OP-TEE) don't support padding
        else pkcs11.Mechanism.AES_CBC
    )


class PKCS11Ed25519Signer:
  """Implements Ed25519 digital signatures backed by a (virtual) PKCS#11 token.

  Ed25519 is the Edwards-curve Digital Signature Algorithm (EdDSA) using Curve25519.
  It's regarded as a high-quality secure signature scheme that is also very efficient
  to compute.

  https://en.wikipedia.org/wiki/EdDSA
  """

  def __init__(self,
               token_label: str,
               key_label: str,
               pkcs11_module: str,
               pin: typing.Optional[str] = None,
               pin_path: typing.Optional[str] = None,
  ):
    """Initialize the signer

    token_label: The label identifying the token to be used
    key_label: The label identifying the AES key to be used
    pkcs11_module: The path to a shared object implementing the desired backend PKCS#11 API
    pin: The user & security officer login PIN (mutually exclusive with pin_path)
    pin_path: Path to file containing pin, as binary (mutually exclusive with pin)
    """
    self._key_label = key_label
    self._certificate_label = f"{key_label}-cert"
    self._token = PKCS11Token(
        token_label=token_label,
        pin=pin,
        pin_path=pin_path,
        pkcs11_module=pkcs11_module,
    )

  def prepare_key(self) -> crypto_ttypes.PublicKey:
    """Prepare the signing key for operation and return its public bytes.

    The key will be created if it does not yet exist.

    Raises pkcs11.exceptions.NoSuchToken if the token has not been initialized.
    """
    with self._token.session(rw=True) as session:
      pubkey = None
      privkey = None
      try:
        pubkey = session.get_key(pkcs11.ObjectClass.PUBLIC_KEY, label=self._key_label)
        log.debug("Key %s:%s is available on %s.", pubkey, self._key_label, session)
        privkey = session.get_key(pkcs11.ObjectClass.PRIVATE_KEY, label=self._key_label)
      except pkcs11.exceptions.NoSuchKey:
        pass

      if pubkey and not privkey:
        log.error("No private key present for public key %s! Regenerating.", pubkey)
        pubkey.destroy()
        pubkey = None

      if not pubkey:
        parameters = session.create_domain_parameters(
            pkcs11.KeyType.EC,
            {
                pkcs11.Attribute.EC_PARAMS: asn1crypto.core.PrintableString("edwards25519").dump(),
            },
            local=True,
        )
        pubkey, _ = parameters.generate_keypair(
            mechanism=pkcs11.Mechanism.EC_EDWARDS_KEY_PAIR_GEN,
            id=uuid.uuid4().bytes,  # Need some unique value here
            label=self._key_label,
            store=True,  # Key should be persistent
            public_template={
                pkcs11.Attribute.KEY_TYPE: pkcs11.KeyType.EC_EDWARDS,
            },
            private_template={
                pkcs11.Attribute.KEY_TYPE: pkcs11.KeyType.EC_EDWARDS,
            },
        )

      # This property is not defined consistently across PKCS#11 implementations. In some cases
      # the EC_POINT prefixes the public key bytes with a header tag, and sometimes it's simply
      # the raw public key. To hack around this we just always take the final 32 bytes.
      public_bytes = pubkey[pkcs11.Attribute.EC_POINT][-32:]
      return crypto_ttypes.PublicKey(
          key_type=crypto_ttypes.AsymmetricKeyType.ED25519,
          key_id=crypto_utils.get_key_id(public_bytes),
          public_bytes=public_bytes,
      )

  def get_certificate(self) -> typing.Optional[bytes]:
    """Get the certificate asserting authenticity of the signing key.

    Returns a DER-encoded X.509 certificate, or None if no certificate is available.
    """
    with self._token.session() as session:
      for obj in session.get_objects({
          pkcs11.Attribute.CLASS: pkcs11.ObjectClass.CERTIFICATE,
          pkcs11.Attribute.LABEL: self._certificate_label,
      }):
        return obj[pkcs11.Attribute.VALUE]

    return None

  def store_certificate(self, cert_bytes: bytes) -> None:
    """Store a certificate asserting authenticity of the signing key.

    cert_bytes: A DER-encoded X.509 certificate
    """
    cert_attrs = pkcs11.util.x509.decode_x509_certificate(cert_bytes)
    with self._token.session(rw=True) as session:
      cert = session.create_object({
          pkcs11.Attribute.LABEL: self._certificate_label,
          pkcs11.Attribute.TOKEN: True,  # Request persistence
          **cert_attrs
      })

  def destroy_key(self) -> None:
    self._token.destroy_all_objects()

  def sign(self, data: bytes) -> bytes:
    with self._token.session() as session:
      key = session.get_key(pkcs11.ObjectClass.PRIVATE_KEY, label=self._key_label)
      signature = key.sign(
          data,
          mechanism=pkcs11.Mechanism.EDDSA,
      )
      return signature
