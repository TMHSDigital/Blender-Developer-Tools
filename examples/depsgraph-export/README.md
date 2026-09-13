# Depsgraph-Evaluated Export

A runnable example that proves **modifiers actually ship in exports** and demonstrates the
[`depsgraph-and-evaluated-data`](../../skills/depsgraph-and-evaluated-data/SKILL.md) lifetime
contract. It builds a cube with a SUBSURF modifier, measures the evaluated mesh via
`evaluated_get().to_mesh()` (paired with `to_mesh_clear()`), exports through `wm.obj_export`,
and asserts the exported vertex count equals the **evaluated** (modifier-applied) count and is
strictly greater than the base mesh.

**What it witnesses:** the `evaluated_get` → `to_mesh` → `to_mesh_clear` contract, and that
`wm.obj_export` writes the depsgraph-evaluated geometry (so modifiers are baked into the
export) rather than the unmodified base mesh.

## Run

```bash
# Cheap correctness check (writes an OBJ to a temp path, asserts the counts) — the CI check:
blender --background --python depsgraph_export.py --

# Falsifier: apply_modifiers=False. Must exit non-zero (export ≠ evaluated).
blender --background --python depsgraph_export.py -- --unevaluated

# Also render a still of base vs evaluated (EEVEE on a GPU host; cycles on GPU-less hosts):
blender --background --python depsgraph_export.py -- --output depsgraph.png
blender --background --python depsgraph_export.py -- --output depsgraph.png --engine cycles

# Write the exported OBJ to a specific path:
blender --background --python depsgraph_export.py -- --obj exported.obj
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Evaluated mesh did not apply the modifier |
| 4 | No OBJ written |
| 5 | Export vert count ≠ evaluated (`--unevaluated` lands here) |
| 6 | `--output` produced no file |
| 10 | Gallery framing violation |

`--obj` is a path selector, not a falsifier.

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`, `--obj`, or `--unevaluated`.


The `--output` render path additionally measures framing against the Layer 1 band via `examples/gallery_framing.py` (exit 10 on violation) before writing the still.
