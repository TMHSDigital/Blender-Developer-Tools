# Stand mixer

A showcase piece, not an example, and the fourth in the `household`
category. It builds a procedural retro tilt-head kitchen stand mixer,
generic and unbranded, on a short countertop section:

- a honed limestone countertop section 0.47 × 0.57 m with a bullnose front
  edge and eased cut ends;
- a cast enamel body in three lofted pieces: a pebble-shaped base foot
  (superellipse plan, stepped chamfer profile) on four rubber feet, a neck
  that leans back as it rises, and a streamlined motor head of
  superellipse sections, rounder over the crown than across the belly,
  closing to a flat nose;
- a tilt hinge at the back of the head: two knuckles cast on the neck, a
  head knuckle between them, and a domed chrome pin through all three;
  the neck's top follows the head's underside 1.5 mm below it, so the
  tilt seam reads as a seam;
- a chrome trim band wrapped round the head on the head's own sections,
  a blank oval badge (chrome bezel, brushed panel), a speed lever in its
  escutcheon, and a tilt-lock lever on the neck;
- an attachment hub on the nose with a domed cap and a knurled thumb
  screw;
- a planetary housing and socket under the head, and a white-coated flat
  beater (a frame that follows the bowl's wall and floor, a centre spine,
  a shaft with its bayonet cross pin) hanging into
- a 4.5 L brushed stainless bowl with a foot ring, a rolled rim and a strap
  handle, twisted onto a chrome bowl plate under three bayonet lugs;
- a cord through a strain relief in the base's rear riser, over the
  counter to a two-pin plug; and
- on the counter: a balloon whisk (five wire loops in a ferrule), a
  measuring cup with a flat handle, and two brown eggs in a glazed
  terracotta dish.

The head is a closed-form surface (`head_sec()`, `head_y()`,
`head_zbot()`), and everything mounted on it reads its position from that
surface: the band is built on the head's sections offset along their
normals, the badge and escutcheon lie in the head's tangent plane with
their backs buried by the surface's measured drop under their outlines,
the neck's top ring follows the head's underside, and the planetary sits
under the head at the bowl's axis. The beater frame is the bowl's inner
profile offset inward by the clearance plus the frame's half-width, run
straight between the profile's vertices as the bowl's own lathe is. A
spline through them bulged toward the wall and cut the clearance from
2.5 mm to 1.65 mm.

Every face carries a `part` tag (a face attribute written as each part is
built), and the audits classify shells by it. The measurements themselves
are read off the mesh.

Things the coplanar budget forced:

- The bowl plate's rim ring coincided with a vertex of the base's top
  loop and welded the plate into the base; the plate is 1 mm smaller.
- The badge panel's back and the trim band's face were both 1.4 mm offset
  surfaces of the head, and a 0.3 mm offset of that slanted side lands on
  the same plane 40 mm away. The panel sits 1.7 mm out, and the badge and
  escutcheon are flat plates rather than conforming shells, whose fan
  triangles were chords that met the band's planes.
- An egg lathed with a half-facet phase lay a facet, not a vertex, on the
  dish floor, 0.11 mm off its plane.
- `--bunch-feet` packs the feet 30 mm apart, where identical feet share
  facet planes (1910 pairs). Each foot now sinks 0.15 mm further into the
  counter, tucks 0.2 mm further into the base, and is turned a quarter
  facet from the last, in the default model too.

Shading follows what each part is. The enamel, bowl, lathe parts and
swept wire are smooth-shaded; chamfers, knurls and steps stay crisp above
35° and at every material boundary. The enamel is a muted slate blue
under a clear coat. The stainless is brushed, its roughness noise squeezed
along Z into circumferential streaks. A plain noise read as a blotchy,
dirty bowl.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: a mixer 0.36 m tall on a 0.03 m counter, a 0.296 × 0.196 m
base foot, a 0.34 m head, and a 4.5 L bowl. The outer AABB is
0.470 × 0.570 × 0.389 m. The counter sets the plan and the head's crown
sets the top. The origin is under the counter.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 29000–30300 | 29620 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 8 distinct; ≥3980 enamel, ≥2410 chrome, ≥5110 stainless, ≥84 stone, ≥1080 rubber, ≥745 ceramic, ≥700 egg, ≥515 beater faces | 8 slots; 4328 / 2626 / 5560 / 91 / 1174 / 812 / 760 / 562 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.470, 0.570, 0.389) m ± 0.01 | (0.4700, 0.5700, 0.3890), zmin 0 |
| Collider tris | ≤ 2450 | 2329 |
| Export | written, size > 0, removed after measuring | 2337532 bytes |

No falsifier changes the topology, so every one of them measures the
default's 29620 triangles and the default's AABB. `--shallow-bowl` keeps
the bowl's four wall stations, spread up to the lower rim, and the beater
follows the full-height wall's r(z), which is the same function.

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
| Feet: each of the 4 rubber feet sunk into the counter top read off the mesh | 0.0001–0.0008 m | 0.00025, 0.00040, 0.00055, 0.00070 |

### Hinge, bowl, size, beater, stance and assembly

| Axis | Declared | Measured |
| --- | --- | --- |
| Hinge: the pin's PCA axis against the axis of each of the 2 neck knuckles and the head knuckle, at that knuckle's own station; the pin spans each in Y; tilt off Y | ≤ 0.0003 m; 2 + 1 knuckles; 0 not through; ≤ 0.5° | 0.000000; 2 + 1; 0; 0.0000° |
| Bowl seated: plate top minus bowl foot; bowl axis (lathe centroid) against the plate's; each of the 3 lugs overlapping the bowl's flange (BVH); handle on the bowl | 0.0002–0.0010 m; ≤ 0.0003 m; 3 of 3 | 0.00050; 0.000000; 3 of 3, handle on |
| Size: head crown above the counter top; brim capacity (rays from the bowl's own axis to its inner wall, 1 mm slices from the floor to the rim) | 0.360 ± 0.006 m; 4.5 ± 0.35 L | 0.35899 m; 4.5465 L |
| Beater coaxial: the shaft's PCA axis against the planetary socket's axis; shaft tilt | ≤ 0.0003 m; ≤ 0.5° | 0.000000; 0.0000° |
| Beater clearance ("dime test"): nearest beater vertex to the bowl's surface; beater's lowest point above the bowl's floor (a ray down the bowl's axis) | both 0.0012–0.0040 m | 0.00245; 0.00250 |
| Stance: mass centre (shell volumes × densities, counter and props excluded) inside the convex polygon of the feet's contact faces | ≥ 0.040 m | 0.0658 (13.94 kg) |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (52 shells) |

A tilt-head mixer carries its motor over the bowl, well forward of the
neck, and stands because its feet are spread under it. The stance budget
measures that. The densities are named constants (cast enamel 6600,
chrome and stainless 7900, coated aluminium 2700, rubber 1200), with the
three castings overridden where the mesh is solid but the part is not:
head 850 (a shell round a motor and air), neck 1300, base 1400.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. None moves the envelope: every run measured the
default's triangle count and outer AABB, and every budget checked before
its own stayed green.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-foot` | feet on the counter (one foot 3 mm up: seat −0.00230 m) | 16 |
| `--offset-hinge` | hinge pin coaxial through its knuckles (pin 2 mm aft: 0.002000 m) | 17 |
| `--offset-bowl` | bowl concentric on its plate (bowl slid 1 mm: 0.001000 m) | 18 |
| `--shallow-bowl` | bowl capacity (rim 30 mm lower: 3.4959 L) | 19 |
| `--offset-beater` | beater coaxial with the socket (0.000800 m) | 20 |
| `--long-beater` | beater clearance band (frame 2 mm lower: wall 0.00050, floor 0.00050 m) | 21 |
| `--bunch-feet` | stance (feet under the neck: margin −0.0785 m) | 22 |
| `--loose-cap` | one connected assembly (hub cap 5 mm off the hub: 2 components) | 23 |

`--offset-bowl` still leaves the beater 1.72 mm clear of the wall and all
three lugs engaged, and `--offset-beater` leaves it 1.87 mm clear, so only
the concentric and coaxial budgets see them. `--float-foot` leaves three
feet and the counter grounding the piece. `--bunch-feet` keeps every foot
under the base and on the counter, so only the mass centre moves out of
the support polygon.

## Run

```bash
blender --background --python stand_mixer.py --
blender --background --python stand_mixer.py -- --skip-decimate
blender --background --python stand_mixer.py -- --stray-vert
blender --background --python stand_mixer.py -- --lift-z
blender --background --python stand_mixer.py -- --float-foot
blender --background --python stand_mixer.py -- --offset-hinge
blender --background --python stand_mixer.py -- --offset-bowl
blender --background --python stand_mixer.py -- --shallow-bowl
blender --background --python stand_mixer.py -- --offset-beater
blender --background --python stand_mixer.py -- --long-beater
blender --background --python stand_mixer.py -- --bunch-feet
blender --background --python stand_mixer.py -- --loose-cap
blender --background --python stand_mixer.py -- --output mixer.png
```

Smoke passes no flags.

The camera looks along (−0.72, 0.69), so the hero shows the mixer's nose
and its −Y side, with the badge, the speed lever, the hinge boss and the
tilt-lock lever toward the camera, and the props in the foreground. The
wall behind the mixer in frame lies 2.5 m to its −X, so the warm wedge is
aimed there rather than at the wall straight behind the piece.

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
| 3 | Mesh did not build / no UV layer |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 8 distinct slots, or a face-count floor missed |
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
| 16 | Not grounded: bounding box `zmin` off 0, or a foot off the counter or not 4 feet (`--lift-z`, `--float-foot`) |
| 17 | Hinge pin off a knuckle's axis, not spanning one, tilted, or not 2 + 1 knuckles (`--offset-hinge`) |
| 18 | Bowl seat: bite outside its band, bowl off the plate's axis, a lug not engaged, or the handle off the bowl (`--offset-bowl`) |
| 19 | Size: mixer height or bowl capacity off (`--shallow-bowl`) |
| 20 | Beater shaft off the socket's axis or tilted (`--offset-beater`) |
| 21 | Beater clearance to the bowl's wall or floor outside its band (`--long-beater`) |
| 22 | Stance: mass centre within 40 mm of the feet's support polygon's edge (`--bunch-feet`) |
| 23 | Assembly splits into more than one connected component (`--loose-cap`) |
| 24 | Asset-quality floor (render path only; remapped from 11) |
