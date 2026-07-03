# Shape-Key Blend

A runnable example that authors a relative shape key entirely through the data
API — `shape_key_add`, per-vertex `key_blocks["Tall"].data[i].co`, and
`.value` — then reads the blend back from the depsgraph-evaluated mesh.

**What it witnesses:** shape keys do not rewrite `mesh.vertices`. The undeformed
mesh stays at Basis; the closed-form blend
`co = basis + value × (key − basis)` appears only on the evaluated mesh. The
check asserts key names `Basis`/`Tall`, `Tall.value == 0.5`, undeformed top z
equals the basis half-extent, and evaluated z matches
`[−half, half + value × lift]`.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python shape_key_blend.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python shape_key_blend.py -- --output blend.png
blender --background --python shape_key_blend.py -- --output blend.png --engine cycles
```

It exits non-zero on failure (missing keys, wrong value, or evaluated z mismatch).
The `blender-smoke` workflow runs the check on Blender 4.5 LTS and 5.1.
