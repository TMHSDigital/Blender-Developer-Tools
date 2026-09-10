# Unapplied scale glTF

Synthesizes unapplied non-uniform object scale on a unit cube, then
asserts the glTF exporter contract. Inverse of
[`gltf-export-roundtrip`](../gltf-export-roundtrip/) (identity scale,
node has no scale) and neighbor of
[`prop-origin-transform`](../prop-origin-transform/) (bake to `(1,1,1)`
in Blender).

**Why this pathology:** `export_apply` RNA is "Apply modifiers … to mesh
objects". AI code treats it as "apply object transforms". Unapplied
scale lands on the glTF node, Y-up permuted; POSITION stays local.

**Pre-assertion (pathology exists):** `obj.scale == (2, 1, 0.5)`
(non-uniform) **and** local verts at ±1 on every axis. `--identity`
exits 3.

**Handling (second axis):** with `export_apply=True`, node.scale is
`(2, 0.5, 1)` (`(sx, sz, sy)` from `(x,y,z)→(x,z,−y)`) and POSITION
bbox stays ±1. Vert count is 8 either way. `--bake` after the
pre-assert exits 4 (node.scale missing, POSITION x ±2).

Same on 4.5 LTS and 5.2 LTS. Not a version split.

No gallery still. A stretched box looks like modeled non-uniform size.

## Run

```bash
blender --background --python unapplied_scale_gltf.py --
blender --background --python unapplied_scale_gltf.py -- --identity
blender --background --python unapplied_scale_gltf.py -- --bake
```
