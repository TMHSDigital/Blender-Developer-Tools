# Soccer goal

A showcase piece, not an example, and the second in the `sports`
category. It builds a procedural freestanding youth (7-a-side) soccer goal,
5 × 2 m, on a patch of turf:

- two posts and a crossbar in one white-painted aluminium extrusion: an oval
  section, 100 × 120 mm, with a net channel down its back. The top corners
  are mitred and welded, with a weld bead standing round the outside of each
  mitre;
- a cast corner bracket bolted behind each mitre, carrying the socket for a
  sloped rear net support;
- a cast foot connector under each post: a foot plate on the turf, a collar
  round the post with a clamp bolt, and a socket for the side ground bar;
- two sloped supports and a ground frame of dark powder-coated steel: two
  side bars and a back bar, closed at the rear corners by cast hubs with
  three sockets each;
- the ground frame pinned down by four galvanised U-staples over the bars,
  and a spike through each foot plate and each hub;
- a woven diamond-mesh net of 120 mm cells: a back panel and two side
  panels. The back panel sags between its supports as a catenary in both
  directions; the side panels belly outward and droop. The two strand
  families pass over and under each other at every knot;
- a red head rope round every panel edge, threaded through 53 black nylon
  clips — a saddle on the member and a loop standing off it — along the
  crossbar, the posts, the supports and the ground bars; and
- a turf patch with a rolled edge, cut soil walls, mown bands parallel to
  the goal line and a painted goal line as wide as the posts are deep.

The layout is solved from named constants. The net's corners are the
points where its head ropes meet, and each rope sits at a clip's height off
its member: the member's half-depth, plus the saddle less its bite, plus the
loop less its bite. Each support's axis is its rope line moved square off
the net, so the supports, sockets, clips and panels all follow from the
mouth size, the depth and the clip.

Three things the coplanar budget forced:

- A support tube that starts at its rope's corner point, moved square off
  the rope, puts its end cap in the plane of the rope's end cap. It starts
  9 mm further up its own axis.
- The same tube starting 5 mm up lands on the plane of the bracket socket's
  own start cap, 782 pairs of it. 9 mm clears both.
- The two bolts on each bracket are set 1.5 mm apart in depth, or their
  heads share a cap plane.

Shading follows what each part is. The extrusion, tubes and castings are
smooth-shaded with sharp edges above 35° and at every material boundary, so
the mitres, chamfers and channel stay crisp. The net cords, ropes and clip
loops are round in life: their four- and eight-sided sections stay smooth
up to 95°. The turf's mown bands, blade mottle and bump are in the
material.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: a 5.000 × 2.000 m clear mouth, 1.5 m deep at the ground, on
a turf patch 6.22 × 2.64 m. The outer AABB is 6.220 × 2.640 × 2.153 m. The
turf sets X and Y; the weld beads on the crossbar's outer corners set the
top. The origin is under the goal line's centre, so the turf's underside is
the ground.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 34000–35600 | 34804 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 10 distinct; ≥2300 paint, ≥8300 cord, ≥150 rope, ≥310 steel, ≥1350 cast, ≥3300 nylon, ≥920 galvanised, ≥180 turf, ≥16 line paint, ≥95 soil faces | 10 slots; 2514 / 9028 / 160 / 340 / 1464 / 3604 / 1000 / 196 / 16 / 102 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (6.220, 2.640, 2.153) m ± 0.01 | (6.2200, 2.6400, 2.1527), zmin 0 |
| Collider tris | ≤ 190 | 126 |
| Export | written, size > 0, removed after measuring | 2523792 / 2523792 / 2523784 bytes (4.5.11 / 5.1.2 / 5.2.1) |

Every falsifier but one leaves the triangle count at 34804: they move or
shorten parts, never add or remove them. `--wide-mouth` measures 34816,
because a 30 mm wider back panel holds one more strand.

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
| Ground frame: each of the 3 steel bars bedded into the turf top read off the turf shell | 0.0015–0.0040 m | 0.0025, 0.0025, 0.0025 |

### Supports, clips, mouth and net

| Axis | Declared | Measured |
| --- | --- | --- |
| Supports seated: for each end of the 2 sloped supports (axis and radius by PCA), how far the tube runs inside a cast socket, sampled round its section at 5 mm stations | ≥ 0.040 m at every end | 0.065 (bracket), 0.080 (hub), both supports |
| Head rope on its clips: each clip loop's centre against the nearest head-rope axis (by PCA); every loop overlapping a saddle, every saddle overlapping a frame member, bar or support | 53 clips; axis offset ≤ 0.0012 m (the rope passes through the loop without touching it) | 53 loops, 53 saddles, 8 ropes; 0.000000 m; 0 loose |
| Mouth: clear width between the inner post faces and clear height from the turf top to the crossbar underside, read off the extrusion | 5.000 × 2.000 m ± 0.003 | 5.00019 × 2.00010 |
| Posts plumb (XY centroid of a low slab against a high one) and crossbar level (underside at both ends) | ≤ 0.10° and ≤ 1 mm | 0.000°, 0.000°; 0 mm |
| Net sag: the deepest back-panel cord below the chord from the crossbar rope to the back-bar rope, in a 0.2 m strip down the middle | 0.110–0.180 m | 0.14752 |

A goal is a size before it is anything else: the laws fix the mouth, and a
goal that is a few centimetres wide is a different goal to every keeper who
stands in it. The mouth budget reads it off the inner faces, not off the
bounding box: the turf sets the box, and the frame could drift to any width
underneath it. The sag budget is the other half of the read. A taut net
lies flat as a fence; a net hung on clips falls between its supports, and
the ball that hits it has to be caught, not bounced.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. None moves the envelope: every run measured the
same outer AABB as the default.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-bar` | every ground bar bedded in the turf (back bar lifted 8 mm: bed −0.0055 m, the two side bars 0.0025) | 16 |
| `--short-support` | supports seated in their sockets (left support stops 90 mm short of its hub: insertion 0.000 m at that end, 0.080 at the bracket) | 17 |
| `--unclip-net` | head rope on its clips (crossbar rope dropped 20 mm out of its loops: axis offset 0.0200 m) | 18 |
| `--wide-mouth` | mouth size (posts 15 mm further out each: clear width 5.03019 m) | 19 |
| `--taut-net` | net sag (no sag: deepest cord 0.00772 m below the chord) | 20 |

`--float-bar` lifts the back bar inside its hub sockets, so the frame stays
whole and the turf still grounds the box. `--short-support` leaves a 20 mm
gap between the tube's end and the hub socket, in the air, where a support
that has slipped shows. `--unclip-net` moves only the crossbar rope; the
net's strands still end at the old rope line and the sag, read against the
dropped rope, stays in band (0.13771 m). `--wide-mouth` rebuilds the whole
goal 30 mm wider, net and clips included, so every other budget still
holds, and the turf still sets the envelope.

## Run

```bash
blender --background --python soccer_goal.py --
blender --background --python soccer_goal.py -- --skip-decimate
blender --background --python soccer_goal.py -- --stray-vert
blender --background --python soccer_goal.py -- --lift-z
blender --background --python soccer_goal.py -- --float-bar
blender --background --python soccer_goal.py -- --short-support
blender --background --python soccer_goal.py -- --unclip-net
blender --background --python soccer_goal.py -- --wide-mouth
blender --background --python soccer_goal.py -- --taut-net
blender --background --python soccer_goal.py -- --output goal.png
```

Smoke passes no flags.

The hero turns the piece `HERO_YAW_DEG` (12°) against a camera raised
above the crossbar, so the mouth reads at three-quarter, the left side
panel shows its sloped support, and the back panel's sag is seen through
the mouth against the turf.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family. `20` is file-local. `21` is the asset-quality
floor on the render path: `check_asset_quality` returns 11, which this
piece already spends on the collider ceiling, so the call site remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build / no UV layer |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 10 distinct slots, or a face-count floor missed |
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
| 16 | Not grounded: bounding box `zmin` off 0, or a ground bar outside its bed band, or not 3 bars (`--lift-z`, `--float-bar`) |
| 17 | Supports: an end less than 40 mm inside a cast socket, or not 2 supports (`--short-support`) |
| 18 | Clips: not 53 clips, a loop's centre off the head rope's axis, a loop off its saddle or a saddle off its member (`--unclip-net`) |
| 19 | Mouth: clear width or height off 5 × 2 m, a post out of plumb, or the crossbar out of level (`--wide-mouth`) |
| 20 | Net sag at mid-panel outside its band (`--taut-net`) |
| 21 | Asset-quality floor (render path only; remapped from 11) |
