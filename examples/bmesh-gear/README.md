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

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python bmesh_gear.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python bmesh_gear.py -- --output gear.png
blender --background --python bmesh_gear.py -- --output gear.png --engine cycles
```

It exits non-zero on failure (topology mismatch or non-manifold edges). The `blender-smoke`
workflow runs the check on Blender 4.5 LTS and 5.1.
