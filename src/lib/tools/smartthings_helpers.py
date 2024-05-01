from datetime import datetime

from lib import serialization
import thrift_types.color.ttypes as color_ttypes


SMARTTHINGS_BRIGHTNESS_SCALE = 100 / 1000  # SmartThings' upper limit / Brilliant upper limit
BRILLIANT_HUE_SCALE = 65535 / 100  # Brilliant upper limit / SmartThings' upper limit
BRILLIANT_SATURATION_SCALE = 254 / 100  # Brilliant upper limit / SmartThings' upper limit
MIRED_CONVERSION = 1000000
DEFAULT_TIMESTAMP_STR = "0001-01-01T00:00:00"
SMARTTHINGS_TIMESTAMP_LENGTH = 19
POSITION_CONVERSION = 0.1


def translate_smartthings_device_state(device_state):
  variables = {}
  if "lock" in device_state:
    variables["locked"] = int(device_state["lock"]["lock"]["value"] == "locked")

  if ("switchLevel" in device_state and device_state["switchLevel"]["level"]["value"] is not None and
      "windowShade" not in device_state):
    variables["intensity"] = round(
        float(device_state["switchLevel"]["level"]["value"]) / SMARTTHINGS_BRIGHTNESS_SCALE
    )

  if "switch" in device_state:
    variables["on"] = int(device_state["switch"]["switch"]["value"] == "on")

  if "colorControl" in device_state or "colorTemperature" in device_state:
    hue_data = device_state.get("colorControl", {}).get("hue", {})
    sat_data = device_state.get("colorControl", {}).get("saturation", {})
    temp_data = device_state.get("colorTemperature", {}).get("colorTemperature", {})

    hue_value = hue_data.get("value")
    sat_value = sat_data.get("value")
    temp_value = temp_data.get("value")

    hue_timestamp = parse_smartthings_timestamp(hue_data.get("timestamp", DEFAULT_TIMESTAMP_STR))
    sat_timestamp = parse_smartthings_timestamp(sat_data.get("timestamp", DEFAULT_TIMESTAMP_STR))
    color_timestamp = max(hue_timestamp, sat_timestamp)
    temp_timestamp = parse_smartthings_timestamp(temp_data.get("timestamp", DEFAULT_TIMESTAMP_STR))

    color = color_ttypes.Color(name="")
    if color_timestamp > temp_timestamp and (hue_value is not None or sat_value is not None):
      color.hue = int(round((hue_value or 0) * BRILLIANT_HUE_SCALE))
      color.sat = int(round((sat_value or 0) * BRILLIANT_SATURATION_SCALE))
    elif temp_timestamp > color_timestamp and temp_value:
      color.temp = convert_color_temperature(temp_value)
    if color != color_ttypes.Color(name=""):
      variables["color"] = color

  if "windowShadeLevel" in device_state:
    variables["position"] = device_state["windowShadeLevel"]["shadeLevel"]["value"]

  if ("windowShade" in device_state and "switchLevel" in device_state and
      device_state["switchLevel"]["level"]["value"] is not None):
    variables["position"] = device_state["switchLevel"]["level"]["value"]

  if device_state.get("healthCheck", {}).get(
      "DeviceWatch-DeviceStatus", {}).get("value"):
    variables["deviceStatus"] = device_state["healthCheck"]["DeviceWatch-DeviceStatus"]["value"]
  return variables


def parse_smartthings_timestamp(timestamp):
  return datetime.strptime(timestamp[:SMARTTHINGS_TIMESTAMP_LENGTH], "%Y-%m-%dT%H:%M:%S")


def convert_color_temperature(temp_value):
  # convert both from Kelvin to Mired and Mired to Kelvin
  if temp_value > 0:
    return int(round(MIRED_CONVERSION / temp_value))
  return 0


def translate_smartthings_event_data(event_json):
  event_data = {}
  capability = event_json["deviceEvent"]["capability"]
  value = event_json["deviceEvent"]["value"]
  if capability == "switch":
    event_data["on"] = str(int(value == "on"))
  elif capability == "switchLevel":
    event_data["intensity"] = str(
        round(float(value) / SMARTTHINGS_BRIGHTNESS_SCALE)
    )
  elif capability == "lock":
    event_data["locked"] = str(int(value == "locked"))
  elif capability == "colorTemperature":
    temp_value = convert_color_temperature(value)
    event_data["color"] = serialization.serialize(color_ttypes.Color(name="", temp=temp_value))
  elif capability == "colorControl":
    attribute = event_json["deviceEvent"]["attribute"]
    if attribute == "hue":
      event_data["hue"] = str(int(round(value * BRILLIANT_HUE_SCALE)))
    elif attribute == "saturation":
      event_data["sat"] = str(int(round(value * BRILLIANT_SATURATION_SCALE)))
  elif capability == "windowShadeLevel":
    attribute = event_json["deviceEvent"]["attribute"]
    if attribute == "shadeLevel":
      event_data["position"] = str(value)
  return event_data
