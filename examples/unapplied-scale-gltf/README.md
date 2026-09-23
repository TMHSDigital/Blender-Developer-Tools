# Unapplied scale glTF

Synthesizes unapplied non-uniform object scale on a unit cube, then
asserts the glTF exporter contract. Inverse of
[`gltf-export-roundtrip`](../gltf-export-roundtrip/) (identity scale,
node has no scale) and neighbor of
[`prop-origin-transform`](../prop-origin-transform/) (bake to `(1,1,1)`
in Blender).

## The contract

`bpy.ops.export_scene.gltf(export_apply=True)` applies **modifiers**, not
object transforms. Its RNA description, identical on 4.5.11, 5.1.2 and
5.2.1, reads:

> Apply modifiers (excluding Armatures) to mesh objects -WARNING: prevents
> exporting shape keys

An object whose `Object.scale` was never applied therefore exports with
that scale on the glTF **node** (`nodes[i].scale`), permuted to Y-up, and
with its **POSITION** accessor still holding the unscaled local
coordinates. `export_apply` has no effect on either: exporting the same
object with `export_apply=False` writes the identical node scale and
POSITION range.

**Who hits this:** a pipeline that sets `export_apply=True` believing it
bakes transforms, then ships a prop whose root carries a non-uniform
scale. In the engine the mesh looks the right size, but any child
rotated under that node skews, physics colliders sized from the mesh
bounds come out at the local size, and a script reading the node's
scale gets `(2, 0.5, 1)` instead of `(1, 1, 1)`. The fix is to apply
scale in Blender before export (`bpy.ops.object.transform_apply(scale=True)`,
or the data-API bake in `prop-origin-transform`), not an exporter flag.

## What the check asserts

**Pre-assertion (pathology exists):** `obj.scale == (2, 1, 0.5)`
(non-uniform) **and** local verts at ±1 on every axis. `--identity`
leaves the scale at `(1, 1, 1)` and exits 3.

**Handling (second axis):** read back from the written `.gltf` and its
`.bin`, not from Blender state:

- `nodes[0].scale == [2, 0.5, 1]` — Blender `(sx, sy, sz)` becomes glTF
  `(sx, sz, sy)` under the Y-up conversion `(x, y, z) → (x, z, −y)`.
- POSITION min/max is ±1 on every axis — the local cube, unscaled.
- POSITION count is 8 either way, so a vertex count alone cannot tell
  applied from unapplied. The node scale and the POSITION range are the
  witnesses.

`--bake` applies the scale to the mesh data after the pre-assertion.
The node then has no `scale` key and POSITION spans x ±2, y ±0.5, z ±1,
so the check exits 4.

## Versions

Re-verified on Blender 4.5.11 LTS, 5.1.2 and 5.2.1 LTS: the RNA
description, the node scale, the POSITION range and both falsifier exits
are the same on all three. Not a version split.

No gallery still. A stretched box looks like modeled non-uniform size;
the defect is unapplied versus baked, which only the file shows.

## API reference

- [`bpy.ops.export_scene.gltf`](https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf)
  ([4.5 LTS](https://docs.blender.org/api/4.5/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf))
  — `export_apply`, `export_yup`
- [`Object.scale`](https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.scale)
- [glTF 2.0 node transforms](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#transformations)

## Run

```bash
blender --background --python unapplied_scale_gltf.py --
blender --background --python unapplied_scale_gltf.py -- --identity
blender --background --python unapplied_scale_gltf.py -- --bake
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage; also exporter RNA missing expected glTF kwargs |
| 3 | Pathology missing: unapplied non-uniform scale (`--identity` lands here) |
| 4 | Export handling failed (`--bake` lands here) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--identity` or `--bake`.
