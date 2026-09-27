# Basketball hoop

A showcase piece, not an example, and the first in the `sports` category.
It builds a procedural outdoor in-ground basketball goal:

- a square anchor plate with four gussets and four anchor bolts, each with
  a washer and a hex nut;
- a 4.5 in steel pole swept in one piece from inside the plate, through an
  S-shaped gooseneck, up into the mast behind the board;
- navy vinyl padding on the pole, split into three panels by grooves;
- a collar carrying two diagonal support braces up to the board's lower
  back rail;
- two clamp collars and standoffs carrying the board on a rail-and-stile
  back frame;
- a framed backboard with a navy edge pad along its bottom, a painted red
  border and a painted shooter's square;
- a regulation orange rim on a tapered bracket and two struts, bolted
  through a flange plate, with twelve welded net hooks;
- a white cord net: twelve loops hung on the hooks, then 24 strands that
  cross in a tapered diamond mesh.

The pole, gooseneck and mast are one sweep, because a bent bar is one bar.
The straight run of the gooseneck is solved from the mast's offset
(`gooseneck_path()`), so the mast always lands behind the standoffs.
Each brace is a tube between two named stations. Its foot sits in the
middle of the collar wall and its head sits inside the lower rail.

The rim follows regulation: the top of the ring is at 3.05 m, its inside
diameter is 0.457 m, and its inner edge sits 0.151 m off the board face.
The bottom line of the shooter's square has its top edge level with the
rim. Each net loop is a torus threaded across the hook eye. Its cord
passes through the eye and bears 1.5 mm into the hook's lower inside, so
the loop hangs *on* the hook rather than floating near it.

Paint lines are thin annuli sunk 1 mm into the board. They stand proud by
different amounts (border 0.8 mm, square 1.2 mm), so neither lands on the
board face or on the other. The frame is one rectangular-annulus shell,
not four boxes sharing faces. The edge pad runs 8 mm past the frame's ends,
so its caps never land on the frame's end faces.

Bevels run once per material with `material=` set. On the first run,
without it, the board's chamfer faces took slot 0 and the board shell
classified as steel.

Shading follows what each part is. Round stock (pole, pad, ring, cord) is
smooth-shaded. Plates and boxes keep their chamfers crisp through sharp
edges above 35° and at every material boundary. The steel is dark,
rough powder coat, not chrome.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: 0.42 m anchor plate; 1.83 × 1.05 m board with its bottom
at 2.90 m; pole axis 1.22 m behind the board face. The outer AABB is
1.846 × 2.054 × 3.950 m; the board edge pad sets the width.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 8700–10000 | 9356 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 6 distinct; ≥1000 steel, ≥30 board, ≥24 paint, ≥450 rim, ≥700 net, ≥120 pad faces | 6 slots; 2206 / 54 / 32 / 916 / 1344 / 368 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.846, 2.054, 3.950) m ± 0.01 | (1.8460, 2.0540, 3.9500), zmin 0 |
| Collider tris | ≤ 220 | 200 |
| Export | written, size > 0, removed after measuring | 694224 bytes |

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

### Joint fit, net seat, rim and assembly

| Axis | Declared | Measured |
| --- | --- | --- |
| Brace bite: deepest vertex of each of the 2 braces inside the collar / inside the lower rail (signed distance to the host shell) | ≥ 0.006 m each, exactly 2 braces | 0.00703 / 0.02176 |
| Net seat: for each of the 12 hooks, distance from the eye centre to the nearest net loop's cord circle (both fitted from the mesh by PCA) | ≤ 0.009 m (the eye's clear radius), 12 hooks, 12 loops | worst 0.00700 |
| Rim top height (ring shell `max z`) | 3.05 m ± 0.010 | 3.0500 |
| Rim inside diameter (min in-plane radius × 2) | 0.457 m ± 0.004 | 0.4570 |
| Rim inner edge to board face | 0.151 m ± 0.005 | 0.1510 |
| Rim tilt (fitted ring axis vs vertical) | ≤ 0.5° | 0.000° |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (93 shells) |

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. The envelope was unchanged in every run
(`--tilt-rim` moves the Y extent 0.9 mm against a 10 mm tolerance).

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--short-brace` | brace bite (braces stop 60 mm short of the rail: −0.02125 m) | 17 |
| `--drop-net` | net seat (net lowered 25 mm: worst eye-to-loop 0.03200 m) | 18 |
| `--tilt-rim` | rim level (rim assembly tilted 3° about the flange: 3.000°) | 19 |
| `--loose-pad` | one connected assembly (pad bore 6 mm clear of the pole: 2 components) | 20 |

`--drop-net` and `--tilt-rim` move whole sub-assemblies. The net drops
without its hooks, and the rim tilts with its hooks and net about the
flange, so only the budget each one targets can see the change.
`--drop-net` also splits the assembly in two, but the net-seat check
runs first.

## Run

```bash
blender --background --python basketball_hoop.py --
blender --background --python basketball_hoop.py -- --skip-decimate
blender --background --python basketball_hoop.py -- --stray-vert
blender --background --python basketball_hoop.py -- --lift-z
blender --background --python basketball_hoop.py -- --short-brace
blender --background --python basketball_hoop.py -- --drop-net
blender --background --python basketball_hoop.py -- --tilt-rim
blender --background --python basketball_hoop.py -- --loose-pad
blender --background --python basketball_hoop.py -- --output hoop.png
```

Smoke passes no flags.

The hero turns the piece `HERO_YAW_DEG` (−172°), which puts the board
about 43° off the camera axis. From there the gooseneck's S reads in
profile while the square and net read face-on. The key light's spread
keeps it on the hoop instead of the near floor, and a warm wedge pools
on the floor behind and to the right.

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
| 5 | Material count ≠ 6 distinct slots, or a face-count floor missed |
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
| 16 | Not grounded: bounding box `zmin` off 0 |
| 17 | Brace bite: a brace end not inside the collar or the lower rail, or not exactly two braces (`--short-brace`) |
| 18 | Net seat: a hook with no net loop threaded through its eye, or not 12 hooks and 12 loops (`--drop-net`) |
| 19 | Rim off regulation: top height, inside diameter, board gap or level (`--tilt-rim`) |
| 20 | Assembly splits into more than one connected component (`--loose-pad`) |
| 21 | Asset-quality floor (render path only; remapped from 11) |
