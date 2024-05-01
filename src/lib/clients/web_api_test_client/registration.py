import lib.br_jwt.br_jwt
import lib.clients.web_api_test_client.base
import lib.clients.web_api_test_client.utils
import lib.ulid


class WebAPIRegistrationTestClient(lib.clients.web_api_test_client.base.WebAPIBaseTestClient):
  async def post_registration_admin_verification_phone(self, **kwargs):
    email_address = kwargs.get(
        "email_address",
        lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    phone_number = kwargs.get(
        "phone_number", lib.clients.web_api_test_client.utils.create_random_phone_number()[0])
    params = {
        "email_address": email_address,
        "phone_number": phone_number,
        "token": lib.br_jwt.br_jwt.encode_admin_registration_token(
            email_address=email_address,
            route_name="registration_admin_verification_phone",
            property_id=lib.ulid.generate(lib.ulid.IDType.ORGANIZATION_PROPERTY).hex,
            secret=self._web_api_admin_registration_jwt_secret,
        ),
    }
    params.update(kwargs)

    return await self._session.post_registration_admin_verification_phone(**params)

  async def post_registration_admin_verification_verify_phone(self, **kwargs):
    email_address = kwargs.get(
        "email_address",
        lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    params = {
        "code": "123456",
        "email_address": email_address,
        "token": lib.br_jwt.br_jwt.encode_admin_registration_token(
            email_address=email_address,
            route_name="registration_admin_verification_verify_phone",
            property_id=lib.ulid.generate(lib.ulid.IDType.ORGANIZATION_PROPERTY).hex,
            secret=self._web_api_admin_registration_jwt_secret,
        ),
    }
    params.update(kwargs)

    return await self._session.post_registration_admin_verification_verify_phone(**params)

  async def post_registration_admin_verify_email(self, **kwargs):
    email_address = kwargs.get(
        "email_address",
        lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    params = {
        "code": "123456",
        "email_address": email_address,
        "token": lib.br_jwt.br_jwt.encode_admin_registration_token(
            email_address=email_address,
            route_name="registration_admin_verify_email",
            property_id=lib.ulid.generate(lib.ulid.IDType.ORGANIZATION_PROPERTY).hex,
            secret=self._web_api_admin_registration_jwt_secret,
        ),
    }
    params.update(kwargs)

    return await self._session.post_registration_admin_verify_email(**params)

  async def post_verify_tenant_email(self, **kwargs):
    email_address = kwargs.get(
        "email_address",
        lib.clients.web_api_test_client.utils.create_randomized_email_address()
    )
    params = {
        "code": "123456",
        "email_address": email_address,
        "token": lib.br_jwt.br_jwt.encode_admin_registration_token(
            email_address=email_address,
            route_name="registration_tenant_verify_email",
            property_id=lib.ulid.generate(lib.ulid.IDType.ORGANIZATION_PROPERTY).hex,
            secret=self._web_api_admin_registration_jwt_secret,
        ),
    }
    params.update(kwargs)

    return await self._session.post_verify_tenant_email(**params)
