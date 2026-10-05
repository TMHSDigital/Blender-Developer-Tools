---
name: timers-modal-and-threading
description: "Run long or repeated work in a Blender add-on without freezing or crashing it: bpy.app.timers return values and persistent=True, modal operators driven by event_timer_add, and worker threads that hand results to the main thread through a queue. Use when the user polls, animates or downloads from an add-on, calls bpy from a thread, writes a modal operator, sees a timer never fire in --background, or loses a timer after opening a file. Targets 5.2 LTS with 4.5 LTS fallback."
standards-version: 1.10.0
---

# Timers, Modal Operators and Threading

## Trigger

Use this skill when the user:

- Wants something to happen later or repeatedly (polling, autosave, a progress readout)
- Runs slow work (network, file processing, a solver) and the UI freezes
- Calls `bpy` from a `threading.Thread` and gets crashes or corrupted data
- Writes a modal operator, or one that never stops
- Registers a timer in `blender --background` and it never runs
- Loses a timer after File → Open or `wm.read_homefile`

## Required inputs

- **What runs, how often, and for how long**
- **Whether it runs headless** (`--background`) or in a windowed Blender
- **Whether the work must survive file loads** (an add-on service) or belongs to one file

## The event loop is the whole story

Timers, modal operators and `event_timer_add` are all driven by Blender's window-manager event loop. A windowed Blender has one. `blender --background --python script.py` does not: the script runs, Blender exits, and a registered timer never runs (measured on 4.5.11, 5.1.2 and 5.2.1: `is_registered` is `True` and the callback never executes). Headless work must run synchronously in the script; there is no deferred callback to wait for.

## `bpy.app.timers`: the return value schedules the next run

```python
import bpy

def poll():
    if done():
        return None      # unregister: this was the last run
    return 0.5           # run again in 0.5 s

bpy.app.timers.register(poll, first_interval=0.5)
```

- `None` unregisters; a float re-runs after that many seconds. Measured in a windowed child: a `None` timer ran once, and one returning `0.05` until its third call ran exactly three times. Afterwards `is_registered` was `False` for both.
- Returning `0.0` does not mean "stop": it re-runs on the next event-loop pass. A timer meant to run once that returns `0.0` ran 5 times before a file load removed it.
- `first_interval` is keyword-only: `register(poll, 0.5)` raises `TypeError: register() takes exactly 1 positional argument (2 given)` on 4.5.11, 5.1.2 and 5.2.1.
- **A file load drops every timer not registered with `persistent=True`.** Measured: after `wm.read_factory_settings` inside a timer, the persistent timer was still registered and the plain one was not. Add-on services that must outlive File → Open need `persistent=True`. Per-file work should be plain, so it does not leak into the next file.
- Unregister in `unregister()`: `if bpy.app.timers.is_registered(poll): bpy.app.timers.unregister(poll)`.

## Threads: compute off the main thread, touch `bpy` on it

`bpy` is not thread-safe. A worker thread may compute, download or read files, but every `bpy` read and write happens on the main thread. Hand results over through a `queue.Queue`, and drain it from a timer:

```python
import queue
import threading
import bpy

results = queue.Queue()

def worker(url):
    data = download(url)           # no bpy here
    results.put(data)

def drain():
    try:
        data = results.get_nowait()
    except queue.Empty:
        return 0.1                 # nothing yet; look again
    apply_to_scene(data)           # bpy, on the main thread
    return None

threading.Thread(target=worker, args=(URL,), daemon=True).start()
bpy.app.timers.register(drain, first_interval=0.1)
```

Measured: the drain timer ran with `threading.current_thread() is threading.main_thread()` true, and created a mesh from the worker's result. Use `daemon=True` so a hung worker cannot keep Blender from quitting. For network work, check `bpy.app.online_access` first (see `extension-runtime-and-packaging`).

## Modal operators: `event_timer_add` plus `modal()`

```python
class MYADDON_OT_watch(bpy.types.Operator):
    bl_idname = "myaddon.watch"
    bl_label = "Watch"

    _timer = None

    def invoke(self, context, event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self.cancel(context)
            return {'CANCELLED'}
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}    # let the UI keep working
        if step(context):              # True when the job is done
            self.cancel(context)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
```

- Return `{'PASS_THROUGH'}` for events you do not handle, or the operator swallows all input and the UI looks frozen.
- `bpy.types.Event` has **no `timer` attribute** (absent from its RNA on 4.5.11 and 5.2.1). `event.timer is self._timer` raises `AttributeError` inside `modal()`. Test `event.type == 'TIMER'`; if several timers feed one operator, count or time the ticks yourself.
- Remove the timer on every exit path: your own `FINISHED` and `CANCELLED` returns, and `cancel()`, which Blender calls when it ends a running modal operator itself.
- Measured in a windowed child: `invoke` returned `{'RUNNING_MODAL'}`, `modal()` received three `TIMER` events, then returned `{'FINISHED'}` and removed its timer.
- To start a modal operator from a timer or a script, there is no window in context; supply one with `with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]): bpy.ops.myaddon.watch('INVOKE_DEFAULT')`.

For a progress readout, call `context.window_manager.progress_begin(0, total)`, `progress_update(i)` and `progress_end()` from the main thread: the modal step or the drain timer, never the worker.

## Common AI mistakes

1. **Calling `bpy` from a worker thread** (`bpy.data.objects.new` inside `Thread.run`). Compute in the thread; apply on the main thread from a timer.
2. **`time.sleep()` or a `while` loop in an operator** to wait for work. It blocks the event loop. Use a timer or a modal operator.
3. **Expecting timers to fire in `--background`**. There is no event loop; run the work directly in the script.
4. **A run-once timer that returns `0`**. Zero means "again on the next pass"; return `None` to stop.
5. **`bpy.app.timers.register(fn, 1.0)`**. `first_interval` is keyword-only on every supported version.
6. **Add-on timers without `persistent=True`**. They vanish on the first File → Open.
7. **`event.timer` in `modal()`**. The attribute does not exist; test `event.type == 'TIMER'`.
8. **Never removing the modal timer**. Remove it in `cancel()` and on every return that ends the operator.

## Compatibility paths

The behaviour above was measured identically on 4.5 LTS, 5.1 and 5.2 LTS. The only visible difference is cosmetic: 5.2's docstring shows `register(function, *, first_interval=0, persistent=False)`, while 4.5 documents the same keyword-only call without the `*`. No version branch is needed.

## Related

- `operators`: operator lifecycle, `bl_options`, `invoke` versus `execute`
- `drivers-and-app-handlers`: `@persistent` application handlers, the other way to react to file loads
- `headless-batch-scripting`: what to do instead when there is no event loop
- `extension-runtime-and-packaging`: `bpy.app.online_access` before network work in a worker
- Snippet: [`snippets/thread-queue-timer.py`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/snippets/thread-queue-timer.py)

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`timers-modal-threading`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/timers-modal-threading): Proves the event-loop contracts behind long-running add-on work. Falsify: `--return-zero-once` (exit 5).

<!-- examples:end -->

## References

- `bpy.app.timers`: https://docs.blender.org/api/current/bpy.app.timers.html
- `WindowManager.event_timer_add`: https://docs.blender.org/api/current/bpy.types.WindowManager.html#bpy.types.WindowManager.event_timer_add
- Modal operators: https://docs.blender.org/api/current/bpy.types.Operator.html#modal-execution
- Thread safety: https://docs.blender.org/api/current/info_gotchas_threading.html
- 4.5 LTS reference: https://docs.blender.org/api/4.5/bpy.app.timers.html
