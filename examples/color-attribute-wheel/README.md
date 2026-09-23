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

## Staging

The disc is zero-thickness, and the still used to show it as a paper-thin oval
hovering 8 cm above the floor. The render path now gives it a render-only
Solidify body (5 cm) and stands it at the same 52° lean on a dark plinth, with
a strut behind it, easel-style. The height is computed so the lowest point of
the rim rests on the plinth. The mesh `check()` asserts is unchanged: the
modifier is added after the check and only in the render path. Measured
framing on 5.2.1: fill 0.794 y, every margin ≥ 0.094.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python color_attribute_wheel.py --

# Falsifier: POINT-domain attribute. Must exit non-zero.
blender --background --python color_attribute_wheel.py -- --point-domain

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python color_attribute_wheel.py -- --output wheel.png
blender --background --python color_attribute_wheel.py -- --output wheel.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Topology ≠ closed form |
| 4 | Color attribute missing |
| 5 | Domain/type ≠ CORNER/FLOAT_COLOR (`--point-domain` lands here) |
| 6 | Attribute sized to verts, not loops |
| 7 | `active_color` not set |
| 8 | Probe loop color off HSV closed form |
| 9 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--point-domain`.

