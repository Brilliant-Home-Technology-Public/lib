import thrift_types.message_bus.constants as mb_consts


def _normalized_gangbox_intensity_helper(gangbox_peripheral, intensity):
  if 'max_intensity_value' in gangbox_peripheral.variables:
    max_gangbox_intensity = int(gangbox_peripheral.variables['max_intensity_value'].value)
  else:
    max_gangbox_intensity = 100

  normalization_factor = 100 / max_gangbox_intensity

  return int(intensity) * normalization_factor


def get_normalized_gangbox_intensity(gangbox_peripheral):
  '''
    Takes in a gangbox peripheral and returns it's intensity as a float on a 0-100 scale. Certain
    versions of the gangbox peripheral have an intensity range of 0-100 while others have 0-1000.
    Those with the 0-1000 range also have a max_intensity_value variable. We'll assume a value of
    100 for max_intensity_value for any gangbox that doesn't have a max_intensity_value variable.
  '''
  return _normalized_gangbox_intensity_helper(
      gangbox_peripheral,
      gangbox_peripheral.variables["intensity"].value,
  )


def normalize_intensity_for_gangbox(gangbox_peripheral, intensity):
  """
  Takes in a given intensity and gangbox peripheral and normalizes the intensity based on the
  scale of the gangbox peripheral. The returned intensity will be a float on a scale from 0-100.
  See get_normalized_gangbox_intensity for a better description of why we need this.
  """
  return _normalized_gangbox_intensity_helper(gangbox_peripheral, intensity)


def translate_normalized_intensity(gangbox_peripheral, normalized_intensity):
  '''
    Takes in a gangbox peripheral and an intensity on a 0-100 scale and returns the correct
    intensity value that should be set on the gangbox. Certain versions of the gangbox peripheral
    have an intensity range of 0-100 while others have 0-1000. Those with the 0-1000 range also
    have a max_intensity_value variable. We'll assume a value of 100 for max_intensity_value for
    any gangbox that doesn't have a max_intensity_value variable.
  '''
  if 'max_intensity_value' in gangbox_peripheral.variables:
    max_gangbox_intensity = int(gangbox_peripheral.variables['max_intensity_value'].value)
  else:
    max_gangbox_intensity = 100

  intensity_multiplier = max_gangbox_intensity / 100

  return (normalized_intensity * intensity_multiplier)


def get_gangbox_id_for_thirdparty_service(device_id, gangbox_peripheral_id):
  '''
    Takes in the device ID and peripheral ID of a Brilliant gangbox and creates an id
    which will be used to refer to that gangbox by thirdparties. The external ID is just a
    the device ID and peripheral ID concaticated by a semi-colon
  '''
  return ":".join([device_id, gangbox_peripheral_id])


def get_device_id_and_gangbox_peripheral_id_from_thirdparty_service_id(thirdparty_service_id):
  '''
    Takes in the ID created by get_gangbox_id_for_thirdparty_service and returns the constituent
    device and peripheral ids
  '''
  # maintain backwards compatibility with devices already registered to Amazon/Google
  if ":" not in thirdparty_service_id:
    return [thirdparty_service_id, "gangbox_peripheral_0"]
  return thirdparty_service_id.split(':')


def is_gangbox_peripheral(peripheral_id):
  return peripheral_id.startswith(mb_consts.GANGBOX_IDENTIFIER)


def get_gang_number(peripheral_name):
  return peripheral_name.split("_")[-1]
