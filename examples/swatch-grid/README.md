# Swatch Grid

A runnable example that renders a tiered 3×2 material library — one sphere per material, each
seated in a chrome collar on a graphite plinth — to a single PNG. It demonstrates the [`procedural-materials-and-shaders`](../../skills/procedural-materials-and-shaders/SKILL.md)
patterns end to end:

- **Principled BSDF** metals (gold, copper: high metallic, low roughness) and dielectrics
  (red/blue plastic, white rough), configured with **string socket lookups** and **4-tuple
  colors**.
- The **emission** pattern (an emissive orange swatch, its `ShaderNodeEmission` core mixed
  toward a dark dielectric shell at the silhouette so it reads as a glowing globe).
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

## Staging

The swatches stand as a tiered material library on the default stage (floor,
wall at y = 9, warm key, cool fill and rim, warm wedge pooling on the floor
behind the display). Each sphere sits in a gunmetal collar on a bevelled
graphite plinth; the back row stands on tall plinths so every sphere clears
the one in front of it. A 50 mm camera looks down on the display with a
`TRACK_TO` aim, which keeps the floor/wall seam above the back row.

The emissive swatch used to be a bare `Emission` at strength 1.4: under the
Standard view transform its red channel clipped across the whole face and it
rendered as a flat orange disk. Now the same `ShaderNodeEmission` (color and
strength asserted) owns the face toward the camera at strength 0.95, below
clipping, and a `Layer Weight` facing ramp hands it over to a dark dielectric
shell at the silhouette, so the globe has a limb. A shadowless warm point
light at its center stands in for the glow it throws on its own collar,
plinth and the floor; the shell is lit from inside only on back faces, so the
ball itself still shows only the asserted emission.

The world is a reflection-only sky: glossy rays see a warm overhead gradient
above a dark horizon, and camera and diffuse rays see the dark stage. The
mirror-finish gold otherwise reflects the near-black world as a black ball.

`verify_png` samples each swatch where the camera sees it: the sphere center
is projected through the render camera (`world_to_camera_view`) rather than
assumed to sit at the center of a third of the frame, so the six-region check
follows the layout.

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
