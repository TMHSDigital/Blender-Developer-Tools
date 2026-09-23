# Shader Node Group

A runnable example that declares a reusable `TintedGloss` shader group through
`tree.interface.new_socket` — the 4.x/5.x API that replaced `tree.inputs`/`tree.outputs` —
and instances it in two materials with different parameters, following
[`procedural-materials-and-shaders`](../../skills/procedural-materials-and-shaders/SKILL.md)
and the [`shader-node-group`](../../snippets/shader-node-group.py) snippet.

**What it witnesses:** the grouping contract. Sockets declared on the interface appear on
every group-node instance; both materials share ONE group datablock (`users == 2`); and the
per-material Tint lives on the group **node**, not inside the group — set it inside the tree
and every material changes at once. The render is the proof: two spheres, one group, two
colors.

## Staging

The still renders under the Standard view transform on the dark house
stage; it had no view transform set, so AgX washed both tints toward
pastel over a lighter floor. The key is larger and softer (the glossy
spheres had mirrored it as a hard white square), and the camera aims
at the sphere centres. Render path only.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python shader_node_group.py --

# Falsifier: identical instance Tints. Must exit non-zero.
blender --background --python shader_node_group.py -- --same-tint

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python shader_node_group.py -- --output spheres.png
blender --background --python shader_node_group.py -- --output spheres.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Interface sockets missing Tint / Roughness / Shader |
| 4 | Group datablock `users` ≠ 2 |
| 5 | Instance points at a different node tree |
| 6 | Instance Tint values identical (`--same-tint` lands here) |
| 7 | `--output` produced no file |
| 10 | Gallery framing violation |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--same-tint`.
