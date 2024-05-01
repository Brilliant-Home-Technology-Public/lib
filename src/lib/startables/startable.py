from abc import ABCMeta
from abc import abstractmethod
import ast
import asyncio
import configparser
import importlib
import logging

from lib import exceptions
from lib.queueing import work_queue


log = logging.getLogger(__name__)


class Startable(metaclass=ABCMeta):

  def __init__(self, startable_id):
    self.startable_id = startable_id

  @abstractmethod
  async def start(self):
    pass

  @abstractmethod
  async def shutdown(self):
    pass


class HostedStartableSpec:

  def __init__(self, startable_id, startable_config, parameter_overrides):
    self.startable_id = startable_id
    self.startable_config = startable_config
    self.parameter_overrides = parameter_overrides

  # Hack for backwards compatibility: support for tuple unpacking
  def __iter__(self):
    return iter((self.startable_config, self.parameter_overrides))


class StartableHost(Startable):

  def __init__(self, startable_id, startable_host_config_path=None, startables_to_host=None):
    '''
    startable_host_config_path: path to the ini file specifying the startables to host
    startables_to_host: list of HostedStartableSpec objects)
    '''
    if not startable_id:
      raise ValueError("startable_id is required for StartableHost!")
    if startable_host_config_path and startables_to_host is not None:
      raise exceptions.BadArgsError(
          "Only one of startable_host_config_path or startables_to_host can be specified"
      )
    super().__init__(startable_id)
    self.startable_host_config_path = startable_host_config_path
    self.startables_to_host = (
        startables_to_host
        if startables_to_host is not None
        else self._get_startables_to_host()
    )

  async def reload(self):
    if self.startable_host_config_path:
      self.startables_to_host = self._get_startables_to_host()

  # Imports the associated modules to get their relevant peripheral configs
  def _get_startables_to_host(self):
    # Disable interpolation to match initial configs in startable_configs.generate_startable_host_ini
    config = configparser.ConfigParser(interpolation=None)
    config.read(self.startable_host_config_path)
    startables_to_host = []
    startable_ids = config.sections()
    for startable_id in startable_ids:
      parameters = dict(config[startable_id])
      module_path = parameters.pop("module_path", None)
      if not module_path:
        log.error("No module path specified for startable %s", startable_id)
        continue
      module = importlib.import_module(module_path)
      startables_to_host.append(
          HostedStartableSpec(
              startable_id=startable_id,
              startable_config=module.__startable_config__,
              parameter_overrides=parameters,
          ),
      )
    return startables_to_host

  def _get_params(self, valid_parameters, override_params):
    valid_params = {param.param_key for param in valid_parameters}
    required_params = {
        param.param_key for param in valid_parameters
        if not param.has_default()
    }
    specified_params = set(override_params.keys())
    missing_params = required_params - specified_params
    # Check required params (i.e. no default) are specified
    if missing_params:
      raise exceptions.BadArgsError("Missing required parameters:", missing_params)
    # Check that the specified override params are valid
    if not specified_params.issubset(valid_params):
      raise exceptions.BadArgsError("Invalid parameters:", specified_params - valid_params)

    params = {}
    for param in valid_parameters:
      value_to_decode = (
          param.default_value
          if param.param_key not in override_params
          else override_params[param.param_key]
      )
      value = self._decode_value(param.param_type, value_to_decode)
      params[param.param_key] = value
    return params

  def _decode_value(self, param_type, value_to_decode):
    if value_to_decode is None:
      return value_to_decode
    if isinstance(value_to_decode, param_type):
      return value_to_decode
    return param_type(ast.literal_eval(value_to_decode))


class SubordinateStartableStartStopTaskManager:

  def __init__(self, startable_object, loop):
    self.loop = loop
    self.startable_object = startable_object
    self.queue = work_queue.ExponentialBackoffWorkQueue(
        loop=self.loop,
        num_workers=1,
        process_job_func=self._manage_startable,
    )
    self.start_job = None

  async def start(self):
    await self.initiate_start()

  async def shutdown(self):
    await self.initiate_shutdown()
    self.queue.shutdown()

  def initiate_start(self):
    self.queue.start()
    self.start_job = self.queue.add_job(True)
    return self.start_job

  def initiate_shutdown(self):
    if self.start_job and not self.start_job.done():
      self.start_job.cancel()
    self.start_job = None
    stop_job = self.queue.add_job(False)
    return stop_job

  def is_active(self):
    return self.start_job is not None

  async def _manage_startable(self, should_start):
    if should_start:
      try:
        await self.startable_object.start()
      except asyncio.CancelledError:  # pylint: disable=try-except-raise
        raise
      except Exception:
        await self.startable_object.shutdown()
        raise
    else:
      try:
        await self.startable_object.shutdown()
      except asyncio.CancelledError:  # pylint: disable=try-except-raise
        raise
      except Exception:
        log.exception("Startable object %r failed to shut down!", self.startable_object)


class SubordinateStartableHost(StartableHost):

  def __init__(self, startable_id, startable_host_config_path, loop, parameter_overrides=None):
    super().__init__(
        startable_id=startable_id,
        startable_host_config_path=startable_host_config_path,
    )
    self.loop = loop
    self.active_startables_by_id = {}
    self.startables_to_host_by_id = {
        spec.startable_id: spec for spec in self.startables_to_host
    }
    self.parameter_overrides = parameter_overrides or {}

  async def start(self):
    pass

  async def shutdown(self):
    shutdown_jobs = [
        manager.shutdown() for manager in self.active_startables_by_id.values()
    ]
    self.active_startables_by_id.clear()
    await asyncio.gather(*shutdown_jobs, return_exceptions=True)

  def start_startable(self, startable_id):
    spec = self.startables_to_host_by_id[startable_id]
    existing = self.active_startables_by_id.get(startable_id)
    if existing and existing.is_running():
      raise KeyError("Startable %s is already running!" % startable_id)

    overrides = dict(spec.parameter_overrides)  # Make a fresh copy so we don't mutate shared state
    overrides.update(self.parameter_overrides)
    startable_object = spec.startable_config.startable_class(
        loop=self.loop,
        **self._get_params(spec.startable_config.parameters, overrides)
    )
    start_stop_task_manager = SubordinateStartableStartStopTaskManager(
        startable_object=startable_object,
        loop=self.loop,
    )
    self.active_startables_by_id[startable_id] = start_stop_task_manager
    start_job = start_stop_task_manager.initiate_start()
    return start_job

  def stop_startable(self, startable_id):
    # TODO garbage collect these somehow?
    start_stop_task_manager = self.active_startables_by_id.pop(startable_id)
    stop_job = start_stop_task_manager.initiate_shutdown()
    return stop_job
