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

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python gn_instance_grid.py -- --output grid.png
blender --background --python gn_instance_grid.py -- --output grid.png --engine cycles
```

It exits non-zero on failure (wrong carrier, topology mismatch, missing material, or
misplaced corner). The `blender-smoke` workflow runs the check on Blender 4.5 LTS and
5.1.
