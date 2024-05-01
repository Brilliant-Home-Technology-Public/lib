import os.path
import unittest


class CustomDiscoveryTestLoader(unittest.TestLoader):

  def __init__(self):
    super().__init__()
    self.exclude_paths = []

  def _find_test_path(self, full_path, pattern, namespace=False):
    if full_path in self.exclude_paths:
      return (None, False)
    return super()._find_test_path(full_path, pattern, namespace=namespace)  # pylint: disable=unexpected-keyword-arg


class CustomDiscoveryTestProgram(unittest.TestProgram):

  def __init__(self):
    super().__init__(module=None, testLoader=CustomDiscoveryTestLoader())
    self.start = None
    self.pattern = None
    self.top = None
    self.test = None

  def parseArgs(self, argv):
    # Overriden to always force discovery
    self._initArgParsers()
    self._do_discovery(argv[1:])

  def _do_discovery(self, argv, Loader=None):
    # Overriden to supply different defaults and capture our command-line args
    if Loader:
      raise NotImplementedError("Loader cannot be specified for this instance")
    self.start = '.'
    self.pattern = '*test.py'
    self.top = None
    self._discovery_parser.parse_args(argv, self)
    self.testLoader.exclude_paths = [
        os.path.abspath(os.path.join(self.start, p)) for p in self.exclude_paths
    ]
    self.test = self.testLoader.discover(self.start, self.pattern, self.top)

  def _getDiscoveryArgParser(self, parent):
    # Overriden to define additional command-line args
    parser = super()._getDiscoveryArgParser(parent)
    parser.add_argument('-X', '--exclude-paths',
                        nargs="*",
                        default=["site-packages"],
                        dest='exclude_paths',
                        help="Paths to exclude during search")
    return parser


if __name__ == "__main__":
  CustomDiscoveryTestProgram()
