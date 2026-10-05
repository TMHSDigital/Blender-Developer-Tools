"""Timers, modal operators and worker threads — a runnable example.

Long-running add-on work has three moving parts, and each depends on
Blender's event loop. This example proves their contracts in child Blender
processes, because the loop only exists in a windowed Blender:

1. In ``--background`` a registered ``bpy.app.timers`` function never runs:
   the script ends, Blender exits, and the timer was only ever registered.
2. In a windowed Blender, a timer that returns ``None`` runs once and
   unregisters; one that returns a float runs again after that many seconds.
3. A worker thread hands its result through a ``queue.Queue``; a timer
   drains it and touches ``bpy`` on the main thread.
4. A modal operator driven by ``window_manager.event_timer_add`` receives
   ``TIMER`` events, finishes, and removes its timer.
5. ``persistent=True`` keeps a timer registered across a file load; a plain
   timer is dropped.

The windowed child quits itself through a timer, so it needs a display: CI
runs smoke under xvfb, and on a desktop a Blender window opens briefly.
Check-only: the witnesses are counts and registration state.

    blender --background --python timers_modal_threading.py --
    blender --background --python timers_modal_threading.py -- --return-zero-once
    blender --background --python timers_modal_threading.py -- --non-persistent
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import bpy

TIMEOUT = 180
REPEATS = 3
MODAL_TICKS = 3

BACKGROUND_CHILD = r'''
import bpy, os
def fire():
    open(os.environ["BDT_TIMER_FIRED"], "w").write("fired")
    return None
bpy.app.timers.register(fire, first_interval=0.0)
print("RESULT registered", bpy.app.timers.is_registered(fire))
'''

WINDOWED_CHILD = r'''
import bpy, json, os, queue, threading, time
OUT = os.environ["BDT_TIMER_OUT"]
FLAGS = os.environ.get("BDT_TIMER_FLAGS", "").split()
T0 = time.time()
log = {"background": bpy.app.background, "once": 0, "repeat": 0, "applied": [],
       "ticks": 0, "invoke": None, "modal_result": None, "timer_removed": False}

# 2. Return value decides the next run: None unregisters, a float reschedules.
def once():
    log["once"] += 1
    return 0.0 if "--return-zero-once" in FLAGS else None

def repeat():
    log["repeat"] += 1
    return 0.05 if log["repeat"] < %(repeats)d else None

# 3. The worker never touches bpy; the drain timer does, on the main thread.
results = queue.Queue()

def worker():
    time.sleep(0.2)
    results.put([0.0, 1.0, 2.0])

threading.Thread(target=worker, daemon=True).start()

def drain():
    try:
        heights = results.get_nowait()
    except queue.Empty:
        return 0.05
    me = bpy.data.meshes.new("FromWorker")
    log["applied"].append({"main_thread": threading.current_thread() is threading.main_thread(),
                           "values": len(heights), "mesh": me.name})
    return None

# 4. A modal operator fed by an event timer.
class BDT_OT_modal_ticks(bpy.types.Operator):
    bl_idname = "bdt.modal_ticks"
    bl_label = "Modal ticks"
    _timer = None

    def invoke(self, context, event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        log["ticks"] += 1
        if log["ticks"] >= %(ticks)d:
            self._cleanup(context)
            log["modal_result"] = "FINISHED"
            return {'FINISHED'}
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._cleanup(context)

    def _cleanup(self, context):
        context.window_manager.event_timer_remove(self._timer)
        self._timer = None
        log["timer_removed"] = True

bpy.utils.register_class(BDT_OT_modal_ticks)

def start_modal():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        log["invoke"] = sorted(bpy.ops.bdt.modal_ticks('INVOKE_DEFAULT'))
    return None

# 5. A file load drops plain timers and keeps persistent ones.
def keeper():
    return 1.0

def plain():
    return 1.0

def load_file():
    if not (log["modal_result"] and log["applied"] and log["repeat"] >= %(repeats)d) and time.time() - T0 < 15:
        return 0.05  # a file load drops plain timers and ends modal operators; let them finish
    bpy.app.timers.register(keeper, first_interval=1.0,
                            persistent="--non-persistent" not in FLAGS)
    bpy.app.timers.register(plain, first_interval=1.0)
    log["before_load"] = [bpy.app.timers.is_registered(f) for f in (keeper, plain)]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    log["after_load"] = [bpy.app.timers.is_registered(f) for f in (keeper, plain)]
    return None

def finish():
    done = log["repeat"] >= %(repeats)d and log["applied"] and log["modal_result"] and "after_load" in log
    if not done and time.time() - T0 < 20:
        return 0.1
    log["still_registered"] = [bpy.app.timers.is_registered(f) for f in (once, repeat, drain)]
    with open(OUT, "w") as fh:
        json.dump(log, fh)
    bpy.ops.wm.quit_blender()
    return None

bpy.app.timers.register(once, first_interval=0.1)
bpy.app.timers.register(repeat, first_interval=0.1)
bpy.app.timers.register(drain, first_interval=0.05)
bpy.app.timers.register(start_modal, first_interval=0.2)
bpy.app.timers.register(load_file, first_interval=0.3)
bpy.app.timers.register(finish, first_interval=0.5, persistent=True)  # must outlive the file load
''' % {"repeats": REPEATS, "ticks": MODAL_TICKS}


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def run_child(source, work, name, env_extra, background):
    script = os.path.join(work, f"{name}.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(source)
    args = [bpy.app.binary_path, "--factory-startup"]
    if background:
        args.append("--background")
    args += ["--python", script]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT,
                           env=dict(os.environ, **env_extra))
    except subprocess.TimeoutExpired:
        return None, ""
    return r.returncode, r.stdout + r.stderr


def check_background(work):
    fired = os.path.join(work, "fired.txt")
    code, out = run_child(BACKGROUND_CHILD, work, "background_child", {"BDT_TIMER_FIRED": fired}, True)
    registered = "RESULT registered True" in out
    print(f"--background child: exit {code}, registered={registered}, fired={os.path.exists(fired)}")
    if code != 0 or not registered:
        print(out[-2000:])
        return fail("the --background child did not run or did not register its timer", 3)
    if os.path.exists(fired):
        return fail("a timer fired in --background; the no-event-loop premise is gone", 3)
    return 0


def check_windowed(work, flags):
    out_json = os.path.join(work, "windowed.json")
    code, out = run_child(WINDOWED_CHILD, work, "windowed_child",
                          {"BDT_TIMER_OUT": out_json, "BDT_TIMER_FLAGS": " ".join(flags)}, False)
    if code is None or not os.path.isfile(out_json):
        print(out[-3000:])
        return fail(f"the windowed child produced no result (exit {code}); it needs a display", 4)
    with open(out_json, encoding="utf-8") as fh:
        log = json.load(fh)
    print(f"windowed child: exit {code}, background={log['background']}")
    print(f"  timers: once ran {log['once']}x, repeat ran {log['repeat']}x, "
          f"still registered (once, repeat, drain)={log['still_registered']}")
    print(f"  worker result applied: {log['applied']}")
    print(f"  modal: invoke={log['invoke']} ticks={log['ticks']} result={log['modal_result']} "
          f"timer_removed={log['timer_removed']}")
    print(f"  file load: (persistent, plain) registered before={log.get('before_load')} "
          f"after={log.get('after_load')}")

    if log["background"]:
        return fail("the windowed child reports bpy.app.background", 4)
    if log["once"] != 1 or log["repeat"] != REPEATS or any(log["still_registered"]):
        return fail(f"timer return values were not honoured (once={log['once']}, "
                    f"repeat={log['repeat']}, registered={log['still_registered']})", 5)
    if len(log["applied"]) != 1 or not log["applied"][0]["main_thread"] or log["applied"][0]["values"] != 3:
        return fail(f"the worker result was not applied once on the main thread: {log['applied']}", 6)
    if log["invoke"] != ["RUNNING_MODAL"] or log["ticks"] != MODAL_TICKS \
            or log["modal_result"] != "FINISHED" or not log["timer_removed"]:
        return fail("the modal operator did not run its timer ticks to FINISHED and clean up", 7)
    if log.get("before_load") != [True, True] or log.get("after_load") != [True, False]:
        return fail(f"file load should keep only the persistent timer: "
                    f"before={log.get('before_load')} after={log.get('after_load')}", 8)
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--return-zero-once", action="store_true",
                   help="falsification: the run-once timer returns 0.0 instead of None")
    p.add_argument("--non-persistent", action="store_true",
                   help="falsification: register the keeper timer without persistent=True")
    args = p.parse_args(argv)
    flags = [f for f, on in (("--return-zero-once", args.return_zero_once),
                             ("--non-persistent", args.non_persistent)) if on]
    print(f"blender={bpy.app.version_string} flags={flags}")

    with tempfile.TemporaryDirectory(prefix="bdt_timers_") as work:
        code = check_background(work)
        if code:
            return code
        code = check_windowed(work, flags)
        if code:
            return code
    print("timers-modal-threading OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
