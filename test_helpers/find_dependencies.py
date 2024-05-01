"""
Prints all of the python dependencies (except for the standard libary dependencies) for a given
path. The path can be a directory or a single file. If the path is a directory, then all of the
python files will be inspected in the given directory. Directories with many files can take a while
to process.
"""

import glob
import itertools
import modulefinder
import sys

import gflags


gflags.DEFINE_string("path", "",
                     "The path to a directory or a file (e.g. 'web_api' or 'web_api/server.py').")

FLAGS = gflags.FLAGS


class NoPathSpecifiedError(Exception):
  pass


def _get_filenames(path):
  if path.endswith(".py"):
    return [path]
  return glob.glob("{}/**/*.py".format(path), recursive=True)


def _get_dependencies(filename):
  # Python 3.8.5 ModuleFinder does not play well with autobahn imports and conditional imports.
  finder = modulefinder.ModuleFinder(excludes=["autobahn", "lib.runner"])
  finder.run_script(filename)

  # Ignore:
  # - Standard library files.
  # - Anything from the system python (i.e. from sys.base_prefix).
  return [
      mod.__file__ for _, mod in finder.modules.items()
      if (mod.__file__
          and not sys.base_prefix in mod.__file__)
  ]


def main(path):
  if not path:
    raise NoPathSpecifiedError("The '--path=<path>' flag must be specified.")

  filenames = _get_filenames(path)
  dependencies_lists = [_get_dependencies(filename) for filename in filenames]
  dependencies = set(itertools.chain.from_iterable(dependencies_lists))
  print("\n".join(dependencies))


if __name__ == "__main__":
  gflags.FLAGS(sys.argv)
  main(FLAGS.path)
