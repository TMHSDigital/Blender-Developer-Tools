"""Timers, modal operators and worker threads — a runnable example.

Long-running add-on work has three moving parts, and each depends on
Blender's event loop. This example proves their contracts in child Blender
processes, because the loop only exists in a windowed Blender:

1. In ``--background`` a registered ``bpy.app.timers`` function never runs:
   the script ends, Blender exits, and the timer was only ever registered.
2. In a windowed Blender, a timer that returns ``None`` runs once and
   unregisters; one that returns a float runs again after that many seconds.
3. Worker threads hand results through a ``queue.Queue``; a timer drains
   it and touches ``bpy`` on the main thread (thread idents are compared,
   because a check inside a timer is always on the main thread). Three
   jobs run at once and one raises: a pending counter keeps the drain alive
   until every job reports, and the worker puts the exception instead of
   dying silently, so nothing is stranded and nothing polls forever.
4. A modal operator driven by ``window_manager.event_timer_add`` receives
   ``TIMER`` events, finishes, and removes its timer.
5. ``persistent=True`` keeps a timer registered across a file load; a plain
   timer is dropped.

The windowed child quits itself through a timer, so it needs a display: CI
runs smoke under xvfb, and on a desktop a Blender window opens briefly.
Check-only: the witnesses are counts and registration state.

    blender --background --python timers_modal_threading.py --
    blender --background --python timers_modal_threading.py -- --return-zero-once
    blender --background --python timers_modal_threading.py -- --stop-after-first
    blender --background --python timers_modal_threading.py -- --no-catch

The README lists every falsifier flag and the exit it lands on.
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
    if not bpy.app.background:  # --windowed-background-child: quit once it has fired
        bpy.ops.wm.quit_blender()
    return None
bpy.app.timers.register(fire, first_interval=0.0)
print("RESULT registered", bpy.app.timers.is_registered(fire))
'''

WINDOWED_CHILD = r'''
import bpy, json, os, queue, threading, time
OUT = os.environ["BDT_TIMER_OUT"]
FLAGS = os.environ.get("BDT_TIMER_FLAGS", "").split()
T0 = time.time()
MAIN_IDENT = threading.get_ident()  # the script runs on Blender's main thread
log = {"background": bpy.app.background, "main_ident": MAIN_IDENT, "once": 0, "repeat": 0,
       "worker_idents": [], "applied": [], "errors": [],
       "ticks": 0, "invoke": None, "modal_result": None, "timer_removed": False}

# 2. Return value decides the next run: None unregisters, a float reschedules.
def once():
    log["once"] += 1
    if "--return-zero-once" in FLAGS:
        return 0.0
    if "--return-late-once" in FLAGS:
        return 30.0  # runs once inside the window, yet stays registered
    return None

def repeat():
    log["repeat"] += 1
    return 0.05 if log["repeat"] < %(repeats)d else None

# 3. Workers never touch bpy; the drain timer does, on the main thread. Three
# concurrent jobs, one of which raises: the snippets/thread-queue-timer.py
# pattern (pending counter, drain everything per tick, the worker always puts).
results = queue.Queue()
pending = 0

def job_heights():
    time.sleep(0.2)
    return [0.0, 1.0, 2.0]

def job_labels():
    time.sleep(0.4)
    return ["a", "b"]

def job_broken():
    time.sleep(0.3)
    raise ValueError("job failed on purpose")

def apply_result(name, value):
    ident = threading.get_ident()
    entry = {"job": name, "ident": ident, "values": len(value), "mesh": None}
    log["applied"].append(entry)
    if ident != MAIN_IDENT:
        return  # --apply-in-worker: identity recorded; bpy itself stays untouched off-thread
    entry["mesh"] = bpy.data.meshes.new("FromWorker_" + name).name

def worker(name, job):
    log["worker_idents"].append(threading.get_ident())
    if "--no-catch" in FLAGS:  # falsifier: the old worker, which dies without putting
        results.put((name, True, job()))
        return
    try:
        value = job()
    except BaseException as e:
        results.put((name, False, e))
        return
    if "--apply-in-worker" in FLAGS:  # falsifier: skip the main-thread handoff
        apply_result(name, value)
        return
    results.put((name, True, value))

def drain():
    global pending
    while True:
        try:
            name, ok, value = results.get_nowait()
        except queue.Empty:
            break
        pending -= 1
        if ok:
            apply_result(name, value)
        else:
            log["errors"].append({"job": name, "ident": threading.get_ident(), "error": repr(value)})
        if "--stop-after-first" in FLAGS:
            return None  # falsifier: the old drain, which stops after one result
    return 0.05 if pending else None

def run_in_background(name, job):
    global pending
    pending += 1
    threading.Thread(target=worker, args=(name, job), daemon=True).start()
    if not bpy.app.timers.is_registered(drain):
        bpy.app.timers.register(drain, first_interval=0.05)

# 4. A modal operator fed by an event timer.
class BDT_OT_modal_ticks(bpy.types.Operator):
    bl_idname = "bdt.modal_ticks"
    bl_label = "Modal ticks"
    _timer = None

    def invoke(self, context, event):
        wm = context.window_manager
        if "--no-event-timer" not in FLAGS:  # falsifier: nothing sends TIMER events
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
        if self._timer is not None:
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
    settled = log["modal_result"] and log["repeat"] >= %(repeats)d and pending == 0
    if not settled and time.time() - T0 < 15:
        return 0.05  # a file load drops plain timers and ends modal operators; let them finish
    # Read registration BEFORE the load: the load itself drops every plain timer,
    # so a read afterwards would be False whatever the return values were.
    log["still_registered"] = [bpy.app.timers.is_registered(f) for f in (once, repeat)]
    log["drain_registered"] = bpy.app.timers.is_registered(drain)
    log["pending"] = pending
    bpy.app.timers.register(keeper, first_interval=1.0,
                            persistent="--non-persistent" not in FLAGS)
    bpy.app.timers.register(plain, first_interval=1.0)
    log["before_load"] = [bpy.app.timers.is_registered(f) for f in (keeper, plain)]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    log["after_load"] = [bpy.app.timers.is_registered(f) for f in (keeper, plain)]
    return None

def finish():
    if "after_load" not in log and time.time() - T0 < 25:
        return 0.1
    with open(OUT, "w") as fh:
        json.dump(log, fh)
    bpy.ops.wm.quit_blender()
    return None

bpy.app.timers.register(once, first_interval=0.1)
bpy.app.timers.register(repeat, first_interval=0.1)
for name, job in (("heights", job_heights), ("labels", job_labels), ("broken", job_broken)):
    run_in_background(name, job)
bpy.app.timers.register(start_modal, first_interval=0.2)
bpy.app.timers.register(load_file, first_interval=0.3)
bpy.app.timers.register(finish, first_interval=0.5, persistent=True)  # must outlive the file load
''' % {"repeats": REPEATS, "ticks": MODAL_TICKS}

EXPECTED_APPLIED = {"heights": 3, "labels": 2}
CHILD_FLAGS = ("--return-zero-once", "--return-late-once", "--apply-in-worker",
               "--stop-after-first", "--no-catch", "--no-event-timer", "--non-persistent")


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


def check_background(work, windowed):
    fired = os.path.join(work, "fired.txt")
    code, out = run_child(BACKGROUND_CHILD, work, "background_child", {"BDT_TIMER_FIRED": fired},
                          background=not windowed)
    registered = "RESULT registered True" in out
    print(f"{'windowed' if windowed else '--background'} timer child: exit {code}, "
          f"registered={registered}, fired={os.path.exists(fired)}")
    if code != 0 or not registered:
        print(out[-2000:])
        return fail("the --background child did not run or did not register its timer", 3)
    if os.path.exists(fired):
        return fail("a timer fired in the background child; the no-event-loop premise is gone", 3)
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
    main_ident = log["main_ident"]
    print(f"windowed child: exit {code}, background={log['background']}")
    print(f"  timers: once ran {log['once']}x, repeat ran {log['repeat']}x, "
          f"registered before the file load (once, repeat)={log.get('still_registered')}")
    print(f"  threads: main={main_ident} workers={log['worker_idents']}")
    print(f"  applied (job, values, on main, mesh): "
          f"{[(a['job'], a['values'], a['ident'] == main_ident, a['mesh']) for a in log['applied']]}")
    print(f"  errors (job, error, on main): "
          f"{[(e['job'], e['error'], e['ident'] == main_ident) for e in log['errors']]}")
    print(f"  drain registered before the file load={log.get('drain_registered')} "
          f"pending={log.get('pending')}")
    print(f"  modal: invoke={log['invoke']} ticks={log['ticks']} result={log['modal_result']} "
          f"timer_removed={log['timer_removed']}")
    print(f"  file load: (persistent, plain) registered before={log.get('before_load')} "
          f"after={log.get('after_load')}")

    if log["background"]:
        return fail("the windowed child reports bpy.app.background", 4)
    # Registration is read before the file load, which drops plain timers itself.
    if log["once"] != 1 or log["repeat"] != REPEATS or log.get("still_registered") != [False, False]:
        return fail(f"timer return values were not honoured (once={log['once']}, "
                    f"repeat={log['repeat']}, registered={log.get('still_registered')})", 5)
    # Thread identity is compared, not asserted inside a timer (which is always main).
    workers = log["worker_idents"]
    handled = log["applied"] + log["errors"]
    if len(workers) != 3 or main_ident in workers \
            or any(h["ident"] != main_ident for h in handled):
        return fail(f"worker results were not handled on the main thread: main {main_ident}, "
                    f"workers {workers}, handled on {[(h['job'], h['ident']) for h in handled]}", 6)
    applied = {a["job"]: a["values"] for a in log["applied"] if a["mesh"]}
    if applied != EXPECTED_APPLIED or len(log["applied"]) != len(EXPECTED_APPLIED):
        return fail(f"not every concurrent job's result was applied once: got {applied}, "
                    f"expected {EXPECTED_APPLIED}", 9)
    errors = [(e["job"], e["error"].split("(")[0]) for e in log["errors"]]
    if errors != [("broken", "ValueError")] or log.get("pending") != 0 or log.get("drain_registered"):
        return fail(f"the raising job was not reported, or the drain kept polling: errors={errors} "
                    f"pending={log.get('pending')} drain registered={log.get('drain_registered')}", 12)
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
    p.add_argument("--windowed-background-child", action="store_true",
                   help="falsification: run the timer-never-fires child with a window")
    p.add_argument("--return-zero-once", action="store_true",
                   help="falsification: the run-once timer returns 0.0 instead of None")
    p.add_argument("--return-late-once", action="store_true",
                   help="falsification: the run-once timer returns 30.0, so it stays registered")
    p.add_argument("--apply-in-worker", action="store_true",
                   help="falsification: the worker applies its own result")
    p.add_argument("--stop-after-first", action="store_true",
                   help="falsification: the drain unregisters after the first result")
    p.add_argument("--no-catch", action="store_true",
                   help="falsification: the worker does not catch the job's exception")
    p.add_argument("--no-event-timer", action="store_true",
                   help="falsification: the modal operator adds no event timer")
    p.add_argument("--non-persistent", action="store_true",
                   help="falsification: register the keeper timer without persistent=True")
    args = p.parse_args(argv)
    flags = [f for f in CHILD_FLAGS if getattr(args, f[2:].replace("-", "_"))]
    print(f"blender={bpy.app.version_string} flags={flags}")

    with tempfile.TemporaryDirectory(prefix="bdt_timers_") as work:
        code = check_background(work, args.windowed_background_child)
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
