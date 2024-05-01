import thrift_types.protocol.ttypes as protocol_ttypes


# TODO Remove this and use the dataclass type instead
class _RequestResponseBase:

  def __repr__(self):
    inner_args = ", ".join("{}={}".format(k, v) for k, v in vars(self).items())
    return "{}({})".format(type(self).__name__, inner_args)

  def __eq__(self, other):
    return isinstance(other, type(self)) and vars(self) == vars(other)


class Request(_RequestResponseBase):

  def __init__(self, *, command=None, args_serialized=None, is_oneway=False):
    self.command = command
    self.args_serialized = args_serialized
    self.is_oneway = is_oneway

  def to_thrift(self):
    if isinstance(self.args_serialized, bytes):
      args_key = "args_serialized_binary"
    else:
      args_key = "args_serialized"
    return protocol_ttypes.Request(
        command=self.command,
        is_oneway=self.is_oneway,
        **{args_key: self.args_serialized},
    )

  @classmethod
  def from_thrift(cls, request):
    return cls(
        command=request.command,
        args_serialized=request.args_serialized_binary or request.args_serialized,
        is_oneway=request.is_oneway,
    )


class Response(_RequestResponseBase):

  def __init__(self, *, status=None, result_serialized=None):
    self.status = status
    self.result_serialized = result_serialized

  def to_thrift(self):
    if isinstance(self.result_serialized, bytes):
      result_key = "result_serialized_binary"
    else:
      result_key = "result_serialized"
    return protocol_ttypes.Response(
        status=self.status,
        **{result_key: self.result_serialized},
    )

  @classmethod
  def from_thrift(cls, response):
    return cls(
        status=response.status,
        result_serialized=response.result_serialized_binary or response.result_serialized,
    )
