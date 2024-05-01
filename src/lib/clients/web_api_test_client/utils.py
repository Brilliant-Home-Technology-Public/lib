import random
import ssl
import string
import uuid


def create_randomized_email_address(base_local_part="test_user", domain="brilliant.tech"):
  """Creates a random email address in the format '<base>+<UUID>@<domain>'.

  Args:
    base_local_part: A string representing the static portion of the email address' local part.
    domain: The domain of the email address.

  Returns:
    The email address as a string.
  """
  return "{base_local_part}+{random_part}@{domain}".format(base_local_part=base_local_part,
                                                           random_part=uuid.uuid1(),
                                                           domain=domain)


def create_random_phone_number():
  """Creates a random phone number in both '(xxx) xxx-xxxx' and '+1xxxxxxxxxx' formats.

  Returns:
    The randomly generated phone number as a string in both '(xxx) xxx-xxxx' and '+1xxxxxxxxxx' formats.
  """
  first_part = "".join(random.choices(string.digits, k=3))
  second_part = "".join(random.choices(string.digits, k=3))
  third_part = "".join(random.choices(string.digits, k=4))

  return (f"({first_part}) {second_part}-{third_part}", f"+1{first_part}{second_part}{third_part}")


def get_client_cert(cert_file):
  """Fetches the client certificate in DER format.

  Args:
    cert_file: The file containing the device certificate in PEM format.

  Returns:
    The client certificate in DEF format.
  """
  pem_cert = None
  with open(cert_file, encoding="utf-8") as f:
    pem_cert = f.read()
  return ssl.PEM_cert_to_DER_cert(pem_cert)
