# Office chair

A showcase piece, not an example, and the second in the `household`
category. It builds a procedural ergonomic task chair standing on a chair
mat at the corner of a desk, with a potted plant beside it:

- a polished aluminium five-star base: five lofted spokes, each a crowned
  section with two channels and a centre rib on its underside, running
  from a moulded nylon hub out to a socket boss;
- five hooded twin-wheel casters, one under each boss on a plumb chrome
  swivel stem: a bearing washer, a nylon web and hood, a chrome axle and
  two crowned wheels (nylon hub, grey polyurethane tread) trailing the stem
  by 30 mm, each caster swivelled its own way as a chair left after being
  rolled about;
- a chrome gas-lift column rising out of the hub through a two-stage
  telescoping cover into the socket of a synchro-tilt mechanism, which
  carries a tilt-spring housing, a knurled tension knob and two lever
  paddles;
- a moulded graphite seat shell cupping a two-tone upholstered cushion:
  a woven muted-teal centre panel sculpted with a rear dish and two thigh
  channels that rolls down over a waterfall front, mid-grey knit side
  panels whose sides bolster up, a piped welt laid in the seam groove
  between the panels and another along the top edge;
- an aluminium spine that sweeps out of the mechanism's rear, down under
  the back and up behind it into a hub plate on a cross bar;
- a reclined mesh back: an elastomeric weave (horizontal ribs over fine
  vertical strands, open between them) stretched over a graphite frame
  that is slim along its arched top rail and swells toward its foot,
  wrapped round the sitter and bulged forward at the lumbar;
- an S-curved lumbar pad on straps whose ends are two sliders clamped
  round the frame's sides;
- a headrest of the same mesh in its own graphite frame, carried forward
  of the back on an aluminium stem into a hub plate behind it;
- two 4D armrests: aluminium brackets bolted under the shell, a
  telescoping cover, a post with a chrome height button on its front and a
  pivot button on its outer face, a pad plate and a soft leatherette pad;
- a smoked polycarbonate chair mat, 4 mm thick with a chamfered foot and a
  bevelled top edge, with a lip that runs forward under a desk; every
  caster presses 0.6 mm into it;
- a snake plant beside the mat: nine folded, lanceolate blades with the
  plant's wavy cross-bands, leaning out and turning slowly, rooted in the
  crowned soil of a speckled stone planter with a foot, a belly, a waist
  and a rolled lip.

Everything is placed from named stations. The casters hang on
`caster_frame(k)`: a stem on the 0.305 m swivel circle at the spoke's own
bearing, the axle 30 mm behind it along the caster's yaw. The chair is
built on the floor and lifted by `CHAIR_Z = MAT_T - MAT_SINK`, so every
wheel sits 0.6 mm into the sheet. The back is one surface function,
`back_point(u, v, off)`, that the frame, mesh, lumbar pad, straps,
sliders, cross bar, hub plate, spine, headrest stem, headrest frame and
headrest mesh all read, so a change of recline or wrap moves every part
of the back together. The seat is one plan (`seat_plan`) and one
sculpting function (`seat_contour`, every term even in x) that the
cushion rings and both welts read.

Four things the coplanar budget shaped before it could fire:

- The two wheels of one caster are mirror images on one axle. A tread
  segment of constant radius would lie in the same plane as its twin's,
  facet for facet, 35 mm away. The tread is crowned instead, and no wheel
  profile segment keeps its radius, so no twin faces share a plane.
- The welts are hexagons turned to put a vertex on top. With a flat on
  top and bottom, the groove welt's top landed on the centre panel's
  plane (8 pairs) and the two welts' bottoms on each other's (6).
- The mechanism housing stops 1 mm under the cushion's floor, and each
  lumbar strap stops 6 mm inside its slider rather than on the frame's
  centreline, where its end cap lay in the mesh's edge band (36 pairs).
- The nine leaf bases are buried 1 mm deeper each, so no two base caps
  share a plane (604 pairs when they all stopped at one depth).

Shading follows what each part is. Moulded, turned and upholstered
surfaces are smooth-shaded; the mechanism's chamfers, the knob's knurl,
the seams and every material boundary stay crisp through sharp edges. The
upholstery is a heathered yarn over an undistorted plain weave (distorted
bands read as wood grain). The mesh lets the light through its open cells,
so the spine and headrest stem show behind it. Aluminium, chrome, the
mechanism, the graphite plastics and the mat carry the studio reflection
term (after `espresso-machine`): a metal on the dark stage mirrors the
stage and reads as grey plastic without it.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: seat 0.50 m high, a 0.66 m star, armrests 0.20 m over
the seat, headrest top 1.32 m; a 1.20 × 1.28 m mat plus its 0.20 m lip; a
planter 0.29 m tall with leaves to 0.96 m. The outer AABB is
1.635 × 1.480 × 1.317 m. The mat sets −X and ±Y, the plant sets +X, the
headrest sets the top. The origin is under the hub, so the chair and its
mat drop onto a floor together.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file. Parts are told apart by a `part` face attribute written at
build time; every position, depth, angle and mass is read off the mesh.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 43700–45200 | 44440 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 14 distinct; ≥1330 fabric, ≥1450 mesh, ≥3260 shell, ≥4100 nylon, ≥3950 aluminium, ≥1370 chrome, ≥1820 tread, ≥1600 leatherette, ≥510 steel, ≥1060 border, ≥790 mat, ≥750 ceramic, ≥220 soil, ≥715 leaf faces | 14 slots; 1402 / 1534 / 3440 / 4322 / 4167 / 1450 / 1920 / 1688 / 538 / 1118 / 836 / 796 / 236 / 756 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.635, 1.480, 1.317) m ± 0.01 | (1.6350, 1.4800, 1.3169), zmin 0 |
| Collider tris | ≤ 580 | 551 |
| Export | written, size > 0, removed after measuring | 3294736 bytes |

No falsifier changes the triangle count, so the band is narrow and
centred on the measurement. DECIMATE COLLAPSE triangle counts are not
identical across Blender series, so the LOD gate is a ratio band, not an
exact count. Bake pixels are stochastic, so the bake gate is `has_data`
plus operator `FINISHED`, not byte-identity. Construction uses no RNG;
the plant's per-blade variation is closed-form from the blade index. Two
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

### Supports, star, gas lift, stance, assembly, lumbar and plant

| Axis | Declared | Measured |
| --- | --- | --- |
| Mat flat on the floor: highest vertex of the mat's downward faces | ≤ 1e-4 | 0.0000 (120 vertices) |
| Named supports: every wheel pressed into the mat, measured against the mat's own surface by a ray straight down from the wheel's lowest vertex | 10 wheels, 0.3–1.0 mm each | 10; 0.6–0.6 mm |
| Pot on the floor | `zmin` ≤ 1e-4 | 0.0000 |
| Five-star geometry: spoke bearings and boss bearings (shell centroids) round the hub | 72° apart ± 0.25° | 0.00001° worst gap error |
| Bosses and swivel stems on one circle | radius spread ≤ 1 mm each | 0.305 / 0.305 m, spread 0 |
| Stems plumb (bottom- and top-slab centroids), coaxial with their bosses, seated in them | tilt ≤ 0.2°; axis ≤ 0.3 mm off the boss's; seat 25–40 mm | 0.000°; 0.0000 mm; 34 mm each |
| Gas lift: the column's axis through the hub's and the socket's axes | ≤ 0.3 mm at each; tilt ≤ 0.2° | 0.0000 / 0.0000 mm; 0.000° |
| Column inserted into the hub / the socket | 40–65 mm / 20–40 mm | 52 / 28 mm |
| Armrests: bracket, cover, post, height button, pivot button, pad plate and pad paired left to right, mirrored in X and level in Y and Z | ≤ 0.5 mm, 7 pairs | 0.0000 mm |
| Seat height (cushion top), armrest height over the seat | 0.44–0.50 m, 0.17–0.26 m | 0.4965, 0.1974 m |
| Star diameter (outer boss reach ×2) | 0.660 m ± 0.005 | 0.6599 |
| Stance: the chair's mass centre (shell volumes × density per material; the mat and plant excluded) inside the hull of the ten wheels' contacts | ≥ 0.12 m inside every edge | 0.2149 (34.24 kg, centre at y 0.035) |
| One connected chair (union of the chair's shells whose BVH trees overlap; the mat and plant are not part of it) | 1 component | 1 (89 shells) |
| Lumbar sliders clamped on the frame: distance from every slider vertex to the frame tube's surface | 2 sliders, 2.0–6.5 mm | 2; 3.5–5.2 mm |
| Plant rooted: each leaf's base depth under the soil's own surface straight above it; base clear of the pot wall | 9 leaves, 15–45 mm; ≥ 10 mm | 9; 24.5–31.6 mm; 66 mm |

The densities are named constants: 50 for seat foam, 300 for the
leatherette pads, 400 for the mesh, 1150 for nylon and the graphite
plastics, 1200 for the treads, 2700 for aluminium, 7850 for chrome steel,
and an effective 3000 for the mechanism, a pressed-steel housing modelled
solid. The five spokes are measured by bearing, not by index: rotating any
one breaks two of the five gaps. The chair's connectivity excludes the
mat because the casters press into it: counted with the mat, a wheel slid
off its axle would still be joined to the chair through the sheet.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code with every earlier budget green. None moves the
envelope or the triangle count: every run measured the default's outer
AABB and 44440 triangles.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-caster` | every wheel pressed into the mat (caster 3's body lifted 5 mm up its stem: its wheels 4.4 mm over the sheet, the other eight still pressed 0.6 mm in) | 16 |
| `--curl-mat` | mat flat on the floor (its back-left corner curled 6 mm up: underside rises to 0.00600 m, clear of every wheel) | 16 |
| `--skew-spoke` | five-star geometry (spoke 0 and its caster turned 3°: worst gap off 72° by 3.000°) | 17 |
| `--offset-column` | gas lift coaxial (column moved 3 mm in X: 0.00300 m off both the hub's and the socket's axes) | 18 |
| `--uneven-arms` | armrests mirrored and level (right post, buttons, plate and pad raised 10 mm in the cover: 0.01000 m) | 19 |
| `--loose-wheel` | one connected chair (caster 0's outer wheel slid 24 mm off its axle end: 2 components) | 20 |
| `--float-lumbar` | lumbar sliders clamped on the frame (pad, straps and sliders floated 6 mm forward: gap 0.07–11.0 mm) | 21 |
| `--float-leaves` | leaves rooted in the soil (every blade lifted 40 mm: depth −15.5 to −8.4 mm) | 22 |

`--float-caster` lifts the caster body, not the stem, so the stem only
rides deeper into the web and the star budget still passes. `--curl-mat`
curls only the corner where −x + y is largest, which no wheel reaches, so
the wheels stay seated and the mat-flat budget is the one that fires.
`--offset-column` leaves the column seated 52 mm and 28 mm deep and
plumb, so only the coaxial budget sees it. `--uneven-arms` slides the
arm up its own cover, as the height adjuster does, so the chair stays
connected and the envelope holds; the seat and armrest heights stay in
band. `--loose-wheel` slides a wheel along its own axle, so it still
presses into the mat and the named-supports budget passes; it is attached
by one joint, the axle, which is why it is the part that splits.
`--float-lumbar` moves the lumbar unit less than a slider's wall is deep
past the frame, so the sliders still bite the frame and the chair stays
one component; only the clamp band sees it. `--float-leaves` lifts the
blades inside the envelope: the headrest, not the plant, sets the top.

## Run

```bash
blender --background --python office_chair.py --
blender --background --python office_chair.py -- --skip-decimate
blender --background --python office_chair.py -- --stray-vert
blender --background --python office_chair.py -- --lift-z
blender --background --python office_chair.py -- --float-caster
blender --background --python office_chair.py -- --curl-mat
blender --background --python office_chair.py -- --skew-spoke
blender --background --python office_chair.py -- --offset-column
blender --background --python office_chair.py -- --uneven-arms
blender --background --python office_chair.py -- --loose-wheel
blender --background --python office_chair.py -- --float-lumbar
blender --background --python office_chair.py -- --float-leaves
blender --background --python office_chair.py -- --output chair.png
```

Smoke passes no flags.

The hero turns the whole vignette `HERO_YAW_DEG` (18°), so the seat and
arms face the camera's right, the mat's lip points toward the camera and
the plant stands to the chair's right. The camera stands low (0.72 m over
the vignette's centre): the mat foreshortens, the chair fills more of the
frame's height, and the mesh back and headrest read against the dark
back wall, with the floor/wall seam behind the seat rather than through
the mesh. The warm wedge pools on the floor to the plant's right, not
behind the back. The mat and plant widen the composition: fill 0.49 of
the frame's width (was 0.27) and 0.84 of its height, which meets the
framing band.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family. `20`–`22` are file-local. `23` is the
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
| 5 | Material count ≠ 14 distinct slots, or a face-count floor missed |
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
| 16 | Not grounded: bounding box `zmin` off 0, the mat not flat on the floor, a wheel not pressed into the mat within its band or not 10 wheels, or the pot off the floor (`--lift-z`, `--curl-mat`, `--float-caster`) |
| 17 | Five-star geometry: spokes or bosses off 72° spacing, bosses or stems off one circle, a stem tilted, off its boss's axis or outside its seat band (`--skew-spoke`) |
| 18 | Gas lift: column off the hub's or the socket's axis, tilted, or inserted outside its bands (`--offset-column`) |
| 19 | Stance and size: armrests not mirrored and level, seat or armrest height, star diameter, or the mass centre within 0.12 m of the caster contact hull's edge (`--uneven-arms`) |
| 20 | The chair splits into more than one connected component (`--loose-wheel`) |
| 21 | Lumbar sliders not clamped on the back frame within their gap band (`--float-lumbar`) |
| 22 | Plant: a leaf's base outside its depth band in the soil, too near the pot wall, or not 9 leaves (`--float-leaves`) |
| 23 | Asset-quality floor (render path only; remapped from 11) |
