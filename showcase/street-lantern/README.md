# Street lantern

A showcase piece, not an example. Procedural hanging street lantern
(stepped iron foot, tapered octagonal post, brass collars, braced arm,
muntined cage with amber panes, square pyramidal brass roof and finial)
then the shipped pipeline: unique-cell UVs, Cycles high-to-low normal
bake, LOD chain, convex collider, Unity glTF export.

The arm axis, drop length, and roof stack are one closed-form chain: the
roof peak stays below the arm, the hanger is the arm's far station, and
the brace is an oriented box tenoned into the post wall and into the
arm's lower half. The square pyramid is lofted on the cage axes, not a 4-gon cone.
Cage posts and rails share a named overlap (`CAGE_JOINT`); glass sits
behind the muntins by `PANE_REBATE`. Collars and the arm root evaluate
`post_radius_at(z)`.

The first build parked the brace's post end 0.35 × `BRACE_T` outside
the post and its arm end under the arm, so a single bevelled corner
grazed each host and the brace read as a loose stick in both side
elevations. The brace-to-arm gap budget passed anyway, because a
grazing corner is a zero gap, and nothing measured the post end at
all. The brace ends now start half a brace inside the post wall and on
the arm's centre-line side, and the brace-bite budget below asserts
that each end is actually inside its host. Brass is aged and rougher
(it was bright polished gold at roughness 0.28).

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).
Hygiene combinatorics match `examples/mesh-hygiene-audit` (copied, not
imported).

Intended size: 0.30 m square foot, 1.12 m octagonal post (0.10 m across
at the base), 0.50 m arm, 0.24 × 0.30 m cage; outer AABB
0.300 × 0.786 × 1.287 m.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 3000–3800 | 3338 / 3338 / 3338 |
| LOD1 ratio | 0.32–0.62 of base | 0.4997 / 0.4997 / 0.4997 |
| LOD2 ratio | 0.10–0.35 of base | 0.2199 / 0.2199 / 0.2193 |
| Materials | exactly 3 distinct; ≥200 metal, ≥8 glass, ≥24 brass | 3 slots; 1530 / 24 / 209 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.300, 0.786, 1.287) m ± 0.01 | (0.3000, 0.7860, 1.2874), zmin 0 |
| Collider tris | ≤ 120 | 78 |
| Export | written, size > 0, removed after measuring | 251016 / 251016 / 251000 bytes |

Base triangles dropped from **3520 to 3338** in the quality pass: the
open 4-gon cone roof became a closed square pyramid, cage crossings
stopped sharing vertices, and a pane rebate replaced coplanar glass.

DECIMATE COLLAPSE triangle counts are **not** identical across series —
5.2.1 is 2 tris leaner on LOD2. The gate is a ratio band, not an exact
count. Bake pixels are stochastic; the gate is `has_data` plus operator
`FINISHED`, not byte-identity. Construction uses no RNG. Export byte
counts differ by 16 B on 5.2.1 (glTF serializer), not a gated axis.

### Hygiene

Recomputed from the generated mesh, not asserted about the script.

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Non-manifold edges | 0 | 0 |
| Loose verts / edges | 0 / 0 | 0 / 0 |
| Doubles merged at 1e-5 | 0 | 0 |
| Zero-area faces | 0 | 0 |
| N-gons | 0 | 0 |
| Coplanar disjoint face pairs | 0 | 0 |
| Grounded: `zmin` | within 1e-4 of 0 | 0.0000 |
| Post plan | 0.100 m across × 1.120 m high ± (0.02, 0.04) | 0.1000 × 1.1200 |
| Post plumb (top vs bottom XY) | ≤ 0.008 m | 0.00000 |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Brace-to-arm BVH gap | ≤ 0.006 m | 0.00000 |
| Brace bite: deepest brace vertex inside the post / inside the arm (signed distance to the host shell) | ≥ 0.004 m each | 0.01305 / 0.01282 |
| Arm underside vs roof peak | ≥ 0.008 m clearance | 0.05300 |
| Hanger-to-roof BVH gap | ≤ 0.004 m | −0.00100 |

### Falsifiers

Each violates one named budget. Every falsifier was run on 4.5.11,
5.1.2 and 5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--float-brace` | brace-to-arm BVH gap | 17 |
| `--sink-arm` | arm-over-roof clearance | 18 |
| `--rake-post` | post plumb | 19 |
| `--shallow-brace` | brace bite (the first build's ends: −0.00593 m into the post, 0.00000 m into the arm) | 20 |

`--sink-arm` lowers only the arm. Hang-station `hang_z` stays at post
top so the cage does not follow, which is what lets the clearance budget
fire.

The brace-bite check runs last, after plumb, so a raked post is reported
as plumb (19) rather than as a brace that no longer reaches it.

## Run

```bash
blender --background --python street_lantern.py --
blender --background --python street_lantern.py -- --skip-decimate
blender --background --python street_lantern.py -- --stray-vert
blender --background --python street_lantern.py -- --lift-z
blender --background --python street_lantern.py -- --float-brace
blender --background --python street_lantern.py -- --sink-arm
blender --background --python street_lantern.py -- --rake-post
blender --background --python street_lantern.py -- --shallow-brace
blender --background --python street_lantern.py -- --output lantern.png
```

Smoke passes no flags.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family; `20` is file-local.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build / no UV layer |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 3 distinct slots, or a face-count floor missed |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | World AABB off declared outer size |
| 9 | LOD ratio band (`--skip-decimate` lands here) |
| 10 | Framing gate (render path only) |
| 11 | Collider triangle count above ceiling |
| 12 | Bake did not finish or image has no data |
| 13 | Export file missing or empty |
| 14 | `--output` produced no file |
| 15 | Mesh hygiene: loose, non-manifold, zero-area, doubles, n-gons, z-fight |
| 16 | Not grounded: bounding box `zmin` off 0 |
| 17 | Joint fit: brace-to-arm gap (`--float-brace`) |
| 18 | Seat: arm-roof clearance or hanger-roof gap (`--sink-arm`) |
| 19 | Post plumb or post size off the stated real-world size (`--rake-post`) |
| 20 | Brace bite: a brace end not inside the post or the arm (`--shallow-brace`) |
