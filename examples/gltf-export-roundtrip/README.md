# glTF Export Round-Trip

A runnable example that builds a sci-fi supply crate — 43 beveled box shells (body, lid with
stiffening ribs, corner armour, carry handles over vent slats, latches, rivets,
a status plate with glowing pips) with three material slots and box-mapped UVs — exports it with
`bpy.ops.export_scene.gltf`, parses the file on disk, re-imports it, and verifies
the whole round-trip against the depsgraph-evaluated mesh, following
[`depsgraph-and-evaluated-data`](../../skills/depsgraph-and-evaluated-data/SKILL.md)
and [`headless-batch-scripting`](../../skills/headless-batch-scripting/SKILL.md).

**Pipeline arc:** modeling/LOD in [`lod-decimate-chain`](../lod-decimate-chain/),
weighting in [`vertex-weight-limit`](../vertex-weight-limit/), export here.

**What it witnesses:** the interchange contracts AI-generated export code most
often gets silently wrong.

- **The +Y-up convention is baked into vertex data.** glTF is +Y-up, Blender is
  +Z-up, and `export_yup=True` (the default) writes `(x, y, z) -> (x, z, -y)`
  directly into the POSITION buffer — the node carries **no** rotation or scale.
  The check parses the `.gltf` JSON and asserts the accessor bounds equal the
  axis-converted evaluated bounding box, and that the node transform is absent.
  Exporting with `export_yup=False` ships raw Z-up data every engine displays
  lying on its back.
- **`export_apply=True` ships the evaluated mesh, not the base cage.** The
  crate's bevel modifier lives only in the depsgraph; with flat shading and UV
  seams the exporter splits exactly one vertex per evaluated loop (9,288), so
  the on-disk POSITION count is an exact witness. `export_apply=False` silently
  writes the 344-vertex cage.
- **The round-trip is faithful.** Re-imported positions (bit-exact here), loop
  normals (≤2e-4), box-mapped UVs (≤3e-5), and per-triangle material bindings
  all match the evaluated mesh. UVs are V-flipped on disk (glTF texture origin
  is top-left) and flipped back on import — both flips are proven by reading
  the `.bin` buffer directly.

**Version witness (probed on Blender 4.5.11 LTS and 5.1.2):** the operator
signatures are byte-identical — 109 exporter properties, 20 importer properties,
same defaults — and the exported JSON differs only in `asset.generator`
("Khronos glTF Blender I/O v4.5.51" vs "v5.1.20"). The example therefore runs
identical kwargs on both versions and guards forward drift explicitly: every
kwarg it passes must still exist in the operator's RNA, so a future rename fails
loudly instead of drifting silently. One genuine 5.x removal surfaced during
authoring: `Mesh.calc_normals()` is gone (loop normals auto-compute on read) —
calling it is itself a cross-version hazard, noted in the code.

Two more authoring hazards are pinned in comments: exact face-plane coincidences
between kit-bashed shells weld loops on export (the count check catches it), and
`read_factory_settings` mid-check frees the original mesh — touching a freed RNA
raises `ReferenceError`, so counts are captured before the wipe.

The render shows **one** crate. The solid crate is the authored one, rebuilt
in place after the check. Laid over it is the actual re-imported mesh — the
file's own triangles — drawn as a thin amber wire cage (a render-only Weld +
Wireframe display stack on the imported object) and masked to the right of a
vertical cut, so the left half reads as the authored asset and the right half
as the file's geometry sitting on it. Neither object is moved: both keep the
identity transform check 13 proved, and the camera does the turning. The cage
lands on every bevel, rivet and vent slat only because the importer undid the
+Y-up bake exactly and the file carried the evaluated (beveled) mesh. If the
axis conversion broke, the cage would be rotated a quarter turn off the solid
crate; a probe that re-applies that quarter turn to the imported object before
rendering drops the cage through the floor and also fails the framing gate
(bottom margin 0.000). If the modifier contract broke, the cage would trace
square corners across the rounded ones.

Presentation only, after every check has run: the authored crate's bevel is
baked into its display mesh (the asset-quality edge measure reads
`Object.data`, which is still the square cage while the bevel lives in the
modifier stack), and its paint and trim get a noise-mottled base colour and
roughness. The exported file only ever carried the flat Principled values.

The render path gates framing through `gallery_framing.check_framing` and the
asset floors through `gallery_asset_quality.check_asset_quality` on the
authored crate. Both helpers' codes (10, 11) are already check codes here, so
the call site remaps them to 22 and 23.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python gltf_export_roundtrip.py --

# Falsifier: export_yup=False. Must exit non-zero (bbox is Z-up on disk).
blender --background --python gltf_export_roundtrip.py -- --no-yup

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python gltf_export_roundtrip.py -- --output crate.png
blender --background --python gltf_export_roundtrip.py -- --output crate.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Exporter/importer RNA kwargs drifted |
| 4 | Base cage drifted from its closed form |
| 5 | Authored UVs drifted from the box-map closed form |
| 6 | Bevel produced no evaluated geometry |
| 7 | On-disk node/mesh/generator contract drifted |
| 8 | On-disk primitive/material binding count drifted |
| 9 | On-disk POSITION bounds ≠ axis-converted bbox (`--no-yup` lands here) |
| 10 | On-disk POSITION count ≠ evaluated loop count |
| 11 | On-disk UV V-flip failed |
| 12 | Re-import did not produce exactly one mesh |
| 13 | Re-imported object carries a transform |
| 14 | Material names drifted on re-import |
| 15 | Re-import vert count ≠ evaluated loop count |
| 16 | Round-trip position drift |
| 17 | Round-trip normal drift |
| 18 | Round-trip UV drift |
| 19 | Re-import triangle count drifted |
| 20 | Per-triangle material bindings drifted |
| 21 | `--output` produced no file |
| 22 | Gallery framing violation (render path only; the helper's 10, remapped) |
| 23 | Gallery asset-quality violation (render path only; the helper's 11, remapped) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--no-yup`.
