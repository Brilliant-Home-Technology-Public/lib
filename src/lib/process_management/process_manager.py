import asyncio
import configparser
import grp
import logging
import os
import pwd
import sys
import tempfile

import gflags


gflags.DEFINE_string("process_configs_dir", "/tmp/processes",
                     "Directory where the INI config files will be added for each process")

FLAGS = gflags.FLAGS

log = logging.getLogger(__name__)


class ProcessManager:

  def __init__(self, configs_dir=None, unprivileged_user=None):
    # The directory the emperor is monitoring
    self.configs_dir = configs_dir or FLAGS.process_configs_dir
    self.unprivileged_user = unprivileged_user

  def add_process(
      self,
      process_name,
      process_module,
      process_flagfile=None,
      additional_flags=None,
      process_priority=None,
      run_as_privileged_user=False,
      supplemental_groups=None,
  ):
    '''
    Constructs a .ini file and adds it to the configs dir monitored by the Emperor

    process_priority: nice value int:[-20, 19] -20 is highest priority, 19 is lowest priority
    '''
    # If the peripheral is already running, don't add it again
    config_file_path = self._get_file_path(process_name)
    if os.path.isfile(config_file_path):
      return
    config = configparser.ConfigParser()
    config['uwsgi'] = {
        'startable_module': process_module,
    }
    if process_flagfile:
      config['uwsgi']['flagfile'] = process_flagfile
    config['uwsgi']['additionalflags'] = self._format_addition_flags(
        additional_flags
    ) if additional_flags else ""

    if process_priority is not None:
      config['uwsgi']['prio'] = str(process_priority)

    if not run_as_privileged_user and self.unprivileged_user:
      group_override = None
      if supplemental_groups:
        # TODO support multiple supplemental groups. Doesn't seem to be possible for now with the
        # way we're launching processes with uWSGI.
        if len(supplemental_groups) > 1:
          raise ValueError("Cannot specify more than one supplemental group!")

        group_name = supplemental_groups[0]
        try:
          grp_entry = grp.getgrnam(group_name)
          group_override = str(grp_entry.gr_gid)
        except KeyError:
          log.error("Can't run %s with non-existent group %s", process_name, group_name)

      try:
        pwd_entry = pwd.getpwnam(self.unprivileged_user)
        config['uwsgi']['user_override'] = str(pwd_entry.pw_uid)
        config['uwsgi']['group_override'] = group_override or str(pwd_entry.pw_gid)
      except KeyError:
        log.error("Can't run %s as non-existent user %s", process_name, self.unprivileged_user)

    temp_file_path = None
    try:
      with tempfile.NamedTemporaryFile(mode='w', delete=False) as config_file:
        temp_file_path = config_file.name
        config.write(config_file)

      # 0o644 = readable/writable by user, readable by group + other
      os.chmod(temp_file_path, 0o644)
      # Now move the tmp file
      os.rename(temp_file_path, config_file_path)
    finally:
      if temp_file_path and os.path.exists(temp_file_path):
        os.unlink(temp_file_path)

  def remove_process(self, process_name):
    '''
    Removes the associated process .ini file in the configs dir monitored by the Emperor
    '''
    if os.path.isfile(self._get_file_path(process_name)):
      os.remove(self._get_file_path(process_name))

  async def restart_process(self, process_name):
    '''
    Restarts the process by modifying (touch) the associated .ini file in the configs dir monitored
    by the Emperor
    '''
    file_path = self._get_file_path(process_name)
    if os.path.isfile(file_path):
      before_stat = os.stat(file_path)
      while True:
        os.utime(file_path)
        after_stat = os.stat(file_path)
        if before_stat.st_mtime == after_stat.st_mtime:
          await asyncio.sleep(1)
        else:
          return

  def _get_file_path(self, process_name):
    return os.path.join(self.configs_dir, process_name + ".ini")

  def _format_addition_flags(self, additional_flags):
    return " ".join(["--%s=%s" % (key, value) for key, value in additional_flags.items()])


if __name__ == '__main__':
  # argv[0] = process_name
  # argv[1] = process_module
  # argv[2] = process_flagfile (optional)
  # argv[3] = process_configs_dir (optional)
  name = sys.argv[1]
  module = sys.argv[2]
  flagfile = sys.argv[3] if len(sys.argv) > 3 else None
  configs_directory = sys.argv[4] if len(sys.argv) > 4 else "/tmp/processes"
  manager = ProcessManager(configs_directory)
  manager.add_process(
      process_name=name,
      process_module=module,
      process_flagfile=flagfile,
  )
