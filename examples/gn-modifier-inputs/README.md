# GN Modifier Inputs

A runnable example that attaches one Geometry Nodes tree to three cubes and
writes a per-modifier Float **Scale** input through the version-appropriate
API. The tree scales a 1 m cube by that value and lifts it onto the floor.
Evaluated Z-extent must match the written scale (1 / 2 / 3). That is the
closed form: if the write did not land, the three cubes collapse to the
socket default and the extents are no longer distinct.

**What it witnesses:** Blender 5.2 removed ID-property assignment on
`NodesModifier`. `mod["Socket_1"] = 2.0` raises `TypeError` rather than
silently no-opping. 4.5 LTS and 5.1 still require that dict form;
`mod.properties` does not exist there (`AttributeError`). 5.2+ writes
`mod.properties.inputs.Socket_1.value`. After the write, the depsgraph
must be updated or `evaluated_get` still sees the previous scale.

Follows [`geometry-nodes-python`](../../skills/geometry-nodes-python/SKILL.md).

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python gn_modifier_inputs.py --

# Portable falsifier: write 1.0 to every modifier. Must exit non-zero.
blender --background --python gn_modifier_inputs.py -- --same-scale

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
| 3 | Scale input identifier missing on the tree interface |
| 4 | Modifiers do not share one node_group |
| 5 | Version-path write raised (`--api dict` on 5.2, `--api rna` on 4.5) |
| 6 | Version-path read raised |
| 7 | Readback ≠ intended scale (`--same-scale` lands here) |
| 8 | Evaluated Z-extent ≠ intended scale |
| 9 | Evaluated mesh not sitting on z=0 |
| 10 | Gallery framing violation |
| 11 | Evaluated extents not distinct |
| 12 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`, `--same-scale`, or `--api dict`/`rna`.

## Falsification

| Probe | Binary | Result |
| --- | --- | --- |
| `--api dict` | 5.2.1 LTS | exit 5, `TypeError: id properties not supported for this type` |
| `--api rna` | 4.5.11 LTS | exit 5, `AttributeError: 'NodesModifier' object has no attribute 'properties'` |
| `--api auto` | 5.2.1, 5.1.2, 4.5.11 | exit 0, extents 1.000 / 2.000 / 3.000 |
