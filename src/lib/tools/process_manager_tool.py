import asyncio
import sys

from lib.async_helpers import iterable_queue
from lib.process_management.process_manager import ProcessManager


def add_process_request(queue):
  queue.put_nowait(sys.stdin.readline())


async def process_process_request(queue, process_manager):
  async for request in queue:
    try:
      request_components = str(request).strip().split(" ")
      command = request_components.pop(0)
      if command == "add_process":
        process_name = request_components.pop(0)
        process_module = request_components.pop(0)
        process_flagfile = request_components.pop(0) if request_components else None
        process_manager.add_process(process_name, process_module, process_flagfile)
      elif command == "remove_process":
        process_manager.remove_process(request_components.pop(0))
      else:
        print("Unsupported operation:", command)
    except Exception:
      print("Incorrect number of args")

if __name__ == '__main__':
  event_loop = asyncio.get_event_loop()
  input_queue = iterable_queue.IterableQueue()
  event_loop.add_reader(sys.stdin, add_process_request, input_queue)
  manager = ProcessManager()
  # manager.add_process("message_bus", "message_bus")
  task = event_loop.create_task(process_process_request(input_queue, manager))
  try:
    event_loop.run_forever()
  except KeyboardInterrupt:
    pass
  input_queue.shutdown()
  event_loop.run_until_complete(task)
  event_loop.close()
