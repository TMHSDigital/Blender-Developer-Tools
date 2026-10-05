# Worker thread + queue + timer: do slow work off the main thread and apply
# the result to bpy on it. bpy is not thread-safe, so the worker never
# touches it; a timer (main thread) drains the queue.
#
# - Timers need the event loop: in `blender --background` they never run.
# - Return None from a timer to stop it, a float to run again; returning 0
#   means "again on the next pass", not "stop".
# - first_interval and persistent are keyword-only.
# - persistent=True keeps the timer across File > Open; plain timers are
#   dropped by a file load.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.app.timers.html
#   https://docs.blender.org/api/current/info_gotchas_threading.html

import queue
import threading

import bpy

_results = queue.Queue()


def _worker(job):
    # No bpy in here: compute, download, read files.
    _results.put(job())


def _drain():
    try:
        value = _results.get_nowait()
    except queue.Empty:
        return 0.1  # nothing yet; look again in 0.1 s
    apply_result(value)  # main thread: bpy is safe here
    return None  # done; unregister


def apply_result(value):
    obj = bpy.data.objects.get("Target")
    if obj is not None:
        obj["result"] = value


def run_in_background(job):
    """Start `job` on a worker thread and apply its result when it lands."""
    threading.Thread(target=_worker, args=(job,), daemon=True).start()
    if not bpy.app.timers.is_registered(_drain):
        bpy.app.timers.register(_drain, first_interval=0.1)


def unregister():
    if bpy.app.timers.is_registered(_drain):
        bpy.app.timers.unregister(_drain)
