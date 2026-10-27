# Worker thread + queue + timer: do slow work off the main thread and apply
# the result to bpy on it. bpy is not thread-safe, so the worker never
# touches it; a timer (main thread) drains the queue.
#
# - Timers need the event loop: in `blender --background` they never run.
# - A timer returning None stops; a float (0 included) runs it again.
# - Count pending jobs and stop the drain only at 0, or a second result is
#   stranded; the worker always puts, even on error, or the drain never stops.
# - File > Open drops the plain drain timer but not the threads: jobs carry an
#   epoch that load_post bumps, so an old file's results are discarded.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.app.timers.html
#   https://docs.blender.org/api/current/info_gotchas_threading.html

import queue
import threading

import bpy
from bpy.app.handlers import persistent

_results = queue.Queue()
_pending = 0  # this file's jobs not yet drained; main thread only
_epoch = 0  # bumped on every file load


def _worker(job, epoch):
    try:  # no bpy in here: compute, download, read files
        _results.put((epoch, True, job()))
    except BaseException as e:
        _results.put((epoch, False, e))  # never leave the drain waiting


def _drain():
    global _pending
    while True:  # take everything that has landed this tick
        try:
            epoch, ok, value = _results.get_nowait()
        except queue.Empty:
            break
        if epoch != _epoch:
            continue  # started for a file that is no longer open
        _pending -= 1
        obj = bpy.data.objects.get("Target")  # main thread: bpy is safe here
        if not ok:
            print(f"background job failed: {value!r}")
        elif obj is not None:
            obj["result"] = value
    return 0.1 if _pending else None  # unregister only once every job is in


@persistent
def _on_load(_):
    global _pending, _epoch
    _epoch, _pending = _epoch + 1, 0  # old jobs' results are now stale


def run_in_background(job):
    """Start `job` on a worker thread and apply its result when it lands."""
    global _pending
    _pending += 1
    threading.Thread(target=_worker, args=(job, _epoch), daemon=True).start()
    if not bpy.app.timers.is_registered(_drain):
        bpy.app.timers.register(_drain, first_interval=0.1)


def register():
    bpy.app.handlers.load_post.append(_on_load)


def unregister():
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    if bpy.app.timers.is_registered(_drain):
        bpy.app.timers.unregister(_drain)
