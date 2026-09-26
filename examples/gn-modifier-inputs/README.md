# GN Modifier Inputs

A runnable example that attaches one Geometry Nodes tree to three carrier
objects and writes a per-modifier Float **Height** input through the
version-appropriate API. The tree is a parametric spiral staircase: from
Height it derives the step count (`round((Height - 0.3) / 0.1)`), instances
the carrier mesh — one bevelled oak tread with its brass baluster — up a
helix at 22.5° per step, and adds a teal newel post and a brass helical
handrail. Written heights 1 / 2 / 3 m give 7 / 17 / 27 treads, so the
three staircases read left to right as one design at three settings of one
input.

The closed form: the newel post runs from the floor at z=0 to exactly
z=Height and every other part stays inside that span, so the evaluated
Z-extent must equal the written height. If a write did not land, that
staircase falls back to the socket default (1 m, 7 treads) and the extents
are no longer distinct — in the render, the tall staircases collapse to
copies of the short one.

**What it witnesses:** Blender 5.2 removed ID-property assignment on
`NodesModifier`. `mod["Socket_1"] = 2.0` raises `TypeError` rather than
silently no-opping. 4.5 LTS and 5.1 still require that dict form;
`mod.properties` does not exist there (`AttributeError`). 5.2+ writes
`mod.properties.inputs.Socket_1.value`. After the write, the depsgraph
must be updated or `evaluated_get` still sees the previous height.

Follows [`geometry-nodes-python`](../../skills/geometry-nodes-python/SKILL.md).

Staging: the default dark studio. The three staircases stand on 1.62 m
centres (`XS`); the check reads only each object's evaluated Z extent and
zmin, never X, so the layout is free. All three share one tree and one set
of materials — the only thing that differs between them is the modifier
input. The key carries a 36° spread so its pool stays on the stairs, and
the rim sits high behind them so it does not wash the foreground floor.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python gn_modifier_inputs.py --

# Portable falsifier: write 1.0 to every modifier. Must exit non-zero.
# (--same-scale is kept as an alias for the pre-staircase flag name.)
blender --background --python gn_modifier_inputs.py -- --same-height

# Force one side of the split (must fail on the other series, not all three):
blender --background --python gn_modifier_inputs.py -- --api dict
blender --background --python gn_modifier_inputs.py -- --api rna

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python gn_modifier_inputs.py -- --output stairs.png
blender --background --python gn_modifier_inputs.py -- --output stairs.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Height input identifier missing on the tree interface |
| 4 | Modifiers do not share one node_group |
| 5 | Version-path write raised (`--api dict` on 5.2, `--api rna` on 4.5) |
| 6 | Version-path read raised |
| 7 | Readback ≠ intended height (`--same-height` lands here) |
| 8 | Evaluated Z-extent ≠ intended height |
| 9 | Evaluated mesh not sitting on z=0 |
| 10 | Gallery framing violation |
| 11 | Evaluated extents not distinct |
| 12 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`, `--same-height`, or `--api dict`/`rna`.

## Falsification

| Probe | Binary | Result |
| --- | --- | --- |
| `--api dict` | 5.2.1 LTS | exit 5, `TypeError: id properties not supported for this type` |
| `--api rna` | 4.5.11 LTS | exit 5, `AttributeError: 'NodesModifier' object has no attribute 'properties'` |
| `--api dict` | 5.1.2 | exit 0 (5.1 still takes the dict form) |
| `--api rna` | 5.1.2 | exit 5, `AttributeError: 'NodesModifier' object has no attribute 'properties'` |
| `--same-height` | 5.2.1, 5.1.2, 4.5.11 | exit 7, `readback 1.0 != written 2.0 on SpiralStair.H2` |
| `RAIL_H = -0.5` (treads climb past the post) | 5.2.1, 4.5.11 | exit 8, `evaluated Z-extent 1.934334 != height 1.0` |
| `--api auto` | 5.2.1, 5.1.2, 4.5.11 | exit 0, extents 1.000 / 2.000 / 3.000 |
