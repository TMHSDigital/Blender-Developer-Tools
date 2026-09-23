# Driver Wave

A runnable example that drives sixteen column heights from a custom function registered in
`bpy.app.driver_namespace` — the pattern from
[`drivers-and-app-handlers`](../../skills/drivers-and-app-handlers/SKILL.md). Each column
gets a SCRIPTED driver on Z scale whose expression calls `wave_scale(i)`, producing a sine
skyline.

**What it witnesses:** the driver evaluation contract. Driven values appear only after a
view-layer update, and they land in **two** places that must agree: the depsgraph-evaluated
copy (`evaluated_get(dg).scale`) and the original datablock, which the animation system
flushes for display. The check asserts both against the closed-form profile.

Note for real add-ons: `driver_namespace` entries do **not** persist in `.blend` files —
re-register them from a `load_post` handler, or every driver that calls them fails on file
open. Headless, registering before driver creation (as here) is enough.

## Staging

The camera is raised to look down about 18 degrees, so the column tops
and their shadows read as a wave. From nearly level (86 degrees) the
skyline flattened into a bar chart. Render path only.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python driver_wave.py --

# Falsifier: constant 1.0 expression. Must exit non-zero.
blender --background --python driver_wave.py -- --flat-expr

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python driver_wave.py -- --output driver.png
blender --background --python driver_wave.py -- --output driver.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Evaluated Z scale ≠ `wave_scale` (`--flat-expr` lands here) |
| 4 | Original datablock was not flushed |
| 6 | `--output` produced no file |
| 10 | Gallery framing violation |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--flat-expr`.

