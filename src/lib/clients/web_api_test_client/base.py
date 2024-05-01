"""The base class for all of the individual WebAPI<Handler>TestClients."""


class WebAPIBaseTestClient:
  def __init__(
      self,
      web_api_session,
      default_client_cert=None,
      web_api_admin_registration_jwt_secret=None,
      web_api_jwt_secret=None,
      web_api_login_jwt_secret=None,
      web_api_user_login_jwt_secret=None,
      web_api_zendesk_jwt_secret=None,
  ):
    """
    Args:
      default_client_cert: The client certificate that will be used by default if an API is not
          provided a client certificate.
      web_api_admin_registration_jwt_secret: (optional) The secret used to encode JSON Web Tokens
          for admin portal registration.
      web_api_jwt_secret: (optional) The secret used to encode a JSON web token.
      web_api_login_jwt_secret: (optional) The secret used to encode JSON web token for MF Admin user login.
      web_api_user_login_jwt_secret: (optional) The secret used to encode JSON web token for Normal user login.
      web_api_session: The session to be used when making requests to the specific set of Web API
          endpoints (e.g. the session for communicating with the '/homes' endpoints).
    """
    self._default_client_cert = default_client_cert
    self._session = web_api_session
    self._web_api_admin_registration_jwt_secret = web_api_admin_registration_jwt_secret
    self._web_api_jwt_secret = web_api_jwt_secret
    self._web_api_login_jwt_secret = web_api_login_jwt_secret
    self._web_api_user_login_jwt_secret = web_api_user_login_jwt_secret
    self._web_api_zendesk_jwt_secret = web_api_zendesk_jwt_secret
