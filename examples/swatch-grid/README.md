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
resolves `BLENDER_EEVEE` on Blender 5.x and `BLENDER_EEVEE_NEXT` on 4.2–4.5, and the chosen
id is asserted against the running build before rendering — so a regression in that mapping
fails the example, not just the docs.

## Run

```bash
# Default: render with the build's EEVEE engine (needs a GPU/display)
blender --background --python swatch_grid.py -- --output swatch.png

# GPU-less / CI hosts: render the pixels with Cycles (CPU). The EEVEE id is still
# asserted; only the final pixels use Cycles.
blender --background --python swatch_grid.py -- --output swatch.png --engine cycles --samples 16 --width 960
```

The script is deterministic and dependency-light (fixed camera and layout, no HDRI, no
network). It **exits non-zero** on any failure, including a render that comes out uniformly
black or without the expected six distinct swatch regions — the same honest check the CI
smoke gate runs on both Blender 4.5 LTS and 5.1.

## Verified

Runs headless on **Blender 4.5.10 LTS** and **5.1.1**; exercised on both by the
`blender-smoke` workflow on every PR and weekly schedule.
