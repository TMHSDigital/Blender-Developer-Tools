---
name: grease-pencil-v3
description: "Create and inspect Grease Pencil v3 (GPv3) data from Python: the datablock address split (bpy.data.grease_pencils_v3 on 4.5 LTS, bpy.data.grease_pencils on 5.x), layers.new -> frames.new(n).drawing -> add_strokes([counts]) -> per-point position/radius/opacity/vertex_color, lazily materialized drawing.attributes, and the Line Art modifier (source_type/source_object, edge-type flags, depsgraph-evaluated strokes, thickness removed in favor of radius). Use when the user scripts Grease Pencil strokes or Line Art, ports GPencil code to 4.3+ or 5.x, writes frame.strokes or GPencilStroke, or hits AttributeError on grease_pencils_v3, frame.drawing, frame.strokes or LineartModifier.thickness. Targets 5.2 LTS with 4.5 LTS fallback."
standards-version: 1.10.0
---

# Grease Pencil v3 in Python

## Trigger

Use this skill when the user:

- Creates Grease Pencil objects, layers, frames, or strokes from a script
- Mentions `grease_pencils`, `grease_pencils_v3`, `GreasePencil`, `GPencilStroke`, `drawing`, `add_strokes`, or the `LINEART` modifier
- Ports pre-4.3 GPencil code (frames that carry `.strokes` directly) to 4.5 LTS or 5.x
- Hits `AttributeError` on `bpy.data.grease_pencils_v3` (5.x), on `frame.drawing` (legacy data on 4.5), or on the Line Art modifier's `thickness` (5.x)
- Gets zero Line Art strokes and does not know why

## High-level shape

GPv3 exists on both supported versions, but at different addresses. Branch on the `bpy.app.version` tuple, never on `bpy.app.version_string`.

```python
import bpy


def gp_data_new(name):
    if bpy.app.version >= (5, 0, 0):
        return bpy.data.grease_pencils.new(name)   # 5.x: GPv3 owns the name
    return bpy.data.grease_pencils_v3.new(name)    # 4.5 LTS: GPv3 lives at _v3


gp = gp_data_new("Ink")
layer = gp.layers.new("Lines")
drawing = layer.frames.new(1).drawing
drawing.add_strokes([4, 4])                        # two strokes, four points each
for stroke in drawing.strokes:
    stroke.cyclic = True
    for i, pt in enumerate(stroke.points):
        pt.position = (float(i), 0.0, 0.0)
        pt.radius = 0.02
        pt.opacity = 1.0
        pt.vertex_color = (1.0, 0.5, 0.0, 1.0)

obj = bpy.data.objects.new("Ink", gp)              # obj.type == 'GREASEPENCIL'
bpy.context.collection.objects.link(obj)
```

The hierarchy is datablock -> `layers` -> `frames` -> `frame.drawing` -> `drawing.strokes` -> `stroke.points`. Strokes are allocated in one call with a list of point counts.

## Datablock address: the 4.5 trap

| | 4.5 LTS | 5.x (5.1, 5.2 LTS) |
| --- | --- | --- |
| GPv3 collection | `bpy.data.grease_pencils_v3` (`GreasePencilv3`) | `bpy.data.grease_pencils` (`GreasePencil`) |
| `bpy.data.grease_pencils` | **Legacy** GPencil: frames carry `.strokes`, no `.drawing` | GPv3 |
| `bpy.data.grease_pencils_v3` | Present | `AttributeError` |
| `bpy.types.GPencilStroke` | Present (legacy) | Gone |

The collection name is identical across versions while the API behind it is incompatible. Code that calls `bpy.data.grease_pencils.new(...)` unconditionally gets legacy GPencil on 4.5, and the first `frame.drawing` raises. Use the version-gated `gp_data_new` above on every creation path.

## Points are views over attributes

Stroke points are views over attribute layers on the drawing, not copies. Writing through the point view lazily creates the layers; a fresh drawing does not have them. After the writes above, `drawing.attributes` holds:

| Attribute | Domain | Type |
| --- | --- | --- |
| `position` | `POINT` | `FLOAT_VECTOR` |
| `radius` | `POINT` | `FLOAT` |
| `opacity` | `POINT` | `FLOAT` |
| `vertex_color` | `POINT` | `FLOAT_COLOR` |
| `cyclic` | `CURVE` | `BOOLEAN` |

For bulk reads, go through the raw buffer. Points are laid out stroke by stroke:

```python
def read_positions(drawing):
    pos = drawing.attributes["position"]
    buf = [0.0] * (3 * len(pos.data))
    pos.data.foreach_get("vector", buf)
    return buf
```

A minimal end-to-end build that runs on both 4.5 LTS and 5.2 LTS:

<!-- smoke: run -->
```python
import bpy

if bpy.app.version >= (5, 0, 0):
    assert not hasattr(bpy.data, "grease_pencils_v3")
    assert not hasattr(bpy.types, "GPencilStroke")
    gp = bpy.data.grease_pencils.new("SmokeGP")
else:
    assert hasattr(bpy.data, "grease_pencils_v3")
    gp = bpy.data.grease_pencils_v3.new("SmokeGP")

drawing = gp.layers.new("Ink").frames.new(1).drawing
drawing.add_strokes([3, 5])
for stroke in drawing.strokes:
    stroke.cyclic = True
    for i, pt in enumerate(stroke.points):
        pt.position = (float(i), 0.0, 0.5 * i)
        pt.radius = 0.03

mat = bpy.data.materials.new("SmokeInk")
bpy.data.materials.create_gpencil_data(mat)
gp.materials.append(mat)
obj = bpy.data.objects.new("SmokeGP", gp)
bpy.context.collection.objects.link(obj)

assert obj.type == 'GREASEPENCIL'
assert [len(s.points) for s in drawing.strokes] == [3, 5]
assert all(s.cyclic for s in drawing.strokes)
attrs = {a.name: (a.domain, a.data_type) for a in drawing.attributes}
assert attrs["position"] == ('POINT', 'FLOAT_VECTOR')
assert attrs["radius"] == ('POINT', 'FLOAT')
assert attrs["cyclic"] == ('CURVE', 'BOOLEAN')
buf = [0.0] * (3 * 8)
drawing.attributes["position"].data.foreach_get("vector", buf)
assert buf[3 * 4:3 * 5] == [1.0, 0.0, 0.5]   # stroke 2, point 1
assert gp.materials[0].grease_pencil is not None
```

Materials: `bpy.data.materials.create_gpencil_data(mat)` adds the `mat.grease_pencil` settings on both versions; append the material to `gp.materials`. To keep ink unlit, set `layer.use_lights = False`.

## Line Art modifier

Contours come from a `LINEART` modifier on a GPv3 object, evaluated through the depsgraph. No bake is needed to read the result.

```python
import math

import bpy


def add_lineart(gp_obj, source, gp_mat, radius=0.02):
    layer = gp_obj.data.layers.new("Ink")
    layer.frames.new(1)                            # a frame for the evaluated strokes
    mod = gp_obj.modifiers.new("LineArt", "LINEART")
    mod.source_type = "OBJECT"
    mod.source_object = source                     # load-bearing: None -> 0 strokes
    mod.use_contour = True
    mod.use_crease = True
    if hasattr(mod, "use_material"):
        mod.use_material = True
    if hasattr(mod, "use_intersection"):
        mod.use_intersection = True
    mod.crease_threshold = math.radians(130)
    mod.target_layer = "Ink"                       # layer name, not the layer
    mod.target_material = gp_mat
    if hasattr(mod, "thickness"):                  # 4.5 only: legacy px width
        mod.thickness = 22
    mod.radius = radius                            # portable width on 4.5 and 5.x
    return mod


def evaluated_counts(gp_obj):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    drawing = gp_obj.evaluated_get(dg).data.layers[0].frames[0].drawing
    strokes = list(drawing.strokes)
    return len(strokes), sum(len(s.points) for s in strokes)
```

- `source_object` is load-bearing: clearing it yields 0 evaluated strokes; restoring it recovers them.
- With every edge-type flag off (`use_contour`, `use_crease`, `use_loose`, `use_intersection`, `use_material`, `use_edge_mark`) the evaluator emits 0 strokes.
- Line Art is view-dependent: it draws from the scene camera, so count strokes from the same camera you render from.
- Stroke width: 4.5 exposes both `thickness` (legacy px) and `radius`; on 5.x (measured 5.1.2 and 5.2.1) `thickness` raises `AttributeError` and `radius` is the only width. Set `radius`; guard `thickness` with `hasattr`.
- The original data holds no Line Art strokes; read `evaluated_get(depsgraph).data`, not `obj.data`.

## Common AI mistakes

1. **Unconditional `bpy.data.grease_pencils.new(...)`.** On 4.5 LTS that is legacy GPencil and `frame.drawing` does not exist. Use `grease_pencils_v3` on 4.5, `grease_pencils` on 5.x.

2. **`bpy.data.grease_pencils_v3` on 5.x.** `AttributeError`. The `_v3` alias is gone; GPv3 took the plain name.

3. **Legacy stroke code: writing strokes into `frame.strokes`.** That is the pre-4.3 GPencil shape (`GPencilStroke`). In GPv3 a frame owns a `drawing`, and strokes are allocated with `drawing.add_strokes([counts])`.

4. **Referencing `bpy.types.GPencilStroke`** in type checks or annotations. Gone on 5.x; it only names the legacy type on 4.5.

5. **Expecting point attributes on a fresh drawing.** `radius`, `opacity`, `vertex_color` and `cyclic` appear in `drawing.attributes` only after something writes them. Do not `drawing.attributes["radius"]` before the first write.

6. **`mod.thickness = ...` on the Line Art modifier on 5.x.** `AttributeError`. Use `mod.radius`; set `thickness` only under `hasattr`.

7. **Line Art with no `source_object`, or every edge type off.** Each yields an empty drawing with no error. Set `source_type='OBJECT'` and `source_object`, and leave `use_contour` on.

8. **Counting Line Art strokes on `obj.data`.** The modifier output exists only on the evaluated object.

## See also

- Example [`examples/grease-pencil-rosette/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/grease-pencil-rosette): the address split, the 4.5 legacy trap, lazy attribute materialization, and a closed-form round-trip of every position through the `position` buffer.
- Example [`examples/gp-lineart-contour/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/gp-lineart-contour): Line Art evaluated through the depsgraph, the `source_object` and edge-flag zero-stroke failure modes, and the `thickness` vs `radius` split.
- Skill [`porting-to-blender-5`](${CLAUDE_PLUGIN_ROOT}/skills/porting-to-blender-5): the Grease Pencil row in the 4.x to 5.x break table.
- Skill [`depsgraph-and-evaluated-data`](${CLAUDE_PLUGIN_ROOT}/skills/depsgraph-and-evaluated-data): `evaluated_get` for reading modifier output.

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`gp-lineart-contour`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/gp-lineart-contour): Grease Pencil LINEART modifier ink via the depsgraph on a cel-shaded lighthouse diorama. Falsify: `--no-contour` (exit 5).
- [`grease-pencil-rosette`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/grease-pencil-rosette): Grease Pencil v3's attribute-based API — layer → frames.new(1).drawing → add_strokes → per-point position/radius/opacity/vertex_color — drawing five nested neon rose curves. Falsify: `--open-strokes` (exit 5).

<!-- examples:end -->

## References

- `bpy.types.GreasePencil` (5.x): https://docs.blender.org/api/current/bpy.types.GreasePencil.html
- `bpy.types.GreasePencilDrawing`: https://docs.blender.org/api/current/bpy.types.GreasePencilDrawing.html
- `bpy.types.GreasePencilLineartModifier`: https://docs.blender.org/api/current/bpy.types.GreasePencilLineartModifier.html
- 4.5 LTS `bpy.types.GreasePencilv3`: https://docs.blender.org/api/4.5/bpy.types.GreasePencilv3.html
- 4.5 LTS `bpy.types.GreasePencilDrawing`: https://docs.blender.org/api/4.5/bpy.types.GreasePencilDrawing.html
- 4.5 LTS `bpy.types.GreasePencilLineartModifier`: https://docs.blender.org/api/4.5/bpy.types.GreasePencilLineartModifier.html
