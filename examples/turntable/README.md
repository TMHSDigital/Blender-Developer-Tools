# Turntable (Slotted Actions)

A runnable example that keyframes a Z-rotation turntable through the **slotted-actions**
cross-version channelbag path from the
[`slotted-actions-animation`](../../skills/slotted-actions-animation/SKILL.md) skill, and
picks the render engine with the version-branch EEVEE-id helper.

**Which fix it witnesses:** the slotted-actions cross-version helper. On Blender 5.x the
channelbag comes from `action_ensure_channelbag_for_slot`; on 4.4/4.5 from
`strip.channelbag(slot, ensure=True)` (legacy `action.fcurves` still works on 4.5, raises
`AttributeError` on 5.x).

## Run

```bash
# Cheap correctness check only (no render) — the CI smoke check:
blender --background --python turntable.py --

# Falsifier: no rotation keys. Must exit non-zero (keys drive playback).
blender --background --python turntable.py -- --no-keys

# Also render one still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python turntable.py -- --output turntable.png
blender --background --python turntable.py -- --output turntable.png --engine cycles
```

By default it runs only the **frame-independent correctness check**: it inserts the rotation
keys, samples the object's Z rotation at frame 1 vs a later frame, and asserts they **differ**
(the keys drive playback). `--output` additionally renders a still; the full animated loop is
a showcase extra, not part of the CI check.

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Rotation keys do not drive playback (`--no-keys` lands here) |
| 4 | `--output` produced no file |
| 5 | Wrong-era EEVEE engine id was accepted |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--no-keys`.
