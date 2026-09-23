# Coincident vert weld

Synthesizes two cubes occupying the same space as one mesh, then
asserts the duplicates exist before asserting they cross glTF export.
Inverse of [`degenerate-bevel-weld`](../degenerate-bevel-weld/)
(coincidences from bevel pinch) and
[`mesh-hygiene-audit`](../mesh-hygiene-audit/) (manifold on a clean
solid). Neighbor of [`gltf-export-roundtrip`](../gltf-export-roundtrip/)
(kit-bash face-plane welds on export).

## The contract

A mesh holding two coincident shells is still **manifold**: every edge
borders exactly two faces, because each shell is closed on its own. A
hygiene check that only counts non-manifold edges reports 0 and passes.
The glTF exporter then writes both shells: nothing in
`bpy.ops.export_scene.gltf` welds coincident vertices, so the file
carries twice the triangles of the visible solid.

**Who hits this:** kit-bash and boolean-cleanup pipelines, duplicated
objects joined back onto themselves, and generators that emit a part
twice. The asset looks like one cube in Blender and in the engine: the
two shells are identical triangles, so the depth test hides the second
without flicker. The cost is invisible in the viewport and real on disk
and at runtime: double the draw triangles, a collider built from the mesh
twice as heavy, and overlapping lightmap UVs if the shells were unwrapped.

**What catches it:** a coincident-vertex check, not a manifold check.
`bmesh.ops.find_doubles(dist=1e-5)` reports **8** doubles on this mesh
while the non-manifold count stays **0**. That is why the showcase
hygiene budgets count doubles separately from non-manifold edges. The
fix is `bmesh.ops.remove_doubles` before export.

## What the check asserts

**Pre-assertion (pathology exists):** **16** verts, **8** unique
positions, **12** faces, **24** edges, valence 2 on every edge.
`--no-duplicate` builds a single cube and exits 3. Vert count 16 alone is
not enough, since any 16-vert mesh has it. Unique positions = 8 is the
construction witness.

**Handling (second axis):** read back from the written `.gltf` and its
`.bin`: **48** loop-split positions, **24** triangles, **8** unique
positions. `--weld` runs `remove_doubles` after the pre-assertion, the
file then carries 24 positions and 12 triangles, and the check exits 4.

`remove_doubles` collapses the pair to one cube: 8 verts, 12 edges,
6 faces, valence 2. That is identical in every count to a cube built
once. It does not leave a 4-faces-per-edge mesh.

## Versions

Re-verified on Blender 4.5.11 LTS, 5.1.2 and 5.2.1 LTS. Every count
above is the same on all three, including the `find_doubles` and
non-manifold figures and both falsifier exits. Not a version split.

No gallery still. Two coincident cubes look like one cube; the defect
is only in the counts.

## API reference

- [`bmesh.ops.find_doubles`](https://docs.blender.org/api/current/bmesh.ops.html#bmesh.ops.find_doubles)
  and [`bmesh.ops.remove_doubles`](https://docs.blender.org/api/current/bmesh.ops.html#bmesh.ops.remove_doubles)
  ([4.5 LTS](https://docs.blender.org/api/4.5/bmesh.ops.html#bmesh.ops.remove_doubles))
- [`bpy.ops.export_scene.gltf`](https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf)
  ([4.5 LTS](https://docs.blender.org/api/4.5/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf))

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
