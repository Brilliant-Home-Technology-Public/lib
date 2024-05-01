class RetryValueManager:

  def __init__(self, loop, last_value_timeout_seconds, set_value_func, max_retries=3,
               set_value_failure_callback=None):
    self.loop = loop
    self.last_requested_value = None
    self.last_acknowledged_value = None
    self.value_missing_handle = None
    self.last_value_timeout = last_value_timeout_seconds
    # The function that will actually set the value
    self.set_value_func = set_value_func
    self.max_retries = max_retries
    self.set_value_failure_callback = set_value_failure_callback

  def set_value(self, value):
    if self.value_missing_handle:
      self.value_missing_handle.cancel()
    # Schedule the execution of the function in x seconds on the event loop
    self.value_missing_handle = self.loop.call_later(
        self.last_value_timeout,
        self.check_value_missing,
        self.max_retries,
    )
    self.last_requested_value = value
    # Schedule the execution of this coroutine
    self.loop.create_task(self.set_value_func(value))

  def acknowledge_value(self, value):
    self.last_acknowledged_value = value

  def check_value_missing(self, retry_count):
    if self.last_acknowledged_value != self.last_requested_value and retry_count > 0:
      # Schedule the execution of this coroutine
      self.loop.create_task(self.set_value_func(self.last_requested_value))
      self.value_missing_handle = self.loop.call_later(
          self.last_value_timeout,
          self.check_value_missing,
          retry_count - 1,
      )
    elif (self.last_acknowledged_value != self.last_requested_value and
          self.set_value_failure_callback):
      self.loop.create_task(self.set_value_failure_callback(self.last_requested_value))
