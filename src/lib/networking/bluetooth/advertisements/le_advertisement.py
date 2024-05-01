import asyncio
import weakref


class LEAdvertisement:
  '''
  This is the base class of all Bluetooth Low Energy Advertisement Packets.

  Instances of this class are registered as objects through pydbus
  '''
  dbus = '''
    <?xml version="1.0" encoding="UTF-8" ?>
    <node>
      <interface name="org.bluez.LEAdvertisement1">
        <method name="Release">
          <annotation name="org.freedesktop.DBus.Method.NoReply" value="true"/>
        </method>

        <annotation name="org.freedesktop.DBus.Properties.PropertiesChanged" value="const"/>

        <property name="Type" type="s" access="read"/>
        <property name="ServiceUUIDs" type="as" access="read"/>
        <property name="ManufacturerData" type="a{qv}" access="read"/>
        <property name="Includes" type="as" access="read"/>
        <property name="SolicitUUIDs" type="as" access="read"/>
        <property name="ServiceData" type="a{sv}" access="read"/>
        <property name="IncludeTxPower" type="b" access="read"/>
        <property name="Appearance" type="q" access="read"/>
        <property name="Duration" type="q" access="read"/>
        <property name="Discoverable" type="b" access="read"/>
        <property name="Timeout" type="q" access="read"/>
      </interface>
    </node>
  '''

  DBUS_OBJECT_NAME_BASE = "tech.brilliant.LEAdvertisement"
  MAX_ADV_TIMEOUT = 20

  def __init__(self, loop, timeout=MAX_ADV_TIMEOUT):
    # NOTE: Only 1 LEAdvertisement object (not including subclasses) can be active at a time.
    #       This is fine for now, since nothing advertises the LEAdvertisement parent class.
    self._dbus_object_name = LEAdvertisement.DBUS_OBJECT_NAME_BASE
    self.adv_release_callback_weak_methods = []
    self.timeout = timeout
    self.loop = loop

  def Release(self):
    for callback_weak_method in self.adv_release_callback_weak_methods:
      callback = callback_weak_method()
      if callback:
        asyncio.run_coroutine_threadsafe(callback(self), self.loop)

  @property
  def Timeout(self):
    return self.timeout

  @property
  def Type(self):
    return "peripheral"

  @property
  def ServiceUUIDs(self):
    return []

  @property
  def Includes(self):
    # BlueZ only partially respects this. Even though we don't put "appearance" in here, it will
    # still try to add it to the advertisement if it's set.
    return []

  @property
  def Discoverable(self):
    return True

  @property
  def ManufacturerData(self):
    return {}

  @property
  def SolicitUUIDs(self):
    return []

  @property
  def ServiceData(self):
    return {}

  @property
  def IncludeTxPower(self):
    return False

  @property
  def LocalName(self):
    return "Brilliant"

  @property
  def Appearance(self):
    # BlueZ now tries to set this into the advertising packet automatically unless it is "unset."
    # When included, the advertising packet is too long and triggers an error.
    return 2**16 - 1  # Max value for an unsigned 16-bit int

  @property
  def Duration(self):
    '''
    int (uint16_t): How long this advertisement packet will be broadcasted for until the system
    moves on to the next queued up advertisement packet. Advertisements are rotated through in a
    round-robin fashion. If this is set to 0, then it will use the BlueZ default. If there are no
    other ongoing advertisements, then this packet will be broadcasted continuously until manually
    stopped or until the 'Timeout' is reached, which ever happens first.

    NOTE: This differs from the 'Timeout' BlueZ parameter in that the 'Timeout' sets a timer for the
          specified length. Once the timer fires, the advertisement automatically stops.
    '''
    return 0

  @property
  def dbus_object_name(self):
    return self._dbus_object_name

  @property
  def dbus_object_path(self):
    return LEAdvertisement._convert_dbus_name_to_path(self._dbus_object_name)

  @staticmethod
  def _convert_dbus_name_to_path(name):
    return "/" + name.replace(".", "/")

  def register_adv_release_callback(self, callback):
    adv_release_callback_weak_methods = weakref.WeakMethod(callback)
    self.adv_release_callback_weak_methods.append(adv_release_callback_weak_methods)
