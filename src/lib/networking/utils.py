import asyncio
import base64
import enum
import functools
import hashlib
import importlib.resources
import ipaddress
import logging
import os
import socket
import ssl
import urllib.parse

import certifi
import gflags
import netifaces

from lib.networking.bluetooth import bluetooth_socket


gflags.DEFINE_string("cert_dir", "/tmp/certs", "Directory where certificates are stored")

log = logging.getLogger(__name__)

FLAGS = gflags.FLAGS
APP_DESIGNATION = "x-brilliant-"
CERTIFI_CA_FILE = certifi.where()


class MessagingProtocol:
  NEWLINE_DELIMITED_MESSAGE = 1
  WEB_SOCKET = 2
  HTTP = 3
  PROCESS_LOCAL = 4
  JSON_RPC = 5


# Define our own enumeration because presence of socket.AF_* constants is platform-dependent
@enum.unique
class AddressFamily(enum.IntEnum):
  # Match socket.AF_* values when present for backwards compatibility
  INET = socket.AF_INET
  UNIX = socket.AF_UNIX
  # Suppress warnings on reused member name
  if hasattr(socket, "AF_PACKET"):
    PACKET = socket.AF_PACKET
  elif hasattr(socket, "AF_LINK"):
    PACKET = socket.AF_LINK  # type: ignore[misc]
  else:
    PACKET = -1  # type: ignore[assignment, misc]

  NONE = 0


def parse_address(address_url):
  if address_url is None:
    raise ValueError("Cannot parse address_url of: None")
  secure = False
  messaging_protocol = None
  address_family = None
  connection_args = None
  parsed = urllib.parse.urlparse(address_url)
  scheme, *subscheme = parsed.scheme.split("+")
  if scheme in ("ws", "wss"):
    messaging_protocol = MessagingProtocol.WEB_SOCKET
    if subscheme:
      if subscheme == ["unix"]:
        address_family = AddressFamily.UNIX
      elif subscheme == ["bt"]:
        address_family = AddressFamily.PACKET
      else:
        raise ValueError("Unrecognized scheme: %s for url %s" % (parsed.scheme, address_url))
    else:
      address_family = AddressFamily.INET

    secure = bool(scheme == "wss")
  elif scheme in ("tcp", "unix", "bt"):
    messaging_protocol = MessagingProtocol.NEWLINE_DELIMITED_MESSAGE
    if subscheme:
      if subscheme == ["tls"]:
        secure = True
      else:
        raise ValueError("Unrecognized scheme: %s for url %s" % (parsed.scheme, address_url))

    address_family = {
        "unix": AddressFamily.UNIX,
        "tcp": AddressFamily.INET,
        "bt": AddressFamily.PACKET,
    }[scheme]
  elif scheme in ("http", "https"):
    messaging_protocol = MessagingProtocol.HTTP
    address_family = AddressFamily.INET
    secure = scheme == "https"
  elif scheme == "local":
    messaging_protocol = MessagingProtocol.PROCESS_LOCAL
    address_family = AddressFamily.NONE
    secure = False
  elif scheme == "json":
    messaging_protocol = MessagingProtocol.JSON_RPC
    address_family = AddressFamily.INET
    if subscheme:
      if subscheme == ["tls"]:
        secure = True
      else:
        raise ValueError("Unrecognized scheme: %s for url %s" % (parsed.scheme, address_url))
  else:
    raise ValueError("Unrecognized scheme: %s for url %s" % (parsed.scheme, address_url))

  if parsed.netloc.startswith("="):
    my_socket = socket.fromfd(int(parsed.netloc[1:]), address_family, socket.SOCK_STREAM)
    connection_args = dict(sock=my_socket)
  elif address_family in (AddressFamily.INET, AddressFamily.PACKET):
    connection_args = dict(host=parsed.hostname or "", port=parsed.port)
    if parsed.path:
      connection_args["path"] = parsed.path
    if parsed.username:
      connection_args["user"] = parsed.username
    if parsed.password:
      connection_args["password"] = parsed.password
  elif address_family == AddressFamily.UNIX:
    connection_args = dict(path=urllib.parse.unquote(parsed.netloc))
  else:
    connection_args = {}

  return messaging_protocol, address_family, connection_args, secure


def format_address(host=None,
                   port=None,
                   path=None,
                   messaging_protocol=MessagingProtocol.NEWLINE_DELIMITED_MESSAGE,
                   address_family=AddressFamily.INET,
                   secure=False,
                   user=None,
                   password=None,
                   fd=None):
  if messaging_protocol == MessagingProtocol.NEWLINE_DELIMITED_MESSAGE:
    scheme = {
        AddressFamily.UNIX: "unix",
        AddressFamily.INET: "tcp",
        AddressFamily.PACKET: "bt",
    }[address_family]
    if secure:
      scheme += "+tls"
  elif messaging_protocol == MessagingProtocol.WEB_SOCKET:
    scheme = "ws"
    if secure:
      scheme += "s"
    if address_family == AddressFamily.UNIX:
      scheme += "+unix"
    if address_family == AddressFamily.PACKET:
      scheme += "+bt"
  elif messaging_protocol == MessagingProtocol.HTTP:
    scheme = "http"
    if secure:
      scheme += "s"
  elif messaging_protocol == MessagingProtocol.PROCESS_LOCAL:
    scheme = "local"
  elif messaging_protocol == MessagingProtocol.JSON_RPC:
    scheme = "json"
    if secure:
      scheme += "+tls"
  else:
    raise ValueError("Invalid protocol")

  if address_family == AddressFamily.INET:
    if not (host and port) and fd is None:
      raise ValueError("Either Host and port or fd must be specified for inet address")
    if host and port:
      netloc = "%s:%s" % (host, port)
    elif fd:
      netloc = "={}".format(fd)
    if path:
      netloc = "%s/%s" % (netloc, urllib.parse.quote(path, safe=""))
  elif address_family == AddressFamily.UNIX:
    if not path:
      raise ValueError("Path must be specified for Unix address")
    netloc = urllib.parse.quote(path, safe="")
  elif address_family == AddressFamily.PACKET:
    if not (host is not None and port):
      raise ValueError("Host and port must be specified for bluetooth packet address")
    netloc = "%s:%s" % (("[%s]" % host if host else ""), port)
  elif address_family == AddressFamily.NONE:
    netloc = ""
  else:
    raise ValueError("Invalid address family")

  if not user and password:
    raise ValueError("Cannot specify a password without a user")
  user_credentials = "{user}{divider}{password}{specifier}".format(
      user=(user or ""),
      password=(password or ""),
      divider=(":" if password else ""),
      specifier=("@" if user else ""),
  )

  return "%s://%s%s" % (scheme, user_credentials, netloc)


def _get_ip_addresses_for_family(family, allow_link_local=False):
  if allow_link_local:
    # Never want to include loopback
    interfaces = [iface for iface in netifaces.interfaces() if not iface.startswith("lo")]
  else:
    gateways = netifaces.gateways().get(family, [])
    interfaces = [g[1] for g in gateways]
  return _get_ip_addresses_for_interfaces_and_family(interfaces, family)


def _get_ip_addresses_for_interfaces_and_family(interfaces, family):
  interface_addrs = [netifaces.ifaddresses(i) for i in interfaces]
  ip_addrs = set(
      addr_info['addr']
      for addrs_by_family in interface_addrs
      for addr_info in addrs_by_family.get(family, [])
  )
  return ip_addrs


def get_ipv4_address(allow_link_local=False):
  '''Tries to pick the best ip of all the ones'''
  ipv4_addrs = _get_ip_addresses_for_family(netifaces.AF_INET, allow_link_local=allow_link_local)
  ipv4_addrs = [addr for addr in ipv4_addrs if not addr.startswith('127.0')]

  if len(ipv4_addrs) > 1:
    # Make an arbitrary (but consistent) choice
    ipv4_addrs.sort()
    log.info("Multiple ips available: %r, picking: %r", ipv4_addrs, ipv4_addrs[0])
  if ipv4_addrs:
    return ipv4_addrs[0]
  return None


def get_ipv4_address_for_tether():
  if 'tether' in netifaces.interfaces():
    ipv4_addrs = _get_ip_addresses_for_interfaces_and_family(['tether'], netifaces.AF_INET)
    if ipv4_addrs:
      has_multiple_addrs = len(ipv4_addrs) > 1
      chosen_ip_addr = ipv4_addrs.pop()
      if has_multiple_addrs:
        log.info("Multiple tether ips available: %r, picking: %r", ipv4_addrs, chosen_ip_addr)
      return chosen_ip_addr
  return None


def get_ipv6_address():
  # Filter out link-local/private IPv6 addresses
  ipv6_addrs = [
      addr
      for addr in _get_ip_addresses_for_family(netifaces.AF_INET6)
      if ipaddress.ip_address(addr.split('%')[0]).is_global
  ]
  # It's not uncommon to have multiple IPv6 addresses
  if ipv6_addrs:
    return sorted(ipv6_addrs).pop()

  return None


def get_link_local_ipv6_addresses(strip_scope_id=True):
  ipv6_addrs = [
      addr.split('%')[0] if strip_scope_id else addr
      for addr in _get_ip_addresses_for_family(netifaces.AF_INET6, allow_link_local=True)
      if ipaddress.ip_address(addr.split('%')[0]).is_link_local
  ]
  # Sort for consistency in return value
  return sorted(ipv6_addrs)


def get_device_cert_dir():
  return FLAGS.cert_dir


def get_device_cert_files(directory_override=None):
  cert_dir = directory_override or get_device_cert_dir()
  key_file = "%s/device.key" % (cert_dir)
  csr_file = "%s/device.csr" % (cert_dir)
  cert_file = "%s/device.cert" % (cert_dir)
  return key_file, csr_file, cert_file


def format_headers(headers):
  if headers is None:
    return None
  formatted_headers = {}
  for k, v in headers.items():
    formatted_key = APP_DESIGNATION + k
    formatted_headers[formatted_key] = v
  return formatted_headers


def get_ssl_context(purpose, check_hostname=True, cert_file_directory=None, load_cert_chain=True):
  ssl_context = None
  with importlib.resources.path("lib.certs", "brilliant_ca_bundle.crt") as path:
    brilliant_ca_file = str(path)
    ca_file = None
    if purpose == ssl.Purpose.SERVER_AUTH:
      # If we want to check the hostname, this means we are connecting via DNS and thus can use
      # certifi to verify the server's presented certificate. Otherwise, we are most likely
      # connecting to another device, in which cause we should verify against the brilliant CA
      # bundle, with the system-loaded certs as backup.
      if check_hostname:
        ca_file = CERTIFI_CA_FILE
      else:
        ca_file = brilliant_ca_file
    elif purpose == ssl.Purpose.CLIENT_AUTH:
      ca_file = brilliant_ca_file
    ssl_context = ssl.create_default_context(
        purpose=purpose,
        cafile=ca_file,
    )

  if load_cert_chain:
    key_file, _, cert_file = get_device_cert_files(directory_override=cert_file_directory)
    ssl_context.load_cert_chain(cert_file, key_file)
  if purpose == ssl.Purpose.CLIENT_AUTH:
    # TODO: Change to CERT_REQUIRED once authentication is implemented on all connecting devices
    ssl_context.verify_mode = ssl.CERT_OPTIONAL
  elif purpose == ssl.Purpose.SERVER_AUTH:
    # check_hostname only applies for server auth
    ssl_context.check_hostname = check_hostname
  return ssl_context


def validate_client_certificate(peer_cert, headers):
  client_cn = get_client_common_name(peer_cert, headers)
  if not client_cn:
    log.error("Error: Did not receive peer cert for client!")
    return False

  return verify_common_name_against_header_ids(client_cn, headers)


def get_client_common_name(peer_cert, headers):
  client_cn = None
  if peer_cert:
    # The server is a peer device
    client_cn = get_common_name_from_peer_cert(peer_cert)
  else:
    # The server is the cloud - peer cert should be in headers under client-cert-subj
    client_cn = get_common_name_from_headers(headers)

  return client_cn


def get_common_name_from_peer_cert(peer_cert):
  for rdn in peer_cert["subject"]:
    for field in rdn:
      if field[0] == "commonName":
        return field[1]
  return None


def get_common_name_from_headers(headers):
  peer_cert_subj = headers.get(APP_DESIGNATION + "client-cert-subj", None)
  if peer_cert_subj is None:
    return None
  for kv_pair in peer_cert_subj.split("/"):
    kv = kv_pair.split("=")
    if kv[0] == "CN":
      return kv[1]
  return None


def get_certificate_from_headers(headers):
  peer_cert_pem_with_tabs = headers.get(APP_DESIGNATION + "client-cert-pem")
  if not peer_cert_pem_with_tabs:
    return None

  # nginx will replace newlines with tabs
  peer_cert_pem = peer_cert_pem_with_tabs.strip().replace("\t", "\n")
  return ssl.PEM_cert_to_DER_cert(peer_cert_pem)


def get_certificate_fingerprint(certificate_der, digest_func=hashlib.sha256):
  cert_digest = digest_func(certificate_der).digest()
  return base64.b64encode(cert_digest).decode()


def get_my_certificate_fingerprint(cert_file_directory=None):
  cert_file_path = get_device_cert_files(directory_override=cert_file_directory)[2]
  with open(cert_file_path, 'r', encoding="utf-8") as cert_file:
    pem_data = cert_file.read()

  der_cert = ssl.PEM_cert_to_DER_cert(pem_data)
  return get_certificate_fingerprint(der_cert)


def verify_common_name_against_header_ids(common_name, headers):
  device_id = headers.get(APP_DESIGNATION + "device-id", None)
  home_id = headers.get(APP_DESIGNATION + "home-id", None)
  cert_ids = common_name.split(":")
  log.info("Validating ids %s %s against common name %s", home_id, device_id, common_name)
  if cert_ids[0] != device_id:
    log.error("Error validating common name for device %s in home %s: Device ID mismatch",
              device_id, home_id)
    return False
  if cert_ids[1] != home_id:
    log.error("Error validating common name for device %s in home %s: Home ID mismatch",
              device_id, home_id)
    return False
  log.info("Connection validated")
  return True


def is_ip_address(maybe_ip_address):
  try:
    parsed_ip = ipaddress.ip_address(maybe_ip_address)
    return bool(parsed_ip)
  except ValueError:
    return False


def normalize_mac_address(mac_address):
  # Chaining replace() is a bit ugly but it's simple and fast
  base_hex = mac_address.replace(":", "").replace("-", "").replace(".", "").upper()
  if len(base_hex) != 12:
    raise ValueError("Invalid MAC address: {}".format(mac_address))

  try:
    int(base_hex, 16)
  except ValueError as e:
    raise ValueError("Invalid MAC address: {}".format(mac_address)) from e

  return ":".join(base_hex[i:i + 2] for i in range(0, len(base_hex), 2))


def get_ssl_context_for_host(address_family, host, cert_file_directory=None):
  have_symbolic_hostname = (
      address_family == AddressFamily.INET and
      host and
      host != "localhost" and
      not is_ip_address(host)
  )
  ssl_context = get_ssl_context(
      purpose=ssl.Purpose.SERVER_AUTH,
      check_hostname=have_symbolic_hostname,
      cert_file_directory=cert_file_directory,
  )
  return ssl_context


async def create_connection(address_family,
                            protocol_factory,
                            loop,
                            secure=False,
                            timeout=None,
                            cert_file_directory=None,
                            ssl_context=None,
                            **kwargs):
  if secure and ssl_context is None:
    ssl_context = get_ssl_context_for_host(
        address_family=address_family,
        host=kwargs.get('host'),
        cert_file_directory=cert_file_directory,
    )

  create_connection_func = {
      AddressFamily.UNIX: loop.create_unix_connection,
      AddressFamily.INET: loop.create_connection,
      AddressFamily.PACKET: functools.partial(
          bluetooth_socket.create_connection,
          loop=loop,
      ),
  }[address_family]

  transport, protocol = await asyncio.wait_for(
      fut=create_connection_func(
          protocol_factory=protocol_factory,
          ssl=ssl_context,
          **kwargs
      ),
      timeout=timeout,  # Waits indefinitely if None
  )
  return transport, protocol


async def create_server(address_family, protocol_factory, loop, secure=False, **kwargs):
  ssl_context = get_ssl_context(purpose=ssl.Purpose.CLIENT_AUTH) if secure else None
  create_server_func = {
      AddressFamily.UNIX: loop.create_unix_server,
      AddressFamily.INET: loop.create_server,
      AddressFamily.PACKET: functools.partial(
          bluetooth_socket.create_server,
          loop=loop,
      ),
  }[address_family]

  if address_family == AddressFamily.UNIX and os.path.exists(kwargs["path"]):
    os.unlink(kwargs["path"])

  if address_family != AddressFamily.INET and "reuse_port" in kwargs:
    kwargs.pop("reuse_port")

  server = await create_server_func(
      protocol_factory=protocol_factory,
      ssl=ssl_context,
      **kwargs
  )

  if address_family == AddressFamily.UNIX:
    os.chmod(kwargs["path"], 0o777)

  return server


async def open_stream(loop, addr_family, timeout, read_limit=2**20, secure=False, **kwargs):
  reader = asyncio.StreamReader(limit=read_limit, loop=loop)
  reader_protocol = asyncio.StreamReaderProtocol(reader, loop=loop)

  transport, _ = await create_connection(
      address_family=addr_family,
      protocol_factory=lambda: reader_protocol,
      loop=loop,
      secure=secure,
      timeout=timeout,
      **kwargs,
  )
  writer = asyncio.StreamWriter(transport, reader_protocol, reader, loop=loop)
  return (reader, writer)
