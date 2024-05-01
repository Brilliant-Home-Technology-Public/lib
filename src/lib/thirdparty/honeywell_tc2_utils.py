import logging


log = logging.getLogger(__name__)


def parse_honeywell_tc2_locations_details(locations_details):
  panels_by_location = {}
  for location in locations_details:
    location_id = str(location["id"])
    location_name = location["name"]
    panel_info = {}
    skip_location = False
    for device in location.get("devices", []):
      if device.get("deviceClass") == "SecuritySystemPanel":
        panel_id = str(device["id"])
        # There should only be 1 panel per location. Log  and don't include locations that do.
        if panel_info:
          log.error(
              "Detected panel (%s) for location %s, already has panel %s",
              panel_id,
              location_id,
              panel_info,
          )
          skip_location = True
        else:
          panel_info = {
              "panel_id": panel_id,
              "panel_name": location_name,
              "user_code_available": device.get("userCodeAvailable"),
          }
    if panel_info and not skip_location:
      panels_by_location[location_id] = panel_info

  return panels_by_location
