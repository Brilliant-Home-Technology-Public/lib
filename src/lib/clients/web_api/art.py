import json

import lib.clients.web_api.base
import lib.networking.utils as networking_utils


class WebAPIArtClient(lib.clients.web_api.base.WebAPIBaseClient):

  def _get_headers(self, headers, jwt_token):
    jwt_token_header = networking_utils.format_headers({"auth-token": jwt_token})
    return self.get_headers(default_headers=headers,
                            header_updates=jwt_token_header)

  async def get_art_library(self, library_id, jwt_token):
    headers = self._get_headers(None, jwt_token)
    return await self.session.get(
        "/art/libraries/{}".format(library_id),
        extra_headers=headers,
        cert_required=True,
    )

  async def create_art_library(self, library_id, title, default_enabled, jwt_token):
    default_enabled = "1" if default_enabled else "0"
    headers = self._get_headers({"Content-Type": "application/json"}, jwt_token)
    return await self.post("/art/libraries/{}".format(library_id),
                           data=json.dumps({"title": title, "default_enabled": default_enabled}),
                           extra_headers=headers,
                           cert_required=True)

  async def create_art_pieces(self, library_id, art_pieces, jwt_token):
    headers = self._get_headers({"Content-Type": "application/json"}, jwt_token)
    return await self.post("/art/libraries/{}/pieces".format(library_id),
                           data=json.dumps({"art_pieces": art_pieces}),
                           extra_headers=headers,
                           cert_required=True)

  async def delete_art_piece(self, library_id, piece_id, jwt_token):
    headers = self._get_headers(None, jwt_token)
    return await self.delete("/art/libraries/{}/pieces/{}".format(library_id, piece_id),
                             extra_headers=headers,
                             cert_required=True)

  async def synchronize_art(self, library_id, restrict_home_ids, jwt_token):
    headers = self._get_headers({"Content-Type": "application/json"}, jwt_token)
    return await self.post(
        "/art/libraries/{}/synchronize".format(library_id),
        data=json.dumps({
            "restrict_home_ids": restrict_home_ids,
            "all_homes": not restrict_home_ids,
        }),
        extra_headers=headers,
        cert_required=True,
    )
