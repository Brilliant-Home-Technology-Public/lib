import gc
import importlib
import sys

import lib.runner


try:
  import uwsgi  # Only present when running within uwsgi
except ImportError:
  uwsgi = None


uwsgi_main_module = None
if uwsgi:
  uwsgi_main_module = uwsgi.opt.get("module", b'').decode().split(":")[0]


def main():
  module_names = [m for m in sys.argv[1:] if not m.startswith("--")]
  if len(module_names) != 1 or sys.argv[-1].startswith("--"):
    print("Usage: python -m {} [--flag=value] mod_name".format(sys.argv[0]), file=sys.stderr)
    print("       Note: Flags must PRECEDE the module name otherwise gflags will get confused when parsing anything after the module name.", file=sys.stderr)

  mod = importlib.import_module(module_names[0])
  # Garbage collection may be disabled as an optimization in the uwsgi zygote process
  if uwsgi:
    gc.enable()
  lib.runner.run_as_main(mod.__startable_config__, module_names[0])


if __name__ in ("__main__", uwsgi_main_module):
  main()
