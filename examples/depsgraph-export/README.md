# Depsgraph-Evaluated Export

A runnable example that proves **modifiers actually ship in exports** and demonstrates the
[`depsgraph-and-evaluated-data`](../../skills/depsgraph-and-evaluated-data/SKILL.md) lifetime
contract. It builds a game controller whose shell is a sparse quad control cage (90 vertices)
under a level-2 `SUBSURF` modifier, with the sticks, d-pad, face buttons and bumpers modeled
as ordinary parts parented to it. It measures every mesh via `evaluated_get().to_mesh()`
(each paired with `to_mesh_clear()`), exports the scene through `wm.obj_export`, and asserts:

- the evaluated shell has exactly the vertex count the Catmull-Clark closed form predicts
  from the cage's own topology — per level `V' = V + E + F`, `E' = 2E + S`, `F' = S`
  (S = face corners) — which for this cage (V=90, E=176, F=88, S=352) is **1,410**;
- the exported OBJ vertex count equals the summed **evaluated** counts of every mesh
  (3,666), not the summed base counts (2,346).

**What it witnesses:** the `evaluated_get` → `to_mesh` → `to_mesh_clear` contract, and that
`wm.obj_export` writes the depsgraph-evaluated geometry (so modifiers are baked into the
export) rather than the unmodified base mesh.

## The render

Left: the shell datablock as the `.blend` stores it — its 90-vertex control cage drawn as
orange wire with a bead on every vertex, over faint blue facets. Right: the same object as the
depsgraph evaluates it and the OBJ contains it — the smooth subdivided cobalt controller with
its controls. If the export shipped the base mesh, the right-hand piece would be the blocky
cage on the left.

Both pieces lean toward the camera on low satin display stands (render-only, added after the
check and export have run).

## Run

```bash
# Cheap correctness check (writes an OBJ to a temp path, asserts the counts) — the CI check:
blender --background --python depsgraph_export.py --

# Falsifier: apply_modifiers=False. Must exit non-zero (export ≠ evaluated).
blender --background --python depsgraph_export.py -- --unevaluated

# Also render a still of cage vs evaluated (EEVEE on a GPU host; cycles on GPU-less hosts):
blender --background --python depsgraph_export.py -- --output depsgraph.png
blender --background --python depsgraph_export.py -- --output depsgraph.png --engine cycles

# Write the exported OBJ to a specific path:
blender --background --python depsgraph_export.py -- --obj exported.obj
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` and `11` are the shared framing and asset-quality helpers.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Evaluated shell did not apply the modifier (evaluated count not above the cage) |
| 4 | No OBJ written |
| 5 | Export vert count ≠ evaluated (`--unevaluated` lands here) |
| 6 | `--output` produced no file |
| 7 | Evaluated shell count ≠ Catmull-Clark closed form |
| 10 | Gallery framing violation |
| 11 | Asset-quality floor violation (render path only) |

`--obj` is a path selector, not a falsifier.

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`, `--obj`, or `--unevaluated`.

The `--output` render path additionally measures framing against the Layer 1 band via
`examples/gallery_framing.py` (exit 10) and the asset-quality floors on the shipped
controller via `examples/gallery_asset_quality.py` (exit 11) before writing the still.
