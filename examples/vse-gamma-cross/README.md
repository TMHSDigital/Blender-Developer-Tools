# VSE GAMMA_CROSS Blend Curve

A runnable follow-up to [`vse-cut-list`](../vse-cut-list/): the check renders
tiny frames across a GAMMA_CROSS between crimson and teal strips and asserts
every sample against the fade's actual math — because AI-generated sequencer
code assumes the cross is the naive linear mix, and it is not.

**What it witnesses:** the fade math and the frame convention behind it.

- **The cross blends in a gamma-0.5 space.** Not `(1-t)·A + t·B` but
  `((1-t)·√A + t·√B)²` — the mid-cross dips below the sRGB lerp. From crimson
  `(0.85, 0.10, 0.22)` and teal `(0.06, 0.75, 0.80)` the midpoint is
  `(0.341, 0.349, 0.463)`: **0.115 darker** on red than the lerp
  `(0.455, 0.425, 0.510)`. The check renders and asserts nine samples
  (t = 0, 1/8, …, 7/8, 31/32) within 5e-3
  (2× the 8-bit quantization step + fit residual; measured 2.93e-3) and that
  the mid lerp deviation is material (≥0.05).
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
expectation (exit 6, deviation 0.1138 at mid), the endpoint-inclusive t
convention (exit 5), and swapped cross inputs (exit 4, `input1=T2`).

**Version witness:** the blend math is identical on Blender 4.5 LTS and 5.1 —
every sample matches to the quantization step. The creation contract from
`vse-cut-list` still gates the timeline: `strips` (never `.sequences`), and
`new_effect` ending in `length=` on 5.x vs `frame_end=` on 4.5.

The render is the bench: the authentic fade as four large emissive panels
(t = 0, 1/4, 1/2, 3/4) above the contrast pair at frame center — the true mid
swatch directly beside the naive lerp mid, the impostor framed in hazard
orange. The gamma dip reads as an adjacency contrast even at card scale: a
naive-lerp cross would make the pair identical, so the still visibly breaks
with the contract.

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
