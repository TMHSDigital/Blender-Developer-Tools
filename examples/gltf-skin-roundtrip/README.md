# glTF Skin Round-Trip

A runnable example that rigs a mech scorpion — 21 bones: a body, a
five-segment tail and stinger, two three-bone claws (arm, hand, movable
finger), eight legs; two-bone blends in the rubber boots at every flexing
joint — exports it with
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

- **The skeleton survives.** `skins[0].joints` names every bone; the
  re-imported armature carries the same 21 bones, the same parent chain,
  and rest matrices within 2.3e-06 — the +Y-up conversion applies to bone
  nodes exactly as it does to meshes, whichever way a bone points (tail
  +Y, claws -Y, legs +/-X).
- **The weights survive.** Every primitive carries JOINTS_0/WEIGHTS_0;
  per-vertex weights on disk sum to 1 (err 3.0e-08; 840 disk vertices carry
  two influences); the re-imported vertex groups match the authored groups
  **bit-exactly** (w_err 0.0), compared as straddle-safe position keys, the
  same protocol as the crate example. Every split copy at a position is
  compared, not just one: the exporter splits vertices per normal, and each
  copy carries its own JOINTS_0/WEIGHTS_0, so one corrupted copy must not
  hide behind a good twin.
- **The deformation survives.** Posed identically, the re-imported rig's
  evaluated mesh matches the original's within 6.0e-07 — linear blend
  skinning through the file format. The comparison is by rest-position key,
  never sorted multisets: the exporter welds duplicate loops (9960 here), so
  cardinalities differ and a naive sorted zip mispairs vertices (a phantom
  2.29 "deviation" measured and fixed during authoring).
- **The mesh must be parented to the armature.** The exporter warns
  "Armature must be the parent of skinned mesh" and picks an armature by
  name otherwise — with two rigs in the file it can bind the wrong one.

**What each check catches on failure:** exporting with `export_skins=False`
(exit 5 — no skin on disk), stripping the weights (exit 4 — no vertex
groups), nudging one re-imported weight (exit 18 — 0.99), moving one
re-imported bone's rest tail 1 mm (exit 14 — 3.9e-03), and posing the
re-imported rig differently (exit 19 — deformation deviates 0.13).

**Straddle-safe keys, for real.** A float32 round-trip can land a
coordinate on the far side of a 1e-4 rounding boundary, so lookups also try
the 26 neighbouring keys. Those neighbours must themselves be rounded:
`0.3601 + 1e-4` in binary floating point is not the key `0.3602`. The first
version of this example added the offset without rounding, so only the
exact key ever matched. It passed by luck until the redesign lowered the
body to z = 0.36, and then it reported a phantom weight loss (exit 18, 1.0).

**Version witness:** the skins pipeline is stable across Blender 4.5 LTS,
5.1 and 5.2 LTS — every measured value matches to the digit on 4.5.11,
5.1.2 and 5.2.1.

The render is a standoff. On the left, the authored scorpion holds the
guard pose the check compares: tail coiled tight over its back, claws
tucked, pincers shut. On the right is the actual re-imported mesh, driven
through its **imported** armature into a different pose: the tail rears
high to strike, the claws are raised and the pincers gape. A file that lost
the skin, the joints, or the weights could not follow that pose. The
rubber boots at the joints bend smoothly and the plates stay rigid, which
is the linear blend skinning surviving the format. The two poses differ on
purpose, so the eye has something to compare. Two identical copies would
render the same whether or not the round-trip worked.

Both rigs are posed by rest-space axes in quaternions, and the yaw is
composed into each armature's world matrix, because the glTF importer
leaves its armature in quaternion mode, where `rotation_euler` does
nothing. Framing is measured by `gallery_framing` (fill 0.856 x, minimum
margin 0.072). The asset floors are measured by `gallery_asset_quality`
(5 materials: hazard paint, gunmetal, chrome, rubber, venom glow; edge90
0.001).

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python gltf_skin_roundtrip.py --

# Falsifier: export_skins=False. Must exit non-zero.
blender --background --python gltf_skin_roundtrip.py -- --no-skins

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python gltf_skin_roundtrip.py -- --output scorp.png
blender --background --python gltf_skin_roundtrip.py -- --output scorp.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Exporter RNA missing expected kwargs |
| 4 | Vertex group count ≠ bone count |
| 5 | Disk skins ≠ 1 (`--no-skins` lands here) |
| 6 | Skin joints ≠ bone names |
| 7 | Missing JOINTS_0/WEIGHTS_0, or accessor length mismatch |
| 8 | Disk weight sums off 1.0 |
| 9 | Disk verts exceed evaluated loops |
| 10 | Armature count after import ≠ 1 |
| 11 | Bone count drifted |
| 12 | Named bone lost |
| 13 | Bone parent drifted |
| 14 | Rest matrices drifted |
| 15 | Skinned mesh count after import ≠ 1 |
| 16 | Re-import vert count ≠ disk |
| 17 | Vertex group names drifted |
| 18 | Weight round-trip drifted |
| 19 | Deformation round-trip drifted |
| 20 | `--output` produced no file |

On the `--output` path only, which runs after every check has passed, 10
also means a `gallery_framing` violation and 11 a `gallery_asset_quality`
floor violation. The shared helpers own those codes, and the log line says
which one fired.

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--no-skins`.

