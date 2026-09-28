# Archery target

A showcase piece, not an example, and the fifth in the `sports` category.
It builds a procedural archery range target on a turf patch:

- a 1.10 m compressed-straw boss, 0.28 m thick, built as one turned coil.
  Seventeen rope courses show as relief on its back, round its edge and on
  the annulus around the face; inside 0.43 m the face is pressed flat. The
  straw shader runs its fibres round the coil from a per-vertex coil
  coordinate, and every rope course has its own tone;
- eight doubled jute bindings over the edge, laid tight on the envelope over
  the crests so they bridge the grooves, their ends diving into the straw;
- an 80 cm World Archery face: ten zones 4 cm wide (gold, red, blue, black,
  white) with black ring lines (a white one in the black), the X ring and a
  printed X, pinned through the white by four target pins with green heads;
- a timber easel leaning the boss back 12°: two front legs tenoned into toe
  skids, each triangulated by a toe and a heel knee brace; a rail on the
  legs' front faces with carriage bolts, a ledge with a stop lip on the rail
  and two gussets; a white butt board numbered 12 above the boss; a head
  block behind the leg tops; a strap hinge (two leaves, three knuckles, a
  riveted pin) to a single rear leg in a steel ferrule on a steel foot; a
  stretcher, and a taut chain between two eye bolts limiting the splay;
- five carbon arrows in the face (turned points, cresting, nocks, three
  vanes at 120° with an off-white cock vane), a sixth glancing into the
  straw edge, a seventh snapped off in the black with its fletched half
  lying on the grass; and
- a leather quiver lying on the turf, with a belt loop and three bands,
  holding three arrows whose tips rest on its floor, among grass tufts.

The layout is solved from named constants. The boss's lowest edge course
bites the ledge 2.5 mm and its back crests bite both front legs 2 mm; the
legs are placed from the boss, not the other way round. Arrows are placed by
where they hit the face and how far they went in. The half arrow and the
quiver are levelled on their own lowest points and dropped onto the turf.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: 2.01 m across the turf patch, 2.69 m front to back, 2.05 m to
the top of the front legs. The turf sets the width and depth, the leg tops
the height. The centre of the gold stands 1.30 m above the turf, the World
Archery height.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 42000–44000 | 42908 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 16 distinct; ≥4490 straw, ≥1760 twine, ≥1030 pine, ≥5970 steel, ≥495 white, ≥775 black, ≥120 blue, ≥120 red, ≥240 gold, ≥310 carbon, ≥475 vane, ≥285 cock vane, ≥1020 nock, ≥4960 grass, ≥270 soil, ≥730 leather faces | 16 slots; 4732 / 1856 / 1086 / 6288 / 522 / 816 / 128 / 128 / 254 / 326 / 500 / 300 / 1076 / 5230 / 286 / 768 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (2.0071, 2.6887, 2.0538) m ± 0.01 | (2.0071, 2.6887, 2.0538), zmin 0 |
| Collider tris | ≤ 1150 | 1083 |
| Export | written, size > 0, removed after measuring | 3288248 bytes |

The collider is the convex hull of the whole piece; its count is carried by
the 96-segment turf outline.

Every falsifier leaves the triangle count at 42908 and the AABB unchanged:
they move parts or change a length, never add or remove geometry.

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. Construction uses only seeded `random.Random` streams;
two default runs print identical measurements.

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
| Supports: both skids and the rear tread bedded into the turf (turf top read off the mesh) | 3 supports, 1–4 mm | 2.0 mm each |

The first draft measured 741 coplanar pairs, all fixed in the model. The
two strands of each binding ended in caps on one plane (256): they now dive
to different depths. The three vanes of each arrow had their rear edges on
one plane square to the shaft (54): the rear edge is raked. The three quiver
arrows' nocks ended on one plane and two of them shared vane angles
(199): each tip bites the quiver floor a different depth and each lathe is
turned by its arrow's roll. Pairs of domed bolt heads put side facets on
one plane (232): heads are turned a quarter segment so no facet is square
to the head's frame. The hinge leaf's edge sat on a knuckle's end face: the
leaf is 2 mm narrower.

### Stand, boss, face, arrows, stability and assembly

| Axis | Declared | Measured |
| --- | --- | --- |
| Hinge: each of the 3 knuckles' centres (vertex mean of the ring) against the pin's axis (PCA) | 3 knuckles; ≤ 0.3 mm | 0.000 mm |
| Boss on its ledge: the ledge's top along the face's up axis minus the boss's lowest point, which must lie over the ledge; each front leg's front face minus the boss's back crests over that leg, along the face normal | seat 1–4 mm; lean 1–4 mm on both legs | 2.5 mm; 2.0, 2.0 mm |
| Regulation and size: gold centre above the turf; boss diameter and thickness about the face's axis; face diameter; tilt of the face normal | 1.30 ± 0.05 m; 1.100, 0.280 ± 0.004; 0.800 ± 0.002; 10–15° | 1.3000; 1.1000, 0.2800; 0.8000; 12.000° |
| Points buried: every shaft with a steel point whose tip is inside the boss; a ray back along the shaft to where it leaves the straw, and one forward to the straw left ahead | 7 arrows; 0.08–0.20 m; ahead ≥ 0.01 m | 7; 0.119–0.149 m; ≥ 0.051 m |
| Fletching clear: every vane's signed distance from the boss surface (BVH nearest, sign by the face normal) | ≥ 0.25 m | 0.419 m |
| Vanes at 120°: every vane assigned to the nearest shaft axis; its angle round that axis | 10 fletched shafts, 3 vanes each; gaps within 1° of 120° | as declared; 0.002° |
| Scoring rings: annuli of the paper's front read off the mesh; each ring line's centre radius, and every zone and line in the ink the table gives it | lines at 0.02, 0.04 … 0.36 m ± 0.5 mm; 0 wrong | 0.000 mm off; 0 |
| Stability: mass centre of boss, face, bindings, stand and hardware (shell volume × density: straw 160, pine 500, twine 500, paper 700, steel 7850 kg/m³) against the convex hull of the supports' contact points; forward tip angle over the front edge | inside; tip ≥ 20° | 73.85 kg, 0.349 m inside; 27.83° |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (722 shells) |

A boss is only safe on an easel if it sits on its ledge and against both
legs. The gold height is the World Archery rule, measured from the turf read
off the mesh. An arrow that has not buried its point falls out; one whose
fletching reaches the face was shot through the boss. The scoring table is
what makes the face a target face. An archer pulling arrows leans on the
boss; the toe skids carry the stand's front edge forward of its mass
centre, and the tip angle is what they buy.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code, with the triangle count and AABB unchanged and
every budget checked before the target still green.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-foot` | every support bedded in the turf (rear tread and ferrule 6 mm up: bite −0.004 m) | 16 |
| `--offset-hinge` | hinge pin coaxial with its knuckles (pin 2.5 mm up the face: all three 0.0025 m off) | 17 |
| `--lift-boss` | boss resting on its ledge (boss and all it carries 6 mm up the legs: seat −0.0035 m, lean unchanged) | 18 |
| `--high-boss` | regulation gold height (boss, ledge, rail and gussets 80 mm up the legs: 1.3783 m) | 19 |
| `--shallow-arrow` | every point buried (third arrow in 30 mm: 0.0287 m) | 20 |
| `--short-arrow` | every fletching clear of the face (second arrow a 0.40 m shaft: a vane 0.1420 m from the straw) | 21 |
| `--skew-vane` | vanes at 120° (one vane of the first arrow turned 15°: 15.000° off) | 22 |
| `--wide-gold` | ring radii of the scoring table (gold/red line printed at 0.09 m) | 23 |
| `--short-skids` | forward tip angle (skid toes cut back to 50 mm ahead of the legs: 15.20°, mass centre still 0.289 m inside) | 24 |
| `--loose-pin` | one connected assembly (one target pin 75 mm out of the face: 2 components) | 25 |

`--lift-boss` moves the boss along the legs, so it still leans on both.
`--high-boss` moves the ledge with the boss, so the seat holds and only the
height fails. `--shallow-arrow` pushes the fletching further from the face.
`--short-arrow` keeps the point's depth. `--short-skids` keeps both skids
bedded and the mass centre inside the supports.

## Run

```bash
blender --background --python archery_target.py --
blender --background --python archery_target.py -- --skip-decimate
blender --background --python archery_target.py -- --stray-vert
blender --background --python archery_target.py -- --lift-z
blender --background --python archery_target.py -- --float-foot
blender --background --python archery_target.py -- --offset-hinge
blender --background --python archery_target.py -- --lift-boss
blender --background --python archery_target.py -- --high-boss
blender --background --python archery_target.py -- --shallow-arrow
blender --background --python archery_target.py -- --short-arrow
blender --background --python archery_target.py -- --skew-vane
blender --background --python archery_target.py -- --wide-gold
blender --background --python archery_target.py -- --short-skids
blender --background --python archery_target.py -- --loose-pin
blender --background --python archery_target.py -- --output target.png
```

Smoke passes no flags.

The hero turns the piece `HERO_YAW_DEG` (6°), so the face meets the camera
at about a third of a right angle: the left edge with its glancing arrow,
the bindings and the courses show, and the arrows in the face read at
length. The wall stands 3.4 m behind the target, and the warm wedge pools
on it.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family. `20`–`25` are file-local. `26` is the
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
| 5 | Material count ≠ 16 distinct slots, or a face-count floor missed |
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
| 16 | Not grounded: bounding box `zmin` off 0, or a support not bedded 1–4 mm into the turf, or not 3 supports (`--lift-z`, `--float-foot`) |
| 17 | Hinge: not 3 knuckles, or one off the pin's axis (`--offset-hinge`) |
| 18 | Boss not resting on its ledge, or not leaning on both legs (`--lift-boss`) |
| 19 | Regulation: gold height, boss or face size, or tilt off (`--high-boss`) |
| 20 | Arrow points: not 7 in the boss, one buried outside its band, or through the back (`--shallow-arrow`) |
| 21 | Fletching: a vane closer to the boss than its clearance (`--short-arrow`) |
| 22 | Vanes: not 10 fletched shafts of 3, or spacing off 120° (`--skew-vane`) |
| 23 | Scoring rings: a line off the table, or a zone in the wrong ink (`--wide-gold`) |
| 24 | Stability: mass centre outside the supports, or forward tip angle under its floor (`--short-skids`) |
| 25 | Assembly: not one connected component (`--loose-pin`) |
| 26 | Asset-quality floor (render path only; remapped from 11) |
