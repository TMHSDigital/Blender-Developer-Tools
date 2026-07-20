# glTF Skin Round-Trip

A runnable example that rigs a mech scorpion — seven-bone chain from pedestal
root to stinger, blend rings at every joint seam — exports it with
`bpy.ops.export_scene.gltf` (`export_skins=True`), parses the file, re-imports
it, and verifies the whole skinning contract against the authored rig,
following [`depsgraph-and-evaluated-data`](../../skills/depsgraph-and-evaluated-data/SKILL.md).

**Pipeline arc:** modeling/LOD in [`lod-decimate-chain`](../lod-decimate-chain/),
weighting in [`vertex-weight-limit`](../vertex-weight-limit/), export in
[`gltf-export-roundtrip`](../gltf-export-roundtrip/) — this is the skinning
counterpart to the crate's geometry round-trip. Tangent frames for the normal
maps are in [`triangulate-tangents`](../triangulate-tangents/).

**What it witnesses:** the skinned-mesh export contract the geometry
round-trip left uncovered.

1. **The skeleton survives.** `skins[0].joints` names every bone; the
   re-imported armature carries the same 7 bones, the same parent chain, and
   rest matrices within 2.4e-07 — the +Y-up conversion applies to bone nodes
   exactly as it does to meshes (their translations convert, no rotation is
   written).
2. **The weights survive.** Every primitive carries JOINTS_0/WEIGHTS_0;
   per-vertex weights on disk sum to 1 (err 3.0e-08); the re-imported vertex
   groups match the authored groups **bit-exactly** (w_err 0.0), compared as
   straddle-safe position keys, the same protocol as the crate example.
3. **The deformation survives.** Posed identically, the re-imported rig's
   evaluated mesh matches the original's within 4.8e-07 — linear blend
   skinning through the file format. The comparison is by rest-position key,
   never sorted multisets: the exporter welds duplicate loops (32 here), so
   cardinalities differ and a naive sorted zip mispairs vertices (a phantom
   2.29 "deviation" measured and fixed during authoring).
4. **The mesh must be parented to the armature.** The exporter warns
   "Armature must be the parent of skinned mesh" and picks an armature by
   name otherwise — with two rigs in the file it can bind the wrong one.

**What each check catches on failure:** exporting with `export_skins=False`
(exit 5 — no skin on disk), stripping the weights (exit 4 — no vertex
groups), and posing the re-imported rig differently (exit 19 — deformation
deviates 0.90).

**Version witness:** the skins pipeline is stable between Blender 4.5 LTS and
5.1 — the exporter/importer RNA is byte-identical (probed with
`gltf-export-roundtrip`), and every measured value matches to the digit on
4.5.11 and 5.1.2.

The render stages the authored scorpion beside the actual re-imported one —
same curl, same glowing stinger — proof the skin rode the format through.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python gltf_skin_roundtrip.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python gltf_skin_roundtrip.py -- --output scorp.png
blender --background --python gltf_skin_roundtrip.py -- --output scorp.png --engine cycles
```

It exits non-zero on failure (missing skin, joint drift, weight-sum drift,
skeleton drift, weight excursion, or deformation excursion). The
`blender-smoke` workflow runs the check on Blender 4.5 LTS and 5.1.
