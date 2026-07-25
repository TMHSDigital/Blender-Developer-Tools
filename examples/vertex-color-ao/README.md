# Vertex Colour AO

A runnable example baking **ambient occlusion into a colour attribute** — the
cheap contact shadows an engine gets for free if it reads vertex colour. Unlike
most bakes this one can be checked against a *formula* rather than against a
previous run's numbers: the hemisphere visibility integral has closed forms.

For a point on the floor a distance `d` from an infinitely wide wall of height
`H`, integrating the cosine-weighted hemisphere over the directions the wall
blocks gives (the φ integral collapses to `π / √(1+k²)`):

```
A(k) = ½ (1 − 1/√(1+k²)),   k = H/d        AO = 1 − A(k)
```

`AO` depends only on the ratio `H/d` and increases strictly with `d` — which is
exactly "a concave corner darkens monotonically with depth", as an equation.
For an unoccluded flat surface the integral is exactly **1**.

**The asset, for reuse:** `Well.Stone`, a 2.5 m stone village well — three
courses of 15 masonry blocks each on a 16-slab paved apron, a 15-slab coping
ring, a lined bore, two braced timber posts with a crossbeam, an iron-banded
windlass with a crank, and a hanging bucket. 11 parts, 11 materials, 6966
vertices. Origin at the ground contact centre (`z == 0` is where it rests),
identity transforms, datablocks under `Well.Stone.*`. Every part ships with the
AO baked into two colour attributes, and `default_color_name` points at the
linear one so an engine reads the right channel.

**Pipeline arc neighbours:** attribute domains in
[`attribute-domain-shear`](../attribute-domain-shear/) and
[`color-attribute-wheel`](../color-attribute-wheel/), the second UV set for
*texture*-baked lighting in [`lightmap-uv-channel`](../lightmap-uv-channel/),
topology gates in [`mesh-hygiene-audit`](../mesh-hygiene-audit/).

**What it witnesses** (all closed form or independently re-derived):

- **Analytic AO.** The integrator matches `1 − A(H/d)` at six probe distances
  spanning two decades of `H/d` (60.0 down to 0.60); worst error
  **6.760e-04** against a **2.5e-03** gate.
- **Unoccluded is exactly 1.** An isolated flat plate bakes to
  **1.000000000** — not approximately, exactly, because no ray can self-hit.
- **Monotone with depth.** AO rises strictly across the calibration ruler,
  **0.508301 → 0.928467**.
- **Range and spread.** Every baked value on the asset lies in [0, 1] and the
  bake actually uses the range (measured spread **1.000000**); a silently
  constant bake would pass a bare range check and fails this one.
- **Storage.** `FLOAT_COLOR` round-trips the linear value exactly
  (**0.000e+00**). `BYTE_COLOR` does not — see below.
- **Depsgraph survival.** Both attributes read back off the evaluated mesh at
  deviation **exactly 0.0**, keeping `data_type` and `domain`.
- **Reuse hygiene.** Identity scales, `Well.Stone.*` names, no default
  datablocks, `min z == 0.00e+00`, render colour attribute pinned to `AO`.

## Hazards found while authoring

- **`BYTE_COLOR` is sRGB-encoded 8-bit, not linear 8-bit.** Writing linear
  0.735 reads back **0.7379107**. The round-trip error peaks at **3.782e-03**,
  and the readback matches an independent
  encode → quantise → decode model to **3.189e-07** — so the encoding is
  confirmed, not guessed. Darks get more precision than a linear ramp would
  give and midtones get less. An exporter that hands the raw bytes to an
  engine expecting linear occlusion ships visibly wrong shadows. Store AO in
  `FLOAT_COLOR` unless the target genuinely wants sRGB.
- **`bmesh.ops.bevel` offsets along *cached* face normals.** Moving a vertex
  does not refresh them. While the stale normal is within 90° of the true one
  the bevel merely skews; past 90° it flips sign and grows the solid outward.
  Measured while authoring, on a ring of bevelled boxes placed around a
  circle: the boxes at 0/36/72° bevelled correctly and the one at **108°**
  grew by exactly one offset (**12 mm**) in both z directions, putting geometry
  below the ground plane. `t.normal_update()` before every bevel is the fix,
  and every `_box`/`_prism` here calls it; the hygiene check (exit 8) is what
  caught it.
- **Point-domain AO needs vertices to vary across.** An 8-vertex slab bakes to
  one nearly-constant value per face, so the crevice gradient never reaches
  the attribute. The first draft rendered as flat pale stone with a correct
  bake underneath. Parts are subdivided before the bake for this reason.
- **`color_attributes` enumeration order is not portable** — measured
  `BYTE_COLOR` first on 4.5.11 and `FLOAT_COLOR` first on 5.1.2 for the same
  mesh. Look attributes up by name, never by index.

**What each check catches on failure** (every one probed, with the measured
error): an integrator sampling the full sphere rather than the hemisphere —
AO **0.752686** against a closed form of **0.508332**, error **2.444e-01**
(exit 3); uniform-solid-angle weighting instead of cosine — error **1.202e-02**
(exit 3); rays cast with no normal offset so they self-hit the surface they
start on — unoccluded plate bakes to **0.160644531** instead of 1.0 (exit 4); a
bake collapsed to a constant — spread **0.000000** (exit 5); the sRGB storage
model swapped for naive linear 8-bit quantisation — **4.577e-03** disagreement
with the real readback (exit 6); a Subdivision modifier resampling the
attribute — **3270** evaluated elements against **840** authored (exit 7); a
part sunk below the ground plane — **-1.200e-02** (exit 8); a default `Cube`
datablock name (exit 8).

The exit-7 probe earned its keep twice: the depsgraph check originally compared
`zip(src.data, eva.data)`, which stops at the shorter sequence, so a resampled
attribute reported a clean **0.0** deviation and the probe exited **0**. The
length guard was added because the falsification pass failed to fail.

**Version witness:** check output is byte-identical on Blender 4.5.11 LTS and
5.1.2 — same 6966 vertices, same closed-form errors to every printed digit,
same storage deviations.

**Render as proof:** the well on the dark stage, lit only by the studio rig,
with the baked AO multiplied into base colour — the masonry joints, the shaft
mouth, the coping undersides and the apron contact all darken from the
attribute, not from the lights. The falsification variant (`--falsify`) writes
the same bake **inverted**: sky-facing coping and apron tops go grimy while the
recesses and post bases glow, occlusion turned inside out.

## Run

```bash
blender --background --python vertex_color_ao.py --
blender --background --python vertex_color_ao.py -- --output well.png
blender --background --python vertex_color_ao.py -- --falsify inverted.png
```

Exits non-zero on failure. The `blender-smoke` workflow runs the check on
Blender 4.5 LTS and 5.1 (the calibration rig gets 4096 samples over six
points, the asset a cheap 64, so the whole check is ~1 s). The `--output`
render path additionally gates framing via `examples/gallery_framing.py`
(fill **0.839y**, margins **0.241/0.238/0.072/0.089**, no edge touched) and the
asset floors via `examples/gallery_asset_quality.py` (11 materials, `edge90`
**0.152**, no default names).
