# Color Attribute Wheel

A runnable example that builds an HSV color wheel disc entirely with `bmesh` and
colors it with `Mesh.color_attributes.new()` — the modern attributes API, not the
deprecated `Mesh.vertex_colors` alias AI code keeps reaching for. It witnesses the
domain trap that comes with it: a `CORNER`-domain attribute is sized to
`len(mesh.loops)`, not `len(mesh.vertices)`, so per-vertex data has to be expanded
across face corners before it is written. The material wires the same attribute
into a Shader `Attribute` node (`attribute_type='GEOMETRY'`) feeding Base Color —
the step AI code most often skips, leaving the mesh gray even when the attribute
data is correct.

**What it witnesses:** a `FLOAT_COLOR` attribute on the `CORNER` domain, filled
with one `foreach_get` (loop → vertex index) and one `foreach_set` (loop color),
never a per-loop Python assignment. The check asserts the attribute is sized to
the loop count and *not* the vertex count, that it is `color_attributes.active_color`
(so a renderer or exporter actually picks it up), and that several probe loops
match the closed-form HSV value for the vertex they reference. A separate check
in the render path confirms the `Attribute` node is actually linked to Base
Color, not just present in the node tree.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python color_attribute_wheel.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python color_attribute_wheel.py -- --output wheel.png
blender --background --python color_attribute_wheel.py -- --output wheel.png --engine cycles
```

It exits non-zero on failure (missing/mis-sized/mis-domained attribute, wrong
active attribute, a probe color mismatch, or an unlinked Attribute node). The
`blender-smoke` workflow runs the check on Blender 4.5 LTS and 5.1.
