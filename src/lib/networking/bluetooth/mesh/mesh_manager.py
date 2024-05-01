import asyncio
import enum
import logging
import threading

from lib.queueing import intervaled_task
import lib.time


log = logging.getLogger(__name__)


class IVIndexUpdateProcedureState(enum.Enum):
  NORMAL = 1          # When iv index update trigger time is 0
  IN_PROGRESS = 2     # When current time < iv index update trigger time + 96hrs
  READY_TO_UPDATE = 3  # When current time >= iv index update trigger time + 96hrs


class NonceInitializers:

  def __init__(self, iv_index, seq_num):
    self.iv_index = iv_index
    self.seq_num = seq_num


class MeshManager:
  '''
  Handles mesh netowrk iv_index updates and key refresh procedues.
  Exposes an interface to get the latest iv_index and sequence numbers.
  '''
  IV_RECOVERY_INCREMENT_LIMIT = 42  # do not recover iv_index if there is more than this change
  IV_RECOVERY_PROCEDURE_LIMIT_MS = 192 * 60 * 60 * 1000  # 192 hours
  IV_UPDATE_PROCEDURE_START_LIMIT_MS = 192 * 60 * 60 * 1000  # 192 hours
  IV_UPDATE_DELAY_SECONDS = 96 * 60 * 60  # increment iv_index 96-144 hours after an update is triggered

  SEQ_MAX = 2 ** 24 - 1
  IV_UPDATE_START_SEQ_THRESHOLD = SEQ_MAX // 2  # rough heuristic
  TRANSPORT_MESSAGE_SEQ_COUNT_MAX = 2 ** 13  # A single message may use this many sequence numbers
  IV_UPDATE_COMPLETE_SEQ_THRESHOLD = SEQ_MAX - TRANSPORT_MESSAGE_SEQ_COUNT_MAX
  # This needs to be computed based on the number of nodes etc but for now, we fix it at 30 secs
  SECURE_BEACON_INTERVAL_SEC = 30

  def __init__(
      self,
      loop,
      datastore,
      beacon_handler,
      send_network_beacon_callback,
      enable_iv_update_test_mode=False,
  ):
    self.datastore = datastore
    self.beacon_handler = beacon_handler
    self.send_network_beacon_callback = send_network_beacon_callback
    self.iv_update_timer = None  # Indicates if an iv_index update procedure is happening
    # Mesh Profile 3.10.5.1 flag for testing iv_update
    self.enable_iv_update_test_mode = enable_iv_update_test_mode
    self.loop = loop
    self.send_secure_network_beacon_task = intervaled_task.IntervaledTask(
        loop=loop,
        interval=self.SECURE_BEACON_INTERVAL_SEC,
        task_func=self._send_network_beacon,
    )
    self.nonce_initializer_lock = threading.RLock()

  async def start(self):
    self.send_secure_network_beacon_task.start(delay_first_job=True)

  async def shutdown(self):
    self.send_secure_network_beacon_task.shutdown()

  def _get_iv_update_procedure_state(self, iv_index_update_trigger_time_ms):
    current_time_ms = lib.time.get_current_time_ms()

    if iv_index_update_trigger_time_ms:
      elapsed_time_since_trigger = current_time_ms - iv_index_update_trigger_time_ms
      delay_to_use = self.IV_UPDATE_DELAY_SECONDS * 1000
      if self.enable_iv_update_test_mode:
        # When the device is in iv update test mode, we use delay of 2 * beacon interval secs.
        # This allows the control to send out SecureNetworkBeacons with iv update flag set
        # to 1 at least once before subsequently sending out SecureNetworkBeacons with
        # iv update flag set back to 0.
        delay_to_use = 2 * self.SECURE_BEACON_INTERVAL_SEC * 1000

      if elapsed_time_since_trigger < delay_to_use:
        return IVIndexUpdateProcedureState.IN_PROGRESS
      return IVIndexUpdateProcedureState.READY_TO_UPDATE

    return IVIndexUpdateProcedureState.NORMAL

  def receive_network_beacon(self, pdu):
    '''
    Mesh Profile 3.10.5

    This function decides when to update the mesh network iv_index
    '''
    netkey = self.datastore.get_netkey()
    current_time_ms = lib.time.get_current_time_ms()
    try:
      iv_update, key_refresh, new_iv_index = self.beacon_handler.parse_network_beacon(netkey, pdu)
    except Exception as e:
      log.warning("Mesh Manager: RX network beacon error: %s", e)
      return

    if key_refresh:
      log.warning("Mesh Manager: RX network beacon key_refresh is not implmented")

    mesh_network_iv_index = self._get_mesh_network_iv_index()
    if mesh_network_iv_index is None:
      # Not part of a home yet. Ignoring network beacon
      log.debug("Mesh Manager: Device not part of home. No update necessary.")
      return

    current_iv_index = mesh_network_iv_index.iv_index

    if new_iv_index == current_iv_index:
      # no iv_index update necessary
      return

    if new_iv_index < current_iv_index:
      log.error("Mesh Manager: RX network beacon iv_index:%s smaller than current: %s",
                new_iv_index, current_iv_index)
      return

    if new_iv_index > (current_iv_index + self.IV_RECOVERY_INCREMENT_LIMIT):
      log.error("Mesh Manager: RX network beacon iv_index jumped more than %d. "
                "Node needs to be re-provisioned",
                self.IV_RECOVERY_INCREMENT_LIMIT)
      return

    if (new_iv_index > (current_iv_index + 1)) or \
        (new_iv_index == (current_iv_index + 1) and not iv_update):
      time_since_last_recovery = \
          current_time_ms - self.datastore.get_mesh_network_iv_index_recovery_time()
      if (time_since_last_recovery < self.IV_RECOVERY_PROCEDURE_LIMIT_MS and
          not self.enable_iv_update_test_mode):
        log.error("Mesh Manager: RX network beacon, can only recover iv_index once every 192 hours")
        return
      log.warning("Mesh Manager: RX network beacon iv_index %s triggered recovery from: %s",
                  new_iv_index, current_iv_index)
      self.datastore.set_mesh_network_iv_index(iv_index=new_iv_index)
      self.datastore.set_mesh_network_iv_index_recovery_time()

    if new_iv_index == (current_iv_index + 1) and iv_update:
      update_procedure_state = self._get_iv_update_procedure_state(
          iv_index_update_trigger_time_ms=mesh_network_iv_index.iv_index_update_trigger_time_ms
      )
      if update_procedure_state != IVIndexUpdateProcedureState.NORMAL:
        # Device is updating. No need to perform recovery
        log.debug("Mesh Manager: Device is updating and no recovery is required.")
        return

      time_since_last_iv_update = \
          current_time_ms - self.datastore.get_mesh_network_iv_index_update_time()
      if (time_since_last_iv_update < self.IV_UPDATE_PROCEDURE_START_LIMIT_MS and
          not self.enable_iv_update_test_mode):
        log.warning(
            "Mesh Manager: RX network beacon, can only start iv_index update once every 192 hours"
        )
        return

      self._update_mesh_network_iv_index(new_iv_index=new_iv_index)

  def initiate_iv_index_update_procedure(self, current_iv_index):
    # Triggering the IV Index Update
    new_iv_index = current_iv_index + 1
    log.info("Mesh Manager: Initiating IV index update procedure.")
    self._update_mesh_network_iv_index(new_iv_index=new_iv_index)

  def complete_iv_index_update_procedure(self):
    log.info("Mesh Manager: Completing IV index update procedure.")
    # Updates seq number to 0 and trigger timestamp to 0
    self._finish_mesh_network_iv_index_update()

  async def _send_network_beacon(self):
    mesh_network_iv_index = await self.datastore.get_mesh_network_iv_index()
    if mesh_network_iv_index is None:
      log.debug("Mesh Manager: Device not part of home. Not sending Secure Network Beacon.")
      return
    netkey = self.datastore.get_netkey()
    if netkey is None:
      log.debug("Mesh Manager: Device not part of network. Not sending Secure Network Beacon.")
      return
    update_procedure_state = self._get_iv_update_procedure_state(
        iv_index_update_trigger_time_ms=mesh_network_iv_index.iv_index_update_trigger_time_ms
    )
    iv_update = 0 if update_procedure_state == IVIndexUpdateProcedureState.NORMAL else 1
    beacon = self.beacon_handler.build_network_beacon(
        netkey=netkey,
        iv_update=iv_update,
        key_refresh=0,
        iv_index=mesh_network_iv_index.iv_index,
    )
    log.debug(
        "Mesh Manager: Sending Secure Network Beacon [iv update flag = %d | iv index = %d].",
        iv_update,
        mesh_network_iv_index.iv_index,
    )
    await self.loop.run_in_executor(None, self.send_network_beacon_callback, beacon)

  def _get_mesh_network_iv_index(self):
    future = asyncio.run_coroutine_threadsafe(
        self.datastore.get_mesh_network_iv_index(),
        self.loop,
    )
    return future.result()

  def _update_mesh_network_iv_index(self, new_iv_index):
    asyncio.run_coroutine_threadsafe(
        self.datastore.update_mesh_network_iv_index(new_iv_index),
        self.loop,
    ).result()

  def _finish_mesh_network_iv_index_update(self):
    asyncio.run_coroutine_threadsafe(
        self.datastore.finish_mesh_network_iv_index_update(),
        self.loop,
    ).result()

  def _roll_over_node_nonce_parameters(self):
    asyncio.run_coroutine_threadsafe(
        self.datastore.roll_over_node_nonce_parameters(),
        self.loop,
    ).result()

  def get_iv_index_for_ivi(self, ivi):
    ''' Used by the NetworkHandler to get iv_index for received messages '''
    mesh_network_iv_index = self._get_mesh_network_iv_index()
    if mesh_network_iv_index is None:
      return None
    if ivi != (mesh_network_iv_index.iv_index & 1):
      return mesh_network_iv_index.iv_index - 1
    return mesh_network_iv_index.iv_index

  def get_nonce_initializers(self):
    with self.nonce_initializer_lock:
      mesh_network_iv_index = self._get_mesh_network_iv_index()
      if mesh_network_iv_index is None:
        log.debug("Mesh Manager: Device not part of home. No nonce initializers found.")
        return None
      update_procedure_state = self._get_iv_update_procedure_state(
          iv_index_update_trigger_time_ms=mesh_network_iv_index.iv_index_update_trigger_time_ms
      )
      node_iv_index = self.datastore.get_node_iv_index()
      next_seq = self.datastore.get_next_seq()

      # When the node iv index has not been initialized, we need to initialize the node iv index
      # with the current mesh iv index.
      if node_iv_index == -1:
        current_node_iv_index = mesh_network_iv_index.iv_index
        if update_procedure_state == IVIndexUpdateProcedureState.IN_PROGRESS:
          current_node_iv_index -= 1

        log.debug("Mesh Manager: Initializing node_iv_index to %d.", current_node_iv_index)
        asyncio.run_coroutine_threadsafe(
            self.datastore.set_node_iv_index(current_node_iv_index),
            self.loop,
        ).result()
        node_iv_index = self.datastore.get_node_iv_index()

      # When update_procedure_state is NORMAL there are 2 distinct possibilities
      #  1) The node_iv_index is not equal to the mesh's iv_index.
      #     The node_iv_index has gotten out of sync with the mesh's iv_index and
      #     has to be updated. The sequence number has to correspondingly be reset
      #     back down to 0.
      #  2) The node_iv_index equals the mesh's iv_index.
      #     If the sequence number is larger than the update threshold, begin the
      #     iv_index update.
      # When update_procedure_state is READY_TO_UPDATE or IN_PROGRESS but the sequence
      # number exceeds a certain threshold, we complete the iv index update procedure
      # so as to not run out of sequence number.
      if update_procedure_state == IVIndexUpdateProcedureState.NORMAL:
        if node_iv_index != mesh_network_iv_index.iv_index:
          log.info(
              "Mesh Manager: Synchronizing node IV Index (%d to %d) & resetting sequence number to "
              "0.",
              node_iv_index,
              mesh_network_iv_index.iv_index,
          )
          self._roll_over_node_nonce_parameters()
          node_iv_index = self.datastore.get_node_iv_index()
          next_seq = self.datastore.get_next_seq()
        elif (node_iv_index == mesh_network_iv_index.iv_index and
              next_seq >= self.IV_UPDATE_START_SEQ_THRESHOLD):
          log.info(
              "Mesh Manager: Current seq_num %d exceeds update start threshold. Updating iv_index.",
              next_seq,
          )
          self.initiate_iv_index_update_procedure(current_iv_index=mesh_network_iv_index.iv_index)

      elif (update_procedure_state == IVIndexUpdateProcedureState.READY_TO_UPDATE or
            (update_procedure_state == IVIndexUpdateProcedureState.IN_PROGRESS and
             next_seq >= self.IV_UPDATE_COMPLETE_SEQ_THRESHOLD)
           ):
        self.complete_iv_index_update_procedure()
        self._roll_over_node_nonce_parameters()
        node_iv_index = self.datastore.get_node_iv_index()
        next_seq = self.datastore.get_next_seq()

      log.debug(
          "Mesh Manager: get_nonce_initializers returned (iv_index = %d, next_seq = %d).",
          node_iv_index,
          next_seq,
      )
      return NonceInitializers(node_iv_index, next_seq)
