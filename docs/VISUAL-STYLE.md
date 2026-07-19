# Gallery Visual Style

The spec for every example render that ships in the gallery. New examples must
conform; deviations are defects. Calibration references: `armature-bend`,
`color-attribute-wheel`, `grease-pencil-rosette`, `compositor-glare`,
`damped-track-aim`, `parent-inverse-orrery`.

## The look in one sentence

A dark staged studio — near-black floor and back wall, one shaped warm key, a
warm light pool raking the backdrop — with a saturated hero subject filling
the frame.

## Color management

- `scene.view_settings.view_transform = 'Standard'`, always, with a comment.
  AgX (the 4.x/5.x default) desaturates hero materials toward pastel and
  lifts the stage toward grey — the washed look of the pre-audit gallery
  traces to renders that never set a transform.
- Standard does not compress highlights: tune light energies so nothing
  clips. If a region reads pure white at full size, the key is too hot.

## Stage

- Floor: 30-unit `create_grid` plane. Wall: a copy at `y ≈ 7–9`, rotated 90°
  about X. Both share one Principled material:
  `Base Color (0.03, 0.032, 0.037)`, `Roughness 0.7`.
- World background: `(0.02, 0.021, 0.025)`.
- The floor/wall seam is acceptable only where it falls into shadow; never
  let it cross the subject.

## Lighting (all AREA lights)

- **Key** — warm white `(1.0, 0.96, 0.9)`, upper left, ~`(-4, -5, 6)`,
  size 4–6, 300–700 W depending on subject albedo. It must shape: visible
  falloff across the subject, a readable cast shadow.
- **Fill** — cool `(0.75, 0.85, 1.0)`, low right, size ~9, ~100 W. Just
  enough that shadow sides stay legible; if the image looks flat, the fill
  is too strong.
- **Rim** — cool `(0.6, 0.78, 1.0)`, behind, 200–400 W, to lift silhouettes
  off the backdrop.
- **Wedge** — the signature: warm `(1.0, 0.76, 0.5)`, 200–500 W, size 5–7,
  raking the back wall so a soft pool of light sits behind the subject.
  Place it **between the subject and the wall**. A grazing area light draws
  a hard terminator line across any flat surface it skims — if a stray
  bright band crosses the subject, a light is grazing it.

## Materials

- Hero materials are designed, never Principled defaults: saturated base
  colors, roughness chosen (0.3–0.6 glossy, 0.7+ matte), optional faint
  emission (~0.1) when the subject carries color data that must read exactly.
- Surfaces that display flat color data (attribute fills, pixel buffers) go
  fully matte: `Specular IOR Level = 0`, otherwise the wall/floor horizon
  reflects as a line across the face.

## Framing

- The subject fills roughly 70–90 % of the frame in at least one axis.
  Nothing that matters may touch or cross the frame edge; no featureless
  quadrant of empty wall or floor.
- Camera: 45–55 mm lens, slightly above subject height, aimed with a
  `TRACK_TO` constraint at an empty on the subject — a chosen angle, not the
  default. Flat subjects present toward the camera (lean or tilt them);
  progressions read left to right.
- The image must still read in under a second at thumbnail scale, and it
  must witness the API: if the contract failed, the render should visibly
  break.

## Output

- Render 1280×720 PNG (`taa_render_samples`/`cycles.samples` 32–64).
- Gallery assets: hero webp 1280×720 and preview webp 1200×675, quality 85
  (load the PNG in Blender, `save(filepath=..., quality=85)`, `scale()` for
  the preview — this preserves pixels without re-applying color management).
- After touching any example: `python scripts/build_gallery.py`, and update
  the README gallery-row alt text if the composition changed.
