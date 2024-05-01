class BadArgsError(Exception):
  pass


class ConfigurationError(Exception):
  pass


class ConsistencyError(Exception):
  pass


class DoesNotExistError(Exception):
  pass


class NoConnectionError(Exception):
  pass


class NotificationSubscriptionException(Exception):
  pass


class ParsingError(Exception):
  pass


class PeripheralInterfaceException(Exception):
  pass


class ProtocolError(Exception):
  pass


class ThirdPartyError(Exception):
  pass


class TooManyConnectedClients(Exception):
  pass


class UARTUnavailableError(Exception):
  pass


class PeripheralSetRequestError(Exception):
  pass


class UARTCommunicationError(Exception):
  pass


class AuthorizationValidationError(Exception):
  pass


class UARTResponseError(Exception):
  pass
