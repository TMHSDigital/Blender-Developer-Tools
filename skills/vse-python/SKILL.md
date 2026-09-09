---
name: vse-python
description: Build Video Sequence Editor timelines from Python. SequenceEditor.strips vs .sequences, new_effect length vs frame_end, and the 5.2 COLOR strip width/height bake from scene resolution.
standards-version: 1.10.0
---

# Video Sequence Editor in Python

## Trigger

Use this skill when the user:

- Builds or inspects a VSE / sequencer timeline from a script
- Mentions `sequence_editor`, `strips`, `sequences`, `new_effect`, COLOR strips, or `StripTransform`
- Hits `AttributeError: 'SequenceEditor' object has no attribute 'sequences'` on 5.x
- Hits `TypeError` on `new_effect` kwargs (`frame_end` vs `length`)
- Renders a sequencer composite whose COLOR cells ignore `transform.scale_*` after a resolution change

## High-level shape

```python
import bpy

scene = bpy.context.scene
se = scene.sequence_editor or scene.sequence_editor_create()
coll = se.strips if hasattr(se, "strips") else se.sequences

if bpy.app.version >= (5, 0, 0):
    strip = coll.new_effect(
        name="A", type="COLOR", channel=1,
        frame_start=1, length=10,
    )
else:
    strip = coll.new_effect(
        name="A", type="COLOR", channel=1,
        frame_start=1, frame_end=11,
    )
strip.color = (0.85, 0.10, 0.22)
```

Branch on `bpy.app.version`, never on `bpy.app.version_string`. An empty `bpy_prop_collection` is falsy — `se.strips or se.sequences` silently falls through to the legacy accessor on an empty timeline. Always branch on `hasattr`.

## Accessor: `.strips` vs `.sequences`

| | 4.5 LTS | 5.1 / 5.2+ |
| --- | --- | --- |
| Canonical collection | `.strips` (`.sequences` is a bridge to the same strips) | `.strips` only |
| `.sequences` | Present, same contents as `.strips` | `AttributeError` |

```python
def strips_coll(se):
    return se.strips if hasattr(se, "strips") else se.sequences
```

Do not write `se.sequences` in new code. On 5.x it is gone; on 4.5 `.strips` already exists.

## `new_effect` end kwarg

`strips.new_effect(...)` ends a strip with **one** accepted end argument. The other raises `TypeError`.

```python
span = (1, 33)  # end-exclusive [start, end)

if bpy.app.version >= (5, 0, 0):
    strip = coll.new_effect(
        name="A", type="COLOR", channel=1,
        frame_start=span[0], length=span[1] - span[0],
    )
else:
    strip = coll.new_effect(
        name="A", type="COLOR", channel=1,
        frame_start=span[0], frame_end=span[1],
    )
```

Timeline bounds: `frame_final_start` / `frame_final_end` / `frame_final_duration` on 4.5. On 5.x those names are deprecated aliases (removal announced for 6.0); canonical accessors are `left_handle` / `right_handle` / `duration`. Scene strips take four args — `new_scene(name, scene, channel, frame_start)` — with no `length` / `frame_end` kwarg on either version.

The `TRANSFORM` effect type is removed on 5.x. Place strips with per-strip `strip.transform` (`StripTransform`) on both versions. Effect inputs are `input_1` / `input_2` (creation kwargs `input1` / `input2`).

## COLOR strip intrinsic size (5.2)

4.5 LTS and 5.1 COLOR strips have **no** intrinsic size. `transform.scale_*` is a fraction of the **output frame**. Creating at factory resolution then rendering a tiny buffer is fine.

5.2 and later bake readonly `width` / `height` from **scene render resolution at `new_effect` time**. Scale and offset are then in that **media** space, not a later output size. Set scene resolution **before** building strips.

This split is **not** in the 5.2 `python_api` release notes. Witnessed by `examples/vse-cut-list/` `--check-pixels`.

```python
width, height = 96, 54
scene.render.resolution_x = width
scene.render.resolution_y = height

se = scene.sequence_editor or scene.sequence_editor_create()
coll = se.strips if hasattr(se, "strips") else se.sequences

if bpy.app.version >= (5, 0, 0):
    strip = coll.new_effect(
        name="A", type="COLOR", channel=1,
        frame_start=1, length=10,
    )
else:
    strip = coll.new_effect(
        name="A", type="COLOR", channel=1,
        frame_start=1, frame_end=11,
    )

if bpy.app.version >= (5, 2, 0):
    # 5.2+: readonly width/height baked at new_effect from scene.render
    assert (strip.width, strip.height) == (width, height)
    # strip.width = 64  # TypeError — readonly
else:
    # 4.5 / 5.1: no intrinsic size; hasattr(strip, "width") is False
    pass

strip.transform.scale_x = 0.36
strip.transform.scale_y = 0.36
```

Creating at factory 1920×1080 then dropping the scene to 96×54 for a check render makes a 0.36-scaled COLOR cell larger than the output. On 5.2 the long-runner covers the frame; pixel samples read the wrong strip.

A lone COLOR strip **does** honor `transform.scale_*` on 5.2. The break is media size vs a later output size, not "transform is ignored."

## Common AI mistakes

1. **`sequence_editor.sequences` on 5.x.** `AttributeError`. Use `.strips` (with `hasattr` only as a 4.5 bridge).

2. **Wrong `new_effect` end kwarg.** `frame_end=` on 5.x and `length=` on 4.5 both raise `TypeError`.

3. **Creating COLOR strips, then changing render size** (the 5.2 trap):

   ```python
   a = coll.new_effect(...)          # bakes 1920×1080 on 5.2
   scene.render.resolution_x = 96    # output changed; media size did not
   ```

   Set `scene.render.resolution_*` **before** `new_effect`.

4. **`se.strips or se.sequences`.** An empty collection is falsy, so this falls through to `.sequences` on a fresh editor.

5. **`TRANSFORM` effect type on 5.x.** Gone. Use `strip.transform`.

6. **Scene strip pointing at its own scene.** Feedback loop; renders transparent. Source a **separate** scene.

7. **Effect strips consume their inputs** only when stacked on a channel **above** those inputs. Below, the inputs keep compositing independently. A `GAMMA_CROSS` asked to outlast its inputs' overlap is silently clamped to the overlap.

## See also

- Example `examples/vse-cut-list/` — accessor rename, `new_effect` kwargs, save/reload, and the 5.2 COLOR size bake (`--check-pixels` asserts `A.width, A.height == render size` on 5.2+).
- Example `examples/vse-gamma-cross/` — `GAMMA_CROSS` blend curve.
- Audit log: `docs/technical-audit.md` § Findings the release notes did not list.

## References

- `bpy.types.SequenceEditor`: https://docs.blender.org/api/current/bpy.types.SequenceEditor.html
- `bpy.types.Sequence`: https://docs.blender.org/api/current/bpy.types.Sequence.html
- 4.5 LTS `SequenceEditor`: https://docs.blender.org/api/4.5/bpy.types.SequenceEditor.html
- 5.1 `SequenceEditor`: https://docs.blender.org/api/5.1/bpy.types.SequenceEditor.html
