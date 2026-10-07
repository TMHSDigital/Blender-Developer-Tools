# Worker thread + queue + timer: do slow work off the main thread and apply
# the result to bpy on it. bpy is not thread-safe, so the worker never
# touches it; a timer (main thread) drains the queue.
#
# - Timers need the event loop: in `blender --background` they never run.
# - Return None from a timer to stop it, a float to run again; returning 0
#   means "again on the next pass", not "stop".
# - Count pending jobs: stop the drain only when every job has reported, or
#   a second job's result sits in the queue with no timer to read it.
# - The worker always puts, even when the job raises; otherwise the drain
#   waits for a result that never comes and polls forever.
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
_pending = 0  # jobs started but not yet drained; read and written on the main thread only


def _worker(job):
    # No bpy in here: compute, download, read files.
    try:
        _results.put((True, job()))
    except BaseException as e:
        _results.put((False, e))  # report the failure; never leave the drain waiting


def _drain():
    global _pending
    while True:  # take everything that has landed this tick
        try:
            ok, value = _results.get_nowait()
        except queue.Empty:
            break
        _pending -= 1
        if ok:
            apply_result(value)  # main thread: bpy is safe here
        else:
            print(f"background job failed: {value!r}")
    return 0.1 if _pending else None  # unregister only once every job is in


def apply_result(value):
    obj = bpy.data.objects.get("Target")
    if obj is not None:
        obj["result"] = value


def run_in_background(job):
    """Start `job` on a worker thread and apply its result when it lands."""
    global _pending
    _pending += 1
    threading.Thread(target=_worker, args=(job,), daemon=True).start()
    if not bpy.app.timers.is_registered(_drain):
        bpy.app.timers.register(_drain, first_interval=0.1)


def unregister():
    if bpy.app.timers.is_registered(_drain):
        bpy.app.timers.unregister(_drain)
