# Damped Track Aim

A runnable example that swings twelve spotlight heads onto one glowing orb with
`Object.constraints.new('DAMPED_TRACK')` — the data-API path, not
`bpy.ops.object.constraint_add` (which needs an active object and fails in
headless loops). Damped Track is the twist-stable aim constraint: it points one
local axis at a target without the roll fights Track To is known for.

Each head is lathed with its lens on local `+Z` and created with an identity
rotation, standing in an open ring at alternating low and high heights. Only the
constraint turns the lenses onto the orb, so heads above it aim down and heads
below it aim up. In the still, every lens facing the orb is the aim.

**What it witnesses:** every lamp head carries exactly one unmuted `DAMPED_TRACK`
bound to the orb on `TRACK_Z`. After a depsgraph update, each evaluated local
`+Z` aligns with the world vector toward the orb (dot ≥ 0.998 ≈ 3.6°). A missing
constraint, a muted one, a `TRACK_TO` stand-in, or a flipped axis fails the
check.

The stands, ball pivots and the orb's pedestal are render-only staging, built after
the check. The ring opens toward the camera so no head hides the orb. The render
path gates framing through `examples/gallery_framing.py` (exit 10) before writing the
still.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python damped_track_aim.py --

# Falsifier: mute every constraint. Must exit non-zero.
blender --background --python damped_track_aim.py -- --mute

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python damped_track_aim.py -- --output aim.png
blender --background --python damped_track_aim.py -- --output aim.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Lamp count ≠ 12 |
| 4 | Lamp does not carry exactly one DAMPED_TRACK |
| 5 | Constraint target is not Orb |
| 6 | `track_axis` is not TRACK_Z |
| 7 | Constraint muted or influence < 1 (`--mute` lands here) |
| 8 | TRACK_TO still present |
| 9 | Evaluated aim dot below 0.998 |
| 10 | Framing gate violation on the `--output` path (`gallery_framing`) |
| 12 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--mute`.
