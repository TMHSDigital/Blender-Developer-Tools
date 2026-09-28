# Fallen log

A showcase piece, not an example, and the second in the `nature` category.
It builds a procedural, game-ready fallen log on its patch of forest floor:

- the log: one lathe along a bowed axis, 3.1 m from butt to break and
  0.67 m across the butt, tapering to the top. Its bark is plated and cut
  by sixteen narrow V furrows whose depth changes along the log;
- four patches where the bark has peeled away. Each shows the sapwood
  about 26 mm under the plates, scored by beetle galleries: a wandering egg
  gallery along the grain with larval tunnels running across it;
- the butt, an old saw cut weathered slightly concave, its growth rings
  running round a heart rotted out into a hollow about 0.4 m deep;
- the top, a snapped break: the upper fibres pulled out longest, a tongue
  torn out along the upper north side, and every ring broken at its own
  length into faceted splinters;
- two broken branch stubs seated in the log, one standing up out of the
  top and one low on the south flank, each with a jagged broken end;
- ten moss cushions on the top and the shaded north side;
- three tiers of bracket fungi (artist's conk) on the south flank, twelve
  shelves overlapping like roof tiles. Each is a horizontal half-lens with
  a zoned, ridged brown cap, a white growing margin and a white pore
  surface underneath, its back edge set into the bark;
- a soil mound the log has settled into along its length, with soil
  drifted against its sides, a green film in the damp hollows and a
  rolled rim;
- a cluster of eight toadstools, two clumps of ferns (ten fronds, 28
  pinnae each) and 130 fallen leaves on the soil round the log.

Every draw comes from `random.Random(SEED)` in `plan_log()`, before
anything is built: peel and moss outlines, shelf sizes and swing, the
splinter lengths, the toadstools, the fronds and the leaves. No flag draws
from the stream, so a falsifier changes only what it names.

Nine materials, one per substance: bark, wood (sapwood, end grain and
broken wood), rot, moss, bracket fungus, toadstool, soil, leaf litter and
fern. The bark shader cuts the furrows with ridged noise stretched along
the log. A `Peel` point attribute is 0.5 exactly on each patch's outline,
so the bark shader cuts the torn edge between vertices, with a dark rim of
broken bark, not along the triangle grid. The end grain draws its growth
rings from a `Radial` point attribute; the brackets and toadstools take
their zones from a `Zone` face attribute, and every cushion, shelf, leaf
and frond has a seeded `Tone`. Wood is smooth-shaded except broken wood:
the splinters and stub ends are flat-shaded facets. Every material
boundary is a hard edge.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: a log 3.60 m long to the tip of its longest splinter,
its top 0.67 m off the ground, on a soil mound 4.12 × 2.17 m. The outer
AABB is 4.119 × 2.189 × 1.027 m. The soil sets X and the south edge, the
tip of one fern frond the north edge, and the upright stub's broken tip
the top. The soil's underside is the ground. The collider is the convex
hull of the log alone, round and unfurrowed: players walk through ferns.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 35600–37200 | 36374 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 9 distinct; ≥4600 bark, ≥800 wood, ≥340 rot, ≥2150 moss, ≥2200 bracket, ≥1160 toadstool, ≥2240 soil, ≥1870 litter, ≥4580 fern faces | 9 slots; 5144 / 892 / 384 / 2400 / 2448 / 1296 / 2494 / 2080 / 5090 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (4.1189, 2.1885, 1.0267) m ± 0.01 | (4.1189, 2.1885, 1.0267), zmin 0 |
| Collider tris (log hull) | ≤ 240 | 215 |
| Export | written, size > 0, removed after measuring | 2826044 bytes |

No falsifier changes the triangle count: they move parts or the soil,
never add or remove them.

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. The plan is seeded and nothing else is random; two
default runs print identical measurements.

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

The first run measured 360 non-manifold edges and 32 zero-area faces,
all leaves flattened to lines: `BVHTree.FromBMesh` reads the stored face
normals, which a fresh bmesh has not computed, so every leaf was laid on
a zero normal. The soil now calls `normal_update()` before its tree is
built. The coplanar budget then caught two more faults. Two bracket
shelves in one tier met in one plane on their undersides, inside the
bark; neighbouring shelves now bite 1.5 mm apart. The fern pinnae along one side
of a rachis are translated copies inside one blade plane: 53 pairs on the
first run. A seeded sine twist left 7, because two neighbours sometimes
drew the same angle. The twist is now period 3, so any two neighbours
differ by at least 0.1 rad, and the droop and midrib depth step per pinna
too.

### Contact patch, rooted brackets, balance, moss and ground cover

These are the organic invariants. A log has no joinery. What makes it read
as a fallen log is that it lies along the ground rather than on it, that
its fungi grow out of it, that it would not roll, and that moss grows
where the sun does not reach.

| Axis | Declared | Measured |
| --- | --- | --- |
| Contact patch: the log shell binned along X at 0.10 m; a station is bedded when its most-buried vertex lies below the soil straight under it (a ray down onto the soil shell alone) by a depth in the band | ≥ 0.75 of the stations bedded, depth band 0.020–0.090 m | 0.8889 (32 of 36; the four off-band stations are the splinters past the break), deepest 0.0461 |
| Rooted brackets: for each shelf, its deepest vertex inside the log shell (signed distance to the nearest bark face along that face's normal) | 12 shelves, each 0.008–0.050 m | 12; 0.0214–0.0293 |
| Balance: the log's volume centroid (signed tetrahedra over the closed shell) inside the plan hull of every vertex buried in the soil | ≥ 0.06 m inside | 0.1491 (centroid at (−0.194, 0.094), volume 0.706 m³) |
| Moss: of the moss top faces (facing away from the bark under them), the area fraction whose normal faces up (z > 0.25) or north into the shade (y > 0.5) | 10 cushions, ≥ 0.85 | 10; 0.9921 |
| Ground cover rooted: soil, leaves, toadstool stems and caps, and fern rachises and pinnae, unioned by BVH overlap | 436 shells, all joined to the soil | 436; 0 loose |

The soil under the log is one line along X, `ground_line(x)`, and the log
settles into it: every ring's lowest vertex is set 45 mm below that line.
The contact budget reads the bed back off the mesh by raycast, so it sees
the soil that was built, not the function that built it. The balance
budget is the tip-over check turned on its side: a log that rests only on
its flank has a contact hull that misses its own centre of mass.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. None moves the envelope: every run measured the
same outer AABB as the default, and every other budget stayed green.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--hump-ground` | contact patch (the bed sinks 90 mm under the log but for a hump under its mass centre: 0.0833 of the stations bedded) | 17 |
| `--float-fungi` | rooted brackets (every shelf moved 35 mm off the bark: deepest vertex −0.0133 to −0.0027 m, outside) | 18 |
| `--tilt-ground` | balance (the bed falls away under the south half and banks up on the north: centroid 0.0316 m outside the contact hull) | 19 |
| `--sunny-moss` | moss on up- and shade-facing surfaces (every cushion turned half round the log: 0.1146) | 20 |
| `--float-litter` | ground cover rooted (every leaf lifted 25 mm off the soil: 130 of 436 shells loose) | 21 |

`--hump-ground` keeps the log where it is and changes only the soil, so
the log balances on one point: the balance budget still passes with the
hump under the mass centre (0.1015 m inside), and only the contact budget
fails. `--tilt-ground` is the converse: the log still lies bedded along
its length (0.8611 of the stations) but only by its north flank, so it
would roll. Both edit the soil within 0.50 m of the log's axis, which
keeps the fern clumps where they are. `--float-fungi` leaves each
shelf's shape and swing alone. `--sunny-moss` moves the cushions onto the
underside and south flank with the same outlines, so the moss face count
is unchanged.

## Run

```bash
blender --background --python fallen_log.py --
blender --background --python fallen_log.py -- --skip-decimate
blender --background --python fallen_log.py -- --stray-vert
blender --background --python fallen_log.py -- --lift-z
blender --background --python fallen_log.py -- --hump-ground
blender --background --python fallen_log.py -- --float-fungi
blender --background --python fallen_log.py -- --tilt-ground
blender --background --python fallen_log.py -- --sunny-moss
blender --background --python fallen_log.py -- --float-litter
blender --background --python fallen_log.py -- --output log.png
```

Smoke passes no flags.

The hero keeps the piece unturned (`HERO_YAW_DEG` 0°) and raises the
camera above the south-west corner. The log then runs across the frame
toward the snapped top. The butt's rings and hollow face the camera, the
brackets and peels on the south flank are lit, and the ferns stand behind
the log against the wall. A long, low subject still fills the frame in
both axes this way: 0.806 × 0.750.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene, grounding, contact and balance family. `20` and `21` are
file-local. `22` is the asset-quality floor on the render path:
`check_asset_quality` returns 11, which this piece already spends on the
collider ceiling, so the call site remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, no UV layer, or no log or soil shell |
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
| 16 | Not grounded: bounding box `zmin` off 0 (`--lift-z`) |
| 17 | Contact patch: under 0.75 of the log's stations bedded in the soil within the depth band (`--hump-ground`) |
| 18 | Rooted brackets: not 12 shelves, or a shelf's deepest vertex in the bark outside its band (`--float-fungi`) |
| 19 | Balance: the log's mass centre less than 0.06 m inside the plan hull of its buried vertices (`--tilt-ground`) |
| 20 | Moss: not 10 cushions, or under 0.85 of the moss top area facing up or north (`--sunny-moss`) |
| 21 | Ground cover: not 436 shells, or a leaf, toadstool or frond part not joined to the soil (`--float-litter`) |
| 22 | Asset-quality floor (render path only; remapped from 11) |
