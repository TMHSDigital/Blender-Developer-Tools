# Coincident vert weld

Synthesizes two cubes occupying the same space as one mesh, then
asserts the duplicates exist before asserting they cross glTF export.
Inverse of [`degenerate-bevel-weld`](../degenerate-bevel-weld/)
(coincidences from bevel pinch) and
[`mesh-hygiene-audit`](../mesh-hygiene-audit/) (manifold on a clean
solid). Neighbor of [`gltf-export-roundtrip`](../gltf-export-roundtrip/)
(kit-bash face-plane welds on export).

**Why this pathology:** coincident shells are still manifold (every
edge borders 2 faces). Hygiene can pass. The engine trap is extra
triangles on disk.

**Pre-assertion (pathology exists):** **16** verts, **8** unique
positions, **12** faces, **24** edges, valence all 2. `--no-duplicate`
exits 3.

**Handling (second axis):** glTF ships **48** loop-split positions,
**24** tris, **8** unique. Vert count 16 is not enough; unique=8 is
the construction axis; 24 tris vs 12 after `remove_doubles` is the
export axis. `--weld` after the pre-assert exits 4.

`remove_doubles` collapses to one cube (8/12/6), still manifold — not
a 4-face-per-edge mesh. Same on 4.5 LTS and 5.2 LTS.

No gallery still. Two coincident cubes look like one cube.

## Run

```bash
blender --background --python coincident_vert_weld.py --
blender --background --python coincident_vert_weld.py -- --no-duplicate
blender --background --python coincident_vert_weld.py -- --weld
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage; also exporter RNA missing expected glTF kwargs |
| 3 | Pathology missing: coincident shells (`--no-duplicate` lands here) |
| 4 | glTF export handling failed (`--weld` lands here) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--no-duplicate` or `--weld`.
