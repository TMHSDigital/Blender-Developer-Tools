# Image Pixels Test Card

A runnable example that writes a procedural broadcast test card — seven neon bars, a
luminance ramp, a PLUGE row with a bottom-left origin marker, and the classic circle —
into a `bpy.data.images.new()` datablock with **one** `pixels.foreach_set()` call
(512 × 288 × 4 = 589,824 floats), then renders it on an emissive studio monitor.

**What it witnesses:** the `bpy.types.Image` pixel-buffer contract. `Image.pixels` is a
flat, row-major, bottom-left-origin float buffer that is *always* RGBA: `channels == 4`
and `len(pixels) == width × height × 4` even when the image is created with
`alpha=False`, so an RGB-stride `foreach_set` raises `TypeError` instead of writing.
A byte image (the default) stores 8 bits per channel — every written float round-trips
with error ≤ 0.5/255 **and strictly > 0** (an exact round-trip would mean storage is
not 8-bit); `float_buffer=True` stores float32 and round-trips at ~1e-7. `Image.scale()`
reallocates the buffer, so a `foreach_get` into a stale-size list raises `TypeError`
rather than silently shearing rows.

**The `save()` trap** (found while authoring — identical on 4.5 LTS and 5.1):
`Image.save()` on a `GENERATED` image silently flips `source` to `'FILE'` and drops the
in-memory buffer (`has_data` becomes `False`). Every later `pixels` read re-loads from
whatever currently sits at `filepath_raw`. The check proves it by overwriting the file
with a flat-gray imposter image *after* `save()` and reading the imposter's pixels back
through the original datablock. `save_render()` writes the same PNG but is
non-destructive: `source` stays `'GENERATED'` and the buffer stays exact. Scripts that
write pixels, `save()`, then keep computing on `pixels` are silently computing on a
decoded PNG.

**What each check catches on failure:**

- *Buffer geometry* — an API change to per-image channel counts, or code assuming an
  RGB stride (falsified: a `W*H*3` write raises and the check exits 3).
- *Byte/float round-trip vs the closed-form card* — any stride, orientation, or
  packing bug in the bulk path; a one-pixel shift was deliberately introduced once and
  the check exited 4 with measured error 0.97 against tolerance 0.00196.
- *Quantization floor* — `byte_err > 0` proves 8-bit storage really quantizes;
  byte and float images swapping behavior cannot hide.
- *Reallocation* — `scale()` no longer reallocating (stale-size read succeeding).
- *save() lifecycle* — the source-flip/buffer-drop behavior changing (falsified:
  substituting `save_render()` for `save()` exits 7 because `source` stays
  `GENERATED`).
- *Disk round-trip* — a byte sRGB image saved to PNG and reloaded must match at
  quantization tolerance.

**Version divergence:** none — every contract above, including the `save()` trap,
was probed and asserts identically on Blender 4.5.11 LTS and 5.1.2. The only gate in
the file is the EEVEE engine id for the optional render (`BLENDER_EEVEE_NEXT` on 4.x,
`BLENDER_EEVEE` on 5.x).

**Render hazard worth knowing:** a bmesh-built plane has no UV map, and
`bmesh.ops.create_grid(..., calc_uvs=True)` silently creates none unless a UV layer
already exists — without one, an Image Texture samples texel (0,0) for every fragment
and the screen renders as one flat color. The render path creates the layer explicitly.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python image_pixels_testcard.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python image_pixels_testcard.py -- --output card.png
blender --background --python image_pixels_testcard.py -- --output card.png --engine cycles
```

It exits non-zero on failure and prints every measured error and tolerance on success,
so CI logs carry the numbers. The `blender-smoke` workflow runs the check on Blender
4.5 LTS and 5.1. In the render, `Closest` interpolation keeps the pixel grid honest —
the jagged circle edge is the 512 × 288 buffer itself, and the white marker in the
PLUGE row sits at the bottom-left because that is where pixel (0, 0) lives.
