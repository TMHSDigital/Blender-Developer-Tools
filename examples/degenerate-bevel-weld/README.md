# Degenerate Bevel Weld

A runnable example isolating the half-dimension bevel collapse: author a
bevel width against one box and reuse it on a thinner one, and at
`offset == min_dimension / 2` the bevel band pinches into zero-area faces —
and those degenerate triangles **cross the export boundary**. Re-parsed from
the shipped GLB with stdlib only, they are sitting in the file, where an
engine-side merge-by-distance welds their loops. Found authoring
[`gltf-export-roundtrip`](../gltf-export-roundtrip/) (its count check caught
a 36-vertex weld on a thin crate part); this example isolates the threshold.

**Pipeline arc neighbors:** round-trip fidelity in
[`gltf-export-roundtrip`](../gltf-export-roundtrip/), topology gates in
[`mesh-hygiene-audit`](../mesh-hygiene-audit/), watertight parametric solids
in [`bmesh-gear`](../bmesh-gear/).

**What it witnesses:** a 1.6 × 0.4 × 1.0 slab (min dim 0.4, half = 0.2) with
every edge beveled at 3 segments. All closed form or independently
re-derived:

- **Threshold.** Offset 0.10 (< 0.2) yields **zero** zero-area faces;
  offset 0.20 (== min/2) yields exactly **12** == 4 min-axis edges × 3
  segments. `min_area` collapses 3.2e5× (5.8e-04 → 1.8e-09).
- **Collapse witness.** Coincident-position verts == **16** == 4 edges ×
  (segments + 1), re-derived by 6-decimal position grouping — the loops a
  merge-by-distance welds.
- **Export crossing.** A stdlib re-parse of the GLB recomputes every
  triangle area from the raw POSITION + indices buffers: **32** degenerate
  triangles ship (the 12 collapsed faces, triangulated — a MEASURED
  regression constant like curve-bevel-arc's `EXPECT_VERTS`; re-measure
  recipe in `check()`), versus 0 for the safe mesh. The exporter ships every
  loop (positions == 384 loops) — nothing warns you.

**What each check catches on failure:** safe offset pushed to the threshold
(exit 3); degenerate offset backed below it (exit 4); coincident closed form
corrupted (exit 6); GLB degenerate-tri expectation off (exit 8, e.g. if a
future Blender changes triangulation — re-measure and update deliberately).

**Version witness:** output is byte-identical on Blender 4.5.11 LTS and
5.1.2 — same counts, same min_area values, same GLB triangle census.

**Render as proof:** dual tray from the same `DIMS`/offsets the check
asserts. Left keeps a soft rounded bevel; right collapses to a knife edge,
with an emissive seam marker at every zero-area face centroid — the markers
are placed from live mesh data, so a change in the data moves them. The
broken state is in-frame by design.

## Run

```bash
blender --background --python degenerate_bevel_weld.py --
blender --background --python degenerate_bevel_weld.py -- --output bevel.png
blender --background --python degenerate_bevel_weld.py -- --output bevel.png --engine cycles
```

Exits non-zero on failure. The `blender-smoke` workflow runs the check on
Blender 4.5 LTS and 5.1. The `--output` render path additionally measures
framing against the Layer 1 band via `examples/gallery_framing.py` (exit 10
on violation) before writing the still.
