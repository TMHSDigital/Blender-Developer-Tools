# GN Instance Grid

A runnable example that builds a generative Geometry Nodes tree — Mesh Grid →
Instance on Points → Realize Instances → Transform → Set Shade Smooth → Set
Material — and attaches it as a `NODES` modifier, following the
[`geometry-nodes-python`](../../skills/geometry-nodes-python/SKILL.md) skill. The
tree has no Group Input: the grid lives inside the node group, and the instance
is a modeled DSA-profile keycap read in through an `Object Info` node (original
transform space). The realized grid is the key field of a 3x3 macropad.

**What it witnesses:** instancing is not free geometry until you realize it. The
check asserts the closed-form evaluated topology — verts = grid points × keycap
verts (9 × 121 = 1089), faces = 9 × 121 = 1089 — where the keycap counts come
from its construction parameters (six rounded-rectangle rings of
4 × (4 + 1) = 20 verts, plus the dish centre; five ring-to-ring quad bands, a
20-triangle dish fan and one bottom n-gon), not from measuring the mesh. It
also asserts that the (+x, +y) corner cell holds exactly one keycap, centred on
its closed-form grid point with its foot at the Transform lift, that `Set
Material` carries `Keycap.PBT`, and that a second `Set Material`, selected by a
per-face position field, puts `Keycap.Accent` on exactly one keycap at the
front-right grid point. If Realize Instances is bypassed, the evaluated mesh is
empty and the count gate fails.

**What the render shows:** nine identical keycaps, one per grid point, seated on
switch housings in the recessed well of an anodized case, and the one orange
"enter" key the position-field selection picked out. The count gate is numeric:
an unrealized grid renders the same keycaps, because the renderer draws
instances either way. What does show is the grid itself — `--one-cell` renders
a single keycap in the centre of an empty well — and where the accent
selection landed. The knob, OLED, case and switch housings are render-only
staging built in bmesh; only the key field comes from the tree.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python gn_instance_grid.py --

# Falsifier: 1×1 grid. Must exit non-zero (4: eight keycaps missing).
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
| 4 | Evaluated topology ≠ 1089 verts / 1089 faces (`--one-cell` lands here) |
| 5 | Corner grid cell does not hold exactly one keycap (121 verts) |
| 6 | Set Material did not carry `Keycap.PBT` and `Keycap.Accent` |
| 7 | Corner keycap off its closed-form grid point or lift |
| 8 | `--output` produced no file |
| 9 | Accent selection did not cover exactly one keycap at the front-right point |
| 10 | Render path: Layer 1 framing violation (`gallery_framing`) |
| 11 | Render path: asset-quality floor violation (`gallery_asset_quality`) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--one-cell`.
