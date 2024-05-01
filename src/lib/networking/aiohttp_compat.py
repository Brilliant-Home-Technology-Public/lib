import aiohttp


if aiohttp.__version__ >= '3.9.0':
  raise ImportError("aiohttp version {} is not known to be compatible".format(aiohttp.__version__))


class FingerprintCheckingTCPConnector(aiohttp.TCPConnector):

  def __init__(self, *, fingerprint=None, ssl_context=None, **kwargs):
    # aiohttp v3 does not allow you to specify both of these parameters simultaneously
    if aiohttp.__version__ >= '3':
      super().__init__(ssl=ssl_context, **kwargs)
      self.__fingerprint = aiohttp.Fingerprint(fingerprint) if fingerprint else None
    else:
      super().__init__(ssl_context=ssl_context, fingerprint=fingerprint, **kwargs)
      self.__fingerprint = None

  def _get_fingerprint(self, *args, **kwargs):
    fingerprint = super()._get_fingerprint(*args, **kwargs)
    if fingerprint:
      return fingerprint

    return self.__fingerprint
