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

The still mounts the checked gear in a small gear train on a painted steel
backplate over a walnut plinth: a blued 8-tooth pinion above right and a
22-tooth gunmetal wheel with a spoked web below left, each on a hub boss,
steel shaft, washer and hex nut. The companions are render-only meshes built
from the same four-verts-per-tooth profile, pitched to the checked gear
(pitch radius midway between root and tip, so all three share one circular
pitch), and each is spun so a gap sits on the line of centres facing a tooth
of the checked gear. A render-only Bevel modifier chamfers the edges after
the check has run, so the mesh the check counts is untouched.

The checked gear keeps its machined finish: lathe-faced caps whose turning
marks run concentric about the gear's own axis (object coordinates), far
finer than a pixel, so they read only as a satin sheen, and rougher hobbed
tooth flanks. A softbox above and left of the camera gives the brass face
one warm reflection. There is no bore in the checked gear: the closed-form
topology check counts exactly two rings and two caps, so the hub boss and nut
sit on its face rather than faking a hole.

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
