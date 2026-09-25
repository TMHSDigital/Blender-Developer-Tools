# Bmesh Gear

A runnable example that builds a 14-tooth gear entirely with bmesh — profile ring, face,
`extrude_face_region`, translate — following the ownership contract from
[`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md) and the
[`always-free-bmesh`](../../rules/always-free-bmesh.mdc) rule: every `bmesh.new()` is paired
with `bm.free()` in a `try`/`finally`.

**What it witnesses:** parametric bmesh construction has exactly predictable topology. The
check asserts the closed-form counts — verts = 2 × (4 × teeth), faces = sides + 2 caps,
edges = 3 × profile — and that the result is watertight (every edge borders exactly two
faces). If an op leaks geometry or a face fails to close, the math catches it.

The still leans the gear back on a matte inclined display wedge. Both
contacts are derived from the posed mesh: the lowest back-cap vertex sits 3 mm
into the floor, and the wedge's slope lies in the back-cap plane, so the lean
is carried rather than held in the air.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python bmesh_gear.py --

# Falsifier: skip the extrude. Must exit non-zero (topology).
blender --background --python bmesh_gear.py -- --no-extrude

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python bmesh_gear.py -- --output gear.png
blender --background --python bmesh_gear.py -- --output gear.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Topology ≠ closed form (`--no-extrude` lands here) |
| 4 | Non-manifold edges |
| 6 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--no-extrude`.
