---
name: drivers-and-app-handlers
description: Drive properties from expressions or other properties via the Driver API, and react to scene events via the bpy.app.handlers callbacks. Covers driver_namespace for Python functions, the new exit_pre handler in 5.1, and the must-be-fast contract for any handler.
standards-version: 1.9.4
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

- `data_path` is the RNA path of the property, like `"location"` or `"scale"` or `'["my_custom_prop"]'`.
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

- `'SINGLE_PROP'`: read any RNA property. Set `targets[0].id = some_id` and `targets[0].data_path = 'some.path'`.
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
var.targets[0].id = bpy.context.scene
var.targets[0].data_path = 'frame_current'

fcurve.driver.expression = 'smooth_step((t - 1.0) / 100.0) * 5.0'
```

The function name in `driver_namespace` must match the call in the expression. Register the function on add-on `register()` and remove it on `unregister()`:

```python
def register():
    bpy.app.driver_namespace['smooth_step'] = smooth_step


def unregister():
    bpy.app.driver_namespace.pop('smooth_step', None)
```

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
| `save_pre` | `(scene)` (some 4.x), `(scene, filepath)` (5.x) | Before the .blend is written. Use to clean up data you don't want serialized. |
| `save_post` | Same | After the .blend is written. Use for post-save bookkeeping. |
| `load_pre` | `(scene)` | Before a .blend is loaded. The current scene is still the old one. |
| `load_post` | `(scene)` | After a .blend is loaded. Use to validate or migrate add-on data. |
| `depsgraph_update_pre` | `(scene, depsgraph)` | Before a depsgraph evaluation pass. |
| `depsgraph_update_post` | `(scene, depsgraph)` | After a depsgraph evaluation pass. Fires very frequently; must be O(1) or near-O(1). |
| `frame_change_pre` | `(scene, depsgraph)` | Before frame is set. |
| `frame_change_post` | `(scene, depsgraph)` | After frame is set. |
| `exit_pre` (new in 5.1) | `(scene)` | Before Blender shuts down. Use for resource cleanup, telemetry flush, etc. |

The `exit_pre` handler in 5.1 is particularly useful for add-ons that need to release external resources (sockets, log files, child processes) deterministically before the process terminates.

### The canonical handler pattern

```python
import bpy
from bpy.app.handlers import persistent


@persistent
def on_save_pre(scene, filepath):
    """Clear temporary cache data before save so it doesn't bloat the .blend."""
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
def increment_save_count(scene, filepath):
    counts = scene.get('save_counts', {})
    counts[filepath] = counts.get(filepath, 0) + 1
    scene['save_counts'] = counts


def register():
    bpy.app.handlers.save_post.append(increment_save_count)


def unregister():
    if increment_save_count in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(increment_save_count)
```

### Worked example: cleanup on exit (5.1+)

```python
import bpy
from bpy.app.handlers import persistent


@persistent
def cleanup_on_exit(scene):
    """Release the external log file handle before the process terminates."""
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
- **Forgetting `@persistent` on handlers.** The handler vanishes on the next file load and the user thinks the add-on broke.
- **Doing real work inside `depsgraph_update_post`.** This handler fires on every depsgraph evaluation, which is many times per second during playback or interaction. Anything more than O(1) bookkeeping causes user-visible slowdown.
- **Recursively modifying the scene from a depsgraph handler.** The modification triggers another depsgraph evaluation, which calls the handler, which modifies the scene. Infinite loop, often manifesting as a hang.
- **Asymmetric register/unregister.** The handler is appended on register but not removed on unregister. Disabling the add-on leaves the callback in place. After enable/disable cycles, the callback runs N times per event.
- **Assuming the `save_pre` signature.** It changed across the 4.x to 5.x window. Use `(scene, filepath=None)` defensively, or `*args` if you don't need the values.

## Version correctness

| Topic | 4.5 LTS | 5.1 stable |
| --- | --- | --- |
| `exit_pre` handler | Not available | New in 5.1; use `atexit` fallback for 4.x |
| `save_pre` signature | `(scene)` in 4.0, varies | `(scene, filepath)` in 5.x |
| `driver_namespace` | Available | Same |
| Driver security | Already restrictive | Same |

## See also

- Snippet `driver-with-custom-function.py` for the driver_namespace pattern.
- Snippet `app-handler-registration.py` for save_pre with proper unregister.
- Skill `custom-properties` for the data the driver might be reading.

## References

- `bpy.app.handlers`: https://docs.blender.org/api/current/bpy.app.handlers.html
- `bpy.types.Driver`: https://docs.blender.org/api/current/bpy.types.Driver.html
- `bpy.types.FCurve.driver`: https://docs.blender.org/api/current/bpy.types.FCurve.html
- `bpy.app.driver_namespace`: https://docs.blender.org/api/current/bpy.app.html
- Blender 5.1 release notes: https://developer.blender.org/docs/release_notes/5.1/
