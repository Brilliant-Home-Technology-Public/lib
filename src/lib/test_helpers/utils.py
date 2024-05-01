import json


class SortableList(list):

  def __init__(self, items, sort_key=None):
    super().__init__(items)
    self._sort_key = sort_key

  def __eq__(self, other):
    if self._sort_key:
      return sorted(self, key=self._sort_key) == sorted(other, key=self._sort_key)
    return super().__eq__(other)

  def __ne__(self, other):
    return not self.__eq__(other)


class JSONDumpedDict(dict):
  """A class used to wrap a dictionary and compare it to a JSON string that was formed by executing
  json.dumps() on a dictionary. The JSON string will be converted to a dictionary and then compared
  to the dictionary stored in this class. Thus, we don't need to worry about the ordering of the
  JSON string changing due to the non-deterministic ordering of dictionaries.

  Usage:
    self.assertEqual(
        JSONDumpedDict(a=1, b=2, c=3),
        "{a=1, b=2, c=3}"
    )

    # Or use within another data structure:
    self.exchange_client_mock.forward_set_variables_request.assert_called_once_with(
        device_id=mb_consts.SMARTTHINGS_IDENTIFIER,
        peripheral_name=self.smartthings_device_id,
        last_set_timestamps=None,
        variables={
            "current_revision": lib.test_helpers.utils.JSONDumpedDict(on=1, intensity=1000),
        },
    )
  """

  def __eq__(self, other):
    return super().__eq__(json.loads(other))

  def __ne__(self, other):
    return not self.__eq__(other)
