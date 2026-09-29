# Wingback armchair

A showcase piece, not an example, and the seventh in the `household`
category. It builds a procedural reading corner: a Queen Anne /
Chesterfield-style wingback armchair in oxblood leather beside a round side
table with a brass reading lamp and two books, on a fringed wool rug.

- a wool rug 1.86 × 1.40 m, 10 mm thick with rounded edges, woven (in its
  material) with an ivory guard, a madder border with a running motif, an
  indigo field, a stepped medallion and corner spandrels, and 84 cotton
  tassels along its two short ends, each rolled its own way about its path
  so it lies on the floor along one edge;
- a tall reclined back, deep-button tufted: thirteen leather buttons on a
  diamond lattice (0.11 m columns, 0.12 m rows), each seated in a funnelled
  dimple, the leather puffed into pillows between them and folded into sharp
  pleats along every line that joins two diagonal neighbours; beyond the
  lattice the pleats run straight out to the top edge and the sides. The
  back's crest is arched and its corners roll down into the wings;
- two wings sweeping forward from the back and down into the arms, crowned
  on both faces, with a piped front edge from inside the arm's roll to inside
  the back;
- two rolled arms, each one lofted section — a flat inner face, an English
  roll over the top that tucks under on the outside, a flared outer panel —
  with crowned ends, a piped welt round the front seam and a row of 28 brass
  nailheads following the scroll;
- an upholstered seat base whose crowned front rail carries a row of 19
  nailheads, and a loose seat cushion with a crowned top, bulged boxing and
  piped welts on both seams, resting on the deck;
- cabriole front legs (knee, ankle, pad foot) tenoned into the arms, and
  square tapered rear legs splayed back into brass ferrules with level soles;
- a walnut side table: a moulded round top, a turned baluster pedestal, three
  snake-foot legs on pad feet;
- a brass reading lamp on the table: a domed base, a knopped stem, a socket,
  a warm bulb, a harp to a finial, a three-arm spider and a linen empire
  shade; and two cloth-bound books, each a case with a rounded spine round a
  page block that bites both boards.

Every face carries a `part` tag (a face attribute written as each part is
built), and the audits classify shells by it. The measurements themselves
are read off the mesh.

The tufted panel is a grid laid out in the lattice's own pitch: a tenth of
a button spacing in each direction, so every pleat line and every button
passes through grid vertices. Each grid cell is split along the diagonal of
the nearest pleat, which is what keeps the folds sharp rather than stepped.
Buttons and nailheads are placed by casting a ray onto the finished host (the
back, an arm, the rail) and are aimed down the host's normal there; the
buttons along the crown's normal, which is the dimple's axis of symmetry.

Things the coplanar budget forced:

- Neighbouring tassels shared the flat faces of their buried and floor-lying
  segments (228, then 120, then 17 pairs). Each tassel now varies its heights
  along the path and is rolled its own way about it, with its path lowered by
  `r cos(roll)` so its lowest vertex still lies on the floor.
- A cushion profile facet sloped at 22.4°, where the welt cord's hexagonal
  facet sits at 22.5°, and the two planes met along the whole seam (180
  pairs). The profile point moved 0.6 mm.
- Consecutive nailheads' bottom caps share a plane on a flat run, so their
  sink alternates by 0.3 mm; one nail's side facet met an arm panel face and
  another's met its neighbour, fixed by the per-nail phase step.

Shading follows what each part is: upholstery, turned wood, brass and cords
are smooth-shaded; pleats sharper than 40°, board edges and every material
boundary stay crisp. The leather is an oxblood with a two-octave mottle,
rubbed lighter and browner where it faces up, darkened in the pleats and
seams by ambient occlusion, with a pebbled grain and crinkles in the bump
and a waxed coat. Brass carries a studio in its material (from
`showcase/espresso-machine`), so it reads as metal on the dark stage.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`,
`procedural-materials-and-shaders`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: a chair 0.868 m wide, its seat 0.453 m and its back 1.111 m
above the rug; a side table 0.575 m high and 0.47 m across. The outer AABB
is 2.0304 × 1.400 × 1.160 m: the tassels set the width, the rug the depth
and the lamp's finial the top. The origin is under the rug.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 43700–44900 | 44324 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 9 distinct; face floors ≥14500 leather, ≥3350 wood, ≥4450 brass, ≥620 shade, ≥615 rug, ≥1390 fringe, ≥114 cloth, ≥11 paper, ≥195 bulb | 9 slots; 15712 / 3628 / 4825 / 672 / 668 / 1512 / 124 / 12 / 212 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (2.0304, 1.400, 1.160) m ± 0.01 | (2.0304, 1.4000, 1.1600), zmin 0 |
| Collider tris | ≤ 820 | 802 |
| Export | written, size > 0, removed after measuring | 3509556 bytes |

No falsifier changes the topology or the envelope: every run measures the
default's 44324 triangles and AABB.

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. Construction uses no RNG; two default runs print
identical measurements.

### Hygiene

Recomputed from the generated mesh, not asserted about the script.

| Axis | Declared | Measured |
| --- | --- | --- |
| Non-manifold edges | 0 | 0 |
| Loose verts / edges | 0 / 0 | 0 / 0 |
| Doubles merged at 1e-5 | 0 | 0 |
| Zero-area faces | 0 | 0 |
| N-gons | 0 | 0 |
| Coplanar cross-shell face pairs (KD range 0.05 m, plane ε 1e-4) | 0 | 0 |
| Grounded: `zmin` | within 1e-4 of 0 | 0.0000 |
| Feet: each of the 4 chair feet (2 pads, 2 ferrules) and 3 table pads sunk into the rug, against the rug's top read off the mesh | 0.0008–0.0040 m | 0.00200 (all 7) |

### Legs, buttons, symmetry, lattice, table, cushion and nails

| Axis | Declared | Measured |
| --- | --- | --- |
| Legs tenoned: each of the 4 chair legs' top above the body's underside, by a ray up from below the top onto the arms, back and base | 0.012–0.045 m | 0.0319, 0.0319 (front); 0.0288, 0.0288 (rear) |
| Buttons: 13, each one's deepest vertex below the back's surface on its axis (the smallest principal axis), its dome proud of that point, and the surface 40 mm round it risen above it (the dimple) | seat 0.0012–0.0045 m; proud ≥ 0.004 m; dimple ≥ 0.008 m | 0.00250; 0.00740; 0.01686–0.01847 |
| Mirror symmetry of the upholstered body (base, back, wings, arms, cushion, every welt): every vertex's distance to the nearest vertex at its mirror position; and size | ≤ 0.0005 m; seat 0.43–0.48 m, back 1.07–1.13 m, width 0.83–0.88 m above the rug | 0.000000 over 10620 verts; 0.4531, 1.1113, 0.8683 |
| Diamond lattice: every pair of buttons closer than 0.20 m (the diagonal neighbours) | 16 pairs; spread ≤ 0.004 m; in 0.150–0.175 m | 16; 0.00089; 0.16169–0.16258 |
| Table: mass centre of table, lamp and books (shell volumes × densities) inside the triangle of the three pads' contacts | ≥ 0.045 m | 0.0922 (7.50 kg) |
| Cushion resting: its underside pressed into the deck's top | 0.0008–0.0040 m | 0.00200 |
| Nailheads: two arm rows and a rail row; each nail's station where its axis meets its host; consecutive stations' spacing; each seated below that point and proud of it | equal arm rows ≥ 20, rail ≥ 12; spread ≤ 0.0015 m; seat 0.0004–0.0025 m; proud ≥ 0.002 m | 28, 28, 19; 0.0 (pitch 0.03000); 0.00100–0.00130; 0.00280–0.00310 |

The densities are named constants (leather 600, walnut 700, brass 4500 for a
hollow cast lamp modelled solid, linen 300, cloth and paper 700, bulb 600).

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code, and every other budget in its run stayed green
(`budget_fails` lists only its own).

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-foot` | feet sunk into the rug (one table pad and its leg's end 3 mm up: −0.00100 m) | 16 |
| `--short-legs` | legs tenoned into the body (the right rear leg's top 40 mm lower: −0.0038 m) | 17 |
| `--sink-buttons` | buttons seated in their dimples (all 6 mm deeper: seat 0.00850, proud 0.00140 m) | 18 |
| `--odd-wing` | mirror symmetry (the right wing 6 mm outward: 0.006000 m) | 19 |
| `--drift-buttons` | diamond lattice (the row-2 side buttons and their dimples 18 mm outward, a mirrored pair: spread 0.01358 m) | 20 |
| `--narrow-tripod` | table mass centre inside its feet (legs' reach cut to 30%: 0.0280 m) | 21 |
| `--lift-cushion` | cushion resting on the deck (5 mm up: −0.00300 m) | 22 |
| `--bunch-nails` | nailheads evenly spaced (nail 6 of each arm slid 45% of a pitch: spread 0.02699 m) | 23 |

`--drift-buttons` moves a mirrored pair, dimples and all, so the back stays
symmetric and every button still sits in its own dimple; only the lattice
breaks. `--short-legs` keeps the leg's foot in its ferrule on the rug.
`--float-foot` lifts the pad with its leg's end, so the leg stays in its pad.
`--bunch-nails` re-seats the slid nails on the arm's surface, so only the
spacing breaks.

## Run

```bash
blender --background --python wingback_armchair.py --
blender --background --python wingback_armchair.py -- --skip-decimate
blender --background --python wingback_armchair.py -- --stray-vert
blender --background --python wingback_armchair.py -- --lift-z
blender --background --python wingback_armchair.py -- --float-foot
blender --background --python wingback_armchair.py -- --short-legs
blender --background --python wingback_armchair.py -- --sink-buttons
blender --background --python wingback_armchair.py -- --odd-wing
blender --background --python wingback_armchair.py -- --drift-buttons
blender --background --python wingback_armchair.py -- --narrow-tripod
blender --background --python wingback_armchair.py -- --lift-cushion
blender --background --python wingback_armchair.py -- --bunch-nails
blender --background --python wingback_armchair.py -- --output armchair.png
```

Smoke passes no flags.

The camera looks along (−0.50, −0.87) from low, so the hero shows the
chair's front — the tufted back between the wings, both arm scrolls with
their nail rows, the cushion and the rail — and its left side, with the
table and lamp to the right on the rug. A warm point light sits in the
lamp's bulb (render only).

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family. `20`–`23` are file-local. `24` is the
asset-quality floor on the render path: `check_asset_quality` returns 11,
which this piece already spends on the collider ceiling, so the call site
remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build / no UV layer / rug, back or cushion not found |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 9 distinct slots, or a face-count floor missed |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | World AABB off declared outer size |
| 9 | LOD ratio band (`--skip-decimate` lands here) |
| 10 | Framing gate (render path only) |
| 11 | Collider triangle count above ceiling |
| 12 | Bake did not finish or image has no data |
| 13 | Export file missing or empty |
| 14 | `--output` produced no file |
| 15 | Mesh hygiene: loose, non-manifold, zero-area, doubles, n-gons, coplanar cross-shell pairs |
| 16 | Not grounded: bounding box `zmin` off 0, or a foot's sink into the rug outside its band (`--lift-z`, `--float-foot`) |
| 17 | A chair leg's top not tenoned into the body by the band (`--short-legs`) |
| 18 | A button's seat, proud height or dimple outside its band, or not 13 buttons (`--sink-buttons`) |
| 19 | Mirror symmetry of the body, or seat height, back height or width off (`--odd-wing`) |
| 20 | Diamond lattice: diagonal-neighbour count, spread or band (`--drift-buttons`) |
| 21 | Table mass centre within 45 mm of its feet's triangle's edge (`--narrow-tripod`) |
| 22 | Cushion's underside not pressed into the deck by the band (`--lift-cushion`) |
| 23 | Nailheads: row counts, spacing spread, seat or proud height (`--bunch-nails`) |
| 24 | Asset-quality floor (render path only; remapped from 11) |
