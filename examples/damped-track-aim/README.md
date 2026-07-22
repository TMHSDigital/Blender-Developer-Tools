# Damped Track Aim

A runnable example that aims twelve brass spikes at an ember core with
`Object.constraints.new('DAMPED_TRACK')` — the data-API path, not
`bpy.ops.object.constraint_add` (which needs an active object and fails in
headless loops). Damped Track is the twist-stable aim constraint: it points one
local axis at a target without the roll fights Track To is known for.

**What it witnesses:** every spike carries exactly one unmuted `DAMPED_TRACK`
bound to the core on `TRACK_Z`. After a depsgraph update, each evaluated local
`+Z` aligns with the world vector toward the core (dot ≥ 0.998 ≈ 3.6°). A missing
constraint, a muted one, a `TRACK_TO` stand-in, or a flipped axis fails the
check.

## Framing deviation

Radiating composition — the twelve spikes read as converging on the core from
beyond the frame, so their tails bleed past the left, right, and bottom edges
by design (measured fill 1.000x/0.917y with edge touch on three sides). If
wired to `examples/gallery_framing.py`, call it with
`deviation="radiating composition; spikes read as extending past frame"`.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python damped_track_aim.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python damped_track_aim.py -- --output aim.png
blender --background --python damped_track_aim.py -- --output aim.png --engine cycles
```

It exits non-zero on failure (wrong constraint type/target/axis, or evaluated
aim outside the angular epsilon). The `blender-smoke` workflow runs the check
on Blender 4.5 LTS and 5.1.
