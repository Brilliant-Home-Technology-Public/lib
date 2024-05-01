import datetime
import ssl
import typing

import lib.br_jwt.br_jwt
import lib.clients.web_api.client
import lib.clients.web_api_test_client.base
import lib.clients.web_api_test_client.utils
import lib.ulid


CONTROL_SIGNING_KEY = b"my-control-signing-key"
DEFAULT_SESSION_ID = "319824705"


class WebAPIDevicesTestClient(lib.clients.web_api_test_client.base.WebAPIBaseTestClient):
  async def get_available_home_for_device(
      self,
      control_id: str = lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
      session_id: str = DEFAULT_SESSION_ID,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    """GET /devices/{}/available-home."""
    return await self._session.get_available_home_for_device(
        control_id=control_id,
        session_id=session_id,
    )

  async def post_available_home_for_device(
      self,
      control_id: str = lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
      control_signing_key: bytes = CONTROL_SIGNING_KEY,
      home_id: str = lib.ulid.generate(lib.ulid.IDType.HOME).hex,
      installing_device_id: str = lib.ulid.generate(lib.ulid.IDType.FACEPLATE).hex,
      session_id: str = DEFAULT_SESSION_ID,
      user_authorization_token: str = "",
      check_software_integrity: bool = False,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    params = dict(
        available_home_token=lib.br_jwt.br_jwt.encode_token(
            payload={"home_id": home_id},
            secret=control_signing_key,
        ),
        # The Control fingerprint should use its own client certificate, but
        # in order to get around the existing limitation on multiple certificates,
        # the same client certificate is being used here for both Control and mobile.
        control_fingerprint=lib.networking.utils.get_certificate_fingerprint(
            self._default_client_cert,
        ),
        control_id=control_id,
        session_id=session_id,
        check_software_integrity=check_software_integrity,
    )
    if user_authorization_token:
      params.update(user_authorization_token=user_authorization_token)
    else:
      params.update(
          home_id=home_id,
          installing_device_id=installing_device_id,
      )
    return await self._session.post_available_home_for_device(**params)

  async def get_device_public_key(
      self,
      device_id: str,
      key_purpose: str = "software-integrity",
      user_authorization_token: typing.Optional[str] = None,
  ) -> lib.clients.web_api.client.WebAPIResponse:
    return await self._session.get_device_public_key(
        device_id=device_id,
        key_purpose=key_purpose,
        user_authorization_token=user_authorization_token,
    )

  async def put_device_public_key(
      self,
      device_id: str,
      asymmetric_key_algorithm: str,
      public_key: bytes,
      key_purpose: str = "software-integrity",
  ) -> lib.clients.web_api.client.WebAPIResponse:
    return await self._session.put_device_public_key(
        device_id=device_id,
        key_purpose=key_purpose,
        asymmetric_key_algorithm=asymmetric_key_algorithm,
        public_key=public_key,
    )

  async def post_new_device(
      self,
      client_cert: typing.Optional[bytes] = None,
      device_type: str = "faceplate",
      pcb_number: str = "01234567890",
      environment: str = "debug",
  ) -> lib.clients.web_api.client.WebAPIResponse:
    authorization_token = lib.br_jwt.br_jwt.encode_device_token(
        client_cert=client_cert or self._default_client_cert,
        exp_timedelta=datetime.timedelta(hours=1),
        secret=self._web_api_jwt_secret,
    )
    return await self._session.post(
        cert_required=True,
        extra_headers={
            "X-Brilliant-Auth-Token": authorization_token,
        },
        json=dict(
            device_type=device_type,
            pcb_number=pcb_number,
            environment=environment,
            provision_homekit_auth_entity=False,
        ),
        path="/v3/devices",
    )

  async def put_updated_device_info(
      self,
      device_id: str,
      client_cert: bytes,
      ssh_public_key: str = "DUMMY SSH KEY",
      faceplate_software_version: str = "v11.22.33.4",
      **extra_params
  ) -> lib.clients.web_api.client.WebAPIResponse:
    authorization_token = lib.br_jwt.br_jwt.encode_device_token(
        client_cert=client_cert,
        exp_timedelta=datetime.timedelta(hours=1),
        secret=self._web_api_jwt_secret,
    )
    client_cert_pem = ssl.DER_cert_to_PEM_cert(client_cert).replace("\n", "")
    return await self._session.put(
        cert_required=True,
        extra_headers={
            "X-Brilliant-Auth-Token": authorization_token,
        },
        json=dict(
            ssl_cert=client_cert_pem,
            ssh_public_key=ssh_public_key,
            initial_software_map={
                "faceplate_emmc": faceplate_software_version,
            },
            **extra_params
        ),
        path=f"/v2/devices/{device_id}",
    )

  async def put_device_integrity_proof(
      self,
      device_id: str,
      challenge: bytes,
      signature: bytes,
      *,
      key_purpose: str = "software-integrity",
  ):
    return await self._session.put_device_integrity_proof(
        device_id=device_id,
        key_purpose=key_purpose,
        challenge=challenge,
        signature=signature,
    )
