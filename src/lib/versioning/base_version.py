import logging
import typing


log = logging.getLogger(__name__)
CURRENT_API_VERSION = "2"


def register(cls):
  if cls.service not in cls.registry:
    cls.registry[cls.service] = {cls.version: cls}
  else:
    if cls.version in cls.registry[cls.service]:
      # handle accidental duplicate version definitions
      if cls != cls.registry[cls.service][cls.version]:
        raise ValueError("Service {}, Version {} defined twice!".format(cls.service, cls.version))
    else:
      cls.registry[cls.service][cls.version] = cls


class BaseMeta(type):
  """
  This metaclass creates a registry of all versions, keyed by service name and then version, for
  easy lookup of a class given its service name and version.
  """
  def __init__(cls, name, bases, attrs):
    if not hasattr(cls, "registry"):
      # base class
      cls.registry = {}
    elif not name.startswith("Base"):
      if cls.service is None or cls.version is None:
        raise ValueError("Must provide a service and version for every class")
      register(cls)
    super(BaseMeta, cls).__init__(name, bases, attrs)


class BaseVersion(metaclass=BaseMeta):
  """
  All thrift service version definitions should inherit from this class. This class
  defines default functions for translating args and responses up and down a single version, as well
  some generic helper functions for converting one version into another via a series of up/down
  migrations.
  """
  version: typing.Optional[str] = None
  next_version: typing.Optional[str] = None
  prev_version: typing.Optional[str] = None

  @classmethod
  def _iterative_forward_translation_func(cls, typ, function_name, val, version, context=None):
    """
    A helper function which defines how to upgrade/downgrade either args or response for a
    given function to a specific version. This function will in turn call the mini step functions to
    execute a series of version upgrade/downgrades so clients do not have to worry about multi-step
    transitions.

    Params:
      - typ: either args or response, based on what is being translated
      - function_name: the service function that is being called
      - val: the arguments to the function is typ is args, or the response if typ is response
      - version: the version to translate to
    """
    registry = cls.registry[cls.service]
    current_cls = cls
    while version != current_cls.version:
      if version > current_cls.version:
        if current_cls.next_version is None:
          raise KeyError("Service {}, Version {} cannot be upgraded!".format(
              current_cls.service,
              current_cls.version
          ))
        if current_cls.next_version not in registry:
          raise KeyError("Service {}, Version {} does not exist!".format(
              current_cls.service,
              current_cls.next_version
          ))
        next_cls = registry[current_cls.next_version]
        val = getattr(next_cls, "translate_{}_up".format(typ))(function_name, val, context=context)
        current_cls = next_cls
      else:
        val = getattr(current_cls, "translate_{}_down".format(typ))(
            function_name,
            val,
            context=context
        )
        if current_cls.prev_version is None:
          raise KeyError("Service {}, Version {} cannot be downgraded!".format(
              current_cls.service,
              current_cls.version
          ))
        if current_cls.prev_version not in registry:
          raise KeyError("Service {}, Version {} does not exist!".format(
              current_cls.service,
              current_cls.prev_version
          ))
        current_cls = registry[current_cls.prev_version]
    return val

  @classmethod
  def translate_args_to_version(cls, function_name, val, version, context=None):
    return cls._iterative_forward_translation_func(
        "args", function_name, val, version, context=context
    )

  @classmethod
  def translate_response_to_version(cls, function_name, val, version, context=None):
    return cls._iterative_forward_translation_func(
        "response", function_name, val, version, context=context
    )

  @classmethod
  def _iterative_backward_translation_func(cls, typ, function_name, val, version, context=None):
    """
    A recursive helper function which defines how to upgrade/downgrade either args or response for a
    given function from a specific version to this class' version.

    Params:
      - typ: either args or response, based on what is being translated
      - function_name: the service function that is being called
      - val: the arguments to the function is typ is args, or the response if typ is response
      - version: the version to translate from
    """
    registry = cls.registry[cls.service]
    if version not in registry:
      raise KeyError("Service {}, Version {} does not exist!".format(cls.service, version))

    other_version = registry[version]
    return other_version._iterative_forward_translation_func(
        typ, function_name, val, cls.version, context=context,
    )

  @classmethod
  def translate_args_from_version(cls, function_name, val, version, context=None):
    return cls._iterative_backward_translation_func(
        "args", function_name, val, version, context=context
    )

  @classmethod
  def translate_response_from_version(cls, function_name, val, version, context=None):
    return cls._iterative_backward_translation_func(
        "response", function_name, val, version, context=context
    )

  @classmethod
  def _single_translation_func(cls, typ, direction, function_name, val, context=None):
    # note that this implies that the version class need not have an implementation of up/down
    # migrations for both args and responses for all functions defined in the service. the default
    # behavior is a no-op
    fn_name = "_{}_{}_{}".format(function_name, typ, direction)
    if hasattr(cls, fn_name):
      return getattr(cls, fn_name)(val, context=context)
    return val

  @classmethod
  def translate_args_up(cls, function_name, val, context=None):
    """
    Defines how to upgrade TO this specific version.
    """
    return cls._single_translation_func("args", "up", function_name, val, context=context)

  @classmethod
  def translate_args_down(cls, function_name, val, context=None):
    """
    Defines how to downgrade FROM this specific version.
    """
    return cls._single_translation_func("args", "down", function_name, val, context=context)

  @classmethod
  def translate_response_up(cls, function_name, val, context=None):
    """
    Defines how to upgrade TO this specific version.
    """
    return cls._single_translation_func("response", "up", function_name, val, context=context)

  @classmethod
  def translate_response_down(cls, function_name, val, context=None):
    """
    Defines how to downgrade FROM this specific version.
    """
    return cls._single_translation_func("response", "down", function_name, val, context=context)
