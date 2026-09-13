# Swatch Grid

A runnable example that renders a 3×2 grid of spheres — one material per cell — to a single
PNG. It demonstrates the [`procedural-materials-and-shaders`](../../skills/procedural-materials-and-shaders/SKILL.md)
patterns end to end:

- **Principled BSDF** metals (gold, copper: high metallic, low roughness) and dielectrics
  (red/blue plastic, white rough), configured with **string socket lookups** and **4-tuple
  colors**.
- The **emission** pattern (an emissive orange swatch).
- The cross-version **`set_specular` shim** (`Specular` → `Specular IOR Level`, renamed in
  Blender 4.0).

It doubles as a live proof of the **EEVEE engine-id** behavior: the version-branch helper
resolves `BLENDER_EEVEE` on Blender 5.x and `BLENDER_EEVEE_NEXT` on 4.2–4.5, and the check
witnesses the inversion for real — the *other* era's id must be **rejected** by the running
build (assignment raises `TypeError`) and the helper's id accepted — so a regression in
that mapping fails the example, not just the docs.

## Run

```bash
# Cheap correctness check (materials + engine-id witness, no render):
blender --background --python swatch_grid.py --

# Falsifier: same RGB on every swatch. Must exit non-zero.
blender --background --python swatch_grid.py -- --same-base

# Render and pixel-verify with the build's EEVEE engine (needs a GPU/display):
blender --background --python swatch_grid.py -- --output swatch.png

# GPU-less / CI hosts: render the pixels with Cycles (CPU). The EEVEE id is still
# asserted; only the final pixels use Cycles.
blender --background --python swatch_grid.py -- --output swatch.png --engine cycles --samples 16 --width 960
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Distinct swatch colors ≠ 6 (`--same-base` lands here); also render not six distinct regions |
| 4 | `--output` produced no file |
| 5 | Wrong-era EEVEE engine id was accepted |
| 10 | Gallery framing violation |

`--no-verify` was a skip-flag and has been removed. Pixel verification always
runs when `--output` is passed.

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--same-base`.

## Verified

Runs headless on **Blender 4.5.10 LTS** and **5.1.1**; exercised on both by the
`blender-smoke` workflow on every PR and weekly schedule.
The `--output` render path additionally measures framing against the Layer 1 band via `examples/gallery_framing.py` (exit 10 on violation) before writing the still.
