# VSE GAMMA_CROSS Blend Curve

A runnable follow-up to [`vse-cut-list`](../vse-cut-list/): the check renders
tiny frames across a GAMMA_CROSS between signal-orange and azure strips and
asserts every sample against the fade's actual math — because AI-generated
sequencer code assumes the cross is the naive linear mix, and it is not.

**What it witnesses:** the fade math and the frame convention behind it.

- **The cross blends in a gamma-0.5 space.** Not `(1-t)·A + t·B` but
  `((1-t)·√A + t·√B)²` — the mid-cross dips below the sRGB lerp. The
  endpoints are chosen to make that dip as large as a cross can: orange
  `(1.0, 0.36, 0.0)` and azure `(0.0, 0.16, 1.0)` have per-channel square
  roots summing to 1, so the gamma midpoint is the neutral
  `(0.25, 0.25, 0.25)` while the lerp midpoint is the violet
  `(0.5, 0.26, 0.5)`: **0.25 darker** on red and blue, the per-channel
  maximum. The check renders and asserts nine samples
  (t = 0, 1/8, …, 7/8, 31/32) within 5e-3
  (2× the 8-bit quantization step + fit residual; measured 2.71e-3) and that
  the mid lerp deviation is material (≥0.05; measured 0.250).
- **`t = (frame − start) / duration`, and it never reaches 1 inside the
  effect.** The last frame of the span blends at `(duration−1)/duration`;
  B arrives only when the effect ends. That final frame (frame 32,
  t = 31/32) is one of the nine asserted samples, so the convention is
  pixel-backed end to end. An endpoint-inclusive convention is off by a
  full frame-step (probe: exit 5 at t 0.129 vs 0.125).
- **The pixel witness demands `view_transform = 'Standard'`** — the factory
  default AgX tone-maps the samples and poisons the fit (measured 0.146 on
  the red channel during authoring), the same class of silent failure the
  gallery's render standard exists to prevent. Also caught: deleting a
  consumed input strip orphans-and-deletes the effect (`Strip 'GC' not in
  scene`) — remove effects before their inputs.

**What each check catches on failure:** asserting the naive lerp as the
expectation (exit 6, deviation 0.2490 at mid), the endpoint-inclusive t
convention (exit 5), and swapped cross inputs (exit 4, `input1=T2`).

**Version witness:** the blend math is identical on Blender 4.5 LTS, 5.1 and
5.2 LTS — every sample matches to the quantization step. The creation contract from
`vse-cut-list` still gates the timeline: `strips` (never `.sequences`), and
`new_effect` ending in `length=` on 5.x vs `frame_end=` on 4.5.

The render is the evidence itself, mounted. All 32 frames of the cross are
rendered by the sequencer and laid side by side as a filmstrip: the
GAMMA_CROSS strip on top, and directly beneath it the same two strips
crossed by the sequencer's linear `CROSS` effect, frame for frame. Both
filmstrips are authentic sequencer pixels shown unaltered (closest-texel
sampling, emission only, Standard view) on a hooded grading monitor beside a
three-ball control surface. The gamma strip sinks into a dark neutral valley
at mid-cross where the linear strip passes through violet; three small warm
ticks mark the t = 1/2 column. A GAMMA_CROSS that was really a lerp would
make the two strips identical, so the still visibly breaks with the contract.

Before shooting, the render path guards its own comparison (exit 9): every
frame must fill its tile edge to edge — a 5.2 COLOR strip bakes the scene
size into its width/height at creation, so strips built before the tile
resolution is set letterbox into black bars (probe: in-frame spread 1.0) —
and each strip's mid frame must match its closed form, so the lower strip
really is the lerp (probe: wiring GAMMA_CROSS in its place fails at 0.249).

## Run

```bash
# Correctness check (tiny per-frame sample renders) — the CI check:
blender --background --python vse_gamma_cross.py --

# Falsifier: GC T2 -> T1. Must exit non-zero (inputs).
blender --background --python vse_gamma_cross.py -- --swap-inputs

# Also render the grading-monitor still (EEVEE on a GPU host; cycles on GPU-less):
blender --background --python vse_gamma_cross.py -- --output bench.png
blender --background --python vse_gamma_cross.py -- --output bench.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | GC span off closed form |
| 4 | GC inputs are not T1 → T2 (`--swap-inputs` lands here) |
| 5 | Sample `t` convention drifted |
| 6 | Cross sample off the gamma-0.5 closed form |
| 7 | Mid-cross lerp deviation missing (naive mix) |
| 8 | `--output` produced no file |
| 9 | `--output` filmstrip guard: a frame not uniform, or a strip's mid frame off its closed form |
| 10 | `--output` framing violation (`gallery_framing`) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--swap-inputs`.
