import itertools
import unittest
from unittest import mock
import urllib.parse

import gflags

# Importing cython_monkeypatch executes code to properly recognize methods in Cython-compiled
# modules.
import lib.test_helpers.cython_monkeypatch  # pylint: disable=unused-import


class PatchingTestCase(unittest.TestCase):

  def setUp(self):
    super().setUp()

    # gflags requires that the flags are initialized once before a flag can be accessed. Thus,
    # initialize the flags with their default values as part of setUp.
    self.update_gflags()
    self.addCleanup(gflags.FLAGS.Reset)

  def update_gflags(self, *args, **kwargs):
    """Update gflags.FLAGS() with the given arguments.

    `args` and keyword argument keys will be prefixed with '--'. Examples:
        update_gflags("nodry_run")
        update_gflags("nodry_run", cert_dir="/var/brilliant/certs")
    """
    gflags_args = (
        ["--" + arg for arg in args]
        + list(itertools.chain.from_iterable(("--" + key, value) for key, value in kwargs.items()))
    )
    gflags.FLAGS(["fake_script.py"] + gflags_args)

  def _auto_patch(self, *args, autospec=True, **kwargs):
    kwargs_to_pass = dict(
        autospec=autospec,
        **kwargs
    )
    if {'new_callable', 'new'} & kwargs.keys():
      kwargs_to_pass.pop('autospec')

    patcher = mock.patch(*args, **kwargs_to_pass)
    self.addCleanup(patcher.stop)
    return patcher.start()

  def assert_url(self, expected_url, url_to_check):
    '''Assert that two URL strings are the same irregardless of whether the query parameters are in
    a different order.

    Args:
      expected_url: A string representing the expected URL.
      url_to_check: A string representing the URL that should be checked against the expected_url.
    '''
    def _get_url_parts(url):
      parts = urllib.parse.urlparse(url)
      query = frozenset(urllib.parse.parse_qsl(parts.query))
      path = urllib.parse.unquote_plus(parts.path)
      return parts._replace(query=query, path=path)

    expected = _get_url_parts(expected_url)
    to_check = _get_url_parts(url_to_check)

    # Assert the individual parts of the ParseResult independently since the error messages are more
    # helpful. Then, assert the whole structure as a final check.
    self.assertEqual(expected.scheme, to_check.scheme)
    self.assertEqual(expected.netloc, to_check.netloc)
    self.assertEqual(expected.path, to_check.path)
    self.assertEqual(expected.query, to_check.query)
    self.assertEqual(expected, to_check)
