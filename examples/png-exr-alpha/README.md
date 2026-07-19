# PNG vs EXR Alpha

A runnable example that witnesses the float-image PNG save trap: a
`float_buffer=True` image saved via `Image.save()` to PNG is written as
**16-bit RGBA** and is **unpremultiplied as if the buffer were
associated-alpha** before storage. The normal `pixels` API authors *straight*
RGBA, so any channel where `c > a` blows past 1.0 and clamps to white —
closed-form RGB error reaches **0.98** for authored `(0.02, 0.02, 0.02)` at
alpha `1/255`. The same buffer saved as OpenEXR round-trips at float
precision. A byte image (`float_buffer=False`) writes **8-bit** PNG with
straight alpha and only pays ordinary quantization.

Found while probing the ROADMAP "image save-format" candidate against live
Blender 5.1 — the hazard is not classic 8-bit premul quantization (float PNG
is 16-bit); it is the false associated-alpha unpremultiply on a straight
buffer. Documented here so the contract cannot quietly drift.

**What it witnesses:**

1. **Float → PNG false unpremul** — `Image.save()` on a Non-Color float image
   writes RGBA16 (`IHDR` bit_depth=16, color_type=6). Reloaded pixels match
   the closed form `q16(min(1, c / q16(a)))` within `2/65535`. Max RGB error
   vs authored on the probe palette is `>= 0.90` (measured **0.98**).
2. **Float → OpenEXR fidelity** — same authored buffer round-trips within
   `1e-5` (measured ~`3e-8`).
3. **Byte → PNG straight alpha** — `float_buffer=False` writes RGBA8; pixels
   match independent per-channel `q8` within `0.5/255`. The stress cell at
   `(0.02, a=1/255)` stays near 0.02, not clamped white.
4. **EXR `color_mode='RGB'` drops alpha** — `save_render` with
   `color_mode='RGB'` reloads opaque alpha (`≈ 1.0`) even when authored
   alpha was `1/255`.

**What each check catches on failure:**

- *RGBA16 IHDR* — float PNG bit-depth or color-type change (falsified
  expectation: 8-bit would exit 4).
- *Error floor* — float PNG path stops destroying straight mid-tones / dark
  values at low alpha (exit 5).
- *Closed-form residual* — encoding no longer matches false-unpremul+clamp
  (falsified once by swapping in the byte straight-alpha model; exited **6**
  with residual **0.9803922**).
- *EXR fidelity* — OpenEXR float RGBA round-trip regressing (exit 7).
- *Byte straight path* — byte images starting to false-unpremul, or bit-depth
  flipping to 16 (exits 9–11).
- *RGB EXR alpha drop* — `color_mode='RGB'` preserving authored alpha (exit 12).

**Version divergence:** none probed on the save/reload contracts above — they
assert on Blender 5.1.1 locally. Blender 4.5 LTS is exercised by the
`blender-smoke` CI job (4.5 is not installed on this authoring host; do not
treat a 4.4 run as a 4.5 substitute). The only version gate in the file is
the EEVEE engine id for the optional render (`BLENDER_EEVEE_NEXT` on 4.x,
`BLENDER_EEVEE` on 5.x).

**Render:** two easel panels. Left bakes the closed-form PNG mangling (dark
rows flash to white at low-alpha columns). Right shows the authored straight
buffer (EXR-clean). If the contract failed, both panels would read the same.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python png_exr_alpha.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python png_exr_alpha.py -- --output alpha.png
blender --background --python png_exr_alpha.py -- --output alpha.png --engine cycles
```

It exits non-zero on failure and prints every measured error and tolerance on
success, so CI logs carry the numbers. The `blender-smoke` workflow runs the
check on Blender 4.5 LTS and 5.1.
