import logging

import email_validator


log = logging.getLogger(__name__)


def get_validated_and_normalized_email_address(email_address, check_deliverability=False,
                                               exception_cls=None):
  '''Verify that an email address is valid. Then, normalize the email address. This function should
  be run on every email address before either inserting the email address into the database or Redis
  or subsequently checking if the email address is in the database or Redis.

  Args:
    email_address: The email address to validate and normalize.
    check_deliverability: If True, executes a domain name resolution check to see if emails to the
        address can be  delivered. False by default. This should generally be left as False in
        backend services to avoid making the DNS request.
    exception_cls: An exception class that will be raised instead of the default
        email_validator.EmailNotValidError. This can be used to specify a backend specific exception
        type.

  Returns:
    A string representing the valid, normalized email address.

  Raises:
    email_validator.EmailNotValidError: If the email address is deemed to be invalid.
    exception_cls: Will be raised instead of the default error if provided.
  '''
  try:
    return email_validator.validate_email(email_address,
                                          check_deliverability=check_deliverability)["email"]
  except email_validator.EmailNotValidError as e:
    log.warning("Email validation failed: %s", str(e))
    if not exception_cls:
      raise
    raise exception_cls(str(e)) from e
