"""A module for encoding and decoding JSON Web Tokens."""

import datetime
import logging
import typing

import jwt

import lib.networking.utils


log = logging.getLogger(__name__)


class InvalidSecretError(Exception):
  """Denotes that the caller attempted to use an invalid secret to encode a token. The secret must
  not be None nor an empty string.
  """


class InvalidTokenError(Exception):
  """Denotes that the provided token is invalid (e.g. because the payload was not the expected
  value, the token had expired, etc.)."""


class InvalidPayloadError(Exception):
  """Denotes that the payload to encode was invalid. For example, the payload was using a key that
  is reserved for the JSON web token's registered claim names
  (https://pyjwt.readthedocs.io/en/latest/usage.html#registered-claim-names).
  """


def encode_admin_registration_token(
    email_address,
    property_id,
    route_name,
    secret,
    exp_timedelta=None,
):
  '''
  Creates a JSON Web Token that includes the email address, property ID, and route name of
  the next step of registration for a new user of the admin portal.

  Args:
    email_address: The email address of the user registering.
    property_id: The property ID as a 32 character hex string.
    route_name: The name of the route at which the token is intended to be decoded and used.
    secret: The secret with which to encode the token.
    exp_timedelta: (optional) The time period for which the token is valid.

  Returns:
    The encoded token as a UTF-8 string.
  '''
  exp_timedelta = exp_timedelta or datetime.timedelta(hours=1)
  return encode_token(
      secret=secret,
      payload=dict(
          email_address=email_address,
          property_id=property_id,
          route_name=route_name,
      ),
      exp_timedelta=exp_timedelta,
  )


def decode_admin_registration_token(token, route_name, secret, email_address=None):
  '''
  Validates the given JSON Web Token and returns the email address, property ID, and route name
  associated with the token.

  Args:
    token: The JWT that was encoded using the encode_admin_registration_token function.
    route_name: Used to verify that the route name in the payload matches.
    secret: The secret with which to decode the token.
    email_address: (optional) Used to verify that the email address in the payload is expected.

  Returns:
    The decoded token's payload.

  Raises:
    web_api.errors.TokenInvalidError, if:
      - The token could not be decoded;
      - The token has expired;
      - The payload does not contain email_address, property_id, and route_name; or
      - The payload's route_name or email_address do not match what is expected.
  '''
  payload = decode_token(secret=secret, token=token)

  for field_name in ["email_address", "property_id", "route_name"]:
    if field_name not in payload:
      log.info("The payload does not contain the field '%s'.", field_name)
      raise InvalidTokenError

  if payload["route_name"] != route_name:
    log.info(
        "The token's route name (%s) was not as expected (%s).",
        payload["route_name"],
        route_name,
    )
    raise InvalidTokenError

  if email_address and payload["email_address"] != email_address:
    log.info(
        "The token's email address (%s) was not as expected (%s).",
        payload["email_address"],
        email_address,
    )
    raise InvalidTokenError

  return payload


def encode_device_token(secret, client_cert, exp_timedelta, payload=None, **kwargs):
  """Creates a JSON Web Token that includes a fingerprint of the device's client certificate as a
  claim that can later be validated with _decode_device_token().

  Args:
    secret: The secret that will be used to encode the token.
    client_cert: The client certificate for which the fingerprint will be encoded in the token.
    exp_timedelta: The amount of time until the token should be considered expired. Represented
        as a datetime.timedelta. The exp_timedelta is required to avoid creating a token without an
        expiration.
    payload: A dictionary containing the data to be encoded within the token.
    **kwargs: See encode_token for additional parameters.

  Returns:
    The encoded token as a UTF-8 string.
  """
  payload = payload or {}

  certificate_fingerprint = lib.networking.utils.get_certificate_fingerprint(client_cert)
  payload["fingerprint"] = certificate_fingerprint

  return encode_token(secret=secret, payload=payload, exp_timedelta=exp_timedelta, **kwargs)


# TODO - Ryan - Update all of the decode APIs to take a recently_expired_secret
def decode_device_token(token, secret, client_cert, **kwargs):
  """Validates that the token contains a fingerprint that matches the fingerprint of the device's
  client certificate that arrived in the request. If the token is valid, the token's decoded
  payload is returned.

  Args:
    token: The JSON Web Token that was encoded with _encode_device_token().
    secret: The secret that was used to encode the token.
    client_cert: The client certificate for which the fingerprint will be encoded in the token.
    **kwargs: See encode_token for additional parameters.

  Returns:
    The decoded token's payload.

  Raises:
    InvalidTokenError: If the token could not be decoded; if the token has expired; or if the
        client certificate fingerprint received in the request does not match the token's client
        certificate fingerprint.
  """
  certificate_fingerprint = lib.networking.utils.get_certificate_fingerprint(client_cert)

  payload = decode_token(token, secret=secret, **kwargs)
  if payload["fingerprint"] != certificate_fingerprint:
    log.info("The client certificate fingerprint does not match the token's fingerprint.")
    raise InvalidTokenError()

  return payload


def encode_email_token(
    secret: str,
    email_address: str,
    allowed_paths: typing.List[str],
    **kwargs
) -> str:
  """Creates a JSON Web Token that includes the email_address as a claim that can later be
  validated.

  Args:
    secret: The secret that will be used to encode the token.
    email_address: The email address that will be encoded in the token.
    allowed_paths: The API paths that this token is allowed to access.

  Returns:
    The encoded token as a UTF-8 string.
  """
  return encode_token(
      secret=secret,
      payload=dict(email_address=email_address, allowed_paths=allowed_paths),
      **kwargs
  )


def decode_email_token(
    token: str,
    secret: str,
    email_address: str,
    **kwargs
) -> typing.Dict[str, str]:
  """Validates that the token contains the given email_address. If the token is valid, the token's
  decoded payload is returned.

  The decoded payload may also contain the `allowed_paths` field. However, it is up to the caller to
  validate that field.

  Args:
    token: The JSON Web Token that was encoded using the encode_email_token function.
    secret: The secret that was used to encode the token.
    email_address: The email address to verify is encoded within the the token.

  Returns:
    The decoded token's payload.

  Raises:
    InvalidTokenError: If the given email address does not match the email address encoded within
        the token; the token could not be decoded; or the token has expired.
  """
  payload = decode_token(token=token,
                         secret=secret,
                         **kwargs)
  if payload.get("email_address", "").casefold() != email_address.casefold():
    log.info("The email address(%s) did not match the token's email address.", email_address)
    raise InvalidTokenError()

  return payload


def decode_open_id_token(token, keys, issuers=None, algorithm=None, audience=None):
  """Decodes and verifies multiple fields of a JSON Web Token. If the token is valid, the token's
  decoded payload is returned.

  Args:
    token: The JSON Web Token sent from an external party (i.e. Google Nest).
    keys: Dictionary of key_id: key. Should contain key with id found in token header.
    (optional) issuers: List of valid issuers for the token. If None, issuers are not verified.
    (optional) algorithm: Algorithm used to encode/decode the token.
    (optional) audience: Expected value to be found in token payload for key 'aud'.

  Returns:
    The decoded token's payload.

  Raises:
    InvalidSecretError: If key is not specified in JWT header, or if key specified in header is
      not found in keys arg.
    InvalidTokenError: If audience is invalid, signature is invalid, signature is expired, other
      decode error occurs, or decoded issuer is not found in non-empty issuers list.
  """
  try:
    unverified_headers = jwt.get_unverified_header(token)
    key_id = unverified_headers["kid"]
    decoded_token_info = jwt.decode(
        jwt=token,
        key=keys[key_id],
        algorithms=algorithm,
        audience=audience,
    )
  except KeyError as e:
    raise InvalidSecretError() from e
  except (
      jwt.exceptions.InvalidAudienceError,
      jwt.exceptions.InvalidSignatureError,
      jwt.exceptions.ExpiredSignatureError,
      jwt.exceptions.DecodeError,
  ) as e:
    raise InvalidTokenError() from e

  issuer = decoded_token_info.get("iss")
  if issuers and issuer not in issuers:
    log.info("Invalid issuer %s for ID token.", issuer)
    raise InvalidTokenError()

  return decoded_token_info


def encode_home_auth_token(secret: str, home_id: str, user_id: str) -> str:
  """Creates a JSON Web Token that includes the home ID in the payload. This should be considered a
  valid "access token" for a given home.

  Args:
    secret: The secret that will be used to encode the token.
    home_id: The home ID as a 32 character hex string.
    user_id: The user ID for which this token is valid for.

  Returns:
    The encoded token as a UTF-8 string.
  """
  exp_timedelta = datetime.timedelta(minutes=30)
  return encode_token(
      secret=secret,
      payload=dict(home_id=home_id, user_id=user_id),
      exp_timedelta=exp_timedelta,
  )


def decode_home_auth_token(token: str, secret: str, home_id: str) -> typing.Dict[str, str]:
  """Validates that the given token contains the given home ID. If the token is valid, the token's
  decoded payload is returned.

  Args:
    token: The JWT that was encoded using the encode_home_auth_token function.
    secret: The secret that was used to encode the token.
    home_id: The home ID to verify is encoded within the token.

  Returns:
    The decoded token's payload.

  Raises:
    web_api.errors.TokenInvalidError if the token is invalid or the home ID is not contained in the
    token.
  """

  payload = decode_token(
      secret=secret,
      token=token,
      include_claims_in_payload=True,
  )
  if payload.get("home_id", None) != home_id:
    log.info("The home ID did not match the token's home ID.")
    raise InvalidTokenError()

  return payload


def encode_token(secret, payload=None, exp_timedelta=None, issued_at=None):
  """Encodes a JSON Web Token that can later be decoded using the decode_token function with the
  same secret.

  Args:
    secret: The secret that will be used to encode the token.
    payload: The payload to encode within the token.
    exp_timedelta: The amount of time until the token should be considered expired. Represented as a
        `datetime.timedelta`.
    issued_at: The time at which the token is issued. Represented as a `datetime.datetime`.

  Returns:
    The encoded token as a UTF-8 string.
  """
  payload = payload or {}

  if not secret:
    raise InvalidSecretError("Invalid secret: %s" % secret)

  # Raise an error if the caller tries to create a payload with a registered claim key. All
  # registered claims should be added by this library.
  # - "exp": Expiration Time
  # - "nbf": Not Before Time
  # - "iss": Issuer
  # - "aud": Audience
  # - "iat": Issued At
  #
  # For more details, see https://pyjwt.readthedocs.io/en/latest/usage.html#registered-claim-names
  for key in ["exp", "nbf", "iss", "aud", "iat"]:
    if key in payload:
      raise InvalidPayloadError("'{key}' is a reserved keyword in the payload.".format(key=key))

  if exp_timedelta:
    payload["exp"] = datetime.datetime.now(datetime.timezone.utc) + exp_timedelta

  if issued_at:
    payload["iat"] = issued_at

  token = jwt.encode(payload=payload, key=secret, algorithm="HS256")
  # By default, the token is byte encoded. Thus, we convert the token to a string.
  return token.decode("UTF-8")


def decode_token(*args, secret, recently_retired_secret=None, **kwargs):
  """Decode a JSON Web Token using the server's secrets. See _decode_token for arguments and keyword
  arguments.

  Returns:
    The decoded token's payload.

  Raises:
    InvalidTokenError: If the token could not be decoded or if the token has expired.
  """
  try:

    # Attempt to decode the token using the current secret first. If the token cannot be decoded
    # using the current secret, attempt to use the recently retired token. Thus, when the system is
    # transitioning to a new secret, both the old and new secrets can be honored until the switch is
    # complete.
    try:
      return _decode_token(*args, secret=secret, **kwargs)
    except jwt.exceptions.DecodeError as e:
      if not recently_retired_secret:
        raise
      return _decode_token(*args, secret=recently_retired_secret, **kwargs)

  except jwt.exceptions.ExpiredSignatureError as e:
    payload = _decode_token(*args, secret=secret, verify=False, **kwargs)
    log.info("An expired JSON Web Token was rejected, payload %s.", payload)
    raise InvalidTokenError from e
  except jwt.exceptions.DecodeError as e:
    log.info("A JSON Web Token could not be decoded.")
    raise InvalidTokenError from e


def _decode_token(
    token,
    secret,
    exp_leeway_timedelta=None,
    include_claims_in_payload=False,
    verify=True,
):
  """Decode a JSON Web Token that was encoded using the encode_token function.

  Args:
    token: The JSON Web Token that was encoded with the encode_token function.
    secret: The secret to use to decode the token.
    exp_leeway_timedelta: The amount of leeway to give the expiration timestamp denoted using a
        datetime.timedelta.
    include_claims_in_payload: True, if the claims managed by this library should be included in the
        payload. If False, only the portion of the payload that was originally encoded by the user
        will be returned.
    verify: If True, the signature should be validated when decoding the token. If False, skip
        signature validation when decoding. Default to True, callers should be cautious about
        disabling signature validation.

  Returns:
    The decoded token's payload. By default, the returned payload will have all of the claims
    removed as all of the claims will be verified within the function. To receive a payload
    containing the library managed claims, set `include_claims_in_payload` to True.

  Raises:
    jwt.exceptions.ExpiredSignatureError: If the token has expired.
    jwt.exceptions.DecodeError: If the token could not be decoded due to an incorrect token or
        incorrect secret.
  """
  # For ease of use, this API accepts the leeway as a timedelta. The jwt library accepts `leeway` as
  # either a timedelta or an integer in seconds, but the default value is 0. Thus, we set the value
  # to 0 when no leeway was specified to retain the default behavior.
  leeway = exp_leeway_timedelta or 0

  if not secret:
    raise InvalidSecretError("Invalid secret: %s" % secret)

  payload = jwt.decode(token, key=secret, leeway=leeway, algorithms="HS256", verify=verify)

  if not include_claims_in_payload:
    for key in ["exp", "nbf", "iss", "aud", "iat"]:
      payload.pop(key, None)

  return payload
