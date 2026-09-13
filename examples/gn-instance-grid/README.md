# GN Instance Grid

A runnable example that builds a generative Geometry Nodes tree — Mesh Grid →
Instance on Points → Realize Instances → Transform → Set Shade Smooth — and
attaches it as a `NODES` modifier, following the
[`geometry-nodes-python`](../../skills/geometry-nodes-python/SKILL.md) skill. The
tree has no Group Input: the grid and cube primitives live inside the node group.

**What it witnesses:** instancing is not free geometry until you realize it. The
check asserts the closed-form evaluated topology — verts = grid points × cube
verts (3 × 3 × 8 = 72), faces = 9 × 6 — that a `Set Material` node carries the
lime accent, and that the corner instance center sits at its closed-form grid
coordinate. If Realize Instances is omitted, the evaluated mesh is empty and the
counts fail.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python gn_instance_grid.py --

# Falsifier: 1×1 grid. Must exit non-zero (corner instance missing).
blender --background --python gn_instance_grid.py -- --one-cell

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python gn_instance_grid.py -- --output grid.png
blender --background --python gn_instance_grid.py -- --output grid.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Carrier vertex count ≠ 1 |
| 4 | Corner instance vert count ≠ 8 (`--one-cell` lands here) |
| 5 | Evaluated topology ≠ 72 verts / 54 faces |
| 6 | Set Material did not carry Lime |
| 7 | Corner instance center off the closed-form grid point |
| 8 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--one-cell`.
