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

The finish follows how a gear blank is actually cut, and the render path
changes only the material and lights — the mesh the check counts is untouched.
The caps are lathe-faced: turning marks run concentric about the gear's own
axis (object coordinates, so they centre on that axis rather than on a
bounding-box corner), far finer than a pixel, so they read only as a narrow
satin roughness band and a whisper of bump — the soft highlight that fans
from the centre. The tooth flanks are hobbed, a rougher finish that spreads
the light across every facet. The key highlight on the face is a softbox
placed on the camera ray's reflection about the front cap, and a low bounce
card gives the downward flanks something to mirror. There is no bore: the
closed-form topology check counts exactly two rings and two caps, so the
gear stays a solid blank rather than faking a hole in the shader.

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
| 10 | `--output` framing violation (Layer 1 fill / margin gate, `gallery_framing`) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--no-extrude`.
