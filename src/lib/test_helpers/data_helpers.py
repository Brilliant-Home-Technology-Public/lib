import datetime
import typing

import lib.serialization
import lib.storage.interface
import lib.tools.peripheral_interface_helpers
import lib.ulid
import thrift_types.battery.ttypes as battery_ttypes
import thrift_types.bluetooth.constants as bt_consts
import thrift_types.bluetooth.ttypes as bluetooth_ttypes
import thrift_types.butterflymx.ttypes as butterflymx_ttypes
import thrift_types.climate_sensor.ttypes as climate_sensor_ttypes
import thrift_types.configuration.constants as config_consts
import thrift_types.configuration.ttypes as config_ttypes
import thrift_types.demo.ttypes as demo_ttypes
import thrift_types.gangbox.ttypes as gangbox_ttypes
import thrift_types.hardware.ttypes as hardware_ttypes
import thrift_types.lock.ttypes as lock_ttypes
import thrift_types.mesh_dfu.ttypes as mesh_dfu_ttypes
import thrift_types.message_bus.constants as mb_consts
import thrift_types.message_bus.ttypes as mb_ttypes
import thrift_types.music.ttypes as music_ttypes
import thrift_types.nest.constants as nest_consts
import thrift_types.nest.ttypes as nest_ttypes
import thrift_types.remote_bridge.ttypes as remote_ttypes
import thrift_types.remote_media.constants as remote_media_consts
import thrift_types.remote_media.ttypes as remote_media_ttypes
import thrift_types.thermostat.ttypes as thermostat_ttypes
import thrift_types.uart.ttypes as uart_ttypes
import thrift_types.version.constants as version_constants
import thrift_types.wifi.ttypes as wifi_ttypes


BEDROOM_ROOM_ID = "1111111"
CONTROL_ID = "0162e4e8eef40003d7bbe77cde8853d6"
HOME_ID = "01646b91a2df0002c97ac6861345a725"
KITCHEN_ROOM_ID = "2222222"
LIVING_ROOM_ROOM_ID = "3333333"
GANGBOX_ULID = "0000016a9a1d086a00042a340c0abdf9aba8"
STATE_CONFIG_ULID = "0182ccdd86ae000a7ca84f900731dec3"
SWITCH_ULID = "0173e908dcb90007a00f2e0b5c1c1702"
PLUG_ULID = "0173e908dcb90008a00f2e0b5c1c1703"
MESH_PERIPHERAL_OWNER_ID = "4c650290fc6b47b2af2a15a2b948ac2a"
GANGBOX_ID = GANGBOX_ULID[4:]
SUN_MAY_13_2018_22_57_20 = 1526252240965
MON_MAY_14_2018_22_57_20 = 1526338640965
STANDARD_WATTAGE_STATUS = bluetooth_ttypes.LoadWattageStatus.STANDARD
NOT_MAGNETIC_WATTAGE_STATUS = bluetooth_ttypes.LoadMagneticStatus.NOT_MAGNETIC
UNKNOWN_CONFIGURATION_TEMPLATE_ID = config_ttypes.ConfigurationTemplateID.UNKNOWN


def apply_peripheral_overrides(peripheral_overrides=None, device=None):
  peripheral_overrides = peripheral_overrides or {}
  for name, peripheral in peripheral_overrides.items():
    device.peripherals[name] = peripheral
    if not peripheral:
      del device.peripherals[name]
  return device


def get_brilliant_control(
    expected_total_gang_count: int = 1,
    control_id: str = CONTROL_ID,
    control_name: str = "Flying Ace",
    peripheral_overrides: typing.Optional[typing.Dict[str, mb_ttypes.Peripheral]] = None,
    room_ids: typing.Optional[typing.List[str]] = None,
    slider_device_id: typing.Optional[str] = None,
) -> mb_ttypes.Device:
  """
  Returns a Device thrift object with expected peripherals.
  Please add to this to make it more robust!
  """
  slider_device_id = slider_device_id if slider_device_id is not None else control_id
  device = mb_ttypes.Device(
      id=control_id,
      peripherals={
          mb_consts.REMOTE_BRIDGE_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.REMOTE_BRIDGE_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.REMOTE_BRIDGE,
              status=mb_ttypes.PeripheralStatus.ONLINE,
              variables={
                  "address": mb_ttypes.Variable(
                      name="address",
                      value="wss://10.10.10.210:5455",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
                  "known_remote_devices": mb_ttypes.Variable(
                      name="known_remote_devices",
                      value=lib.serialization.serialize(remote_ttypes.KnownRemoteDevices([
                          remote_ttypes.RemoteDevice(
                              device_id="cloud",
                              device_status=remote_ttypes.DeviceStatus.ONLINE,
                              always_connect=True,
                          ),
                      ])),
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
                  "device_provisioning_ip_listen_port": mb_ttypes.Variable(
                      name="device_provisioning_ip_listen_port",
                      value="0",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
              },
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          mb_consts.WIFI_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.WIFI_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.WIFI,
              status=mb_ttypes.PeripheralStatus.ONLINE,
              variables={
                  "preferred_network": mb_ttypes.Variable(
                      name="preferred_network",
                      value="Daisy Hill Puppy Farm",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
                  "association_status": mb_ttypes.Variable(
                      name="association_status",
                      value=str(wifi_ttypes.AssociationStatusType.SUCCESS),
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
                  "available_networks": mb_ttypes.Variable(
                      name="available_networks",
                      value=lib.serialization.serialize(wifi_ttypes.AvailableNetworks([
                          wifi_ttypes.Network(
                              name="Daisy Hill Puppy Farm",
                              security=wifi_ttypes.SecurityType.WEP,
                              signal_strength=80,
                              status=wifi_ttypes.NetworkStatusType.ONLINE,
                          ),
                          wifi_ttypes.Network(
                              name="Red Baron",
                              security=wifi_ttypes.SecurityType.WEP,
                              signal_strength=10,
                              status=wifi_ttypes.NetworkStatusType.IDLE,
                          ),
                      ])),
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
                  "scan_requested": mb_ttypes.Variable(
                      name="scan_requested",
                      value=str(wifi_ttypes.AssociationStatusType.SUCCESS),
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
              },
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          mb_consts.DEVICE_CONFIG_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.DEVICE_CONFIG_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.DEVICE_CONFIGURATION,
              status=mb_ttypes.PeripheralStatus.ONLINE,
              variables={
                  "device_name": mb_ttypes.Variable(
                      name="device_name",
                      value=control_name,
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
                  "display_name": mb_ttypes.Variable(
                      name="display_name",
                      value=control_name,
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
                  "software_update_poll_time": mb_ttypes.Variable(
                      name="software_update_poll_time",
                      value=lib.serialization.serialize(config_ttypes.Trigger()),
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
                  "enable_intercom_audio": mb_ttypes.Variable(
                      name="enable_intercom_audio",
                      value="0",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
                  "video_is_upright": mb_ttypes.Variable(
                      name="video_is_upright",
                      value="0",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
                  "enable_demo_mode": mb_ttypes.Variable(
                      name="enable_demo_mode",
                      value="0",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
                  "gesture_configs": mb_ttypes.Variable(
                      name="gesture_configs",
                      value=lib.serialization.serialize(config_ttypes.GestureConfigs()),
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
                  "room_assignment": mb_ttypes.Variable(
                      name="room_assignment",
                      value=lib.serialization.serialize(
                          config_ttypes.RoomAssignment(
                              room_ids=(
                                  room_ids
                                  or [BEDROOM_ROOM_ID, KITCHEN_ROOM_ID, LIVING_ROOM_ROOM_ID]
                              ),
                          ),
                      ),
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
              },
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          mb_consts.HARDWARE_IDENTIFIER: get_hardware_peripheral(),
          mb_consts.GANGBOX_UART_STATUS_PREFIX + "_0": mb_ttypes.Peripheral(
              name=mb_consts.GANGBOX_UART_STATUS_PREFIX + "_0",
              peripheral_type=mb_ttypes.PeripheralType.GANGBOX_UART_STATUS,
              status=mb_ttypes.PeripheralStatus.ONLINE,
              variables={
                  "target_firmware_git_version": mb_ttypes.Variable(
                      name="target_firmware_git_version",
                      value="7e3e2c17a",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
                  "reported_firmware_git_version": mb_ttypes.Variable(
                      name="reported_firmware_git_version",
                      value="7e3e2c17a",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
                  "device_type": mb_ttypes.Variable(
                      name="device_type",
                      value=str(uart_ttypes.UARTDeviceType.GANGBOX),
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
                  "device_revision": mb_ttypes.Variable(
                      name="device_revision",
                      value=str(gangbox_ttypes.GangboxDeviceRevision.V1),
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
              },
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          mb_consts.FACEPLATE_UART_STATUS_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.FACEPLATE_UART_STATUS_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.FACEPLATE_UART_STATUS,
              status=mb_ttypes.PeripheralStatus.ONLINE,
              variables={
                  "target_firmware_git_version": mb_ttypes.Variable(
                      name="target_firmware_git_version",
                      value="7e3e2c17a",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
                  "reported_firmware_git_version": mb_ttypes.Variable(
                      name="reported_firmware_git_version",
                      value="7e3e2c17a",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
              },
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          mb_consts.GANGBOX_CONFIG_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.GANGBOX_CONFIG_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.GANGBOX_CONFIGURATION,
              variables={
                  "expected_total_gang_count": mb_ttypes.Variable(
                      name="expected_total_gang_count",
                      value=str(expected_total_gang_count),
                  ),
              },
          ),
          mb_consts.MOTION_DETECTION_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.MOTION_DETECTION_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.MOTION_DETECTION_CONFIGURATION,
              variables={
                  "trigger_screen_off_timeout_sec": mb_ttypes.Variable(
                      name="trigger_screen_off_timeout_sec",
                      value="300",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
                  "trigger_screen": mb_ttypes.Variable(
                      name="trigger_screen",
                      value=str(False),
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
                  "trigger_screen_off": mb_ttypes.Variable(
                      name="trigger_screen_off",
                      value=str(False),
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
              },
          ),
      },
      timestamp=MON_MAY_14_2018_22_57_20,
      device_type=mb_ttypes.DeviceType.CONTROL,
  )
  for gangbox_id in range(expected_total_gang_count):
    gangbox = get_gangbox_peripheral(
        gangbox_id=gangbox_id,
        room_ids=room_ids or [BEDROOM_ROOM_ID, KITCHEN_ROOM_ID],
    )
    device.peripherals[gangbox.name] = gangbox
    slider_config = mb_ttypes.Variable(
        name="{}{}".format(config_consts.CAP_TOUCH_CONFIG_VARIABLE_PREFIX, gangbox_id),
        value=lib.serialization.serialize(
            config_ttypes.CapTouchSliderConfig(
                peripheral_id=gangbox.name,
                index=gangbox_id,
                device_id=slider_device_id,
                double_tap_scene_id=None,
                disable_tap=None,
            ),
        ),
        timestamp=0,
        externally_settable=True,
    )
    device.peripherals["device_config_peripheral"].variables[slider_config.name] = slider_config

  return apply_peripheral_overrides(peripheral_overrides=peripheral_overrides, device=device)


def get_device_provision_state(
    honeywell_devices: typing.Optional[typing.List[typing.Dict[str, typing.Any]]] = None,
    switch_variables_per_control_id: typing.Optional[
        typing.Dict[str, typing.List[typing.Dict[str, str]]]
    ] = None,
) -> typing.List[typing.Dict[str, str]]:
  """Returns device provision state as sent up by mobile when completing installation.

  Args:
  - honeywell_devices: A list of dictionaries of Honeywell device variables. Each dictionary of
      variables must include: `peripheral_id`, `peripheral_type`, `display_name`, and `room_ids`.
  - switch_variables_per_control_id: A dictionary of Control IDs to a list of variables for each
      Switch that belongs to the Control. The dictionary of variables for the Switch must include
      `switch_id`, `display_name`, and `room_ids`.
  """
  device_provision_state = []
  honeywell_devices = honeywell_devices or []
  switch_variables_per_control_id = switch_variables_per_control_id or {}
  device_provision_state.extend([
      {
          "variable_name": f"{mb_consts.PROCESS_CONFIGURATION_VARIABLE_PREFIX}{honeywell_info['peripheral_id']}",
          "serialized_peripheral_info": lib.serialization.serialize(config_ttypes.PeripheralInfo(
              owner=mb_consts.HONEYWELL_IDENTIFIER,
              name=honeywell_info["peripheral_id"],
              peripheral_type=honeywell_info["peripheral_type"],
              thirdparty_device_id='1285894',
              configuration_peripheral_id=mb_consts.HONEYWELL_CONFIG_IDENTIFIER,
              configuration_variables=None,
              stubbed=None,
              hidden=False,
              unrecognized=False,
              default_display_name='Honeywell',
              initial_state_config=config_ttypes.StateConfig(
                  id="",
                  title="",
                  peripheral_configuration_assignments=[
                      config_ttypes.PeripheralConfigurationAssignment(
                          unique_peripheral_id=config_ttypes.UniquePeripheralID(
                              device_id=mb_consts.HONEYWELL_IDENTIFIER,
                              peripheral_id=honeywell_info["peripheral_id"],
                          ),
                          peripheral_configuration=config_ttypes.PeripheralConfiguration(
                              peripheral_configuration_template_id=config_ttypes.ConfigurationTemplateID.PERIPHERAL_INFO_INITIAL_STATE,
                              additional_variable_configuration={
                                  "display_name": honeywell_info["display_name"],
                                  "room_assignment": lib.serialization.serialize(
                                      config_ttypes.RoomAssignment(
                                          room_ids=honeywell_info["room_ids"],
                                      )
                                  ),
                              },
                          ),
                      ),
                  ],
              ),
          )),
      } for honeywell_info in honeywell_devices
  ])

  for control_id, switch_variables in switch_variables_per_control_id.items():
    device_provision_state.extend([
        {
            "variable_name": f"mesh_device:{variables['switch_id']}",
            "serialized_peripheral_info": lib.serialization.serialize(config_ttypes.PeripheralInfo(
                owner=control_id,
                name=variables["switch_id"],
                peripheral_type=mb_ttypes.PeripheralType.LIGHT,
                thirdparty_device_id=variables["switch_id"],
                configuration_peripheral_id="mesh_configuration",
                configuration_variables={
                    "mac_address": "d8:1f:45:d7:9f:66",
                    "is_plug": variables["is_plug"],
                },
                stubbed=True,
                hidden=None,
                unrecognized=None,
                default_display_name=None,
                initial_state_config=config_ttypes.StateConfig(
                    id="",
                    title="",
                    peripheral_configuration_assignments=[
                        config_ttypes.PeripheralConfigurationAssignment(
                            unique_peripheral_id=config_ttypes.UniquePeripheralID(
                                device_id="ble_mesh",
                                peripheral_id=variables["peripheral_id"],
                            ),
                            peripheral_configuration=config_ttypes.PeripheralConfiguration(
                                peripheral_configuration_template_id=config_ttypes.ConfigurationTemplateID.PERIPHERAL_INFO_INITIAL_STATE,
                                additional_variable_configuration={
                                    "display_name": variables["display_name"],
                                    "room_assignment": lib.serialization.serialize(
                                        config_ttypes.RoomAssignment(
                                            room_ids=variables["room_ids"],
                                        ),
                                    ),
                                },
                            ),
                        ),
                    ],
                )
            ))
        } for variables in switch_variables
    ])
  return device_provision_state


def get_gangbox_peripheral(
    break_circuit: bool = False,
    low_wattage: bool = False,
    break_dimming: bool = False,
    dimmable: bool = False,
    display_name: str = "Light",
    gangbox_id: int = 0,
    minimum_dim_level: int = 0,
    multi_way: bool = False,
    peripheral_type: mb_ttypes.PeripheralType = mb_ttypes.PeripheralType.LIGHT,
    room_ids: typing.Optional[typing.List[str]] = None,
    ulid: str = GANGBOX_ULID,
) -> mb_ttypes.Peripheral:
  room_ids = room_ids or [BEDROOM_ROOM_ID, KITCHEN_ROOM_ID]
  gangbox_peripheral_name = f"gangbox_peripheral_{gangbox_id}"
  return mb_ttypes.Peripheral(
      name=gangbox_peripheral_name,
      peripheral_type=peripheral_type,
      variables={
          "break_circuit": mb_ttypes.Variable(
              name="break_circuit",
              value="1" if break_circuit else "0",
          ),
          "low_wattage": mb_ttypes.Variable(
              name="low_wattage",
              value="1" if low_wattage else "0",
          ),
          "break_dimming": mb_ttypes.Variable(
              name="break_dimming",
              value="1" if break_dimming else "0",
          ),
          "display_name": mb_ttypes.Variable(
              name="display_name",
              value=display_name,
          ),
          "room_assignment": mb_ttypes.Variable(
              name="room_assignment",
              value=lib.serialization.serialize(
                  config_ttypes.RoomAssignment(room_ids),
              ),
          ),
          "multi_way": mb_ttypes.Variable(
              name="multi_way",
              value="1" if multi_way else "0",
          ),
          "dimmable": mb_ttypes.Variable(
              name="dimmable",
              value="1" if dimmable else "0",
          ),
          "minimum_dim_level": mb_ttypes.Variable(
              name="minimum_dim_level",
              value=str(minimum_dim_level),
          ),
          "ulid": mb_ttypes.Variable(
              name="ulid",
              value=ulid,
          ),
      },
  )


def get_hardware_peripheral(tracked_release_stage=hardware_ttypes.SoftwareReleaseStage.STABLE):
  return mb_ttypes.Peripheral(
      name=mb_consts.HARDWARE_IDENTIFIER,
      peripheral_type=mb_ttypes.PeripheralType.HARDWARE,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      variables={
          "current_boot_version": mb_ttypes.Variable(
              name="current_boot_version",
              value="1201SaMpLeVeRsIoN1984",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "current_release_tag": mb_ttypes.Variable(
              name="current_release_tag",
              value="V0.3.1.4.1.5.9",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "num_cap_touch_sliders": mb_ttypes.Variable(
              name="num_cap_touch_sliders",
              value="1",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "tracked_release_stage": mb_ttypes.Variable(
              name="tracked_release_stage",
              value=str(tracked_release_stage),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "soc": mb_ttypes.Variable(
              name="soc",
              value=str(hardware_ttypes.SoC.UNKNOWN),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          )
      },
      timestamp=SUN_MAY_13_2018_22_57_20,
  )


def get_home_config_peripheral(user=None):
  return mb_ttypes.Peripheral(
      name=mb_consts.HOME_CONFIG_IDENTIFIER,
      peripheral_type=mb_ttypes.PeripheralType.HOME_CONFIGURATION,
      variables=dict(
          name=mb_ttypes.Variable(
              name="name",
              value="Adobe Abode",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          local_timezone=mb_ttypes.Variable(
              name="local_timezone",
              value="America/Los_Angeles",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          passcode=mb_ttypes.Variable(
              name="passcode",
              value="0000",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          passcode_enabled=mb_ttypes.Variable(
              name="passcode_enabled",
              value="1",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          primary_user=mb_ttypes.Variable(
              name="primary_user",
              value=lib.serialization.serialize(user) if user else None,
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          rooms=mb_ttypes.Variable(
              name="rooms",
              value=lib.serialization.serialize(
                  config_ttypes.Rooms(
                      rooms={
                          BEDROOM_ROOM_ID: config_ttypes.Room(
                              id=BEDROOM_ROOM_ID,
                              name="Bedroom",
                          ),
                          KITCHEN_ROOM_ID: config_ttypes.Room(
                              id=KITCHEN_ROOM_ID,
                              name="Kitchen",
                          ),
                          LIVING_ROOM_ROOM_ID: config_ttypes.Room(
                              id=LIVING_ROOM_ROOM_ID,
                              name="Living Room",
                          ),
                      },
                  ),
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          thirdparty_discovery_owner=mb_ttypes.Variable(
              name="thirdparty_discovery_owner",
              value=CONTROL_ID,
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
      ),
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
  )


def get_demo_config_peripheral(variant=demo_ttypes.DemoType.NONE):
  return mb_ttypes.Peripheral(
      name=mb_consts.DEMO_CONFIG_IDENTIFIER,
      peripheral_type=mb_ttypes.PeripheralType.DEMO_CONFIGURATION,
      variables={
          "variant": mb_ttypes.Variable(
              name="variant",
              value=str(variant),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
      },
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
  )


def get_state_config_peripheral(
    configuration_template_id: typing.Optional[str] = None,
    configuration_title: typing.Optional[str] = None,
    scheduled_datetime: typing.Optional[datetime.datetime] = None,
    state_config_id: typing.Optional[str] = None,
) -> mb_ttypes.Peripheral:
  configuration_template_id = configuration_template_id or config_ttypes.ConfigurationTemplateID.VACANT
  configuration_title = configuration_title or "Vacant"
  scheduled_datetime = scheduled_datetime or datetime.datetime(
      year=3020,
      month=12,
      day=10,
      hour=16,
      minute=30,
  )
  scheduled_datetime_seconds_from_midnight = (
      scheduled_datetime - scheduled_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
  ).seconds
  state_config_id = state_config_id or STATE_CONFIG_ULID
  state_config_var_name = lib.tools.peripheral_interface_helpers.format_dynamic_variable_name(
      peripheral_type=mb_ttypes.PeripheralType.STATE_CONFIGURATION,
      variable_suffix=state_config_id,
  )

  variables = dict(
      executing_device_id=mb_ttypes.Variable(
          name="executing_device_id",
          value=CONTROL_ID,
          timestamp=SUN_MAY_13_2018_22_57_20,
          externally_settable=True,
      ),
  )
  variables[state_config_var_name] = mb_ttypes.Variable(
      name=state_config_var_name,
      value=lib.serialization.serialize(
          config_ttypes.StateConfig(
              id=state_config_id,
              title=configuration_title,
              peripheral_configuration_assignments=[
                  config_ttypes.PeripheralConfigurationAssignment(
                      unique_peripheral_id=config_ttypes.UniquePeripheralID(
                          device_id=CONTROL_ID,
                          peripheral_id=mb_consts.MOTION_DETECTION_IDENTIFIER,
                      ),
                      peripheral_configuration=config_ttypes.PeripheralConfiguration(
                          peripheral_configuration_template_id=configuration_template_id,
                      ),
                  )
              ],
              time_trigger=config_ttypes.Trigger(
                  enabled=True,
                  time_range=config_ttypes.ExecutionTimeRange(
                      start_day=config_ttypes.CalendarDay(
                          day_of_month=scheduled_datetime.day,
                          month=scheduled_datetime.month,
                          year=scheduled_datetime.year,
                      ),
                      end_day=config_ttypes.CalendarDay(
                          day_of_month=scheduled_datetime.day,
                          month=scheduled_datetime.month,
                          year=scheduled_datetime.year,
                      ),
                      valid_days_of_week=[1, 2, 3, 4, 5, 6, 7],
                      valid_time_ranges=[
                          config_ttypes.DailyTimeRange(
                              start_seconds_from_midnight=scheduled_datetime_seconds_from_midnight,
                              end_seconds_from_midnight=60 * 60 * 24,
                          ),
                      ],
                  )
              ),
          )
      ),
      timestamp=SUN_MAY_13_2018_22_57_20,
  )

  return mb_ttypes.Peripheral(
      name=mb_consts.STATE_CONFIG_IDENTIFIER,
      peripheral_type=mb_ttypes.PeripheralType.STATE_CONFIGURATION,
      dynamic_variable_prefix=config_consts.STATE_CONFIG_VARIABLE_PREFIX,
      variables=variables,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
  )


def add_mesh_device_to_mesh_config_peripheral(
    mesh_config_peripheral,
    mesh_device_id,
    owner,
    unicast_address,
    mesh_elements=None,
):
  mesh_config_variable_name = lib.tools.peripheral_interface_helpers.format_dynamic_variable_name(
      peripheral_type=mb_ttypes.PeripheralType.MESH_CONFIGURATION,
      variable_suffix=mesh_device_id,
  )
  mesh_config_peripheral.variables.update({
      mesh_config_variable_name: mb_ttypes.Variable(
          name=mesh_config_variable_name,
          value=lib.serialization.serialize(
              get_mesh_peripheral_info(
                  is_plug=False,
                  is_locked=False,
                  name=mesh_device_id,
                  owner=owner,
                  mesh_elements=lib.serialization.serialize(
                      mesh_elements or
                      get_mesh_elements(unicast_address, 0)
                  ),
              ),
          ),
          timestamp=SUN_MAY_13_2018_22_57_20,
      ),
  })


def get_mesh_config_peripheral(
    mesh_device_id=None,
    owner=MESH_PERIPHERAL_OWNER_ID,
    mesh_elements=None,
):
  mesh_config_peripheral = mb_ttypes.Peripheral(
      name=mb_consts.MESH_CONFIG_IDENTIFIER,
      peripheral_type=mb_ttypes.PeripheralType.MESH_CONFIGURATION,
      variables=dict(
          app_keys=mb_ttypes.Variable(
              name="app_keys",
              value=lib.serialization.serialize(
                  bluetooth_ttypes.AppKeys(
                      keys=[],
                  ),
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          net_keys=mb_ttypes.Variable(
              name="net_keys",
              value=lib.serialization.serialize(
                  bluetooth_ttypes.NetKeys(
                      keys=[],
                  ),
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          iv_index=mb_ttypes.Variable(
              name="iv_index",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          iv_index_update_mode_trigger_time_ms=mb_ttypes.Variable(
              name="iv_index_update_mode_trigger_time_ms",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          iv_index_recovery_time_ms=mb_ttypes.Variable(
              name="iv_index_recovery_time_ms",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          relay_arbiter_device_id=mb_ttypes.Variable(
              name="relay_arbiter_device_id",
              value="123",
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          next_unicast_address=mb_ttypes.Variable(
              name="next_unicast_address",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
      ),
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      dynamic_variable_prefix=bt_consts.MESH_CONFIG_VARIABLE_PREFIX,
  )
  if mesh_device_id:
    add_mesh_device_to_mesh_config_peripheral(
        mesh_config_peripheral=mesh_config_peripheral,
        mesh_device_id=mesh_device_id,
        owner=owner,
        unicast_address=87,
        mesh_elements=mesh_elements,
    )
  return mesh_config_peripheral


def get_configuration_virtual_device(peripheral_overrides=None):
  """
  Returns a Device thrift object with expected peripherals.
  Please add to this to make it more robust!
  """
  device = mb_ttypes.Device(
      id=mb_consts.CONFIGURATION_VIRTUAL_DEVICE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      peripherals={
          mb_consts.HOME_CONFIG_IDENTIFIER: get_home_config_peripheral(),
          mb_consts.STATE_CONFIG_IDENTIFIER: get_state_config_peripheral(),
          mb_consts.SONOS_CONFIG_IDENTIFIER: get_sonos_configuration_peripheral(),
          mb_consts.WEMO_CONFIG_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.WEMO_CONFIG_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.WEMO_CONFIGURATION,
              dynamic_variable_prefix=mb_consts.PROCESS_CONFIGURATION_VARIABLE_PREFIX,
              variables=dict(
                  owner=mb_ttypes.Variable(
                      name="owner",
                      value=CONTROL_ID,
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
                  thirdparty_integration_state=mb_ttypes.Variable(
                      name="thirdparty_integration_state",
                      value=lib.serialization.serialize(
                          config_ttypes.ThirdpartyIntegrationState(
                              oauth_status=config_consts.OAuthStatus.NEVER_ATTEMPTED,
                          )
                      ),
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
              ),
              status=mb_ttypes.PeripheralStatus.ONLINE,
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          mb_consts.DEMO_CONFIG_IDENTIFIER: get_demo_config_peripheral(),
          mb_consts.REMOTE_BRIDGE_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.REMOTE_BRIDGE_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.REMOTE_BRIDGE,
              variables={
                  "owner": mb_ttypes.Variable(
                      name="owner",
                      value="",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
              },
              status=mb_ttypes.PeripheralStatus.ONLINE,
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          mb_consts.MESH_CONFIG_IDENTIFIER: get_mesh_config_peripheral(),
          mb_consts.SCENE_CONFIG_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.SCENE_CONFIG_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.LIGHT,
              variables={
                  "scene:all_off": mb_ttypes.Variable(
                      name="scene:all_off",
                      value=lib.serialization.serialize(
                          config_ttypes.Scene(
                              actions=[],
                              id="all_off",
                              title="All Lights Off",
                              icon_url=None,
                              multi_actions=[],
                          )
                      ),
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
              },
              timestamp=None,
          ),
      },
  )
  return apply_peripheral_overrides(peripheral_overrides=peripheral_overrides, device=device)


def get_sonos_configuration_peripheral(variables=None):
  variables = variables or {}
  sonos_config_variables = dict(
      owner=mb_ttypes.Variable(
          name="owner",
          value=CONTROL_ID,
          timestamp=SUN_MAY_13_2018_22_57_20,
          externally_settable=True,
      ),
      thirdparty_integration_state=mb_ttypes.Variable(
          name="thirdparty_integration_state",
          value=lib.serialization.serialize(
              config_ttypes.ThirdpartyIntegrationState(
                  oauth_status=config_consts.OAuthStatus.AUTHORIZED,
              )
          ),
          timestamp=SUN_MAY_13_2018_22_57_20,
          externally_settable=True,
      ),
  )
  sonos_config_variables.update(variables)
  return mb_ttypes.Peripheral(
      name=mb_consts.SONOS_CONFIG_IDENTIFIER,
      peripheral_type=mb_ttypes.PeripheralType.SONOS_CONFIGURATION,
      dynamic_variable_prefix=mb_consts.PROCESS_CONFIGURATION_VARIABLE_PREFIX,
      variables=sonos_config_variables,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
  )


def get_configuration_virtual_device_dict():
  """
  Returns a python dictionary representing what the base config virtual device thrift object would
  look like if serialized using the JSON protocol.
  """
  return dict(
      id=mb_consts.CONFIGURATION_VIRTUAL_DEVICE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      peripherals={
          mb_consts.HOME_CONFIG_IDENTIFIER: dict(
              name=mb_consts.HOME_CONFIG_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.HOME_CONFIGURATION,
              variables=dict(
                  name=dict(
                      name="name",
                      value="Adobe Abode",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=1,
                  ),
              ),
              status=mb_ttypes.PeripheralStatus.ONLINE,
              timestamp=SUN_MAY_13_2018_22_57_20,
              deleted_variables=[],
          ),
          mb_consts.SONOS_CONFIG_IDENTIFIER: dict(
              name=mb_consts.SONOS_CONFIG_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.SONOS_CONFIGURATION,
              dynamic_variable_prefix=mb_consts.PROCESS_CONFIGURATION_VARIABLE_PREFIX,
              variables=dict(
                  owner=dict(
                      name="owner",
                      value=CONTROL_ID,
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=1,
                  ),
                  thirdparty_integration_state=dict(
                      name="thirdparty_integration_state",
                      value=dict(
                          oauth_status=config_consts.OAuthStatus.AUTHORIZED,
                      ),
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=1,
                  ),
              ),
              status=mb_ttypes.PeripheralStatus.ONLINE,
              timestamp=SUN_MAY_13_2018_22_57_20,
              deleted_variables=[],
          ),
          mb_consts.WEMO_CONFIG_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.WEMO_CONFIG_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.WEMO_CONFIGURATION,
              dynamic_variable_prefix=mb_consts.PROCESS_CONFIGURATION_VARIABLE_PREFIX,
              variables=dict(
                  owner=dict(
                      name="owner",
                      value=CONTROL_ID,
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=1,
                  ),
                  thirdparty_integration_state=dict(
                      name="thirdparty_integration_state",
                      value=dict(
                          oauth_status=config_consts.OAuthStatus.NEVER_ATTEMPTED,
                      ),
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=1,
                  ),
              ),
              status=mb_ttypes.PeripheralStatus.ONLINE,
              timestamp=SUN_MAY_13_2018_22_57_20,
              deleted_variables=[],
          ),
      },
  )


def get_ble_mesh_switch_light_peripheral(name=SWITCH_ULID,
                                         wattage_status=STANDARD_WATTAGE_STATUS,
                                         magnetic_status=NOT_MAGNETIC_WATTAGE_STATUS,
                                         dimmable=False,
                                         max_intensity_power_reading=175,
                                         minimum_dim_level="0",
                                         room_ids=None,
                                         display_name="Brilliant Switch Light",
                                         peripheral_type=mb_ttypes.PeripheralType.LIGHT,
                                         on=False,
                                         timestamp=SUN_MAY_13_2018_22_57_20,
                                         intensity=1000):
  # NOTE: Variables currently correspond to PeripheralType.LIGHT
  room_ids = room_ids if room_ids is not None else [LIVING_ROOM_ROOM_ID]
  return mb_ttypes.Peripheral(
      name=name,
      variables={
          "on": mb_ttypes.Variable(
              name="on",
              value="1" if on else "0",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "high_wattage_power_threshold": mb_ttypes.Variable(
              name="high_wattage_power_threshold",
              value="550",
              timestamp=0,
              externally_settable=True,
          ),
          "enable_compatibility_check": mb_ttypes.Variable(
              name="enable_compatibility_check",
              value="0",
              timestamp=1594420482837,
              externally_settable=True,
          ),
          "dimmable": mb_ttypes.Variable(
              name="dimmable",
              value=str(int(dimmable)),
              timestamp=0,
              externally_settable=True,
          ),
          "intensity": mb_ttypes.Variable(
              name="intensity",
              value=str(intensity),
              timestamp=0,
              externally_settable=True,
          ),
          "movement_detected": mb_ttypes.Variable(
              name="movement_detected",
              value="0",
              timestamp=0,
              externally_settable=False,
          ),
          "api_version": mb_ttypes.Variable(
              name="api_version",
              value="0",
              timestamp=0,
              externally_settable=False,
          ),
          "room_assignment": mb_ttypes.Variable(
              name="room_assignment",
              value=lib.serialization.serialize(config_ttypes.RoomAssignment(room_ids)),
              timestamp=0,
              externally_settable=True,
          ),
          "ota_update_status": mb_ttypes.Variable(
              name="ota_update_status",
              value="0",
              timestamp=1594420482837,
              externally_settable=False,
          ),
          "display_name": mb_ttypes.Variable(
              name="display_name",
              value=display_name,
              timestamp=0,
              externally_settable=True,
          ),
          "temperature": mb_ttypes.Variable(
              name="temperature",
              value="0.00",
              timestamp=0,
              externally_settable=False,
          ),
          "wattage_status": mb_ttypes.Variable(
              name="wattage_status",
              value=str(wattage_status),
              timestamp=0,
              externally_settable=False,
          ),
          "magnetic_status": mb_ttypes.Variable(
              name="magnetic_status",
              value=str(magnetic_status),
              timestamp=0,
              externally_settable=False,
          ),
          "max_intensity_power_reading": mb_ttypes.Variable(
              name="max_intensity_power_reading",
              value=str(max_intensity_power_reading),
              timestamp=0,
              externally_settable=False,
          ),
          "minimum_dim_level": mb_ttypes.Variable(
              name="minimum_dim_level",
              value=minimum_dim_level,
              timestamp=0,
              externally_settable=True,
          ),
          "motion_high_threshold": mb_ttypes.Variable(
              name="motion_high_threshold",
              value="25",
              timestamp=0,
              externally_settable=True,
          ),
          "motion_low_threshold": mb_ttypes.Variable(
              name="motion_low_threshold",
              value="14",
              timestamp=0,
              externally_settable=True,
          ),
          "amps_safe_max_threshold": mb_ttypes.Variable(
              name="amps_safe_max_threshold",
              value="5500",
              timestamp=0,
              externally_settable=True,
          ),
          "configuration_peripheral_id": mb_ttypes.Variable(
              name="configuration_peripheral_id",
              value="mesh_configuration",
              timestamp=0,
              externally_settable=False,
          ),
          mb_consts.PERIPHERAL_INFO_ID_VARIABLE_NAME: mb_ttypes.Variable(
              name=mb_consts.PERIPHERAL_INFO_ID_VARIABLE_NAME,
              value=name,
              timestamp=0,
              externally_settable=False,
          ),
          "maximum_dim_level": mb_ttypes.Variable(
              name="maximum_dim_level",
              value="1000",
              timestamp=0,
              externally_settable=True,
          ),
      },
      peripheral_type=peripheral_type,
      dynamic_variable_prefix=None,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=timestamp,
      deleted_variables=[],
      version=version_constants.VERSION_20190903,
  )


def get_ble_mesh_switch_config_peripheral(name_suffix: str = SWITCH_ULID,
                                          slider_config_peripheral_id: typing.Optional[str] = None,
                                          slider_config_device_id: str = mb_consts.BLE_MESH_VIRTUAL_DEVICE,
                                          display_name: str = "Brilliant Switch Light",
                                          double_tap_scene_id: str = "all_off",
                                          room_ids: typing.Optional[typing.List[str]] = None,
                                          firmware_version: typing.Optional[bluetooth_ttypes.MeshDeviceFirmware] = None,
                                          slider_controls_group: bool = False
) -> mb_ttypes.Peripheral:
  room_ids = room_ids if room_ids is not None else [LIVING_ROOM_ROOM_ID]
  slider_config_peripheral_id = slider_config_peripheral_id or name_suffix
  firmware_version = (
      firmware_version
      if firmware_version is not None
      else bluetooth_ttypes.MeshDeviceFirmware(
          application_version=1000,
          bootloader_version=2,
          firmware_version="00000200e8030000",
      )
  )
  slider_peripheral_filter = (
      None
      if not slider_controls_group
      else config_ttypes.PeripheralFilter(
          group_ids={"group123"}
      )
  )
  name = "switch_config:{}".format(name_suffix)
  return mb_ttypes.Peripheral(
      name=name,
      variables={
          "status_light_max_brightness": mb_ttypes.Variable(
              name="status_light_max_brightness",
              value="1000",
              timestamp=0,
              externally_settable=True,
          ),
          "peripheral_configuration": mb_ttypes.Variable(
              name="peripheral_configuration",
              value=lib.serialization.serialize(
                  config_ttypes.PeripheralConfiguration(
                      peripheral_configuration_template_id=2,
                      additional_variable_configuration={
                          "display_name": name,
                      },
                  ),
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "firmware_version": mb_ttypes.Variable(
              name="firmware_version",
              value=lib.serialization.serialize(firmware_version),
              timestamp=0,
              externally_settable=False,
          ),
          "display_name": mb_ttypes.Variable(
              name="display_name",
              value=display_name,
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "configuration_peripheral_id": mb_ttypes.Variable(
              name="configuration_peripheral_id",
              value="mesh_configuration",
              timestamp=0,
              externally_settable=False,
          ),
          mb_consts.PERIPHERAL_INFO_ID_VARIABLE_NAME: mb_ttypes.Variable(
              name=mb_consts.PERIPHERAL_INFO_ID_VARIABLE_NAME,
              value=name_suffix,
              timestamp=0,
              externally_settable=False,
          ),
          "room_assignment": mb_ttypes.Variable(
              name="room_assignment",
              value=lib.serialization.serialize(
                  config_ttypes.RoomAssignment(room_ids),
              ),
              timestamp=0,
              externally_settable=True,
          ),
          "ota_update_status": mb_ttypes.Variable(
              name="ota_update_status",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "slider_config": mb_ttypes.Variable(
              name="slider_config",
              value=lib.serialization.serialize(
                  config_ttypes.CapTouchSliderConfig(
                      peripheral_id=slider_config_peripheral_id,
                      index=0,
                      device_id=slider_config_device_id,
                      double_tap_scene_id=double_tap_scene_id,
                      disable_tap=None,
                      peripheral_filter=slider_peripheral_filter,
                  ),
              ),
              timestamp=0,
              externally_settable=True,
          ),
          "dcdc_regulator_enable": mb_ttypes.Variable(
              name="dcdc_regulator_enable",
              value="0",
              timestamp=0,
              externally_settable=True,
          ),
      },
      peripheral_type=mb_ttypes.PeripheralType.SWITCH_CONFIGURATION,
      dynamic_variable_prefix=config_consts.LIGHT_MOTION_CONFIG_VARIABLE_PREFIX,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      deleted_variables=[],
      version=version_constants.VERSION_20190903,
  )


def get_ble_mesh_plug_peripheral(name=PLUG_ULID, room_ids=None, firmware_version=None):
  room_ids = room_ids if room_ids is not None else [LIVING_ROOM_ROOM_ID]
  firmware_version = (
      firmware_version
      if firmware_version is not None
      else bluetooth_ttypes.MeshDeviceFirmware(
          application_version=1000,
          bootloader_version=2,
          firmware_version="00000200e8030000",
      )
  )
  return mb_ttypes.Peripheral(
      name=name,
      variables={
          "status_light_max_brightness": mb_ttypes.Variable(
              name="status_light_max_brightness",
              value="1000",
              timestamp=0,
              externally_settable=True,
          ),
          "peripheral_configuration": mb_ttypes.Variable(
              name="peripheral_configuration",
              value=lib.serialization.serialize(
                  config_ttypes.PeripheralConfiguration(
                      peripheral_configuration_template_id=2,
                      additional_variable_configuration={
                          "display_name": name,
                      },
                  ),
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "firmware_version": mb_ttypes.Variable(
              name="firmware_version",
              value=lib.serialization.serialize(firmware_version),
              timestamp=0,
              externally_settable=False,
          ),
          "display_name": mb_ttypes.Variable(
              name="display_name",
              value="Brilliant Plug",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          mb_consts.CONFIGURATION_PERIPHERAL_ID_VARIABLE_NAME: mb_ttypes.Variable(
              name=mb_consts.CONFIGURATION_PERIPHERAL_ID_VARIABLE_NAME,
              value="mesh_configuration",
              timestamp=0,
              externally_settable=False,
          ),
          mb_consts.PERIPHERAL_INFO_ID_VARIABLE_NAME: mb_ttypes.Variable(
              name=mb_consts.PERIPHERAL_INFO_ID_VARIABLE_NAME,
              value=name,
              timestamp=0,
              externally_settable=False,
          ),
          "room_assignment": mb_ttypes.Variable(
              name="room_assignment",
              value=lib.serialization.serialize(
                  config_ttypes.RoomAssignment(room_ids),
              ),
              timestamp=0,
              externally_settable=True,
          ),
          "ota_update_status": mb_ttypes.Variable(
              name="ota_update_status",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "last_advertised_dfu_packet": mb_ttypes.Variable(
              name="last_advertised_dfu_packet",
              value=lib.serialization.serialize(
                  mesh_dfu_ttypes.MeshDfuPacket(
                      packet_type=mesh_dfu_ttypes.MeshDfuPacketType.UNKNOWN,
                      raw_data=b'',
                  ),
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "api_version": mb_ttypes.Variable(
              name="api_version",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "enable_fwid_packet_broadcast": mb_ttypes.Variable(
              name="enable_fwid_packet_broadcast",
              value="1",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
      },
      peripheral_type=mb_ttypes.PeripheralType.BRILLIANT_PLUG,
      dynamic_variable_prefix=None,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      deleted_variables=[],
      version=version_constants.VERSION_20190903,
  )


def get_ble_mesh_device(
    control_id=None,
    peripheral_overrides=None,
    switch_light_peripheral_id: str = SWITCH_ULID,
):
  control_id = control_id or CONTROL_ID
  switch_light_peripheral = get_ble_mesh_switch_light_peripheral(
      name=switch_light_peripheral_id,
  )
  switch_config_peripheral = get_ble_mesh_switch_config_peripheral(
      name_suffix=switch_light_peripheral_id,
  )
  plug_config_peripheral = get_ble_mesh_plug_peripheral()
  plug_load_peripheral = get_ble_mesh_plug_load_peripheral()
  device = mb_ttypes.Device(
      id=mb_consts.BLE_MESH_VIRTUAL_DEVICE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      peripherals={
          mb_consts.REMOTE_BRIDGE_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.REMOTE_BRIDGE_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.REMOTE_BRIDGE,
              status=mb_ttypes.PeripheralStatus.ONLINE,
              variables={
                  "relay_device": mb_ttypes.Variable(
                      name="relay_device",
                      value=control_id,
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
              },
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          switch_config_peripheral.name: switch_config_peripheral,
          switch_light_peripheral.name: switch_light_peripheral,
          plug_config_peripheral.name: plug_config_peripheral,
          plug_load_peripheral.name: plug_load_peripheral,
      },
  )
  return apply_peripheral_overrides(peripheral_overrides=peripheral_overrides, device=device)


def get_ble_mesh_plug_load_peripheral(
    peripheral_info_id=PLUG_ULID,
    room_ids=None,
    on=False,
    display_name="Brilliant Plug",
    status=mb_ttypes.PeripheralStatus.ONLINE,
    peripheral_type=mb_ttypes.PeripheralType.OUTLET,
    timestamp=SUN_MAY_13_2018_22_57_20,
):
  # NOTE: Variables currently correspond to PeripheralType.OUTLET
  room_ids = room_ids if room_ids is not None else [LIVING_ROOM_ROOM_ID]
  return mb_ttypes.Peripheral(
      name="{}_0".format(peripheral_info_id),
      peripheral_type=peripheral_type,
      variables={
          mb_consts.PERIPHERAL_INFO_ID_VARIABLE_NAME: mb_ttypes.Variable(
              name=mb_consts.PERIPHERAL_INFO_ID_VARIABLE_NAME,
              value=peripheral_info_id,
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "display_name": mb_ttypes.Variable(
              name="display_name",
              value=display_name,
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "peripheral_configuration": mb_ttypes.Variable(
              name="peripheral_configuration",
              value=lib.serialization.serialize(
                  config_ttypes.PeripheralConfiguration(
                      peripheral_configuration_template_id=UNKNOWN_CONFIGURATION_TEMPLATE_ID,
                      additional_variable_configuration=None,
                  ),
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "break_circuit": mb_ttypes.Variable(
              name="break_circuit",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "load_index": mb_ttypes.Variable(
              name="load_index",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "ota_update_status": mb_ttypes.Variable(
              name="ota_update_status",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          mb_consts.CONFIGURATION_PERIPHERAL_ID_VARIABLE_NAME: mb_ttypes.Variable(
              name=mb_consts.CONFIGURATION_PERIPHERAL_ID_VARIABLE_NAME,
              value="mesh_configuration",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "room_assignment": mb_ttypes.Variable(
              name="room_assignment",
              value=lib.serialization.serialize(
                  config_ttypes.RoomAssignment(room_ids),
              ),
              timestamp=0,
              externally_settable=True,
          ),
          "on": mb_ttypes.Variable(
              name="on",
              value="1" if on else "0",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
      },
      dynamic_variable_prefix=None,
      status=status,
      timestamp=timestamp,
      deleted_variables=[],
      version=version_constants.VERSION_20190903,
  )


def get_mesh_elements(unicast_address=87, index=0):
  return bluetooth_ttypes.MeshElements(
      mesh_elements=[
          bluetooth_ttypes.MeshElement(
              index=index,
              unicast_address=unicast_address,
              models=[
                  bluetooth_ttypes.Model(app_key_indexes=[0], id=2),
                  bluetooth_ttypes.Model(app_key_indexes=[0], id=4096),
                  bluetooth_ttypes.Model(app_key_indexes=[0], id=4098),
                  bluetooth_ttypes.Model(app_key_indexes=[0], id=1)
              ],
          )
      ]
  )


def get_mesh_peripheral_info(
    is_plug=False,
    is_locked=False,
    mesh_elements=None,
    name='01727d07dc240007ab2d80eefcbf6f70',
    **kwargs
):
  mesh_elements = mesh_elements or lib.serialization.serialize(get_mesh_elements())
  params = dict(
      peripheral_type=mb_consts.PeripheralType.LIGHT,
      hidden=False,
      name=name,
      configuration_variables={
          'is_plug': str(int(is_plug)),
          'lock_owner': str(int(is_locked)),
          'initial_magnetic_status': '1',
          'initial_wattage_status': '1',
          'mac_address': '7c:10:15:01:36:f7',
          'max_intensity_power_reading': '175',
          'device_key': '20FF86CE7CCBB20F5F9F58B9C43E3F5B',
          'mesh_elements': mesh_elements
      },
      owner=MESH_PERIPHERAL_OWNER_ID,
      default_display_name='',
      configuration_peripheral_id=mb_consts.MESH_CONFIG_IDENTIFIER,
  )
  params.update(kwargs)
  return config_ttypes.PeripheralInfo(**params)


def get_plug_initial_state_config(
    mesh_device_id: str = "0175547d31c00008ea4c99208e124d29",
    load_display_name: str = "Living Room Lamp",
    load_room_ids: typing.Optional[typing.List[str]] = None,
    plug_display_name: str = "Living Room Plug",
    plug_room_ids: typing.Optional[typing.List[str]] = None,
) -> config_ttypes.StateConfig:
  load_room_ids = load_room_ids or ["1"]
  plug_room_ids = plug_room_ids or ["1"]
  return config_ttypes.StateConfig(
      id="",
      title="",
      peripheral_configuration_assignments=[
          config_ttypes.PeripheralConfigurationAssignment(
              unique_peripheral_id=config_ttypes.UniquePeripheralID(
                  device_id=mb_consts.BLE_MESH_VIRTUAL_DEVICE,
                  peripheral_id=f"{mesh_device_id}_0",
              ),
              peripheral_configuration=config_ttypes.PeripheralConfiguration(
                  peripheral_configuration_template_id=config_ttypes.ConfigurationTemplateID.PERIPHERAL_INFO_INITIAL_STATE,
                  additional_variable_configuration={
                      "display_name": load_display_name,
                      "room_assignment": lib.serialization.serialize(
                          config_ttypes.RoomAssignment(load_room_ids)
                      ),
                  },
              ),
          ),
          config_ttypes.PeripheralConfigurationAssignment(
              unique_peripheral_id=config_ttypes.UniquePeripheralID(
                  device_id=mb_consts.BLE_MESH_VIRTUAL_DEVICE,
                  peripheral_id=mesh_device_id,
              ),
              peripheral_configuration=config_ttypes.PeripheralConfiguration(
                  peripheral_configuration_template_id=config_ttypes.ConfigurationTemplateID.PERIPHERAL_INFO_INITIAL_STATE,
                  additional_variable_configuration={
                      "display_name": plug_display_name,
                      "room_assignment": lib.serialization.serialize(
                          config_ttypes.RoomAssignment(plug_room_ids)
                      ),
                  },
              ),
          ),
      ],
  )


def get_switch_initial_state_config(
    mesh_device_id: str = "01727d07dc240007ab2d80eefcbf6f70",
    load_display_name: str = "Bedroom Light",
    load_room_ids: typing.Optional[typing.List[str]] = None,
    switch_display_name: str = "Bedroom Switch",
    switch_room_ids: typing.Optional[typing.List[str]] = None,
) -> config_ttypes.StateConfig:
  load_room_ids = load_room_ids or ["0"]
  switch_room_ids = switch_room_ids or ["0"]
  return config_ttypes.StateConfig(
      id="",
      title="",
      peripheral_configuration_assignments=[
          config_ttypes.PeripheralConfigurationAssignment(
              unique_peripheral_id=config_ttypes.UniquePeripheralID(
                  device_id=mb_consts.BLE_MESH_VIRTUAL_DEVICE,
                  peripheral_id=mesh_device_id,
              ),
              peripheral_configuration=config_ttypes.PeripheralConfiguration(
                  peripheral_configuration_template_id=config_ttypes.ConfigurationTemplateID.PERIPHERAL_INFO_INITIAL_STATE,
                  additional_variable_configuration={
                      "display_name": load_display_name,
                      "room_assignment": lib.serialization.serialize(
                          config_ttypes.RoomAssignment(load_room_ids)
                      ),
                  },
              ),
          ),
          config_ttypes.PeripheralConfigurationAssignment(
              unique_peripheral_id=config_ttypes.UniquePeripheralID(
                  device_id=mb_consts.BLE_MESH_VIRTUAL_DEVICE,
                  peripheral_id=f"{bt_consts.SWITCH_CONFIG_PERIPHERAL_PREFIX}{mesh_device_id}"
              ),
              peripheral_configuration=config_ttypes.PeripheralConfiguration(
                  peripheral_configuration_template_id=config_ttypes.ConfigurationTemplateID.PERIPHERAL_INFO_INITIAL_STATE,
                  additional_variable_configuration={
                      "display_name": switch_display_name,
                      "room_assignment": lib.serialization.serialize(
                          config_ttypes.RoomAssignment(switch_room_ids)
                      ),
                      "slider_config": lib.serialization.serialize(
                          config_ttypes.CapTouchSliderConfig(
                              index=0,
                              device_id=mb_consts.BLE_MESH_VIRTUAL_DEVICE,
                              peripheral_id=mesh_device_id,
                              disable_tap=None,
                              double_tap_scene_id=None,
                          )
                      ),
                  },
              ),
          ),
      ],
  )


def get_butterflymx_building_entry_panel_peripheral(name="panel_123"):
  """Returns a Peripheral object with expected values for a ButterflyMX Building Entry Panel
  peripheral.
  """
  return mb_ttypes.Peripheral(
      name=name,
      peripheral_type=mb_ttypes.PeripheralType.BUILDING_ENTRY_PANEL,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      variables={
          "event": mb_ttypes.Variable(
              name="event",
              value=lib.serialization.serialize(mb_ttypes.Event()),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "thirdparty_display_name": mb_ttypes.Variable(
              name="thirdparty_display_name",
              value="ButterflyMX Panel",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "call_guid": mb_ttypes.Variable(
              name="call_guid",
              value="",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "video_call_answering_device_id": mb_ttypes.Variable(
              name="video_call_answering_device_id",
              value="",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "call_offer_sdp": mb_ttypes.Variable(
              name="call_offer_sdp",
              value="",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "call_answer_sdp": mb_ttypes.Variable(
              name="call_answer_sdp",
              value="",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "call_preview_image": mb_ttypes.Variable(
              name="call_preview_image",
              value="",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "media_transmitted": mb_ttypes.Variable(
              name="media_transmitted",
              value=str(remote_media_ttypes.MediaTransmission.NONE),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "grant_access": mb_ttypes.Variable(
              name="grant_access",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "chime_setting": mb_ttypes.Variable(
              name="chime_setting",
              value="2",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "configuration_peripheral_id": mb_ttypes.Variable(
              name="configuration_peripheral_id",
              value=mb_consts.BUTTERFLYMX_CONFIG_IDENTIFIER,
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False
          ),
      },
  )


def get_butterflymx_building_peripheral(name="building_123", building_entry_panel_ids=None):
  """Returns a Peripheral object with expected values for a ButterflyMX Building peripheral."""
  building_entry_panel_ids = building_entry_panel_ids or []
  return mb_ttypes.Peripheral(
      name=name,
      peripheral_type=mb_ttypes.PeripheralType.MANAGED_BUILDING,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      variables={
          "thirdparty_display_name": mb_ttypes.Variable(
              name="thirdparty_display_name",
              value="ButterflyMX Building",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "building_entry_panels": mb_ttypes.Variable(
              name="building_entry_panels",
              value=lib.serialization.serialize(
                  butterflymx_ttypes.BuildingEntryPanels(building_entry_panel_ids)
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
      },
  )


def get_butterflymx_device(control_id=CONTROL_ID, peripheral_overrides=None):
  """Returns a Device thrift object with expected peripherals for a ButterflyMX Virtual Device."""
  building_entry_peripheral = get_butterflymx_building_entry_panel_peripheral()
  building_peripheral = get_butterflymx_building_peripheral(
      building_entry_panel_ids=[building_entry_peripheral.name],
  )
  device = mb_ttypes.Device(
      id=mb_consts.BUTTERFLYMX_IDENTIFIER,
      timestamp=SUN_MAY_13_2018_22_57_20,
      peripherals={
          mb_consts.REMOTE_BRIDGE_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.REMOTE_BRIDGE_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.REMOTE_BRIDGE,
              status=mb_ttypes.PeripheralStatus.ONLINE,
              variables={
                  "relay_device": mb_ttypes.Variable(
                      name="relay_device",
                      value=control_id,
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
              },
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          building_entry_peripheral.name: building_entry_peripheral,
          building_peripheral.name: building_peripheral,
      },
  )
  return apply_peripheral_overrides(peripheral_overrides=peripheral_overrides, device=device)


def get_ecobee_thermostat_peripheral(
    name: str = "ecobee_thermostat_54321",
    thirdparty_display_name: str = "Ecobee Thermostat",
    ambient_temperature_f: int = 71,
):
  """Returns a Peripheral object with typical values for an Ecobee thermostat peripheral."""
  return mb_ttypes.Peripheral(
      name=name,
      variables={
          "target_temperature_high_f": mb_ttypes.Variable(
              name="target_temperature_high_f",
              value="82",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "thermostat_capabilities": mb_ttypes.Variable(
              name="thermostat_capabilities",
              value=lib.serialization.serialize(
                  thermostat_ttypes.ThermostatCapabilities(
                      supported_hvac_modes=[1, 2, 3, 4],
                      supported_fan_modes=[],
                      supports_fan_timer=False,
                  )
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "thirdparty_display_units": mb_ttypes.Variable(
              name="thirdparty_display_units",
              value="1",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "temperature_ranges": mb_ttypes.Variable(
              name="temperature_ranges",
              value=lib.serialization.serialize(
                  thermostat_ttypes.TemperatureRanges(
                      target_temperature_range=thermostat_ttypes.TemperatureRange(
                          min_f=60,
                          max_f=75,
                      ),
                      target_temperature_low_range=thermostat_ttypes.TemperatureRange(
                          min_f=60,
                          max_f=75,
                      ),
                      target_temperature_high_range=thermostat_ttypes.TemperatureRange(
                          min_f=60,
                          max_f=75,
                      ),
                      heat_cool_min_delta=5,
                  )
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "fan_mode": mb_ttypes.Variable(
              name="fan_mode",
              value=None,
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "display_name": mb_ttypes.Variable(
              name="display_name",
              value="",
              timestamp=0,
              externally_settable=True,
          ),
          "target_temperature_f": mb_ttypes.Variable(
              name="target_temperature_f",
              value="65",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "configuration_peripheral_id": mb_ttypes.Variable(
              name="configuration_peripheral_id",
              value="ecobee_configuration",
              timestamp=0,
              externally_settable=False,
          ),
          "thirdparty_display_name": mb_ttypes.Variable(
              name="thirdparty_display_name",
              value=thirdparty_display_name,
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "hvac_mode": mb_ttypes.Variable(
              name="hvac_mode",
              value="4",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "room_assignment": mb_ttypes.Variable(
              name="room_assignment",
              value=lib.serialization.serialize(
                  config_ttypes.RoomAssignment(LIVING_ROOM_ROOM_ID),
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "ambient_temperature_f": mb_ttypes.Variable(
              name="ambient_temperature_f",
              value=str(ambient_temperature_f),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "target_temperature_low_f": mb_ttypes.Variable(
              name="target_temperature_low_f",
              value="65",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "current_revision": mb_ttypes.Variable(
              name="current_revision",
              value="210519175620:210519172206",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
      },
      peripheral_type=mb_ttypes.PeripheralType.THERMOSTAT,
      dynamic_variable_prefix=None,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      deleted_variables=[],
      version="20190903",
  )


def get_ecobee_device(control_id: str = CONTROL_ID, peripheral_overrides=None):
  """Returns a Device thrift object with the expected peripherals for an Ecobee thermostat."""

  ecobee_thermostat_peripheral = get_ecobee_thermostat_peripheral()
  device = mb_ttypes.Device(
      id=mb_consts.ECOBEE_IDENTIFIER,
      timestamp=SUN_MAY_13_2018_22_57_20,
      peripherals={
          mb_consts.REMOTE_BRIDGE_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.REMOTE_BRIDGE_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.REMOTE_BRIDGE,
              status=mb_ttypes.PeripheralStatus.ONLINE,
              variables={
                  "relay_device": mb_ttypes.Variable(
                      name="relay_device",
                      value=control_id,
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
              },
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          ecobee_thermostat_peripheral.name: ecobee_thermostat_peripheral,
      }
  )
  return apply_peripheral_overrides(peripheral_overrides=peripheral_overrides, device=device)


def get_honeywell_climate_sensor_peripheral(
    name: str = "honeywell_climate_sensor_demo_123",
    climate_alarms: list[int] | None = None,
    battery_status: battery_ttypes.BatteryStatus = battery_ttypes.BatteryStatus.NORMAL,
):
  """Returns a Peripheral object with typical values for a Honeywell leak detector peripheral."""
  if climate_alarms is None:
    climate_alarms = []

  return mb_ttypes.Peripheral(
      name=name,
      variables={
          "ambient_humidity": mb_ttypes.Variable(
              name="ambient_humidity",
              value="48.8",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "ambient_temperature_f": mb_ttypes.Variable(
              name="ambient_temperature_f",
              value="71",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "battery_status": mb_ttypes.Variable(
              name="battery_status",
              value=str(battery_status),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "climate_alarms": mb_ttypes.Variable(
              name="climate_alarms",
              value=lib.serialization.serialize(
                  climate_sensor_ttypes.ClimateAlarms(climate_alarms=climate_alarms),
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "configuration_peripheral_id": mb_ttypes.Variable(
              name="configuration_peripheral_id",
              value="honeywell_configuration",
              timestamp=0,
              externally_settable=False,
          ),
          "display_name": mb_ttypes.Variable(
              name="display_name",
              value="",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "room_assignment": mb_ttypes.Variable(
              name="room_assignment",
              value=lib.serialization.serialize(
                  config_ttypes.RoomAssignment(room_ids=[KITCHEN_ROOM_ID]),
              ),
              timestamp=0,
              externally_settable=True,
          ),
          "thirdparty_display_name": mb_ttypes.Variable(
              name="thirdparty_display_name",
              value="Kitchen Sink Leak Detector",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
      },
      peripheral_type=mb_ttypes.PeripheralType.CLIMATE_SENSOR,
      dynamic_variable_prefix=None,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      deleted_variables=[],
      version=version_constants.VERSION_20200923,
  )


def get_honeywell_climate_sensor_peripheral_info(
    name: str = "37670512-8f4e-46c7-a5c5-1cb0e606206e",
    default_display_name: str = "Water Cabbage",
    display_name: str = "Water Cabbage Custom Name",
) -> config_ttypes.PeripheralInfo:
  """Returns a PeripheralInfo object with typical values for a Honeywell leak detector."""
  return config_ttypes.PeripheralInfo(
      owner=mb_consts.HONEYWELL_IDENTIFIER,
      name=name,
      peripheral_type=mb_ttypes.PeripheralType.CLIMATE_SENSOR,
      thirdparty_device_id="1285894",
      configuration_peripheral_id=mb_consts.HONEYWELL_CONFIG_IDENTIFIER,
      default_display_name=default_display_name,
      initial_state_config=config_ttypes.StateConfig(
          id="",
          title="",
          peripheral_configuration_assignments=[
              config_ttypes.PeripheralConfigurationAssignment(
                  unique_peripheral_id=config_ttypes.UniquePeripheralID(
                      device_id=mb_consts.HONEYWELL_IDENTIFIER,
                      peripheral_id=name,
                  ),
                  peripheral_configuration=config_ttypes.PeripheralConfiguration(
                      peripheral_configuration_template_id=config_ttypes.ConfigurationTemplateID.PERIPHERAL_INFO_INITIAL_STATE,
                      additional_variable_configuration={
                          "room_assignment": lib.serialization.serialize(
                              config_ttypes.RoomAssignment(room_ids=["1"]),
                          ),
                          "display_name": display_name,
                      }
                  )
              ),
          ],
      ),
  )


def get_honeywell_thermostat_peripheral(
    name: str = "honeywell_thermostat_12345",
    ambient_temperature_f: int = 71,
):
  """Returns a Peripheral object with typical values for a Honeywell thermostat peripheral."""
  return mb_ttypes.Peripheral(
      name=name,
      variables={
          "schedule_type": mb_ttypes.Variable(
              name="schedule_type",
              value=None,
              timestamp=None,
              externally_settable=False,
          ),
          "target_temperature_high_f": mb_ttypes.Variable(
              name="target_temperature_high_f",
              value=None,
              timestamp=None,
              externally_settable=False,
          ),
          "thermostat_capabilities": mb_ttypes.Variable(
              name="thermostat_capabilities",
              value=lib.serialization.serialize(
                  thermostat_ttypes.ThermostatCapabilities(
                      supported_hvac_modes=[2, 3, 1],
                      supported_fan_modes=[3, 2, 4],
                      supports_fan_timer=False,
                  )
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "thirdparty_display_units": mb_ttypes.Variable(
              name="thirdparty_display_units",
              value="1",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "peripheral_configuration": mb_ttypes.Variable(
              name="peripheral_configuration",
              value=lib.serialization.serialize(
                  config_ttypes.PeripheralConfiguration(
                      peripheral_configuration_template_id=2,
                      additional_variable_configuration={
                          "display_name": name,
                      },
                  ),
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "temperature_ranges": mb_ttypes.Variable(
              name="temperature_ranges",
              value=lib.serialization.serialize(
                  thermostat_ttypes.TemperatureRanges(
                      target_temperature_range=thermostat_ttypes.TemperatureRange(
                          min_f=50,
                          max_f=55,
                      ),
                      target_temperature_low_range=thermostat_ttypes.TemperatureRange(
                          min_f=50,
                          max_f=55,
                      ),
                      target_temperature_high_range=thermostat_ttypes.TemperatureRange(
                          min_f=50,
                          max_f=55,
                      ),
                      heat_cool_min_delta=0,
                  )
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "fan_mode": mb_ttypes.Variable(
              name="fan_mode",
              value="3",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "display_name": mb_ttypes.Variable(
              name="display_name",
              value="Living Room Honeywell Thermostat",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "target_temperature_f": mb_ttypes.Variable(
              name="target_temperature_f",
              value="65",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "configuration_peripheral_id": mb_ttypes.Variable(
              name="configuration_peripheral_id",
              value="honeywell_configuration",
              timestamp=0,
              externally_settable=False,
          ),
          "thirdparty_display_name": mb_ttypes.Variable(
              name="thirdparty_display_name",
              value="Round",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "hvac_mode": mb_ttypes.Variable(
              name="hvac_mode",
              value="2",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "room_assignment": mb_ttypes.Variable(
              name="room_assignment",
              value=lib.serialization.serialize(
                  config_ttypes.RoomAssignment(LIVING_ROOM_ROOM_ID),
              ),
              timestamp=0,
              externally_settable=True,
          ),
          "ambient_temperature_f": mb_ttypes.Variable(
              name="ambient_temperature_f",
              value=str(ambient_temperature_f),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "target_temperature_low_f": mb_ttypes.Variable(
              name="target_temperature_low_f",
              value=None,
              timestamp=None,
              externally_settable=False,
          ),
          "model_name": mb_ttypes.Variable(
              name="model_name",
              value="Lyric Round",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          )
      },
      peripheral_type=mb_ttypes.PeripheralType.THERMOSTAT,
      dynamic_variable_prefix=None,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      deleted_variables=[],
      version="20190903",
  )


def get_honeywell_thermostat_peripheral_info(
    name: str = "LCC-B82CA00FCE12",
    display_name: str = "",
) -> config_ttypes.PeripheralInfo:
  """Returns a PeripheralInfo object with typical values for a Honeywell thermostat."""
  return config_ttypes.PeripheralInfo(
      owner=mb_consts.HONEYWELL_IDENTIFIER,
      name=name,
      peripheral_type=4,
      thirdparty_device_id="1285894",
      configuration_peripheral_id=mb_consts.HONEYWELL_CONFIG_IDENTIFIER,
      initial_state_config=config_ttypes.StateConfig(
          id="",
          title="",
          peripheral_configuration_assignments=[
              config_ttypes.PeripheralConfigurationAssignment(
                  unique_peripheral_id=config_ttypes.UniquePeripheralID(
                      device_id=mb_consts.HONEYWELL_IDENTIFIER,
                      peripheral_id=name,
                  ),
                  peripheral_configuration=config_ttypes.PeripheralConfiguration(
                      peripheral_configuration_template_id=config_ttypes.ConfigurationTemplateID.PERIPHERAL_INFO_INITIAL_STATE,
                      additional_variable_configuration={
                          "room_assignment": lib.serialization.serialize(
                              config_ttypes.RoomAssignment(room_ids=["1"]),
                          ),
                          "display_name": display_name,
                      }
                  )
              )
          ],
      ),
  )


def get_honeywell_device(control_id: str = CONTROL_ID, peripheral_overrides=None):
  """Returns a Device thrift object for a Honeywell device.

  The device contains a Honeywell thermostat peripheral and a Honeywell leak detector peripheral.
  """

  honeywell_climate_sensor_peripheral = get_honeywell_climate_sensor_peripheral()
  honeywell_thermostat_peripheral = get_honeywell_thermostat_peripheral()
  device = mb_ttypes.Device(
      id=mb_consts.HONEYWELL_IDENTIFIER,
      timestamp=SUN_MAY_13_2018_22_57_20,
      peripherals={
          mb_consts.REMOTE_BRIDGE_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.REMOTE_BRIDGE_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.REMOTE_BRIDGE,
              status=mb_ttypes.PeripheralStatus.ONLINE,
              variables={
                  "relay_device": mb_ttypes.Variable(
                      name="relay_device",
                      value=control_id,
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
              },
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          honeywell_climate_sensor_peripheral.name: honeywell_climate_sensor_peripheral,
          honeywell_thermostat_peripheral.name: honeywell_thermostat_peripheral,
      }
  )
  return apply_peripheral_overrides(peripheral_overrides=peripheral_overrides, device=device)


def get_nest_structure_peripheral(name="12345ABCDE", thermostat_ids=None):
  """Returns a Peripheral object with expected values for a Nest Structure peripheral."""
  thermostat_ids = thermostat_ids or None
  return mb_ttypes.Peripheral(
      name=name,
      peripheral_type=mb_ttypes.PeripheralType.NEST_STRUCTURE,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      variables={
          "thirdparty_display_name": mb_ttypes.Variable(
              name="thirdparty_display_name",
              value="Nest Structure 1234",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "thermostat_ids": mb_ttypes.Variable(
              name="thermostat_ids",
              value=lib.serialization.serialize(nest_ttypes.ThermostatIds(thermostat_ids)),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
      },
  )


def get_nest_thermostat_peripheral(
    name: str = "ABCDE12345",
    ambient_temperature_f: int = 70,
):
  """Returns a Peripheral object with expected values for a Nest Thermostat peripheral."""
  return mb_ttypes.Peripheral(
      name=name,
      peripheral_type=mb_ttypes.PeripheralType.THERMOSTAT,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      variables={
          "thirdparty_display_name": mb_ttypes.Variable(
              name="thirdparty_display_name",
              value="Nest Thermostat 1234",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "target_temperature_f": mb_ttypes.Variable(
              name="target_temperature_f",
              value="70",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "ambient_temperature_f": mb_ttypes.Variable(
              name="ambient_temperature_f",
              value=str(ambient_temperature_f),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "thermostat_capabilities": mb_ttypes.Variable(
              name="thermostat_capabilities",
              value=lib.serialization.serialize(
                  thermostat_ttypes.ThermostatCapabilities(supported_hvac_modes=[],
                                                           supported_fan_modes=[])
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "hvac_mode": mb_ttypes.Variable(
              name="hvac_mode",
              value=str(thermostat_ttypes.HVACMode.OFF),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "fan_mode": mb_ttypes.Variable(
              name="fan_mode",
              value=str(thermostat_ttypes.FanMode.OFF),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "structure_id": mb_ttypes.Variable(
              name="structure_id",
              value="1234",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "fan_timer_duration": mb_ttypes.Variable(
              name="fan_timer_duration",
              value=str(thermostat_ttypes.FanTimerDuration.FIFTEEN_MINS),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "target_temperature_low_f": mb_ttypes.Variable(
              name="target_temperature_low_f",
              value="50",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "target_temperature_high_f": mb_ttypes.Variable(
              name="target_temperature_high_f",
              value="55",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "eco_temperature_low_f": mb_ttypes.Variable(
              name="eco_temperature_low_f",
              value="50",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "eco_temperature_high_f": mb_ttypes.Variable(
              name="eco_temperature_high_f",
              value="55",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "temperature_ranges": mb_ttypes.Variable(
              name="temperature_ranges",
              value=lib.serialization.serialize(
                  thermostat_ttypes.TemperatureRanges(
                      target_temperature_range=thermostat_ttypes.TemperatureRange(
                          min_f=50,
                          max_f=55,
                      ),
                      target_temperature_low_range=thermostat_ttypes.TemperatureRange(
                          min_f=50,
                          max_f=55,
                      ),
                      target_temperature_high_range=thermostat_ttypes.TemperatureRange(
                          min_f=50,
                          max_f=55,
                      ),
                      heat_cool_min_delta=nest_consts.HEAT_COOL_MIN_DELTA,
                  )
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "is_locked": mb_ttypes.Variable(
              name="is_locked",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "thirdparty_display_units": mb_ttypes.Variable(
              name="thirdpart_display_units",
              value=str(thermostat_ttypes.TemperatureUnits.FAHRENHEIT),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "configuration_peripheral_id": mb_ttypes.Variable(
              name="configuration_peripheral_id",
              value=mb_consts.NEST_CONFIG_IDENTIFIER,
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False
          ),
      },
  )


def get_nest_device(control_id=CONTROL_ID, peripheral_overrides=None):
  """Returns a Device thrift object with expected peripherals for a Nest Virtual Device."""
  thermostat_peripheral = get_nest_thermostat_peripheral()
  structure_peripheral = get_nest_structure_peripheral(thermostat_ids=thermostat_peripheral.name)
  device = mb_ttypes.Device(
      id=mb_consts.NEST_IDENTIFIER,
      timestamp=SUN_MAY_13_2018_22_57_20,
      peripherals={
          mb_consts.REMOTE_BRIDGE_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.REMOTE_BRIDGE_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.REMOTE_BRIDGE,
              status=mb_ttypes.PeripheralStatus.ONLINE,
              variables={
                  "relay_device": mb_ttypes.Variable(
                      name="relay_device",
                      value=control_id,
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
              },
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          structure_peripheral.name: structure_peripheral,
          thermostat_peripheral.name: thermostat_peripheral,
      },
  )
  return apply_peripheral_overrides(peripheral_overrides=peripheral_overrides, device=device)


def get_post_provision_state_config(
    state_config_id: str = "",
    device_id: typing.Optional[str] = None,
    control_name: str = "control name",
    time_trigger_start_datetime: typing.Optional[datetime.datetime] = None,
    time_trigger_end_datetime: typing.Optional[datetime.datetime] = None,
) -> config_ttypes.StateConfig:
  """Returns a StateConfig object with example values for a 3G Control. If device_id is None,
  assume there is no device in the home.
  """
  if not device_id:
    return config_ttypes.StateConfig(
        id=state_config_id,
        title="",
        peripheral_configuration_assignments=[],
    )
  now = datetime.datetime.now()
  time_trigger_start_datetime = time_trigger_start_datetime or now
  time_trigger_end_datetime = time_trigger_end_datetime or now
  return config_ttypes.StateConfig(
      id=state_config_id,
      title="",
      peripheral_configuration_assignments=[
          config_ttypes.PeripheralConfigurationAssignment(
              unique_peripheral_id=config_ttypes.UniquePeripheralID(
                  device_id=device_id,
                  peripheral_id=mb_consts.DEVICE_CONFIG_IDENTIFIER,
              ),
              peripheral_configuration=config_ttypes.PeripheralConfiguration(
                  peripheral_configuration_template_id=config_ttypes.ConfigurationTemplateID.VACANT,
                  additional_variable_configuration={
                      "device_name": control_name,
                      "room_assignment": lib.serialization.serialize(
                          config_ttypes.RoomAssignment(room_ids=["0"])
                      ),
                      "slider_config:0": lib.serialization.serialize(
                          config_ttypes.CapTouchSliderConfig(
                              index=0,
                              device_id=device_id,
                              peripheral_id="gangbox_peripheral_0",
                          ),
                      ),
                      "slider_config:1": lib.serialization.serialize(
                          config_ttypes.CapTouchSliderConfig(
                              index=1,
                              device_id=device_id,
                              peripheral_id="gangbox_peripheral_1",
                          ),
                      ),
                      "slider_config:2": lib.serialization.serialize(
                          config_ttypes.CapTouchSliderConfig(
                              index=2,
                              device_id="",
                              peripheral_id="",
                          ),
                      ),
                      "gesture_configs": lib.serialization.serialize(
                          config_ttypes.GestureConfigs(gesture_configs={
                              config_ttypes.GestureType.SINGLE: [
                                  # May want to check with product again to see what the exact logic they want here is.
                                  # By default, we only configure SINGLE finger gestures for 1G.
                                  # For 1G, if the load is ALWAYS_ON, then this would just be an empty list
                                  config_ttypes.GestureConfig(
                                      gesture_type=config_ttypes.GestureType.SINGLE,
                                      device_id=device_id,
                                      peripheral_id="gangbox_peripheral_0",
                                  ),
                              ],
                              config_ttypes.GestureType.TWO: [
                                  config_ttypes.GestureConfig(
                                      gesture_type=config_ttypes.GestureType.TWO,
                                      device_id=device_id,
                                      peripheral_id=mb_consts.DEVICE_CONFIG_IDENTIFIER,
                                  ),
                              ],
                          })
                      ),
                  },
              ),
          ),
          config_ttypes.PeripheralConfigurationAssignment(
              unique_peripheral_id=config_ttypes.UniquePeripheralID(
                  device_id=device_id,
                  peripheral_id=mb_consts.GANGBOX_CONFIG_IDENTIFIER,
              ),
              peripheral_configuration=config_ttypes.PeripheralConfiguration(
                  peripheral_configuration_template_id=config_ttypes.ConfigurationTemplateID.VACANT,
                  additional_variable_configuration={
                      "process_config:0": lib.serialization.serialize(
                          config_ttypes.PeripheralInfo(
                              owner=device_id,
                              name='gangbox_peripheral_0',
                              peripheral_type=mb_ttypes.PeripheralType.LIGHT,
                              configuration_peripheral_id=mb_consts.GANGBOX_CONFIG_IDENTIFIER,
                              configuration_variables={
                                  'gang_identifier': '0',
                                  'uart_identifier': '0',
                              },
                              initial_state_config=config_ttypes.StateConfig(
                                  id="",
                                  title="",
                                  peripheral_configuration_assignments=[
                                      config_ttypes.PeripheralConfigurationAssignment(
                                          unique_peripheral_id=config_ttypes.UniquePeripheralID(
                                              device_id=device_id,
                                              peripheral_id="gangbox_peripheral_0",
                                          ),
                                          peripheral_configuration=config_ttypes.PeripheralConfiguration(
                                              peripheral_configuration_template_id=config_ttypes.ConfigurationTemplateID.PERIPHERAL_INFO_INITIAL_STATE,
                                              additional_variable_configuration={
                                                  "display_name": "process_config:0 name",
                                                  "room_assignment": lib.serialization.serialize(
                                                      config_ttypes.RoomAssignment(room_ids=["0"])
                                                  ),
                                                  "low_wattage": "0",
                                                  "multi_way": "0",
                                                  "dimmable": "1",
                                                  "minimum_dim_level": "83",
                                              },
                                          ),
                                      ),
                                  ],
                              ),
                          )
                      ),
                      "process_config:1": lib.serialization.serialize(
                          config_ttypes.PeripheralInfo(
                              owner=device_id,
                              name='gangbox_peripheral_1',
                              peripheral_type=mb_ttypes.PeripheralType.GENERIC_ON_OFF,
                              configuration_peripheral_id=mb_consts.GANGBOX_CONFIG_IDENTIFIER,
                              configuration_variables={
                                  'gang_identifier': '1',
                                  'uart_identifier': '0',
                              },
                              initial_state_config=config_ttypes.StateConfig(
                                  id="",
                                  title="",
                                  peripheral_configuration_assignments=[
                                      config_ttypes.PeripheralConfigurationAssignment(
                                          unique_peripheral_id=config_ttypes.UniquePeripheralID(
                                              device_id=device_id,
                                              peripheral_id="gangbox_peripheral_1",
                                          ),
                                          peripheral_configuration=config_ttypes.PeripheralConfiguration(
                                              peripheral_configuration_template_id=config_ttypes.ConfigurationTemplateID.PERIPHERAL_INFO_INITIAL_STATE,
                                              additional_variable_configuration={
                                                  "display_name": "process_config:1 name",
                                                  "room_assignment": lib.serialization.serialize(
                                                      config_ttypes.RoomAssignment(room_ids=["0"])
                                                  ),
                                              },
                                          ),
                                      ),
                                  ],
                              ),
                          )
                      ),
                      "process_config:2": lib.serialization.serialize(
                          config_ttypes.PeripheralInfo(
                              owner=device_id,
                              name='gangbox_peripheral_2',
                              peripheral_type=mb_ttypes.PeripheralType.ALWAYS_ON,
                              configuration_peripheral_id=mb_consts.GANGBOX_CONFIG_IDENTIFIER,
                              configuration_variables={
                                  'gang_identifier': '0',
                                  'uart_identifier': '1',
                              },
                              initial_state_config=config_ttypes.StateConfig(
                                  id="",
                                  title="",
                                  peripheral_configuration_assignments=[
                                      config_ttypes.PeripheralConfigurationAssignment(
                                          unique_peripheral_id=config_ttypes.UniquePeripheralID(
                                              device_id=device_id,
                                              peripheral_id="gangbox_peripheral_2",
                                          ),
                                          peripheral_configuration=config_ttypes.PeripheralConfiguration(
                                              peripheral_configuration_template_id=config_ttypes.ConfigurationTemplateID.PERIPHERAL_INFO_INITIAL_STATE,
                                              additional_variable_configuration={
                                                  "display_name": "process_config:2 name",
                                                  "room_assignment": lib.serialization.serialize(
                                                      config_ttypes.RoomAssignment(room_ids=["0"])
                                                  ),
                                              },
                                          ),
                                      ),
                                  ],
                              ),
                          )
                      ),
                  },
              ),
          ),
      ],
  )


def get_ring_doorbell_peripheral(name="doorbell_12345"):
  """Returns a Peripheral object with expected values for a Ring Doorbell.

  Please add to this to make it more robust!
  """
  return mb_ttypes.Peripheral(
      name=name,
      peripheral_type=mb_ttypes.PeripheralType.DOORBELL,
      dynamic_variable_prefix=remote_media_consts.LIVE_VIEW_SESSION_PREFIX,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      variables={
          "video_call_active": mb_ttypes.Variable(
              name="video_call_active",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True
          ),
          "limited_functionality": mb_ttypes.Variable(
              name="limited_functionality",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True
          ),
          "room_assignment": mb_ttypes.Variable(
              name="room_assignment",
              value=lib.serialization.serialize(
                  config_ttypes.RoomAssignment(LIVING_ROOM_ROOM_ID),
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "model_name": mb_ttypes.Variable(
              name="model_name",
              value=None,
              timestamp=None,
              externally_settable=False
          ),
          "display_name": mb_ttypes.Variable(
              name="display_name",
              value="",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True
          ),
          "remote_sessions": mb_ttypes.Variable(
              name="remote_sessions",
              value=lib.serialization.serialize(
                  remote_media_ttypes.RemoteMediaSessions(remote_sessions=[]),
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False
          ),
          "chime_setting": mb_ttypes.Variable(
              name="chime_setting",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True
          ),
          "last_ding": mb_ttypes.Variable(
              name="last_ding",
              value=None,
              timestamp=None,
              externally_settable=True
          ),
          "video_call_answering_device_id": mb_ttypes.Variable(
              name="video_call_answering_device_id",
              value="",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True
          ),
          "thirdparty_display_name": mb_ttypes.Variable(
              name="thirdparty_display_name",
              value="Ring Doorbell demo",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False
          ),
          "configuration_peripheral_id": mb_ttypes.Variable(
              name="configuration_peripheral_id",
              value="ring_configuration",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False
          ),
      },
  )


def get_ring_device(control_id=CONTROL_ID, peripheral_overrides=None):
  """
  Returns a Device thrift object with expected peripherals for a Ring Virtual Device.
  Please add to this to make it more robust!
  """
  DOORBELL_NAME = "doorbell_12345"
  device = mb_ttypes.Device(
      id=mb_consts.RING_VIRTUAL_DEVICE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      peripherals={
          mb_consts.REMOTE_BRIDGE_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.REMOTE_BRIDGE_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.REMOTE_BRIDGE,
              status=mb_ttypes.PeripheralStatus.ONLINE,
              variables={
                  "relay_device": mb_ttypes.Variable(
                      name="relay_device",
                      value=control_id,
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
              },
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          DOORBELL_NAME: get_ring_doorbell_peripheral(name=DOORBELL_NAME),
      },
  )
  return apply_peripheral_overrides(peripheral_overrides=peripheral_overrides, device=device)


def get_sonos_music_library_peripheral(name=None, dynamic_variables=None):
  """Returns a Peripheral object with expected values for a Sonos Music Library."""
  name = name or "{}_{}".format(mb_consts.SONOS_MUSIC_LIRBARY_PREFIX, "12345")
  dynamic_variables = dynamic_variables or {}
  music_library_variables = {
      "favorites_version": mb_ttypes.Variable(
          name="favorites_version",
          value="",
          timestamp=SUN_MAY_13_2018_22_57_20,
          externally_settable=False,
      ),
      "favorites": mb_ttypes.Variable(
          name="favorites",
          value=lib.serialization.serialize(music_ttypes.Playlists(playlists=[])),
          timestamp=SUN_MAY_13_2018_22_57_20,
          externally_settable=False,
      ),
      "playlists_version": mb_ttypes.Variable(
          name="playlists_version",
          value="",
          timestamp=SUN_MAY_13_2018_22_57_20,
          externally_settable=False,
      ),
      "playlists": mb_ttypes.Variable(
          name="playlists",
          value=lib.serialization.serialize(music_ttypes.Playlists(playlists=[])),
          timestamp=SUN_MAY_13_2018_22_57_20,
          externally_settable=False,
      ),
      "line_in_sources": mb_ttypes.Variable(
          name="line_in_sources",
          value=lib.serialization.serialize(music_ttypes.Playlists(playlists=[])),
          timestamp=SUN_MAY_13_2018_22_57_20,
          externally_settable=False,
      ),
  }
  music_library_variables.update(dynamic_variables)
  return mb_ttypes.Peripheral(
      name=name,
      peripheral_type=mb_ttypes.PeripheralType.MUSIC_LIBRARY,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      variables=music_library_variables,
  )


def get_sonos_device(control_id=CONTROL_ID, peripheral_overrides=None):
  """
  Returns a Device thrift object with expected peripherals for a sonos.
  Please add to this to make it more robust!
  """
  music_library_peripheral = get_sonos_music_library_peripheral()
  device = mb_ttypes.Device(
      id=mb_consts.SONOS_IDENTIFIER,
      timestamp=SUN_MAY_13_2018_22_57_20,
      peripherals={
          mb_consts.REMOTE_BRIDGE_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.REMOTE_BRIDGE_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.REMOTE_BRIDGE,
              status=mb_ttypes.PeripheralStatus.ONLINE,
              variables={
                  "relay_device": mb_ttypes.Variable(
                      name="relay_device",
                      value=control_id,
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
              },
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          "5C-AA-FD-7C-68-BE:8": mb_ttypes.Peripheral(
              name="5C-AA-FD-7C-68-BE:8",
              peripheral_type=mb_ttypes.PeripheralType.MUSIC,
              status=mb_ttypes.PeripheralStatus.ONLINE,
              variables={
                  "volume": mb_ttypes.Variable(
                      name="volume",
                      value="0",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True
                  ),
                  "configuration_peripheral_id": mb_ttypes.Variable(
                      name="configuration_peripheral_id",
                      value=mb_consts.SONOS_CONFIG_IDENTIFIER,
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
                  "model_name": mb_ttypes.Variable(
                      name="model_name",
                      value="Sonos PLAY:1",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False
                  ),
                  "display_name": mb_ttypes.Variable(
                      name="display_name",
                      value="Kitchen",
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=True,
                  ),
              },
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          music_library_peripheral.name: music_library_peripheral,
      },
  )
  return apply_peripheral_overrides(peripheral_overrides=peripheral_overrides, device=device)


def get_wemo_device(control_id=CONTROL_ID, peripheral_overrides=None):
  """
  Returns a Device thrift object with expected peripherals for a wemo.
  Please add to this to make it more robust!
  """
  device = mb_ttypes.Device(
      id=mb_consts.WEMO_IDENTIFIER,
      timestamp=SUN_MAY_13_2018_22_57_20,
      peripherals={
          mb_consts.REMOTE_BRIDGE_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.REMOTE_BRIDGE_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.REMOTE_BRIDGE,
              status=mb_ttypes.PeripheralStatus.ONLINE,
              variables={
                  "relay_device": mb_ttypes.Variable(
                      name="relay_device",
                      value=control_id,
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
              },
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
      },
  )
  return apply_peripheral_overrides(peripheral_overrides=peripheral_overrides, device=device)


def get_remotelock_peripheral(
    name: str = "remotelock_54321",
    thirdparty_display_name: str = "RemoteLock Lock 123",
) -> mb_ttypes.Peripheral:
  """Returns a Peripheral object with typical values for a RemoteLock peripheral."""
  return mb_ttypes.Peripheral(
      name=name,
      variables={
          "display_name": mb_ttypes.Variable(
              name="display_name",
              value="",
              timestamp=0,
              externally_settable=True,
          ),
          "configuration_peripheral_id": mb_ttypes.Variable(
              name="configuration_peripheral_id",
              value=mb_consts.REMOTELOCK_CONFIG_IDENTIFIER,
              timestamp=0,
              externally_settable=False,
          ),
          "thirdparty_display_name": mb_ttypes.Variable(
              name="thirdparty_display_name",
              value=thirdparty_display_name,
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "room_assignment": mb_ttypes.Variable(
              name="room_assignment",
              value=lib.serialization.serialize(
                  config_ttypes.RoomAssignment(LIVING_ROOM_ROOM_ID),
              ),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "current_revision": mb_ttypes.Variable(
              name="current_revision",
              value="210519175620:210519172206",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "battery_status": mb_ttypes.Variable(
              name="battery_status",
              value=str(battery_ttypes.BatteryStatus.NORMAL),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "event": mb_ttypes.Variable(
              name="event",
              value=lib.serialization.serialize(mb_ttypes.Event()),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
          "is_common_area": mb_ttypes.Variable(
              name="is_common_area",
              value="0",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "lock_status": mb_ttypes.Variable(
              name="lock_status",
              value=str(lock_ttypes.LockStatus.NORMAL),
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=False,
          ),
          "locked": mb_ttypes.Variable(
              name="locked",
              value="1",
              timestamp=SUN_MAY_13_2018_22_57_20,
              externally_settable=True,
          ),
      },
      peripheral_type=mb_ttypes.PeripheralType.LOCK,
      dynamic_variable_prefix=None,
      status=mb_ttypes.PeripheralStatus.ONLINE,
      timestamp=SUN_MAY_13_2018_22_57_20,
      deleted_variables=[],
      version="20190903",
  )


def get_remotelock_device(
    control_id=CONTROL_ID,
    peripheral_overrides=None,
) -> mb_ttypes.Device:
  """
  Returns a Device thrift object with expected peripherals for a RemoteLock.
  Please add to this to make it more robust!
  """
  lock_peripheral = get_remotelock_peripheral()
  device = mb_ttypes.Device(
      id=mb_consts.REMOTELOCK_IDENTIFIER,
      timestamp=SUN_MAY_13_2018_22_57_20,
      peripherals={
          mb_consts.REMOTE_BRIDGE_IDENTIFIER: mb_ttypes.Peripheral(
              name=mb_consts.REMOTE_BRIDGE_IDENTIFIER,
              peripheral_type=mb_ttypes.PeripheralType.REMOTE_BRIDGE,
              status=mb_ttypes.PeripheralStatus.ONLINE,
              variables={
                  "relay_device": mb_ttypes.Variable(
                      name="relay_device",
                      value=control_id,
                      timestamp=SUN_MAY_13_2018_22_57_20,
                      externally_settable=False,
                  ),
              },
              timestamp=SUN_MAY_13_2018_22_57_20,
          ),
          lock_peripheral.name: lock_peripheral,
      },
  )
  return apply_peripheral_overrides(peripheral_overrides=peripheral_overrides, device=device)


def object_metadata(**kwargs):
  params = dict(
      brilliant_content_encoding="gzip",
      content_type="text/html; charset=utf-8",
      content_encoding="identity",
      device_id=CONTROL_ID,
      home_id=HOME_ID,
      name="Really_cool_data",
      size=len(b"12345"),
  )
  params.update(kwargs)
  return lib.storage.interface.ObjectMetadata(**params)
