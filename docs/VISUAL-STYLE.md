# Gallery Visual Style

The spec for every example render that ships in the gallery.

This document has two layers. **House identity** is mandatory for every render
without exception — a render that violates it is a defect. The **default stage**
is the presumption: use it unless the example's own API contract requires
otherwise, and when it does, state the reason in one line in the example README.
A stage deviation without a stated reason is a defect; a stage deviation with one
is normal.

The canonical contact-sheet calibration set lives in `CLAUDE.md` §&nbsp;Quality
Gates for Example Runs. Do not restate its membership here.

## The look in one sentence

A dark staged studio — near-black floor and back wall, one shaped warm key, a
warm light pool raking the backdrop — with a saturated hero subject filling
the frame.

---

# Layer 1 — House identity (mandatory)

These hold for every render in the gallery, including examples that deviate from
the default stage.

## Color management

- `scene.view_settings.view_transform = 'Standard'`, always, with a comment.
  AgX (the 4.x/5.x default) desaturates hero materials toward pastel and
  lifts the stage toward grey — the washed look of the pre-audit gallery
  traces to renders that never set a transform.
- Standard does not compress highlights: tune light energies so nothing
  clips. If a region reads pure white at full size, the key is too hot.
  (Exception: a subject whose contract *is* a blown or clamped value —
  see Deviations — must still confine the clipping to the witnessed region.)

## Materials

- Hero materials are designed, never Principled defaults: saturated base
  colors, roughness chosen (0.3–0.6 glossy, 0.7+ matte), optional faint
  emission (~0.1) when the subject carries color data that must read exactly.
- Surfaces that display flat color data (attribute fills, pixel buffers) go
  fully matte: `Specular IOR Level = 0`, otherwise the wall/floor horizon
  reflects as a line across the face.
- Nothing in frame may read as programmer art. Subjects are modeled with
  intent, not primitives with modifiers.

## Framing and camera

- The subject fills roughly 70–90 % of the frame in at least one axis.
  Nothing that matters may touch or cross the frame edge.
- Camera: a chosen angle, not the default — typically a 45–55 mm lens,
  slightly above subject height, aimed with a `TRACK_TO` constraint at an
  empty on the subject. Flat subjects present toward the camera (lean or
  tilt them); progressions read left to right.
- No visible helper objects, light shapes, tracking empties, or backdrop
  seams crossing the subject.

## The render is the proof

- The image must read in under a second at thumbnail scale.
- The image must witness the API: if the contract failed, the render should
  visibly break. If the render would look the same whether the code worked or
  not, the scene design is wrong, not merely unpolished.
- Presentation may be staged; evidence may not. When the witnessed artifact
  is itself an image (a sequencer frame, a pixel buffer, a baked texture),
  the authentic pixels must appear unaltered — mount them in the scene
  (`vse-cut-list` on a monitor, `image-pixels-testcard` on a TV) rather than
  recreating them.

## Output

- Render 1280×720 PNG (`taa_render_samples`/`cycles.samples` 32–64).
- Gallery assets: hero webp 1280×720 and preview webp 1200×675, quality 85
  (load the PNG in Blender, `save(filepath=..., quality=85)`, `scale()` for
  the preview — this preserves pixels without re-applying color management).
- After touching any example: `python scripts/build_gallery.py`, and update
  the README gallery-row alt text if the composition changed.

---

# Layer 2 — Default stage (the presumption)

Use this unless the contract requires otherwise. It is what makes the gallery
read as one body of work, and the great majority of examples should use it
unmodified.

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

---

# Deviations

Some contracts cannot be witnessed on the default stage. The stage is a
presumption, not a cage: when the subject of the example *is* the lighting, the
world, the atmosphere, or the camera itself, the default stage would hide the
very thing being proven.

**When a deviation is legitimate.** The contract requires it. Examples:

- **Lighting contracts** (light linking, shadow-catcher, light groups) — the
  arrangement of lights is the evidence; the fixed four-light rig pre-empts it.
- **World / sky contracts** (sky texture, sun elevation, HDRI mapping, world
  node trees) — the near-black world value is the thing under test.
- **Volumetric contracts** (scatter density, god rays, absorption) — a
  near-black stage swallows the phenomenon.
- **Camera contracts** (depth of field, focus distance, motion blur, sensor
  fit) — these need depth and background content the default framing avoids.
- **Non-photoreal contracts** (Freestyle, line art, flat NPR shading) — a
  raking key fights the flat readable field the technique produces.
- **Clamping / exposure contracts** — where a blown or clamped value is
  precisely what the check asserts.

**What a deviation must still satisfy.** Everything in Layer 1, without
exception: Standard view transform, designed materials, chosen camera,
70–90 % subject fill, no visible helpers, thumbnail legibility, render-as-proof,
authentic evidence, and the output pipeline. Deviate from the stage, never from
the identity.

**What a deviation must not be.** A deviation is not permission to skip staging
effort. "The default stage did not suit this" is not a reason; "this example
witnesses sun elevation, so the world background carries a sky texture" is.
Lighting a deviating scene is *more* work than using the rig, not less — the
scene still needs a designed key, deliberate falloff, and a background that was
chosen rather than defaulted.

**Documenting it.** One line in the example README under a `Stage deviation`
heading: what changed, and which contract required it. One line in the PR body.
That is the whole ceremony.

**The contact-sheet gate under deviation.** The gate still applies and the
composite is still committed. The pass condition is unchanged in substance —
the candidate must not be sortable as belonging to a *different gallery* — but
judge it on materials, framing, finish, view transform, and thumbnail legibility
rather than backdrop match. Report mean luminance against the calibration set as
*information*, not as a pass/fail criterion, and say in the verdict that the
example deviates and why. A bright sky-texture render can hold the lineup; a
carelessly lit one cannot, and the sheet is how you tell them apart.