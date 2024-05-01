"""The Web API Test Client wraps the standard lib.clients.web_api client with default values for the
various APIs. Whereas the standard Web API Client can be used in production services, the test
client should only be used for testing and within internal tools.
"""

import asyncio
import os

import lib.clients.web_api.client
import lib.clients.web_api_test_client.art
import lib.clients.web_api_test_client.devices
import lib.clients.web_api_test_client.emails
import lib.clients.web_api_test_client.entrata
import lib.clients.web_api_test_client.genie
import lib.clients.web_api_test_client.graphql_homes
import lib.clients.web_api_test_client.homes
import lib.clients.web_api_test_client.honeywell
import lib.clients.web_api_test_client.login
import lib.clients.web_api_test_client.organizations
import lib.clients.web_api_test_client.provisioning
import lib.clients.web_api_test_client.registration
import lib.clients.web_api_test_client.remotelock
import lib.clients.web_api_test_client.software_support
import lib.clients.web_api_test_client.users
import lib.clients.web_api_test_client.utils
import lib.clients.web_api_test_client.zendesk


class WebAPITestClientSession:
  def __init__(
      self,
      loop: asyncio.AbstractEventLoop,
      cert_dir: str,
      cert_file_prefix: str = "device",
      cert_port: int = 9000,
      non_cert_port: int = 9000,
      web_api_admin_registration_jwt_secret: str = "TEST_ADMIN_REGISTRATION_SECRET",
      web_api_jwt_secret: str = "TEST_SECRET",
      web_api_login_jwt_secret: str = "TEST_LOGIN_SECRET",
      web_api_user_login_jwt_secret: str = "TEST_USER_LOGIN_SECRET",
      web_api_server_prefix: str = "https://localhost",
      web_api_zendesk_jwt_secret: str = "TEST_ZENDESK_SECRET",
  ):
    """
    Args:
      cert_dir: The directory containing the client certificates in PEM format that will be used
          when making requests that require client certificates.
      cert_file_prefix: The prefix for the '<prefix>.cert/.csr/.key' files.
      cert_port: The port to which to send requests that require a client certificate.
      non_cert_port: The port to which to send requests that do not contain a client certificate.
      web_api_admin_registration_jwt_secret: The secret used to encode and decode JSON Web Tokens
          for admin portal registration.
      web_api_jwt_secret: The secret used to encode and decode JSON Web Tokens for Web API requests.
      web_api_login_jwt_secret: The secret used to encode and decode JSON Web Tokens for MF Admin user logins.
      web_api_user_login_jwt_secret: The secret used to encode and decode JSON Web Tokens for Normal user logins.
      web_api_zendesk_jwt_secret: The secret used to encode and decode JSON Web Tokens for Zendesk requests.
      web_api_server_prefix: The scheme://hostname to which to send Web API requests.
      loop: The event loop on which Web API requests should be executed.
    """
    self.session = lib.clients.web_api.client.WebAPIClientSession(
        cert_dir=cert_dir,
        cert_file_prefix=cert_file_prefix,
        web_api_server_prefix=web_api_server_prefix,
        cert_port=cert_port,
        non_cert_port=non_cert_port,
        loop=loop,
    )
    default_client_cert = lib.clients.web_api_test_client.utils.get_client_cert(
        cert_file=os.path.join(cert_dir, "device.cert"),
    )

    ##########################
    # Implementation Clients #
    ##########################
    self.art = lib.clients.web_api_test_client.art.WebAPIArtTestClient(
        default_client_cert=default_client_cert,
        web_api_jwt_secret=web_api_jwt_secret,
        web_api_session=self.session.art,
    )
    self.devices = lib.clients.web_api_test_client.devices.WebAPIDevicesTestClient(
        default_client_cert=default_client_cert,
        web_api_jwt_secret=web_api_jwt_secret,
        web_api_login_jwt_secret=web_api_login_jwt_secret,
        web_api_session=self.session.devices,
    )
    self.emails = lib.clients.web_api_test_client.emails.WebAPIEmailsTestClient(
        default_client_cert=default_client_cert,
        web_api_admin_registration_jwt_secret=web_api_admin_registration_jwt_secret,
        web_api_login_jwt_secret=web_api_login_jwt_secret,
        web_api_jwt_secret=web_api_jwt_secret,
        web_api_session=self.session.emails,
    )
    self.entrata = lib.clients.web_api_test_client.entrata.WebAPIEntrataTestClient(
        web_api_login_jwt_secret=web_api_login_jwt_secret,
        web_api_session=self.session.entrata,
    )
    self.genie = lib.clients.web_api_test_client.genie.WebAPIGenieTestClient(
        web_api_session=self.session.genie,
    )
    self.graphql_homes = lib.clients.web_api_test_client.graphql_homes.WebAPIGraphQLHomesTestClient(
        web_api_login_jwt_secret=web_api_login_jwt_secret,
        web_api_session=self.session.graphql_homes,
    )
    self.homes = lib.clients.web_api_test_client.homes.WebAPIHomesTestClient(
        default_client_cert=default_client_cert,
        web_api_login_jwt_secret=web_api_login_jwt_secret,
        web_api_user_login_jwt_secret=web_api_user_login_jwt_secret,
        web_api_jwt_secret=web_api_jwt_secret,
        web_api_session=self.session.homes,
    )
    self.honeywell = lib.clients.web_api_test_client.honeywell.WebAPIHoneywellTestClient(
        web_api_session=self.session.honeywell,
    )
    self.login = lib.clients.web_api_test_client.login.WebAPILoginTestClient(
        web_api_login_jwt_secret=web_api_login_jwt_secret,
        web_api_session=self.session.login,
    )
    self.organizations = lib.clients.web_api_test_client.organizations.WebAPIOrganizationsTestClient(
        web_api_admin_registration_jwt_secret=web_api_admin_registration_jwt_secret,
        web_api_login_jwt_secret=web_api_login_jwt_secret,
        web_api_session=self.session.organizations,
    )
    self.provisioning = lib.clients.web_api_test_client.provisioning.WebAPIProvisioningTestClient(
        web_api_session=self.session.provisioning,
    )
    self.registration = lib.clients.web_api_test_client.registration.WebAPIRegistrationTestClient(
        web_api_admin_registration_jwt_secret=web_api_admin_registration_jwt_secret,
        web_api_session=self.session.registration,
    )
    self.remotelock = lib.clients.web_api_test_client.remotelock.WebAPIRemoteLockTestClient(
        web_api_session=self.session.remotelock,
    )
    self.software_support = lib.clients.web_api_test_client.software_support.WebAPISoftwareSupportTestClient(
        web_api_session=self.session.software_support,
    )
    self.users = lib.clients.web_api_test_client.users.WebAPIUsersTestClient(
        web_api_admin_registration_jwt_secret=web_api_admin_registration_jwt_secret,
        web_api_jwt_secret=web_api_jwt_secret,
        web_api_session=self.session.users,
    )
    self.zendesk = lib.clients.web_api_test_client.zendesk.WebAPIZendeskTestClient(
        web_api_jwt_secret=web_api_jwt_secret,
        web_api_zendesk_jwt_secret=web_api_zendesk_jwt_secret,
        web_api_session=self.session.zendesk,
    )
