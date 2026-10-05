# Quad drone

A showcase piece, not an example, and the first in the `vehicles`
category. It builds a procedural prosumer camera quadcopter on an X frame:

- a two-tone moulded body shell, lofted from superellipse sections: a light
  canopy over a dark belly, a parting-line groove along both flanks and two
  transverse panel lines, a grille on the nose and one on each flank, and a
  flat nose face carrying a sensor visor with two stereo lenses;
- a battery pack sitting in the top of the shell, with grip ribs, a red
  release latch on each side, a power button and four charge lights, and a
  GPS puck on a mast in front of it;
- four folding arms. Each hinges on a vertical pin through a clevis on the
  body (a block and two lugs) and a tongue on the arm's root cuff, with a
  knurled red lock ring. A carbon tube runs out to a clamp cuff with two
  screws, a navigation light on its end and a round mount plate;
- four brushless motors: a base, a stator bell with twelve cooling slots,
  a red anodised band, four top screws and four mount screws;
- four two-blade propellers, 0.33 m across. Each blade is lofted from
  cambered airfoil sections, twisted to a 115 mm geometric pitch, swept back
  at the tip and handed to its motor's spin. The spinners are colour-coded:
  red on the counter-clockwise props, gunmetal on the clockwise ones;
- two carbon skids on four raked struts, each strut in a T-collar on the
  skid and a pad under the belly, with a rubber foot on each skid end;
- a three-axis gimbal under the nose, hung from a damper stack (two plates,
  four rubber balls): yaw motor, yaw arm, roll motor, roll arm, pitch
  motor and bearing cap, and a camera with a top grille, a ribbed lens
  barrel, a silver front ring and a glass element; and
- two antennas pointing down and back from the belly.

The layout is solved from named constants. The motor axes sit at 45°,
135°, 225° and 315°, 0.26 m from the body centre (a 0.52 m diagonal). The
hinge pin of each arm is placed where a level ray at arm height leaves the
shell's closed-form surface, plus a named gap. Grilles and the visor are
laid on that surface along its own normal, and the battery is seated below
the lowest point of the crown under its footprint.

Three things the coplanar budget forced:

- Repeated small lathes on one host (four motor-top screws, four mount
  screws, four charge lights, two stereo lenses, two clamp screws, four
  damper balls) share tangent planes if they are identical. Each one is
  turned a fraction of a facet from its neighbour and set 0.15–0.2 mm
  deeper or prouder, so no two share a cap or a side facet.
- The two lugs of each clevis are not copies. The lower lug is 0.4 mm
  smaller round the pin and set back 1.2 mm, or their chamfered back
  corners land on one plane.
- The motor cuff starts 0.5 mm further in than first drawn, or its back
  cap lies in the plane of the anodised band's inner face.

Shading follows what each part is. The shell, tubes, blades and lathes are
smooth-shaded; grilles, chamfers, knurls and slots stay crisp through sharp
edges above 35° and at every material boundary. The navigation lights are
one emissive material whose colour is chosen from object-space X: red
forward of the body centre, green aft of it.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: a 0.52 m motor-to-motor diagonal, 0.33 m propellers, and a
body shell 0.255 m long and 0.136 m wide. The outer AABB is
0.692 × 0.569 × 0.243 m. The props, as parked, set X and Y; the battery
and spinners set the top. The origin is under the body centre, so the
drone lands on its feet.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 40000–42000 | 41048 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 8 distinct; ≥1580 shell, ≥2120 carbon, ≥5950 gunmetal, ≥480 glass, ≥700 light, ≥1190 rubber, ≥7800 graphite, ≥2000 anodised faces | 8 slots; 1720 / 2304 / 6472 / 524 / 760 / 1296 / 8464 / 2184 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.692, 0.569, 0.243) m ± 0.01 | (0.6924, 0.5693, 0.2433), zmin 0 |
| Collider tris | ≤ 540 | 374 |
| Export | written, size > 0, removed after measuring | 3121080 / 3121080 / 3121072 bytes (4.5.11 / 5.1.2 / 5.2.1) |

Every falsifier leaves the triangle count at 41048: they move, scale or
narrow parts, never add or remove them.

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
| Feet: each of the 4 rubber feet has its own `zmin` | within 1e-4 of 0 | 0, 0, 0, 0 |

### Motor layout, propeller clearance, stance and assembly

| Axis | Declared | Measured |
| --- | --- | --- |
| Motor layout: the 4 stator bells' axes (vertex mean; tilt by PCA) about the body shell's centre | angular gaps 90° ± 0.3°; radii within 1 mm of each other; the two diagonals within 1 mm; axes within 0.5° of vertical; 4 hubs at one height ± 0.5 mm and each on its motor's axis ± 0.3 mm; motor centroid within 1 mm of the body centre | 45, 135, 225, 315°; 0 error; 0.000 mm; diagonals 0.52000, 0.52000; 0°; 0 mm; 0 mm; 0 mm |
| Propeller clearance: each prop's disc (farthest blade vertex from its motor's axis) against each neighbouring prop's disc; 2 blades per prop, each overlapping its hub | gap 0.028–0.050 m | discs 0.16558 m; gaps 0.03653 m (all four) |
| Stance: mass centre (shell volumes × density per material) inside the convex footprint of the feet's soles (each foot's lowest ring) | ≥ 0.090 m inside every edge | 0.1146 (3.46 kg, centre at x 0.0067) |
| Wheelbase (mean motor-to-motor diagonal) | 0.520 m ± 0.003 | 0.52000 |
| Body shell length and width | 0.255 × 0.136 m ± 0.003 | 0.2546 × 0.1360 |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (171 shells) |

A camera drone's layout is its flight controller's assumption: the mixer
treats the four thrust axes as the corners of an exact square, level, in
one plane. An arm that did not lock fully open is the commonest way to
break that in the field, and the layout budget sees it as an angular gap.
The clearance budget is the other half: a prop that fouls its neighbour's
disc is the failure a longer prop invites. The densities are named
constants (the moulded shell at 350 kg/m³ for a hollow moulding with its
electronics, carbon 1600, aluminium 2700, glass 2500, lights and rubber
1200, graphite plastic 1400), and the volumes come from the mesh.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. None moves the envelope: every run measured the
same outer AABB as the default.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-foot` | every foot on the ground (front-left foot 3 mm up: its `zmin` 0.00300, the other three 0) | 16 |
| `--unlock-arm` | motor axes on an exact X (rear-left arm 2.5° short of locked open: worst gap 1.491° off 90°, motor centroid 1.69 mm off centre) | 17 |
| `--long-blades` | propeller clearance (rear-left blades 14 mm longer: disc 0.1795 m, gap to both neighbours 0.0226 m) | 18 |
| `--narrow-skids` | stance (skids drawn in to ±0.075 m: margin 0.0776 m) | 19 |
| `--drop-lens` | one connected assembly (glass element 12 mm out of its barrel: 2 components) | 20 |

The rear-left arm is the one both `--unlock-arm` and `--long-blades` move
because its prop is parked across its arm, so neither its tips nor its
motor ever set the envelope. `--unlock-arm` leaves the prop gaps inside
their band (0.0317 and 0.0412 m), so only the layout budget sees it.
`--long-blades` leaves every motor where it was. `--float-foot` lifts one
foot while the other three still ground the box. `--narrow-skids` keeps
the feet on the ground and the envelope unchanged; only the footprint
shrinks. It stops at ±0.075 m on purpose: drawn in to ±0.044 m, the
front struts ran through the gimbal's roll arm and the run exited 15 on 69
coplanar pairs instead of 19. The stance footprint is each foot's sole
(its lowest ring) rather than only the vertices touching the floor.
Otherwise `--float-foot` also collapsed the footprint to a triangle
(margin 0.0039 m) and broke two budgets at once.

## Run

```bash
blender --background --python quad_drone.py --
blender --background --python quad_drone.py -- --skip-decimate
blender --background --python quad_drone.py -- --stray-vert
blender --background --python quad_drone.py -- --lift-z
blender --background --python quad_drone.py -- --float-foot
blender --background --python quad_drone.py -- --unlock-arm
blender --background --python quad_drone.py -- --long-blades
blender --background --python quad_drone.py -- --narrow-skids
blender --background --python quad_drone.py -- --drop-lens
blender --background --python quad_drone.py -- --output drone.png
```

Smoke passes no flags.

The hero turns the piece `HERO_YAW_DEG` (−118°), so the nose and the
gimbal camera face the lens and the X of the arms reads in depth from
above. The wall stands 2.2 m behind the drone, where the floor seam falls
above the far propeller tips, and the warm wedge pools on it.

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
| 16 | Not grounded: bounding box `zmin` off 0, or a foot off the ground, or not 4 feet (`--lift-z`, `--float-foot`) |
| 17 | Motor layout: axes off an exact X (angular gap, radius, diagonal, tilt, hub height, hub off axis, centroid), or not 4 motors and 4 hubs (`--unlock-arm`) |
| 18 | Propeller clearance: a neighbouring disc gap outside its band, a prop without 2 blades, or a blade not in its hub (`--long-blades`) |
| 19 | Stance and size: mass centre within 90 mm of the feet's footprint edge, wheelbase, or body length and width (`--narrow-skids`) |
| 20 | Assembly splits into more than one connected component (`--drop-lens`) |
| 21 | Asset-quality floor (render path only; remapped from 11) |
