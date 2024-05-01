import datetime
import logging
import os

import sentry_sdk

from lib.error_logging import chunked_file_sentry_transport
import lib.time


class ChunkedFileSentryClient:

  def __init__(self,
               loop,
               storage_dir,
               sample_rate,
               unit_name,
               software_version,
               configure_logger=True,
               **client_kwargs):
    self._loop = loop
    self._unit_name = unit_name
    self._configure_logger = configure_logger
    self._transport = chunked_file_sentry_transport.ChunkedJSONFileSentryTransport(
        loop=loop,
        unit_name=unit_name,
        storage_dir=os.path.join(storage_dir, unit_name),
    )
    self._client = None
    self._init_args = dict(
        transport=self._transport.async_send,
        sample_rate=sample_rate,
        release=software_version,
        max_breadcrumbs=0,
        **client_kwargs
    )

  async def start(self):
    await self._transport.start()
    if self._configure_logger:
      sentry_sdk.init(**self._init_args)
      self._client = sentry_sdk.Hub.current.client
    else:
      self._client = sentry_sdk.Client(
          default_integrations=False,  # Disallow logging integration and other built-ins
          **self._init_args
      )

  async def shutdown(self):
    await self._transport.shutdown()

  def _get_level_name(self, levelno):
    if levelno > logging.ERROR:
      return "fatal"

    if levelno < logging.DEBUG:
      return None

    return logging._levelToName.get(levelno, "ERROR").lower()

  def report_message(
      self,
      message,
      levelno,
      *,
      format_string=None,
      format_parameters=None,
      timestamp=None,
      extra=None,
      **data_kwargs
  ):
    if timestamp is None:
      timestamp = lib.time.get_current_time_ms()

    timestamp_dt = datetime.datetime.utcfromtimestamp(timestamp // 1000)
    self._client.capture_event(
        event=dict(
            message=dict(
                formatted=message,
                message=format_string or message,
                params=format_parameters or (),
            ),
            extra=extra or {},
            timestamp=timestamp_dt,
            level=self._get_level_name(levelno),
            logger=self._unit_name,
            **data_kwargs
        ),
    )
