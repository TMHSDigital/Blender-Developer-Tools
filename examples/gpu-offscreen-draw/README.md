# GPU offscreen draw

Check-only witness for drawing with the `gpu` module, the replacement for
the `bgl` module that 5.x removed. It draws into a `gpu.types.GPUOffScreen`
under `--background` and reads the pixels back. There is no gallery still:
the witness is pixel counts, which a render could show but not prove (same
class as [`eval-mesh-datablock-name`](../eval-mesh-datablock-name/)).

Follows [`gpu-drawing-and-overlays`](../../skills/gpu-drawing-and-overlays/SKILL.md)
and the [`no-bgl`](../../rules/no-bgl.mdc) rule.

**What it witnesses:**

- `gpu.init()` initializes the GPU module "for background use". It is new
  in 5.2. On 5.1 and 4.5 LTS any draw call under `--background` raises
  `SystemError: GPU functions for drawing are not available in background
  mode`, so the example skips there (exit 77).
- A `UNIFORM_COLOR` quad with NDC corners at ±0.5 covers exactly 32 × 32 =
  1024 pixels of a 64 × 64 offscreen.
- A red quad at alpha 0.5 over an opaque blue clear gives a 50/50 mix
  (0.498, 0, 0.502) only with `gpu.state.blend_set('ALPHA')`. Without it the
  draw overwrites the target: (1, 0, 0, 0.498).
- `POLYLINE_UNIFORM_COLOR` with `lineWidth` 6 draws a line 7 px thick
  (one antialiased edge pixel counted). With `lineWidth` 1 it is 2 px.
- `importlib.util.find_spec('bgl')` is `None`: the module is absent on
  5.0.1, 5.1.2 and 5.2.1. It still exists, deprecated, on 4.5.14.

**What failure each check would catch:**

- exit 3 — `gpu.init()` raised: no background drawing on this build
- exit 4 — the opaque quad did not cover the predicted pixels
- exit 5 — the half-alpha draw did not blend (`--skip-blend` lands here)
- exit 6 — the polyline is not `lineWidth` ± 1 px thick (`--thin-line` lands here)
- exit 7 — `bgl` presence differs from the expectation (`--expect-bgl` lands here)

## Who hits this

Add-ons that draw viewport overlays (measurements, guides, debug
visualization) with code from before 4.0, or from models trained on it:
`import bgl`, `bgl.glEnable(bgl.GL_BLEND)`, `bgl.glLineWidth(3)`. On 5.x
the import fails, so the add-on does not register at all. The `gpu`
equivalents are `gpu.state.blend_set('ALPHA')` and a `POLYLINE_*` shader's
`lineWidth` uniform.

## Re-verified

| Measurement | 4.5.14 | 5.0.1 | 5.1.2 | 5.2.1 |
| --- | --- | --- | --- | --- |
| `bgl` importable | yes (deprecated) | no | no | no |
| `gpu.init` exists | no | no | no | yes |
| quad coverage | skip | — | skip | 1024 / 1024 |
| blended centre | skip | — | skip | (0.498, 0, 0.502, 1) |
| polyline thickness, `lineWidth` 6 | skip | — | skip | 7 px |
| default exit | 77 | — | 77 | 0 |
| `--skip-blend` / `--thin-line` / `--expect-bgl` exit | — | — | — | 5 / 6 / 7 |

Measured on Windows (OpenGL backend). CI runs it on Linux under xvfb.

## API reference

- [`gpu`](https://docs.blender.org/api/current/gpu.html) (`gpu.init`, `gpu.state`, `gpu.shader.from_builtin`)
- [`gpu.types.GPUOffScreen`](https://docs.blender.org/api/current/gpu.types.html#gpu.types.GPUOffScreen)
- [`gpu_extras.batch.batch_for_shader`](https://docs.blender.org/api/current/gpu_extras.batch.html)

## Run

```bash
blender --background --python gpu_offscreen_draw.py --
blender --background --python gpu_offscreen_draw.py -- --skip-blend
blender --background --python gpu_offscreen_draw.py -- --thin-line
blender --background --python gpu_offscreen_draw.py -- --expect-bgl
```

## Exit codes

Per-script sequential checks. `77` is the smoke skip protocol, not a product check.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | `gpu.init()` raised under `--background` |
| 4 | Opaque quad pixel coverage wrong |
| 5 | Half-alpha draw did not blend (`--skip-blend`) |
| 6 | Polyline thickness is not `lineWidth` ± 1 (`--thin-line`) |
| 7 | `bgl` presence differs from the expectation (`--expect-bgl`) |
| 77 | Smoke skip: Blender older than 5.2 has no `gpu.init` |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch). It
skips below 5.2 through the catalog's `min_version`. Its catalog falsifiers
are `--skip-blend` (exit 5), `--thin-line` (exit 6) and `--expect-bgl`
(exit 7).
