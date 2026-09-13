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

# Falsifier: Tall.value = 0. Must exit non-zero.
blender --background --python shape_key_blend.py -- --zero-blend

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python shape_key_blend.py -- --output blend.png
blender --background --python shape_key_blend.py -- --output blend.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | No shape keys on mesh |
| 4 | Key names ≠ Basis, Tall |
| 5 | Tall.value ≠ 0.5 (`--zero-blend` lands here) |
| 6 | Undeformed `mesh.vertices` not at Basis |
| 7 | Evaluated vert off closed-form blend |
| 8 | Evaluated Z span off closed form |
| 9 | Top flare off closed form |
| 10 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--zero-blend`.

