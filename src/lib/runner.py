import asyncio
import functools
import logging
import logging.handlers
import os
import signal
import sys
import types
import typing

import gflags
from thrift.protocol import fastbinary

# We need lib.process_manager.process_manager for the gflags.
from lib import utils
from lib.error_logging import chunked_file_sentry_client
import lib.process_management.process_manager  # pylint: disable=unused-import
from lib.process_management.vassal import Vassal
from lib.startables import startable_configs
from lib.tools import async_inspect
from lib.tools import tracer


uvloop: typing.Optional[types.ModuleType]

try:
  import uvloop
except AttributeError:
  import warnings
  warnings.warn("Error importing uvloop. Your Python/uvloop version combo might be incompatible")
  uvloop = None
except ImportError:
  uvloop = None

log = logging.getLogger(__name__)

_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

log = logging.getLogger(__name__)

_validation_modes = {
    "none": fastbinary.NO_VALIDATION,
    "loose": fastbinary.LOOSE_VALIDATION,
    "strict": fastbinary.STRICT_VALIDATION,
}


gflags.DEFINE_string(
    "log_level",
    "INFO",
    "Logging level threshold",
)
gflags.RegisterValidator(
    "log_level",
    lambda val: val in _log_levels,
    message="--log_level must be one of %s" % ",".join(_log_levels),
)

gflags.DEFINE_boolean(
    "asyncio_debug",
    False,
    "Enable debugging for asyncio event loop",
)
gflags.DEFINE_boolean(
    "enable_uvloop",
    True,
    "Use the uvloop implementation of the event loop",
)

gflags.DEFINE_boolean(
    "enable_tracing",
    False,
    "Enable trace logs for performance profiling",
)

gflags.DEFINE_boolean(
    "enable_uwsgi_heartbeat",
    True,
    "Periodically send heartbeats to the uWSGI emperor? "
    "It can potentially discover and terminate stuck processes. "
    "Only meaningful when running under uWSGI.",
)

gflags.DEFINE_string(
    "error_log_storage_dir",
    "/tmp/errors",
    "Directory in which to write serialized Sentry error logs.",
)

gflags.DEFINE_float(
    "error_log_sample_rate",
    0.,
    "Sampling rate to apply to Sentry error logging.",
)

gflags.DEFINE_string(
    "thrift_serialization_validation_mode",
    "loose",
    "Validation mode to use when serializing Thrift objects.",
)
gflags.RegisterValidator(
    "thrift_serialization_validation_mode",
    lambda val: val.lower() in _validation_modes,
    message="--thrift_serialization_validation_mode must be one of {}".format(
        ", ".join(_validation_modes.keys()),
    ),
)

gflags.DEFINE_string(
    "log_output_directory",
    None,
    "Directory to which to write log files, e.g. /var/log/brilliant. "
    "Logging to files is disabled if unspecified.",
)


FLAGS = gflags.FLAGS

STOP_REQUESTED = False


def get_log_output_directory():
  return FLAGS.log_output_directory


def _setup_signals(event_loop, unit_name):
  for signo in (signal.SIGINT, signal.SIGTERM):
    event_loop.add_signal_handler(signo, _request_stop)
  if FLAGS.enable_tracing:
    event_loop.add_signal_handler(signal.SIGUSR1, tracer.reset_global_trace)
    event_loop.add_signal_handler(signal.SIGUSR2, tracer.write_global_trace, unit_name)


def _request_stop():
  global STOP_REQUESTED  # pylint: disable=global-statement
  if not STOP_REQUESTED:
    asyncio.get_event_loop().stop()
    STOP_REQUESTED = True


def _get_unit_name(main_module_override):
  if main_module_override:
    unqualified_module_name = main_module_override.rsplit(".", 1)[-1]
  else:
    unqualified_module_name = os.path.splitext(os.path.basename(sys.argv[0]))[0]

  return unqualified_module_name


def _setup_logging(level_name, unit_name):
  log_format_str = f"%(asctime)-15s %(process)d {unit_name} %(filename)s:%(lineno)d %(levelname).1s %(message)s"

  sys.stderr.reconfigure(encoding="utf-8")
  logging.basicConfig(
      level=getattr(logging, level_name),
      format=log_format_str,
  )

  if FLAGS.log_output_directory:
    # If the `log_output_directory` flag was specified then we need to make sure that that directory
    # exists and is writable by the current user, because the `TimedRotatingFileHandler` will raise
    # a `FileNotFoundError` otherwise.
    if not (
        os.path.isdir(FLAGS.log_output_directory)
        and os.access(FLAGS.log_output_directory, os.W_OK)
    ):
      raise ValueError(
          f"Log output directory '{FLAGS.log_output_directory}' does not exist or is not writable "
          "by the current user. Logs will not be written to files."
      )
    # The `TimedRotatingFileHandler` will save old log files by appending extensions to the filename.
    # The extensions are date-and-time based, using the strftime format `%Y-%m-%d_%H-%M-%S` or a
    # leading portion thereof, depending on the rollover interval. In our case, the rollover interval
    # is 1 hour, so the extension will be the hour of the day. This means that the log files will be
    # rotated every hour, and the old log files will be saved with the extension `%Y-%m-%d_%H`.
    # Hence we don't need to explicitly add any timestamp to the log file name.
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=f"{FLAGS.log_output_directory}/{unit_name}.log",
        when="h",
        interval=1,
        backupCount=3,
    )
    file_handler.setFormatter(logging.Formatter(log_format_str))

    logging.getLogger().addHandler(file_handler)


def _setup_error_capture_logger(loop, unit_name):
  # Don't bother setting up the logger if we don't want to sample.
  if FLAGS.error_log_sample_rate == 0:
    log.info("Error log sample rate set to 0, not setting up error logger")
    return None

  error_logger = chunked_file_sentry_client.ChunkedFileSentryClient(
      loop=loop,
      storage_dir=FLAGS.error_log_storage_dir,
      sample_rate=FLAGS.error_log_sample_rate,
      unit_name=unit_name,
      software_version=utils.get_release_tag(utils.get_release_info_filepath()) or "<unknown>",
      environment=utils.get_sentry_environment(utils.get_tracking_branch_filepath()) or "<unknown>",
  )
  try:
    loop.run_until_complete(error_logger.start())
    return error_logger
  except Exception:
    log.exception("Failed to start logging client!")

  return None


def get_error_log_storage_dir():
  return FLAGS.error_log_storage_dir


def get_error_log_sample_rate():
  return FLAGS.error_log_sample_rate


def _get_args(startable_config):
  args = {}
  for param in startable_config.startable_parameters:
    args[param.param_key] = gflags.FLAGS.get(param.gflag_name, None)
  return args


def run_as_main(startable_config, module_name_override=None):
  startable_configs.define_gflags(startable_config)
  FLAGS(sys.argv)
  kwargs = _get_args(startable_config)
  startable_class = startable_config.get_startable_class(all_defined_parameters=gflags.FLAGS)
  run(functools.partial(startable_class, **kwargs),
      module_name_override=module_name_override)


def run(StartableFactory, module_name_override=None):
  '''This function should be used for starting all processes that are event loop based. It
     - Handles sigterm
     - Sets up logging
     - Creates and runs the eventloop
    It takes a single argument: A StartableFactory. The startable factory must create an instance
    of an object that has methods start() and shutdown() that are called with no arguments. The
    StartableFactory will be called with a single argument: the event loop, so any other arguments
    must be curried'''
  # TODO: Remove the run function once we migrate everything over to inherit from Startable
  FLAGS(sys.argv)

  unit_name = _get_unit_name(main_module_override=module_name_override)
  _setup_logging(level_name=FLAGS.log_level, unit_name=unit_name)

  validation_mode = _validation_modes[FLAGS.thrift_serialization_validation_mode.lower()]
  fastbinary.set_validation_mode(validation_mode)

  if FLAGS.enable_uvloop:
    if uvloop:
      asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    else:
      log.error("uvloop was requested but is not available!")

  event_loop = asyncio.get_event_loop()
  event_loop.set_debug(FLAGS.asyncio_debug)
  event_loop.set_exception_handler(async_inspect.exception_handler)
  async_inspect.patch_format_coroutine()

  _setup_signals(event_loop, unit_name)
  error_capture_logger = _setup_error_capture_logger(loop=event_loop, unit_name=unit_name)

  startable_object = StartableFactory(loop=event_loop)
  uwsgi_emperor_fd_var = os.environ.get('UWSGI_EMPEROR_FD')
  if uwsgi_emperor_fd_var:
    startable_object = Vassal(startable_object=startable_object,
                              emperor_fd=int(uwsgi_emperor_fd_var),
                              loop=event_loop,
                              request_stop_callback=_request_stop,
                              enable_heartbeat=FLAGS.enable_uwsgi_heartbeat)

  _run(event_loop, startable_object)

  if error_capture_logger:
    event_loop.run_until_complete(error_capture_logger.shutdown())

  tracer.write_traces(unit_name)
  event_loop.close()


def _run(event_loop, startable_object):
  start_task = event_loop.create_task(startable_object.start())
  try:
    event_loop.run_until_complete(start_task)
    event_loop.run_forever()
  except KeyboardInterrupt:
    logging.info("Shutting Down")
  finally:
    if not start_task.done():
      start_task.cancel()
    event_loop.run_until_complete(startable_object.shutdown())
