# Hitching post

A showcase piece, not an example. Procedural timber hitching post: a
125 mm square post seated in a closed iron shoe, one cross-rail through
the post, carried on two raking knee braces and capped with iron end
sleeves, a pyramidal cap with eaves, two rings hung through eyes under
the rail, and a horseshoe nailed heels-up to the post's face. Then the
shipped pipeline: unique-cell UVs, Cycles high-to-low normal bake, LOD
chain, convex collider, Unity glTF export.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

Intended size: post 0.125 m square and 1.16 m of timber, cap 0.096 m,
cross-rail 0.50 m (0.506 m over its end caps). Outer AABB
0.506 × 0.149 × 1.246 m.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).
Hygiene combinatorics match `examples/mesh-hygiene-audit` (copied, not
imported). Coplanar-pair counting matches `showcase/signpost`.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 1400–2400 | 2156 / 2156 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2199 / 0.2199 |
| Materials | exactly 2 distinct, ≥70 wood, ≥560 metal | 2 slots, 222 wood, 880 metal |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.506, 0.149, 1.246) m ± 0.01 | (0.5060, 0.1490, 1.2460) |
| Grounded zmin | within 1e-4 of 0 | 0 / 0 / 0 |
| Hygiene | loose/nonman/zero-area/doubles/n-gons/coplanar pairs = 0 | all 0 |
| Post seat | world zmin in (0.004, 0.014), XY centroid within 0.010 of origin, arm axis cos ≥ cos(0.5°) | 0.01000, 0, 1.000 |
| Hung ring | centerline error ≤ 0.008 m, ring–wood overlap 0, eye–wood overlap 0, shank–ring overlap 0, shank bites the eye | 0, 0, 0, 0, 40 |
| Shoe | each band overlaps the post, shoe overlaps the sole | band gap 0, sole–shoe 8 |
| **Band seat** | each band above the shoe stands ≥ 0.004 m proud of the post faces | 0.00650 |
| **Horseshoe seat** | exactly 1; back bites the post face 0.0005–0.004 m, face ≥ 0.004 m proud | 1, 0.00150, 0.00750 |
| **Brace seat** | exactly 2 knee braces, each housed in the post and in the rail (triangle overlap ≥ 1 with each); exactly 2 end caps, each gripping the rail | 2 braces, worst post 12 / rail 16; 2 caps, worst 12 |
| Wood–metal gap | BVH surface < 0.008 m | 0.00075 |
| Collider tris | ≤ 280 | 44 |
| Export | written, size > 0 | 158568 / 158568 / 158560 bytes (4.5.11 / 5.1.2 / 5.2.1) |

Base triangles rose from **1598 to 1680**. The old rings were faceted
tori clipped into the arm; the new eyes, shanks, and 24-segment hung
rings replace that mesh. Cylinder caps are triangulated so the n-gon
budget stays at 0.

DECIMATE COLLAPSE triangle counts are **not** identical across series —
the gate is a ratio band, not an exact count. On this mesh the three
binaries agreed. Bake pixels are stochastic; the gate is `has_data`
plus operator `FINISHED`, not byte-identity. Construction is
closed-form; the only RNG is the seeded per-piece wood tone. Bevel inputs are sorted by edge index, so the face order is the same on
every run; a Python set of edges handed to the bevel had made it vary.
Export byte counts differ on 5.2.1 (glTF serializer), not a gated axis. Euler is 14 (12 before the horseshoe added one more closed shell) and is not gated to 2.

### Horseshoe

A lone post with a stub rail read as the plainest object in the showcase
lineup. A horseshoe nailed heels-up to the post's front face is what a
real hitching post carries, and it is geometry, so it is budgeted: a
flat iron bar (17 mm wide, 7.5 mm thick) swept around 290° of an arc,
heels capped, centred on the post between the upper band and the rail
and clear of the rings. Its back face bites the post face by 1.5 mm
(`HS_BITE`); its face stands 7.5 mm proud. The shell classifier sets it
apart from the hung rings, which are the same flat-loop shape class, by
where it sits (on the post's centre line, not at ±`EYE_X`). **Horseshoe
seat** reads the bite and the stand-off against the post's own front face
off the mesh; `--float-horseshoe` pulls it 4 mm off the face and exits 18
(bite −0.0025 m). It moved the budgets it should: base triangles 1680 →
1852 (inside the declared 1400–2400) and metal faces 742 → 828. The outer
AABB, collider (80 tris) and every other seat are unchanged. The hero key
light rose from 660 to 960 W so the still sits in the calibration luma
band.

### Knee braces and end caps

After the horseshoe the post was still among the simplest objects in the
asset-sheet lineup: a stub rail pinned through a post reads as a cross, not
as a load-bearing hitch. The rail now sits on two raking knee braces, one
under each arm, as a hitch rail that takes a pulling horse needs. Each brace
is a 40 × 50 mm strut from the post's side face at 0.66 m up to the rail's
underside, housed 22 mm into both (`BRACE_BITE`), and it stops at x = 0.090,
inboard of the hung rings. The ring–wood overlap gate now counts the braces
as wood. Both rail ends carry an iron sleeve 36 mm long, with bevelled
edges and 5 mm walls, standing 3 mm past the end grain.

`seat_audit` classifies the new shells by position. A wood shell off the
post's centre line is a brace; the cap sits on it. A metal shell out at the
rail ends is an end cap, not a band. **Brace seat** asserts exactly two
braces, each overlapping the post and the rail, and two caps gripping the
rail. `--float-braces` drops each brace head 36 mm below the rail and exits
18 (brace_arm 0). The additions moved the budgets they should: base
triangles 1852 → 2156 (inside the declared 1400–2400), wood faces
114 → 222, metal faces 828 → 880. The outer AABB widened by the caps' 3 mm
standoff per end, from 0.500 to 0.506 m, and `OUTER_SIZE` follows the
measurement. The collider went from 80 to 72 triangles.

### Bands, wood and stage

The two iron bands were sized from `half - grip`: an inner half-width of
53 mm and an outer one of 61 mm, against a 62.5 mm post face. They sat
inside the post, and only the chamfered corners broke the surface,
showing as small black slits up the post. They now wrap it: the inner
face bites 1.5 mm into the post (`BAND_BITE`), so each band stands
6.5 mm proud. **Band seat** asserts it; `--sunk-bands` restores the old
bands and exits 18 (proud −0.0015 m).

The post, rail and cap each carry their own tone and grain, and the
iron is rusted. The stage grid grew from 14 to 60 m, because the wall's
left edge showed as a bright band in the corner of the hero. The temp
`.glb` is removed after its size is measured.

Each falsifier violates exactly one named budget. Proven on Blender
4.5.11 LTS, 5.1.2, and 5.2.1 LTS (the binaries' own `--version`):

| Falsifier | Budget violated | Exit | Measured failure |
| --- | --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 | ratio 1.0000 |
| `--stray-vert` | Mesh hygiene, loose verts | 15 | `loose_v=1` |
| `--twin-sole` | Coplanar face pairs | 15 | `zfight=6` |
| `--lift-z` | Grounded zmin | 16 | zmin 0.050000 |
| `--clip-ring` | Hung-ring centerline | 18 | ring_err 0.024, ring–wood overlap 32 |
| `--short-post` | Seated post | 19 | post zmin 0.030 |
| `--sunk-bands` | Band seat | 18 | band proud −0.0015 |
| `--float-horseshoe` | Horseshoe seat | 18 | bite −0.0025 |
| `--float-braces` | Brace seat | 18 | brace_arm 0 |

Default exit is 0 on all three. `--clip-ring` also overlaps the rail;
the centerline gate is the one that fires.

## Run

```bash
blender --background --python hitching_post.py --
blender --background --python hitching_post.py -- --skip-decimate
blender --background --python hitching_post.py -- --stray-vert
blender --background --python hitching_post.py -- --twin-sole
blender --background --python hitching_post.py -- --lift-z
blender --background --python hitching_post.py -- --clip-ring
blender --background --python hitching_post.py -- --short-post
blender --background --python hitching_post.py -- --sunk-bands
blender --background --python hitching_post.py -- --float-horseshoe
blender --background --python hitching_post.py -- --float-braces
blender --background --python hitching_post.py -- --output preview.webp --engine cycles
```

Smoke does not pass `--output` or a falsifier.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build / no UV layer |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 2 distinct slots, or wood/metal faces missing |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | World AABB off declared outer size |
| 9 | LOD ratio band (`--skip-decimate` lands here) |
| 10 | Framing gate (render path only) |
| 11 | Collider triangle count above ceiling |
| 12 | Bake did not finish or image has no data |
| 13 | Export file missing or empty |
| 14 | `--output` produced no file |
| 15 | Hygiene, including coplanar pairs (`--stray-vert`, `--twin-sole`) |
| 16 | Grounded zmin (`--lift-z`) |
| 17 | Wood–metal BVH gap above 8 mm |
| 18 | Hung ring, shoe, band, horseshoe, brace or end-cap seat (`--clip-ring`, `--sunk-bands`, `--float-horseshoe`, `--float-braces`) |
| 19 | Post plumb, origin, and cup seat (`--short-post`) |
| 20 | Gallery asset-quality violation (render path; the floors' 11 is remapped here) |
