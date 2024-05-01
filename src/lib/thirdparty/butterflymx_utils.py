import logging

import thrift_types.butterflymx.constants as butterflymx_constants
import thrift_types.message_bus.ttypes as mb_ttypes


log = logging.getLogger(__name__)


def generate_peripheral_id(id_, peripheral_type):
  prefix = ""
  if peripheral_type == mb_ttypes.PeripheralType.BUILDING_ENTRY_PANEL:
    prefix = butterflymx_constants.BUTTERFLYMX_PANEL_ID_PREFIX
  elif peripheral_type == mb_ttypes.PeripheralType.MANAGED_BUILDING:
    prefix = butterflymx_constants.BUTTERFLYMX_BUILDING_ID_PREFIX
  else:
    log.error("unsupported peripheral type %s (id: %s)", peripheral_type, id_)
    return ""

  return "{}_{}".format(prefix, id_)
