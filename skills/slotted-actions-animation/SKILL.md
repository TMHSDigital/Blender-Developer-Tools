---
name: slotted-actions-animation
description: Animate from Python under the Blender 5.x Slotted Actions architecture. Action contains Layers contain Strips contain Channelbags. The action_ensure_channelbag_for_slot bridge utility for 4.5 LTS and 5.x compatibility.
standards-version: 1.9.4
---

# Slotted Actions Animation

## Trigger

Use this skill when the user:

- Wants to create or edit animation from Python in Blender 5.x
- Mentions `Action`, `slot`, `channelbag`, `keyframe_insert`, `fcurves`
- Has older 4.x animation code (`action.fcurves.new(...)`) that no longer works in 5.x
- Asks how to insert keyframes programmatically and have them persist

## What changed and why

Blender 5.0 introduced **Slotted Actions** to support non-linear, multi-target animation. The pre-5.0 Action data model was a flat list of F-curves owned directly by the Action. That made it impossible for one Action to drive two different IDs (e.g. an armature pose and the armature's custom property channels at the same time) without overwriting each other.

The 5.x model:

```
Action
  Slots[]           # one per ID being driven
  Layers[]          # animation layers, blendable
    Strips[]        # time ranges within a layer
      Channelbags[] # one per slot, holds the actual F-curves
        FCurves[]
```

Pre-5.0 code that walked `action.fcurves` directly does not find anything in a 5.x Action because the F-curves live inside a Channelbag inside a Strip inside a Layer.

## The bridge utility: `action_ensure_channelbag_for_slot`

`bpy_extras.anim_utils.action_ensure_channelbag_for_slot(action, slot)` is the cross-version helper that:

- On 5.x: ensures the Action has a Layer, a Strip in that Layer, and a Channelbag for the given Slot, then returns the Channelbag.
- On 4.5 LTS where there is no Slotted Actions concept: returns a shim object that exposes `.fcurves` pointing at `action.fcurves`, so the same calling code works.

Import path verified against the Blender 5.1 API reference: `bpy_extras.anim_utils.action_ensure_channelbag_for_slot(action, slot)`. See [`bpy_extras.anim_utils`](https://docs.blender.org/api/current/bpy_extras.anim_utils.html).

```python
import bpy
from bpy_extras.anim_utils import action_ensure_channelbag_for_slot


def get_channelbag_for_object(obj):
    """Return the Channelbag (5.x) or fcurves shim (4.5 LTS) for obj's animation."""
    if obj.animation_data is None:
        obj.animation_data_create()

    if obj.animation_data.action is None:
        action = bpy.data.actions.new(name=f"{obj.name}_Action")
        obj.animation_data.action = action
    else:
        action = obj.animation_data.action

    # On 5.x, slot may not be set; pick or create one for this ID.
    slot = obj.animation_data.action_slot
    if slot is None and hasattr(action, "slots"):
        # Create a slot bound to OBJECT type, then assign it.
        slot = action.slots.new(id_type='OBJECT', name=obj.name)
        obj.animation_data.action_slot = slot

    return action_ensure_channelbag_for_slot(action, slot)
```

The `hasattr(action, "slots")` check is the version sniff: present in 5.x, absent in 4.5 LTS.

## Inserting keyframes the cross-version way

The high-level `obj.keyframe_insert(data_path, frame=...)` works on both 4.5 LTS and 5.x and is the preferred entry point for most cases. Blender takes care of the slot/layer/strip/channelbag plumbing internally.

```python
import bpy

obj = bpy.context.active_object
obj.location = (0.0, 0.0, 0.0)
obj.keyframe_insert(data_path="location", frame=1)

obj.location = (5.0, 0.0, 0.0)
obj.keyframe_insert(data_path="location", frame=24)
```

Each `keyframe_insert` adds keys for all three components of `location` (since it's a vector). `index=0` would key only X.

This works on 4.5 LTS and 5.x without any version branching.

## When you need direct F-curve access

For programmatic curve construction (importing motion capture, writing a curve solver, building a baked animation track), you need the F-curves directly:

```python
import bpy
from bpy_extras.anim_utils import action_ensure_channelbag_for_slot


def get_or_create_fcurve(obj, data_path, index):
    if obj.animation_data is None:
        obj.animation_data_create()

    action = obj.animation_data.action
    if action is None:
        action = bpy.data.actions.new(f"{obj.name}_Action")
        obj.animation_data.action = action

    slot = obj.animation_data.action_slot
    if slot is None and hasattr(action, "slots"):
        slot = action.slots.new(id_type='OBJECT', name=obj.name)
        obj.animation_data.action_slot = slot

    cbag = action_ensure_channelbag_for_slot(action, slot)

    fcurve = next(
        (fc for fc in cbag.fcurves if fc.data_path == data_path and fc.array_index == index),
        None,
    )
    if fcurve is None:
        fcurve = cbag.fcurves.new(data_path=data_path, index=index)
    return fcurve


def bake_translation(obj, frame_value_pairs):
    """frame_value_pairs is an iterable of ((frame, x, y, z), ...)."""
    fcs = [get_or_create_fcurve(obj, "location", i) for i in range(3)]

    for frame, x, y, z in frame_value_pairs:
        fcs[0].keyframe_points.insert(frame, x, options={'FAST'})
        fcs[1].keyframe_points.insert(frame, y, options={'FAST'})
        fcs[2].keyframe_points.insert(frame, z, options={'FAST'})

    for fc in fcs:
        fc.update()
```

Notes:
- `options={'FAST'}` skips per-insertion sorting and curve update; call `fc.update()` once at the end.
- `cbag.fcurves` is the unified access point. On 4.5 LTS, the bridge returns a shim whose `.fcurves` is `action.fcurves`. On 5.x, it's the real Channelbag's F-curves.

## The 4.5 LTS path explicitly

If you are not yet on 5.x and want pre-bridge code:

```python
import bpy

obj = bpy.context.active_object
if obj.animation_data is None:
    obj.animation_data_create()
if obj.animation_data.action is None:
    obj.animation_data.action = bpy.data.actions.new(name=f"{obj.name}_Action")

action = obj.animation_data.action
fcurve = action.fcurves.new(data_path="location", index=0)
fcurve.keyframe_points.insert(1, 0.0)
fcurve.keyframe_points.insert(24, 5.0)
```

This compiles on 4.5 LTS but on 5.x the `action.fcurves` attribute is absent or empty (depending on the exact 5.x version), and curves added there do not drive the animation.

## Detecting Slotted Actions support

```python
import bpy

def has_slotted_actions():
    major, minor, _ = bpy.app.version
    return (major, minor) >= (5, 0)
```

Use the bridge utility unconditionally if you can. Use the version sniff only when the bridge cannot help (e.g. enumerating slots, which is meaningful only on 5.x).

## Common AI mistakes

1. **Using pre-5.0 `action.fcurves.new(...)` in 5.x code**. The call may not raise but the curve will not drive anything because the slot/layer routing isn't set up.

2. **Forgetting the slot binding**:

   ```python
   action = bpy.data.actions.new("A")
   obj.animation_data.action = action
   # Missing: setting obj.animation_data.action_slot
   ```

   Without a slot binding, the Action has no idea which datablock it drives. Symptom: animation plays back as if it isn't there.

3. **Hardcoding the import path** to where it was in some older 5.x. Verify against current docs:
   - 5.1+: `from bpy_extras.anim_utils import action_ensure_channelbag_for_slot`

4. **Not calling `fcurve.update()`** after bulk inserts with `options={'FAST'}`. The curve is internally sorted and analytically prepared by `update()`.

5. **Treating `obj.animation_data` as always present**. It is `None` on a fresh object. Call `obj.animation_data_create()` first.

6. **Using `keyframe_insert` for high-volume baking**. It is convenient but slow for thousands of frames. Use direct F-curve access with `options={'FAST'}` for performance.

## Compatibility paths summary

| Operation | 4.5 LTS | 5.x | Cross-version |
| --- | --- | --- | --- |
| Insert a single keyframe | `obj.keyframe_insert("location", frame=1)` | Same | High-level API works on both |
| Get the F-curves for an Action+Object | `action.fcurves` | Channelbag inside Layer/Strip/Slot | `action_ensure_channelbag_for_slot(action, slot)` |
| Create an Action | `bpy.data.actions.new(...)` | Same | Same |
| Bind Action to ID | `obj.animation_data.action = action` | Same plus `action_slot` | Set both, the slot setter is a no-op on 4.5 LTS |

## Related

- `addon-scaffolding` for the registration of animation-driving operators
- Snippet `action-ensure-channelbag-for-slot.py` for a minimal copy-paste

## References

- Blender 5.x release notes (Slotted Actions section): https://developer.blender.org/
- `bpy_extras.anim_utils`: https://docs.blender.org/api/current/bpy_extras.anim_utils.html
- `bpy.types.Action`: https://docs.blender.org/api/current/bpy.types.Action.html
- 4.5 LTS reference: https://docs.blender.org/api/4.5/bpy.types.Action.html
