# Car Mirror Symmetry

A runnable example that builds a stylized hatchback as **one half** — a loft
of 52 stations, each a 13-point half-ring from the bottom centerline out to
the roof centerline — and completes it with a **Mirror modifier**, evaluated
through the depsgraph, following
[`depsgraph-and-evaluated-data`](../../skills/depsgraph-and-evaluated-data/SKILL.md).
Wheels, headlamps, taillamps, grille, door mirrors and door handles are
separate objects mirrored the idiomatic way: the object origin sits **on**
the symmetry plane and the mesh data is offset — mirror mirrors about the
object's own origin, so you offset the data, never the object. The grille is
the one part authored *across* the plane: a half profile whose end points lie
exactly on `x = 0`, welded into one grille by the merge.

**What it witnesses:** the original datablock keeps only the authored half
while the depsgraph carries the mirrored whole, and both directions are
closed forms:

- **Original holds the half.** Body datablock is exactly 676 verts / 1289
  edges / 614 faces (52 × 13, loft closed forms), with exactly 104
  centerline verts (probe: modifier applied into data → exit 3, datablock
  reads `(1248, 2474, 1228)`).
- **Evaluated is the welded whole.** Exactly `2n − c = 1248` verts (probe:
  `use_mirror_merge = False` → exit 5, **1352** verts — the doubled seam;
  probe: one centerline vert pulled off the plane → exit 4, **103 ≠ 104**
  welded; probe: mirror axis off → exit 5, **676** — the half-car). The
  evaluated shell is watertight (every edge borders 2 faces) with Euler
  characteristic **2** — the two halves weld into a topological sphere.
- **Exact ±X partners.** Every evaluated vertex has a partner at negated X:
  measured deviation **0.000e+00** (mirror copies exactly; tol 2e-5 guards
  float32), evaluated bbox symmetric (`min.x == −max.x`).
- **Mirrored parts.** Offset parts double exactly: wheels 390/361 →
  780/722, headlamp 64/50 → 128/100, taillamp and each handle 48/34 →
  96/68, door mirror 80/66 → 160/132, partner deviation 0.0, every origin
  `x == 0` (probe: headlamp origin at `x = 0.01` → exit 12; probe: front
  wheel's mirror axis off → exit 14, `(390, 361)`). The split grille
  authors 36 verts with 8 on the plane and must evaluate to `2n − 8 = 64`
  with exactly 8 on-plane verts (probe: grille merge off → exit 14, **72**
  verts / 16 on the plane — two grilles; probe: one grille end point moved
  to `x = 0.004`, beyond the merge threshold → exit 13, 7 ≠ 8 on the plane).

**Why the checks target the modifier, not the base:** mutating a non-plane
base vertex cannot break the ±X pairing — the evaluated set is always
`half ∪ mirror(half)`, symmetric by construction. Realistic failures live in
the modifier (merge off, axis off, modifier applied into data, origin off
the plane), which is what the probes break.

**Version witness:** check output is byte-identical on Blender 4.5.11 LTS,
5.1.2 and 5.2.1 LTS. Mirror, `evaluated_get` / `to_mesh` / `to_mesh_clear`
(no argument — passing the mesh raises TypeError on both), `BVHTree`, and
`TRACK_TO` constraint behavior are stable across them; only the EEVEE
engine id is version-gated.

The render is the proof: hide the mirror and the still is literally half a
car — one headlamp, one door mirror, half a grille, a hood cut open at the
centerline. The camera stands on the key light's side, high enough to look
down the hood centerline so both halves read at once. The weld itself is
not a pixel witness — the hood and roof are nearly flat across the plane,
so an unwelded seam renders within 12/255 of the welded one; the `2n − c`
count is what catches it.

Render notes: the loft is smooth-shaded with sharp edges set on the
authored half by dihedral angle (35°) and material border — no bevel or
weighted-normal modifier, so the stack stays Mirror only and every count
stays closed-form. Boundary edges on the plane take the angle to their own
mirror image, `acos(1 − 2nₓ²)`, so the centerline shades smooth. The
previous faceted loft had a thin pink-white streak on the hood by the
windshield: not a seam (it sat at `|x|` 0.11–0.38, on the mirrored half, and
all weld checks passed) but a sliver facet — the loft's greenhouse points
collapsing onto the hood — flat-shaded and facing the key almost head on
(`n · −key = 0.967`). The redesigned ring lerps a hood layout into a cabin
layout, so no such sliver exists. Panel classes are by construction
position: underbody, rocker and arch cladding are trim; side glass is the
sill-to-glass-top segment under the roof, broken by a trim B-pillar; the
drip rail becomes the A-pillar; windshield and hatch glass are the roof
bands where the cabin factor ramps. The glass is a dark dielectric whose
base colour ramps toward steel blue at grazing angles (Layer Weight →
Color Ramp) — on a near-black stage there is little to reflect, and flat
dark glass read as dull paint. Lamps, grille, mirrors and handles are
closed superellipse pods seated on the skin by a `BVHTree` ray cast, with a
chrome bezel and an inset lens rather than flat boxes.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python car_mirror_symmetry.py --

# Falsifier: Mirror X off. Must exit non-zero (evaluated verts stay at n).
blender --background --python car_mirror_symmetry.py -- --no-mirror

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python car_mirror_symmetry.py -- --output car.png
blender --background --python car_mirror_symmetry.py -- --output car.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Body datablock is not the authored half |
| 4 | Authored centerline vert count ≠ 28 |
| 5 | Evaluated verts ≠ `2n − c` (`--no-mirror` lands here) |
| 6 | Evaluated on-plane verts ≠ centerline; also `--output` produced no file |
| 7 | Evaluated Euler characteristic ≠ 2 |
| 8 | Non-manifold edges in the evaluated shell |
| 9 | Evaluated verts lack a mirrored partner |
| 10 | Mirror partner deviation above tolerance |
| 11 | Evaluated bbox not symmetric about X |
| 12 | Mirrored-part origin off the plane |
| 13 | Mirrored-part datablock is not the authored half (verts, faces, on-plane verts) |
| 14 | Mirrored-part evaluated counts ≠ `2n − weld` / `2f`, or on-plane verts ≠ weld |
| 15 | Mirrored-part partner check failed |
| 16 | Mirrored-part evaluated mesh stayed on one side |
| 17 | Gallery framing violation (`--output` path only; `gallery_framing` returns 10, remapped) |
| 18 | Asset-quality floor violation (`--output` path only; `gallery_asset_quality` returns 11, remapped) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--no-mirror`.
