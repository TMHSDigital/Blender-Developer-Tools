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

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python shader_node_group.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python shader_node_group.py -- --output spheres.png
blender --background --python shader_node_group.py -- --output spheres.png --engine cycles
```

It exits non-zero on failure (missing interface sockets, unshared group, or identical
instance parameters). The `blender-smoke` workflow runs the check on Blender 4.5 LTS and 5.1.
