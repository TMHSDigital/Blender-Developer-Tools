---
name: curves-and-text
description: "Build legacy Curve and TextCurve datablocks from Python: bpy.data.curves.new(type='CURVE' or 'FONT'), splines.new('BEZIER'), bezier_points.add, handle types, bevel_depth, bevel_resolution, resolution_u, use_fill_caps, extrude, TextCurve.body, align_x/align_y, the built-in Bfont, and reading the tessellated result through evaluated_get(...).to_mesh() / to_mesh_clear(). Use when the user scripts beveled tubes, wires, logos or 3D text, reads obj.data.vertices on a curve or text object and finds nothing, gets an uncapped hollow pipe, mis-predicts text or tube dimensions, or hits ReferenceError after to_mesh_clear(). Targets 5.2 LTS with 4.5 LTS fallback."
standards-version: 1.10.0
---

# Curves and Text

## Trigger

Use this skill when the user:

- Creates a curve or 3D text object from a script (`bpy.data.curves.new`, `type='CURVE'` or `type='FONT'`)
- Mentions `splines`, `bezier_points`, `bevel_depth`, `bevel_resolution`, `use_fill_caps`, `extrude`, `TextCurve`, `body`, `align_x`, or Bfont
- Needs the vertex positions, bounds or face count of a beveled curve or extruded text
- Reports that a tube renders as a hollow pipe, or that text dimensions do not match the numbers they set
- Hits `ReferenceError` reading a mesh after `to_mesh_clear()`

## High-level shape

A curve or text object is a **Curve datablock**, not a mesh. Author it on the data API, link an object to a collection, and read geometry only through the depsgraph:

```python
import bpy

curve = bpy.data.curves.new("Tube", 'CURVE')   # 'FONT' returns a TextCurve
curve.dimensions = '3D'
curve.bevel_depth = 0.15
curve.use_fill_caps = True

spline = curve.splines.new('BEZIER')
spline.bezier_points.add(3)                     # one point exists already -> 4
for i, bp in enumerate(spline.bezier_points):
    bp.co = (i, 0.0, 0.15)
    bp.handle_left_type = 'AUTO'
    bp.handle_right_type = 'AUTO'

obj = bpy.data.objects.new("Tube", curve)
bpy.context.collection.objects.link(obj)
```

No operator, no mesh conversion: the tube renders from the curve settings. The curve and text APIs taught here do **not** diverge between 4.5 LTS and 5.x; the examples run the same code on 4.5 LTS, 5.1 and 5.2 LTS, and the curve tessellation counts are identical across them. The one version split nearby is `bpy.app.version_string` (see Text below).

## Curves: splines, points, bevel

- `splines.new('BEZIER')` creates a spline that already holds **one** point. `bezier_points.add(n - 1)` gives `n` points; `add(n)` gives `n + 1`.
- `bp.co` is the point; `handle_left_type` / `handle_right_type` = `'AUTO'` lets Blender place smooth handles. For exact shapes (a straight leg, a quarter-circle bend), set both types to `'FREE'` **first**, then write `bp.co`, `bp.handle_left`, `bp.handle_right`.
- `bevel_depth` is the tube **radius**. `bevel_resolution` and `resolution_u` set the cross-section and along-curve sampling.
- `use_fill_caps = True` closes the ends of an open spline with faces. Without it the ends are hollow; the caps exist only in the evaluated mesh, so check them there.

Measured closed forms ([`curve-bevel-arc`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/curve-bevel-arc), a semicircle of radius 1.5, centerline at `z = bevel_depth`):

| Quantity | Value |
| --- | --- |
| Evaluated Z span | `[0, 2 * bevel_depth]` (the tube rests on the floor) |
| Evaluated X span | `2 * radius + 2 * bevel_depth` |
| Verts / faces (8 points, `bevel_resolution` 4, `resolution_u` 12, caps on) | 1044 / 1028 — measured, no closed form |

Tessellation counts have no simple formula. Treat them as a regression pin, never derive them.

<!-- smoke: run -->
```python
import bpy, math

BEVEL, RADIUS, N = 0.15, 1.5, 8
cu = bpy.data.curves.new("Arc", 'CURVE')
cu.dimensions = '3D'
cu.bevel_depth = BEVEL
cu.bevel_resolution = 4
cu.resolution_u = 12
cu.use_fill_caps = True
sp = cu.splines.new('BEZIER')
sp.bezier_points.add(N - 1)
for i, bp in enumerate(sp.bezier_points):
    a = i / (N - 1) * math.pi
    bp.co = (RADIUS * math.cos(a), RADIUS * math.sin(a), BEVEL)
    bp.handle_left_type = 'AUTO'
    bp.handle_right_type = 'AUTO'
obj = bpy.data.objects.new("Arc", cu)
bpy.context.collection.objects.link(obj)

bpy.context.view_layer.update()
ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
me = ev.to_mesh()
try:
    zs = [v.co.z for v in me.vertices]
    xs = [v.co.x for v in me.vertices]
    n_faces = len(me.polygons)
finally:
    ev.to_mesh_clear()

assert len(cu.splines[0].bezier_points) == N
assert n_faces > 0
assert abs(min(zs)) < 1e-4 and abs(max(zs) - 2 * BEVEL) < 1e-4
assert abs((max(xs) - min(xs)) - (2 * RADIUS + 2 * BEVEL)) < 0.05
```

## Text: TextCurve, body, alignment, Bfont

`bpy.data.curves.new(name, type='FONT')` returns a `bpy.types.TextCurve`, which is also a `bpy.types.Curve`; the object's `type` is `'FONT'`. The built-in font (`font.name` contains `"Bfont"`, "Bfont Regular") is assigned and loaded even under `--background`, so no font file is needed.

- `body` is plain assignable text. Editing it regenerates the geometry: more characters give a strictly wider evaluated mesh.
- `align_x = 'CENTER'`, `align_y = 'CENTER'` center the text on the object origin.
- Flat text (no `extrude`, no `bevel_depth`) is already **filled**: the evaluated mesh has faces, and its Z extent is 0.
- `extrude` and `bevel_depth` give exact solids: evaluated Z extent = `2 * (extrude + bevel_depth)`, and a round bevel pushes an upright glyph's outline out by exactly `bevel_depth`.
- A **curved** glyph overshoots: a body ending in "e" grew 0.0208 on the right for a 0.02 bevel (#505). Assert outline growth exactly only on a straight-sided edge, and give curved edges a band.
- Other fonts load with `bpy.data.fonts.load(path, check_existing=True)`. Blender ships fonts under `bpy.utils.system_resource('DATAFILES')` + `fonts/` (`Inter.woff2`, `DejaVuSansMono.woff2` on 4.5 LTS and 5.x). On 4.5 LTS, Inter's variable-font outlines are built with broken counters, so use `DejaVuSansMono.woff2` there. Bfont's "1" is a bare stem that reads as a capital I.

Version split: `bpy.app.version_string` is `"5.1.2"` on 5.x but `"4.5.11 LTS"` on 4.5. Use it as display text in `body` if you like, but branch on the `bpy.app.version` tuple, never on the string.

<!-- smoke: run -->
```python
import bpy

EXTRUDE, BEVEL = 0.06, 0.02
txt = bpy.data.curves.new("Stamp", type='FONT')
txt.body = bpy.app.version_string
txt.align_x = 'CENTER'
txt.align_y = 'CENTER'
txt.extrude = EXTRUDE
txt.bevel_depth = BEVEL
txt.bevel_resolution = 3
obj = bpy.data.objects.new("Stamp", txt)
bpy.context.collection.objects.link(obj)

deps = bpy.context.evaluated_depsgraph_get()
deps.update()
ev = obj.evaluated_get(deps)
me = ev.to_mesh()
try:
    zs = [v.co.z for v in me.vertices]
    n_faces = len(me.polygons)
finally:
    ev.to_mesh_clear()

assert isinstance(txt, bpy.types.TextCurve) and isinstance(txt, bpy.types.Curve)
assert obj.type == 'FONT' and "Bfont" in txt.font.name
assert n_faces > 0
assert abs((max(zs) - min(zs)) - 2 * (EXTRUDE + BEVEL)) < 1e-4
```

## Reading the evaluated mesh

`obj.data` on a curve or text object is the Curve, so it has no `vertices`. The tessellated mesh (bevel, caps, extrude, glyph fill) exists only after evaluation: `obj.evaluated_get(depsgraph).to_mesh()`, then `to_mesh_clear()` in a `finally`. After `to_mesh_clear()` the returned Mesh is dead and any access raises `ReferenceError`; copy out the numbers you need first. The full lifetime contract is in [`depsgraph-and-evaluated-data`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/skills/depsgraph-and-evaluated-data/SKILL.md) § The lifetime rule.

After changing curve settings or `body` in the same script, call `bpy.context.view_layer.update()` or `depsgraph.update()` before evaluating again, as both examples do.

## Common AI mistakes

1. **Reading `obj.data.vertices` on a curve or text object.** The Curve has no vertices. Evaluate and use `to_mesh()`.

2. **`bezier_points.add(n)` for `n` points.** The spline starts with one point; this yields `n + 1`.

3. **Forgetting `use_fill_caps`.** An open beveled spline renders as a hollow pipe. The caps are faces in the evaluated mesh, not a flag to re-read.

4. **Treating `bevel_depth` as a diameter.** It is the radius: a tube spans `2 * bevel_depth`, and text Z extent is `2 * (extrude + bevel_depth)`.

5. **Exact bevel growth on every glyph edge.** Straight sides grow by exactly `bevel_depth`; curved glyphs overshoot (#505). Use a band.

6. **Converting to a mesh or calling curve operators to get a tube.** Bevel, caps and extrude render straight from the Curve datablock.

7. **Deriving tessellation counts.** Vert/face counts are measured regression pins (1044 / 1028 for the arc above), not closed forms.

8. **Shipping a font file for headless text.** Bfont is built in and loaded under `--background`.

9. **Parsing `version_string` as semver.** `"4.5.11 LTS"` breaks it. Compare `bpy.app.version` tuples.

10. **Using the mesh after `to_mesh_clear()`.** `ReferenceError`. Read first, clear in `finally`.

## See also

- Example [`examples/curve-bevel-arc/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/curve-bevel-arc) — Bezier semicircle with `bevel_depth`, `use_fill_caps`, measured tessellation and closed-form spans; falsifier `--no-caps` (exit 7).
- Example [`examples/text-version-stamp/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/text-version-stamp) — `TextCurve` with `body`, Bfont, extrude/bevel closed forms, the #505 trailing-glyph band, and the dead-mesh `ReferenceError`; falsifier `--wrong-body` (exit 4).
- Skill [`depsgraph-and-evaluated-data`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/skills/depsgraph-and-evaluated-data/SKILL.md) — `evaluated_get` / `to_mesh` / `to_mesh_clear` lifetimes.

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`curve-bevel-arc`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/curve-bevel-arc): A beveled Bezier semicircle authored on bpy.types.Curve — splines.new('BEZIER'), bezier_points, bevel_depth, use_fill_caps — so the curve renders as a solid tube without a prior mesh conversion. Falsify: `--no-caps` (exit 7).
- [`text-version-stamp`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/text-version-stamp): The TextCurve data API — curves.new(type='FONT'), live body text from bpy.app.version_string, extrude and bevel_depth solids, and evaluated-mesh conversion. Falsify: `--wrong-body` (exit 4).

<!-- examples:end -->

## References

- `bpy.types.Curve`: https://docs.blender.org/api/current/bpy.types.Curve.html
- `bpy.types.TextCurve`: https://docs.blender.org/api/current/bpy.types.TextCurve.html
- `bpy.types.Spline`: https://docs.blender.org/api/current/bpy.types.Spline.html
- `bpy.types.BezierSplinePoint`: https://docs.blender.org/api/current/bpy.types.BezierSplinePoint.html
- `bpy.types.Object.to_mesh`: https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.to_mesh
- 4.5 LTS `Curve`: https://docs.blender.org/api/4.5/bpy.types.Curve.html
- 4.5 LTS `TextCurve`: https://docs.blender.org/api/4.5/bpy.types.TextCurve.html
- 4.5 LTS `Spline`: https://docs.blender.org/api/4.5/bpy.types.Spline.html
