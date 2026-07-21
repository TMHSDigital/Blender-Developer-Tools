# VSE GAMMA_CROSS Blend Curve

A runnable follow-up to [`vse-cut-list`](../vse-cut-list/): the check renders
tiny frames across a GAMMA_CROSS between crimson and teal strips and asserts
every sample against the fade's actual math — because AI-generated sequencer
code assumes the cross is the naive linear mix, and it is not.

**What it witnesses:** the fade math and the frame convention behind it.

1. **The cross blends in a gamma-0.5 space.** Not `(1-t)·A + t·B` but
   `((1-t)·√A + t·√B)²` — the mid-cross dips below the sRGB lerp. From crimson
   `(0.85, 0.10, 0.22)` and teal `(0.06, 0.75, 0.80)` the midpoint is
   `(0.341, 0.349, 0.463)`: **0.115 darker** on red than the lerp
   `(0.455, 0.425, 0.510)`. The check asserts every sample within 5e-3
   (2× the 8-bit quantization step + fit residual; measured 2.93e-3) and that
   the mid lerp deviation is material (≥0.05).
2. **`t = (frame − start) / duration`, and it never reaches 1 inside the
   effect.** The last frame of the span blends at `(duration−1)/duration`;
   B arrives only when the effect ends. An endpoint-inclusive convention is
   off by a full frame-step (probe: exit 5 at t 0.129 vs 0.125).
3. **The pixel witness demands `view_transform = 'Standard'`** — the factory
   default AgX tone-maps the samples and poisons the fit (measured 0.146 on
   the red channel during authoring), the same class of silent failure the
   gallery's render standard exists to prevent. Also caught: deleting a
   consumed input strip orphans-and-deletes the effect (`Strip 'GC' not in
   scene`) — remove effects before their inputs.

**What each check catches on failure:** asserting the naive lerp as the
expectation (exit 6, deviation 0.1138 at mid), the endpoint-inclusive t
convention (exit 5), and swapped cross inputs (exit 4, `input1=T2`).

**Version witness:** the blend math is identical on Blender 4.5 LTS and 5.1 —
every sample matches to the quantization step. The creation contract from
`vse-cut-list` still gates the timeline: `strips` (never `.sequences`), and
`new_effect` ending in `length=` on 5.x vs `frame_end=` on 4.5.

The render is a mixing bench: the eight authentic cross samples as emissive
panels fading crimson to teal, with the naive lerp midpoint framed in hazard
orange below — visibly brighter than the true mid, the gamma dip made visible.

## Run

```bash
# Correctness check (tiny per-frame sample renders) — the CI check:
blender --background --python vse_gamma_cross.py --

# Also render the mixing bench still (EEVEE on a GPU host; cycles on GPU-less):
blender --background --python vse_gamma_cross.py -- --output bench.png
blender --background --python vse_gamma_cross.py -- --output bench.png --engine cycles
```

It exits non-zero on failure (span drift, wrong inputs, t-convention drift,
a sample off the closed form, or a missing gamma dip). The `blender-smoke`
workflow runs the check on Blender 4.5 LTS and 5.1.
