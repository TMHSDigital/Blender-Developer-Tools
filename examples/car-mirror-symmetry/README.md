# Car Mirror Symmetry

A runnable example that builds a generic hatchback as **one half** — a loft of
14 stations, each a 9-point half-ring from the bottom centerline out to the
roof centerline — and completes it with a **Mirror modifier**, evaluated
through the depsgraph, following
[`depsgraph-and-evaluated-data`](../../skills/depsgraph-and-evaluated-data/SKILL.md).
Wheels and lamps are separate objects mirrored the idiomatic way: the object
origin sits **on** the symmetry plane and the mesh data is offset — mirror
mirrors about the object's own origin, so you offset the data, never the
object.

**What it witnesses:** the original datablock keeps only the authored half
while the depsgraph carries the mirrored whole, and both directions are
closed forms:

- **Original holds the half.** Body datablock is exactly 126 verts / 231
  edges / 106 faces (14 × 9, loft closed forms), with exactly 28 centerline
  verts (probe: modifier applied into data → exit 3, datablock reads
  `(224, 434, 212)`).
- **Evaluated is the welded whole.** Exactly `2n − c = 224` verts (probe:
  `use_mirror_merge = False` → exit 5, **252** verts — the doubled seam;
  probe: one centerline vert pulled off the plane → exit 4, **27 ≠ 28**
  welded; probe: mirror axis off → exit 5, **126** — the half-car). The
  evaluated shell is watertight (every edge borders 2 faces) with Euler
  characteristic **2** — the two halves weld into a topological sphere.
- **Exact ±X partners.** Every evaluated vertex has a partner at negated X:
  measured deviation **0.000e+00** (mirror copies exactly; tol 2e-5 guards
  float32), evaluated bbox symmetric (`min.x == −max.x`).
- **Mirrored parts.** Wheels (96/81 half → 192/162 evaluated) and lamps
  (8/6 → 16/12) each double across the plane with partner deviation 0.0 —
  and each object origin reads `x == 0`.

**Why the checks target the modifier, not the base:** mutating a non-plane
base vertex cannot break the ±X pairing — the evaluated set is always
`half ∪ mirror(half)`, symmetric by construction. Realistic failures live in
the modifier (merge off, axis off, modifier applied into data, origin off
the plane), which is what the probes break.

**Version witness:** check output is byte-identical on Blender 4.5.11 LTS and
5.1.2. Mirror, `evaluated_get` / `to_mesh` / `to_mesh_clear` (no argument —
passing the mesh raises TypeError on both), and `TRACK_TO` constraint
behavior are stable across the pair; only the EEVEE engine id is
version-gated.

The render is the proof: hide the mirror and the still is literally half a
car — halved windshield and hood at the centerline, one headlamp. Render
notes: the loft is faceted by design (flat shading, no bevel modifier — the
modifier stack is Mirror only, so counts stay closed-form); the window band
is glass by construction class (steepest roof-rise slope is the windshield,
steepest drop the rear window, ring segment 5 the side windows), and the
glass is dielectric — metallic glass mirrors the key light and renders the
windshield as a hot salmon slab.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python car_mirror_symmetry.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python car_mirror_symmetry.py -- --output car.png
blender --background --python car_mirror_symmetry.py -- --output car.png --engine cycles
```

It exits non-zero on failure (applied mirror, doubled centerline, unwelded
seam, broken symmetry, or a mirrored part off its plane origin). The
`blender-smoke` workflow runs the check on Blender 4.5 LTS and 5.1.
