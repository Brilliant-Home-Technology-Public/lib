import datetime

import lib.br_jwt.br_jwt
import lib.clients.web_api_test_client.base
import lib.clients.web_api_test_client.utils


class WebAPIArtTestClient(lib.clients.web_api_test_client.base.WebAPIBaseTestClient):

  async def post_art_add_library(self, client_cert=None, **kwargs):
    client_cert = client_cert or self._default_client_cert
    params = {
        "library_id": "library:test_library",
        "title": "Test Library",
        "default_enabled": True,
        "jwt_token": lib.br_jwt.br_jwt.encode_device_token(
            client_cert=client_cert,
            exp_timedelta=datetime.timedelta(hours=1),
            secret=self._web_api_jwt_secret,
        ),
    }
    params.update(kwargs)

    return await self._session.create_art_library(**params)

  async def post_art_add_art_pieces(self, client_cert=None, **kwargs):
    client_cert = client_cert or self._default_client_cert
    params = {
        "library_id": "library:test_library",
        "art_pieces": [
            {
                "piece_id": "test_piece",
                "primary": {
                    "s3_key": "test_s3_key",
                    "content_type": "image/png",
                },
                "previews": [],
            },
        ],
        "jwt_token": lib.br_jwt.br_jwt.encode_device_token(
            client_cert=client_cert,
            exp_timedelta=datetime.timedelta(hours=1),
            secret=self._web_api_jwt_secret,
        ),
    }
    params.update(kwargs)

    return await self._session.create_art_pieces(**params)

  async def post_art_synchronize(self, client_cert=None, **kwargs):
    client_cert = client_cert or self._default_client_cert
    params = {
        "library_id": "library:test_library",
        "restrict_home_ids": [],
        "jwt_token": lib.br_jwt.br_jwt.encode_device_token(
            client_cert=client_cert,
            exp_timedelta=datetime.timedelta(hours=1),
            secret=self._web_api_jwt_secret,
        ),
    }
    params.update(kwargs)

    return await self._session.synchronize_art(**params)
