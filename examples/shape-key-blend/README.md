# Shape-Key Blend

A runnable example that authors a relative shape key entirely through the data
API — `shape_key_add`, per-vertex `key_blocks["Tall"].data[i].co`, and
`.value` — then reads the blend back from the depsgraph-evaluated mesh. The Tall
key both lifts and flares the top face, so the silhouette is a truncated pyramid.

**What it witnesses:** shape keys do not rewrite `mesh.vertices`. The undeformed
mesh stays at Basis; every evaluated vertex matches the closed-form blend
`co = basis + value × (key − basis)`. The check also asserts the flared top half-extent
(`0.5 + value × flare`) so a uniform-scale mistake cannot pass.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python shape_key_blend.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python shape_key_blend.py -- --output blend.png
blender --background --python shape_key_blend.py -- --output blend.png --engine cycles
```

It exits non-zero on failure (missing keys, wrong value, per-vert blend mismatch, or
flare miss). The `blender-smoke` workflow runs the check on Blender 4.5 LTS and 5.1.
