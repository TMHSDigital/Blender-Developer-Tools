---
name: drivers-and-app-handlers
description: "Drive properties from expressions with the Driver API (driver_add, driver_namespace for custom Python functions) and react to events with bpy.app.handlers (load_post, save_pre, frame_change_post, depsgraph_update_post, exit_pre in 5.1+). Use when the user wants one property to follow another, runs code on load, save, frame change or exit, or has a driver failing with NameError or the Python security block, including drivers that die after reopening a file."
standards-version: 1.10.0
---

# Drivers and Application Handlers

## Trigger

Use this skill when the user:

- Wants property A to follow property B with some math (driver)
- Asks about `driver_add`, `FCurve.driver`, `driver.expression`, `driver_namespace`
- Wants to run code on file save, file load, frame change, depsgraph update, or process exit
- Mentions `bpy.app.handlers`, `save_pre`, `load_post`, `depsgraph_update_post`, `exit_pre`
- Has a driver expression that fails security checks because it tries to call a Python function

This skill bundles two related "reactive" patterns. They show up together often (a driver that calls a function registered on a handler), so they share one skill.

## Part 1: Drivers

### What a driver is

A driver replaces a static animation curve with a real-time-evaluated expression. It is attached to one property (the **target**) and reads zero or more other properties (the **variables**), then evaluates a string expression to compute the target's value on each frame.

Concretely: an `FCurve` whose `.driver` field is set is a driver. The animation system evaluates `driver.expression` instead of sampling the curve.

### The Driver API

```python
import bpy


def add_simple_driver(obj, data_path, index, expression):
    """Attach a driver to obj.data_path[index] that evaluates `expression`.

    Returns the FCurve so the caller can add variables.
    """
    fcurve = obj.driver_add(data_path, index)
    fcurve.driver.type = 'SCRIPTED'
    fcurve.driver.expression = expression
    return fcurve
```

`driver_add(data_path, index)`:

- `data_path` is the RNA path of the property, like `"location"` or `"scale"`. A user custom (ID) property set with `obj["my_custom_prop"] = 1.0` is `'["my_custom_prop"]'`; a registered `bpy.props` property is its plain name, `"my_prop"`. On 5.0+ `'["my_prop"]'` no longer resolves a registered property (`ValueError`), though it did on 4.x.
- `index` is the array index for vector or color properties (0 = X, 1 = Y, 2 = Z), or `-1` for scalar properties.
- Returns the `FCurve` whose `.driver` is now active.

### Adding variables to a driver

Drivers reference other properties by adding **variables** to their `driver.variables` collection. Each variable has a name (used in the expression) and one or two property targets.

```python
fcurve = obj.driver_add("location", 0)
fcurve.driver.type = 'SCRIPTED'

var = fcurve.driver.variables.new()
var.name = 'src_x'
var.type = 'TRANSFORMS'
var.targets[0].id = source_obj
var.targets[0].transform_type = 'LOC_X'
var.targets[0].transform_space = 'WORLD_SPACE'

fcurve.driver.expression = 'src_x * 2.0'
```

Common variable types:

- `'SINGLE_PROP'`: read any RNA property. Set `targets[0].id = some_id` and `targets[0].data_path = 'some.path'`. The target id pointer defaults to the `OBJECT` type; to point at a non-object datablock (a Scene, Material, etc.) set `targets[0].id_type` first, e.g. `targets[0].id_type = 'SCENE'`, otherwise the `id =` assignment raises `TypeError`.
- `'TRANSFORMS'`: read a transform channel. Set `transform_type` (`LOC_X`, `ROT_Y`, `SCALE_Z`, etc.).
- `'ROTATION_DIFF'`: angle between two bones in radians.
- `'LOC_DIFF'`: distance between two object locations.

### The expression security model

Driver expressions run on every depsgraph evaluation. Blender restricts what they can call:

- Built-in math is allowed: `+`, `-`, `*`, `/`, `**`, `%`.
- A whitelist of math functions: `sin`, `cos`, `sqrt`, `pi`, `radians`, etc. (see the docs for the full list).
- **Arbitrary Python is blocked.** Function calls to user-defined functions are blocked unless the function is registered in `bpy.app.driver_namespace`.

This is intentional. Without the restriction, opening a malicious .blend would auto-execute Python.

### The driver_namespace escape hatch

When a driver needs custom Python logic, register the function in `bpy.app.driver_namespace`:

```python
import bpy
import math


def smooth_step(t):
    """Smoothstep easing: 3t^2 - 2t^3 on [0, 1]."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


bpy.app.driver_namespace['smooth_step'] = smooth_step

fcurve = obj.driver_add("location", 2)
fcurve.driver.type = 'SCRIPTED'

var = fcurve.driver.variables.new()
var.name = 't'
var.type = 'SINGLE_PROP'
var.targets[0].id_type = 'SCENE'  # required before assigning a non-Object id
var.targets[0].id = bpy.context.scene
var.targets[0].data_path = 'frame_current'

fcurve.driver.expression = 'smooth_step((t - 1.0) / 100.0) * 5.0'
```

The function name in `driver_namespace` must match the call in the expression.

`driver_namespace` is **reset on every file load**. Registering only in `register()` works until the user opens a file: the drivers then evaluate with the function missing, raise `NameError: name 'smooth_step' is not defined`, and are disabled (`driver.is_valid = False`). They stay disabled even after the function is added back. Re-register from a `@persistent` `load_post` handler and re-enable the drivers there:

```python
import bpy
from bpy.app.handlers import persistent


@persistent
def restore_driver_functions(_filepath=None):
    bpy.app.driver_namespace['smooth_step'] = smooth_step
    # Drivers that failed during load stay off until re-enabled.
    for ids in (bpy.data.objects, bpy.data.shape_keys, bpy.data.materials):
        for id_data in ids:
            anim = id_data.animation_data
            for fcurve in (anim.drivers if anim else ()):
                fcurve.driver.is_valid = True


def register():
    bpy.app.driver_namespace['smooth_step'] = smooth_step
    bpy.app.handlers.load_post.append(restore_driver_functions)


def unregister():
    if restore_driver_functions in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(restore_driver_functions)
    bpy.app.driver_namespace.pop('smooth_step', None)
```

Extend the ID collections to wherever your add-on puts drivers (node groups, scenes, cameras). Measured on 4.5.11 and 5.2.1: without the handler, a saved and reopened file leaves the driver dead; with it, the driver evaluates again.

### Removing drivers

```python
obj.driver_remove("location", 0)
obj.driver_remove("location", -1)
```

The first form removes the driver on a specific channel. The second (with `-1`) removes drivers on all channels of a vector property.

## Part 2: Application Handlers

### What a handler is

A handler is a Python callable registered against a Blender event. When the event fires, every callable in the handler's list is called with a documented signature. Handlers run in registration order and exceptions in one do not stop the others (Blender catches and logs).

The handlers live as lists at `bpy.app.handlers.<event>`. To register, append; to unregister, remove.

### Common handlers and their signatures

| Handler | Signature | Fires when |
| --- | --- | --- |
| `save_pre` | `(filepath: str)` | Before the .blend is written. The argument is the file being saved (empty string for the startup file), **not** a Scene. Use to clean up data you don't want serialized. |
| `save_post` | `(filepath: str)` | After the .blend is written. Same single filepath argument. |
| `load_pre` | `(filepath: str)` | Before a .blend is loaded. The argument is the file being loaded. |
| `load_post` | `(filepath: str)` | After a .blend is loaded. Use to validate or migrate add-on data. |
| `depsgraph_update_pre` | `(scene, depsgraph)` | Before a depsgraph evaluation pass. |
| `depsgraph_update_post` | `(scene, depsgraph)` | After a depsgraph evaluation pass. Fires very frequently; must be O(1) or near-O(1). |
| `frame_change_pre` | `(scene, depsgraph)` | Before frame is set. |
| `frame_change_post` | `(scene, depsgraph)` | After frame is set. |
| `exit_pre` (new in 5.1) | `(*args)` | Before Blender shuts down. Use for resource cleanup, telemetry flush, etc. The argument is not a Scene; accept `*args`. |

The save/load handlers (`save_pre`, `save_post`, `load_pre`, `load_post`) all receive the **file path as a string** as their single argument, **not** a Scene. (Verified empirically on 4.5.10 LTS and 5.1.1. The [`bpy.app.handlers`](https://docs.blender.org/api/current/bpy.app.handlers.html) docs type these as `Callable[[str], None]`; `save_pre` is described as "on saving a blend file (before). Accepts one argument: the file being saved, an empty string for the startup-file." — the load handlers use the same wording with "the file being loaded".) Only the depsgraph/frame-change handlers receive `(scene, depsgraph)`.

The `exit_pre` handler in 5.1 is particularly useful for add-ons that need to release external resources (sockets, log files, child processes) deterministically before the process terminates.

### The canonical handler pattern

```python
import bpy
from bpy.app.handlers import persistent


@persistent
def on_save_pre(filepath):
    """Clear temporary cache data before save so it doesn't bloat the .blend.

    The handler argument is the path being saved (a string), not a Scene, so
    reach the scene(s) through bpy.data.
    """
    for scene in bpy.data.scenes:
        if 'my_addon_cache' in scene:
            del scene['my_addon_cache']


def register():
    bpy.app.handlers.save_pre.append(on_save_pre)


def unregister():
    if on_save_pre in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(on_save_pre)
```

### The `@persistent` decorator

By default, handlers are removed when a new .blend loads (so each file gets a clean handler list). Decorate with `@persistent` to keep your handler attached across file loads. This is what add-ons almost always want.

### Performance contract

Handlers run on the main thread, synchronously, on every event. The user feels every millisecond. Rules:

1. **Make handlers fast or asynchronous.** A 10ms handler on `depsgraph_update_post` slows playback noticeably.
2. **Guard against recursion.** A `depsgraph_update_post` that modifies the scene re-triggers the handler. Use a module-level flag or `bpy.app.handlers.depsgraph_update_post` removal to break loops.
3. **Defend against missing data.** Handlers run before your add-on may have fully initialized (load_post fires while UI is still rebuilding). Check membership before dereferencing.
4. **Always pair register/unregister.** Forgetting to remove a handler on add-on disable leaves a zombie callback that fires forever.

### Worked example: track save count per file

```python
import bpy
from bpy.app.handlers import persistent


@persistent
def increment_save_count(filepath):
    # save_pre runs before the write, so the new count lands in the file being
    # saved (a save_post write would only reach the next save). It receives the
    # target path. ID-property keys are limited to 63 characters, so key by the
    # file name, never the full path, which raises KeyError when longer.
    scene = bpy.context.scene
    key = bpy.path.basename(filepath)[:63] or "untitled"
    counts = scene.get('save_counts', {})
    counts[key] = counts.get(key, 0) + 1
    scene['save_counts'] = counts


def register():
    bpy.app.handlers.save_pre.append(increment_save_count)


def unregister():
    if increment_save_count in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(increment_save_count)
```

### Worked example: cleanup on exit (5.1+)

```python
import bpy
from bpy.app.handlers import persistent


@persistent
def cleanup_on_exit(*args):
    """Release the external log file handle before the process terminates.

    exit_pre's argument is unused here; accept *args to stay signature-proof.
    """
    global _log_handle
    if _log_handle is not None:
        _log_handle.close()
        _log_handle = None


def register():
    bpy.app.handlers.exit_pre.append(cleanup_on_exit)


def unregister():
    if cleanup_on_exit in bpy.app.handlers.exit_pre:
        bpy.app.handlers.exit_pre.remove(cleanup_on_exit)
```

The `exit_pre` handler list is new in Blender 5.1. On 4.5 LTS, fall back to OS-level `atexit` registration, which fires later and has fewer guarantees about access to `bpy` state.

## Common AI mistakes

- **Calling Python functions in a driver expression without registering them.** Hits the security block. Either rewrite as math, or register via `bpy.app.driver_namespace`.
- **Registering a driver function only in `register()`.** `driver_namespace` is reset on file load, so the driver dies with `NameError` on the first file the user opens and stays disabled. Re-register and reset `driver.is_valid` from a `@persistent` `load_post` handler.
- **Forgetting `@persistent` on handlers.** The handler vanishes on the next file load and the user thinks the add-on broke.
- **Doing real work inside `depsgraph_update_post`.** This handler fires on every depsgraph evaluation, which is many times per second during playback or interaction. Anything more than O(1) bookkeeping causes user-visible slowdown.
- **Recursively modifying the scene from a depsgraph handler.** The modification triggers another depsgraph evaluation, which calls the handler, which modifies the scene. Infinite loop, often manifesting as a hang.
- **Asymmetric register/unregister.** The handler is appended on register but not removed on unregister. Disabling the add-on leaves the callback in place. After enable/disable cycles, the callback runs N times per event.
- **Treating the `save_pre` argument as a Scene.** The save/load handlers receive the **file path string** (empty for the startup file), not a Scene. Name the parameter `filepath` (or take `*args`), and reach scenes via `bpy.context.scene` / `bpy.data.scenes`. A membership test like `'key' in arg0` against the path string is silently wrong, and `del arg0['key']` raises `TypeError`.
- **Doing exit cleanup in the script body instead of `exit_pre`.** A `--background --python` script can `sys.exit(0)` without the handler firing if you never registered it. The witness is a sidecar written from `exit_pre`, asserted after the process dies.

## Version correctness

| Topic | 4.5 LTS | 5.1 / 5.2 LTS |
| --- | --- | --- |
| `exit_pre` handler | Not available | New in 5.1; use `atexit` fallback for 4.x |
| `save_pre` / `save_post` signature | `(filepath)` — a string | `(filepath)` — a string (unchanged) |
| `driver_namespace` | Available; reset on file load | Same (re-register from `load_post`) |
| Driver security | Already restrictive | Same |

## See also

- Snippet `driver-with-custom-function.py` for the driver_namespace pattern.
- Snippet `app-handler-registration.py` for save_pre with proper unregister.
- Example `exit-pre-sidecar` for `exit_pre` writing a post-exit sidecar (5.1+; skip 4.5).
- Skill `custom-properties` for the data the driver might be reading.

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`driver-wave`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/driver-wave): A driver_namespace function driving sixteen organ-pipe heights through SCRIPTED drivers — the sine skyline of the pipe tops is entirely driver-evaluated. Falsify: `--flat-expr` (exit 3).
- [`exit-pre-sidecar`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/exit-pre-sidecar): `bpy.app.handlers.exit_pre` writes `$BDT_SMOKE_SIDECAR` as Blender dies. Blender 5.1+. Falsify: `--atexit-instead` (harness fails the sidecar).

<!-- examples:end -->

## References

- `bpy.app.handlers`: https://docs.blender.org/api/current/bpy.app.handlers.html
- `bpy.types.Driver`: https://docs.blender.org/api/current/bpy.types.Driver.html
- `bpy.types.FCurve.driver`: https://docs.blender.org/api/current/bpy.types.FCurve.html
- `bpy.app.driver_namespace`: https://docs.blender.org/api/current/bpy.app.html
- Blender 5.1 release notes: https://developer.blender.org/docs/release_notes/5.1/
