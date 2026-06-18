---
name: slotted-actions-animation
description: Animate from Python under the Slotted Actions architecture (data model shipped in Blender 4.4). Action contains Layers contain Strips contain Channelbags. Cross-version channelbag access - action_ensure_channelbag_for_slot is new in 5.0; on 4.4/4.5 LTS use strip.channelbag(slot, ensure=True) or the still-present legacy action.fcurves.
standards-version: 1.10.0
---

# Slotted Actions Animation

## Trigger

Use this skill when the user:

- Wants to create or edit animation from Python in Blender 5.x
- Mentions `Action`, `slot`, `channelbag`, `keyframe_insert`, `fcurves`
- Has older 4.x animation code (`action.fcurves.new(...)`) that no longer works in 5.x
- Asks how to insert keyframes programmatically and have them persist

## What changed and why

Blender **4.4** introduced the **Slotted Actions** data model to support non-linear, multi-target animation. The old model was a flat list of F-curves owned directly by the Action, which made it impossible for one Action to drive two different IDs (e.g. an armature pose and the armature's custom property channels at the same time) without overwriting each other.

Two version boundaries matter:

- **Blender 4.4 / 4.5 LTS**: the slotted data model (`action.slots`, `action.layers`, `strip.channelbag`) is present **alongside** the legacy flat API (`action.fcurves`, `action.groups`, `action.id_root`), which still works as a proxy. The helper `bpy_extras.anim_utils.action_get_channelbag_for_slot(action, slot)` exists; `action_ensure_channelbag_for_slot` does **not**.
- **Blender 5.0+**: the legacy flat API was **removed** (`action.fcurves` raises `AttributeError`). The new helper `bpy_extras.anim_utils.action_ensure_channelbag_for_slot(action, slot)` is added.

The slotted model:

```
Action
  Slots[]           # one per ID being driven
  Layers[]          # animation layers, blendable
    Strips[]        # time ranges within a layer
      Channelbags[] # one per slot, holds the actual F-curves
        FCurves[]
```

On 5.0+, code that walks `action.fcurves` directly raises `AttributeError` because that property was removed; the F-curves live inside a Channelbag inside a Strip inside a Layer. On 4.4 / 4.5 LTS `action.fcurves` still works as a proxy.

## Getting a channelbag across versions

`bpy_extras.anim_utils.action_ensure_channelbag_for_slot(action, slot)` is **new in Blender 5.0**. It ensures the Action has a Layer, a Strip in that Layer, and a Channelbag for the given Slot, then returns the Channelbag. It does **not** exist on 4.4 / 4.5 LTS — there is no auto-detecting shim, and importing-and-calling it on 4.5 raises `AttributeError`.

On 4.4 / 4.5 LTS, ensure the channelbag yourself with `strip.channelbag(slot, ensure=True)` (the slotted model is present there), or just use the still-present legacy `action.fcurves`. So a genuinely cross-version helper must branch on `bpy.app.version`:

Import path (5.0+) verified against the Blender 5.1 API reference: `bpy_extras.anim_utils.action_ensure_channelbag_for_slot(action, slot)`. See [`bpy_extras.anim_utils`](https://docs.blender.org/api/current/bpy_extras.anim_utils.html).

```python
import bpy


def get_channelbag_for_slot(action, slot):
    """Return the Channelbag for `slot`, creating layer/strip/channelbag as needed.

    Verified on Blender 4.5.10 LTS and 5.1.1.
    """
    if bpy.app.version >= (5, 0, 0):
        from bpy_extras.anim_utils import action_ensure_channelbag_for_slot
        return action_ensure_channelbag_for_slot(action, slot)
    # 4.4 / 4.5 LTS: the ensure-helper does not exist; build the path explicitly.
    layer = action.layers[0] if action.layers else action.layers.new("Layer")
    strip = layer.strips[0] if layer.strips else layer.strips.new(type='KEYFRAME')
    return strip.channelbag(slot, ensure=True)


def get_channelbag_for_object(obj):
    """Return the Channelbag for obj's animation, creating Action and Slot if needed."""
    if obj.animation_data is None:
        obj.animation_data_create()

    action = obj.animation_data.action
    if action is None:
        action = bpy.data.actions.new(name=f"{obj.name}_Action")
        obj.animation_data.action = action

    # Slots exist on 4.4+; create and bind one for this ID if not set.
    slot = obj.animation_data.action_slot
    if slot is None:
        slot = action.slots.new(id_type='OBJECT', name=obj.name)
        obj.animation_data.action_slot = slot

    return get_channelbag_for_slot(action, slot)
```

The version boundary that matters is `bpy.app.version >= (5, 0, 0)` (legacy removed / ensure-helper added), **not** `hasattr(action, "slots")` — `action.slots` is present on 4.4 and 4.5 too, so that check does not distinguish 4.5 from 5.x.

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
# get_channelbag_for_slot is the cross-version helper defined above.


def get_or_create_fcurve(obj, data_path, index):
    if obj.animation_data is None:
        obj.animation_data_create()

    action = obj.animation_data.action
    if action is None:
        action = bpy.data.actions.new(f"{obj.name}_Action")
        obj.animation_data.action = action

    slot = obj.animation_data.action_slot
    if slot is None:
        slot = action.slots.new(id_type='OBJECT', name=obj.name)
        obj.animation_data.action_slot = slot

    cbag = get_channelbag_for_slot(action, slot)

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
- `cbag.fcurves` is the unified access point on both 4.4/4.5 LTS and 5.x. The `get_channelbag_for_slot` helper above returns the slot's real Channelbag on every version (via `strip.channelbag(slot, ensure=True)` on 4.4/4.5, the ensure-helper on 5.0+).

## The legacy `action.fcurves` path (4.4 / 4.5 LTS only)

On 4.4 and 4.5 LTS the legacy flat API is still present and is the simplest path if you do not need to target 5.x:

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

This works on 4.4 / 4.5 LTS, but on **5.0+** the `action.fcurves` attribute was removed entirely, so `action.fcurves.new(...)` raises `AttributeError`. For 5.x, go through the channelbag (`get_channelbag_for_slot` above).

## Detecting the version boundaries

```python
import bpy

def has_slotted_model():
    # action.slots / layers / strip.channelbag: shipped in Blender 4.4.
    return bpy.app.version >= (4, 4, 0)

def legacy_fcurves_removed():
    # action.fcurves / groups / id_root removed, and
    # action_ensure_channelbag_for_slot added: Blender 5.0.
    return bpy.app.version >= (5, 0, 0)
```

The slotted data model (and `action.slots`) is meaningful on 4.4 and 4.5 too, so do not gate slot code behind `>= (5, 0)`. The boundary that decides legacy-removal and which channelbag helper exists is `>= (5, 0, 0)` — that is the check `get_channelbag_for_slot` uses above.

## Common AI mistakes

1. **Using legacy `action.fcurves.new(...)` in 5.x code**. On Blender 5.0+ the `action.fcurves` property was removed, so this raises `AttributeError: 'Action' object has no attribute 'fcurves'`. Go through a channelbag instead.

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

| Operation | 4.4 / 4.5 LTS | 5.x | Cross-version |
| --- | --- | --- | --- |
| Insert a single keyframe | `obj.keyframe_insert("location", frame=1)` | Same | High-level API works on both |
| Get the F-curves for an Action+Slot | `strip.channelbag(slot, ensure=True)`, or legacy `action.fcurves` | `action_ensure_channelbag_for_slot(action, slot)` | `get_channelbag_for_slot(action, slot)` (branches on version) |
| Create an Action | `bpy.data.actions.new(...)` | Same | Same |
| Bind Action to ID | `obj.animation_data.action = action` + `action_slot` | Same | `action_slot` is settable on 4.4+; set both |

## Related

- `addon-scaffolding` for the registration of animation-driving operators
- Snippet `action-ensure-channelbag-for-slot.py` for a minimal copy-paste

## References

- Blender 5.x release notes (Slotted Actions section): https://developer.blender.org/
- `bpy_extras.anim_utils`: https://docs.blender.org/api/current/bpy_extras.anim_utils.html
- `bpy.types.Action`: https://docs.blender.org/api/current/bpy.types.Action.html
- 4.5 LTS reference: https://docs.blender.org/api/4.5/bpy.types.Action.html
