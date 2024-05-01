from lib.tools import peripheral_interface_helpers
import thrift_types.demo.ttypes as demo_ttypes
import thrift_types.message_bus.ttypes as mb_ttypes


def is_employee_home(home_details_peripheral, demo_config_peripheral):
  # Here we define an employee home as one which is not a demo home, and that has at least one
  # user with a brilliant.tech email address
  if not home_details_peripheral or not demo_config_peripheral:
    return False
  demo_variant = peripheral_interface_helpers.deserialize_peripheral_variable(
      peripheral_type=mb_ttypes.PeripheralType.DEMO_CONFIGURATION,
      name="variant",
      value=demo_config_peripheral.variables["variant"].value,
  )
  if demo_variant != demo_ttypes.DemoType.NONE:
    return False
  users = peripheral_interface_helpers.deserialize_peripheral_variable(
      peripheral_type=mb_ttypes.PeripheralType.HOME_DETAILS,
      name="users",
      value=home_details_peripheral.variables["users"].value,
  )
  return any((user.email_address.endswith("@brilliant.tech") for user in users.users))
