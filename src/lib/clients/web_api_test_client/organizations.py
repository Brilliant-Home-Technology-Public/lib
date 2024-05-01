import datetime

import lib.br_jwt.br_jwt
import lib.clients.web_api_test_client.base
import lib.clients.web_api_test_client.utils
import lib.ulid


class WebAPIOrganizationsTestClient(lib.clients.web_api_test_client.base.WebAPIBaseTestClient):
  async def delete_invitation_to_home_property(self, **kwargs):
    params = {
        "email_address": lib.clients.web_api_test_client.utils.create_randomized_email_address(),
        "property_id": lib.ulid.generate(lib.ulid.IDType.ORGANIZATION_PROPERTY).hex,
        "user_token": lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_admin_registration_jwt_secret,
            payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
            exp_timedelta=datetime.timedelta(hours=24),
        ),
    }
    params.update(kwargs)

    return await self._session.delete_invitation_to_home_property(**params)

  async def post_add_user_to_home(self, email_address=None, **kwargs):
    email_address = (
        email_address or lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    property_id = (
        kwargs.get("property_id", None) or
        lib.ulid.generate(lib.ulid.IDType.ORGANIZATION_PROPERTY).hex
    )
    params = {
        "property_id": property_id,
        "token": lib.br_jwt.br_jwt.encode_admin_registration_token(
            email_address=email_address,
            route_name="organizations_add_user_to_home",
            property_id=property_id,
            secret=self._web_api_admin_registration_jwt_secret,
        ),
        "user_id": lib.ulid.generate(lib.ulid.IDType.USER).hex
    }
    params.update(kwargs)

    return await self._session.post_add_user_to_home(**params)

  async def post_add_user_to_organization(self, email_address=None, **kwargs):
    email_address = (
        email_address or lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    params = {
        "property_id": lib.ulid.generate(lib.ulid.IDType.ORGANIZATION_PROPERTY).hex,
        "token": lib.br_jwt.br_jwt.encode_admin_registration_token(
            email_address=email_address,
            route_name="organizations_add_user_to_organization",
            property_id=lib.ulid.generate(lib.ulid.IDType.ORGANIZATION_PROPERTY).hex,
            secret=self._web_api_admin_registration_jwt_secret,
        ),
        "user_id": lib.ulid.generate(lib.ulid.IDType.USER).hex
    }
    params.update(kwargs)

    return await self._session.post_add_user_to_organization(**params)

  async def post_reset_home_for_home_property(self, **kwargs):
    user_id = kwargs.pop("user_id", lib.ulid.generate(lib.ulid.IDType.USER).hex)
    params = {
        "property_id": lib.ulid.generate(lib.ulid.IDType.ORGANIZATION_PROPERTY).hex,
        "user_token": lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_login_jwt_secret,
            payload=dict(user_id=user_id),
            exp_timedelta=datetime.timedelta(hours=24),
        ),
    }
    params.update(kwargs)

    return await self._session.post_reset_home_for_home_property(**params)

  async def delete_user_from_organization(self, **kwargs):
    params = {
        "property_id": lib.ulid.generate(lib.ulid.IDType.ORGANIZATION_PROPERTY).hex,
        "user_id": lib.ulid.generate(lib.ulid.IDType.USER).hex,
        "user_token": lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_admin_registration_jwt_secret,
            payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
            exp_timedelta=datetime.timedelta(hours=24),
        ),
    }
    params.update(kwargs)

    return await self._session.delete_user_from_organization(**params)

  async def delete_portal_user_invitation_to_organization(self, **kwargs):
    params = {
        "email_address": lib.clients.web_api_test_client.utils.create_randomized_email_address(),
        "property_id": lib.ulid.generate(lib.ulid.IDType.ORGANIZATION_PROPERTY).hex,
        "user_token": lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_admin_registration_jwt_secret,
            payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
            exp_timedelta=datetime.timedelta(hours=24),
        ),
    }
    params.update(kwargs)

    return await self._session.delete_portal_user_invitation_to_organization(**params)

  async def post_invite_portal_user_to_organization(self, **kwargs):
    params = {
        "user_token": lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_login_jwt_secret,
            payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
            exp_timedelta=datetime.timedelta(hours=24),
        ),
        "email_address": lib.clients.web_api_test_client.utils.create_randomized_email_address(),
        "organization_id": lib.ulid.generate(lib.ulid.IDType.ORGANIZATION_PROPERTY).hex,
    }
    params.update(kwargs)

    return await self._session.post_invite_portal_user_to_organization(**params)

  async def post_invite_user_to_home(self, **kwargs):
    params = {
        "email_address": lib.clients.web_api_test_client.utils.create_randomized_email_address(),
        "property_id": lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        "user_token": lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_login_jwt_secret,
            payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
            exp_timedelta=datetime.timedelta(hours=1),
        ),
    }
    params |= kwargs

    return await self._session.post_invite_user_to_home(**params)

  async def post_resend_invite_to_home(self, **kwargs):
    params = {
        "email_address": lib.clients.web_api_test_client.utils.create_randomized_email_address(),
        "property_id": lib.ulid.generate(lib.ulid.IDType.HOME).hex,
        "user_token": lib.br_jwt.br_jwt.encode_token(
            secret=self._web_api_login_jwt_secret,
            payload=dict(user_id=lib.ulid.generate(lib.ulid.IDType.USER).hex),
            exp_timedelta=datetime.timedelta(hours=1),
        ),
    }
    params |= kwargs

    return await self._session.post_resend_invite_to_home(**params)
