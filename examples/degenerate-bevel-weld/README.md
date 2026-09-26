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

**Render as proof:** two rugged hard-shell equipment cases whose shells
*are* the check's two meshes — `beveled_box(DIMS, 0.10)` and
`beveled_box(DIMS, 0.20)` — with every fitting (handle, latches, molded
frame, purge valve, ID plate, feet) kept inside the flat front land that
survives both offsets, so the bevel is the only difference. The cases turn
their end panels to the camera: the left keeps a flat end framed by clean
chamfer bands; on the right the end and top lands are gone and the band
rolls into a knife ridge at mid-depth. That collapsed seam is traced in hot
red from live mesh data (every edge of every face thinner than 1e-6), with
an orange bead on each of the 12 zero-area faces the check counts — change
the offset and the overlay moves or disappears. The clean case is the
designed asset and passes the asset-quality floors (exit 11).

## Run

```bash
blender --background --python degenerate_bevel_weld.py --
blender --background --python degenerate_bevel_weld.py -- --both-safe
blender --background --python degenerate_bevel_weld.py -- --output bevel.png
blender --background --python degenerate_bevel_weld.py -- --output bevel.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper, `11` the shared
asset-quality helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Safe bevel produced zero-area faces |
| 4 | Degenerate bevel zero-area count ≠ closed form (`--both-safe` lands here) |
| 5 | min_area collapse under 1e5× |
| 6 | Coincident-position count off the closed form |
| 7 | Safe GLB carries degenerate triangles |
| 8 | Degenerate GLB triangle or position count drifted |
| 9 | `--output` produced no file |
| 10 | Gallery framing violation |
| 11 | Asset-quality floor violation (render path only) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--both-safe`.
