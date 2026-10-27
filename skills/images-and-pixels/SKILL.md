---
name: images-and-pixels
description: "Create and edit bpy.types.Image pixel buffers from Python: bpy.data.images.new, Image.pixels bulk access with foreach_get/foreach_set, the flat always-RGBA bottom-left-origin layout, byte vs float_buffer storage, colorspace_settings, and saving PNG vs OpenEXR with alpha through Image.save (filepath_raw, file_format) vs Image.save_render (scene render.image_settings). Use when the user writes or reads image pixels, gets TypeError from pixels.foreach_set or foreach_get, sees an image flip upside down, finds pixels changed after Image.save() (source becomes FILE; a float image also drops its buffer), gets a float PNG with dark low-alpha pixels blown to white, an EXR that lost its alpha, or a save_render that ignored image.file_format. Targets 5.2 LTS with 4.5 LTS fallback."
standards-version: 1.10.0
---

# Images and Pixels in Python

## Trigger

Use this skill when the user:

- Creates an image with `bpy.data.images.new` and fills it from code (test cards, masks, lookup textures, bake targets)
- Reads or writes `Image.pixels`, or mentions `foreach_get` / `foreach_set`, `float_buffer`, `is_float`, `channels`
- Hits `TypeError` from `pixels.foreach_set` / `foreach_get` (wrong length: RGB stride, or a buffer sized before `Image.scale()`)
- Sees an image land upside down in the saved file, or pixels that changed after `Image.save()`
- Saves PNG or OpenEXR and loses alpha, gets low-alpha pixels clamped to white, or finds `save_render` wrote a PNG despite `image.file_format = "OPEN_EXR"`

## High-level shape

```python
import bpy

W, H = 512, 288
img = bpy.data.images.new("Card", W, H, alpha=True)  # byte (8-bit) by default

buf = [0.0] * (W * H * 4)              # always RGBA, even with alpha=False
for y in range(H):                     # y = 0 is the BOTTOM row
    for x in range(W):
        i = (y * W + x) * 4
        buf[i:i + 4] = (x / (W - 1), y / (H - 1), 0.0, 1.0)

img.pixels.foreach_set(buf)            # one bulk write, not W*H*4 item sets

got = [0.0] * (W * H * 4)
img.pixels.foreach_get(got)            # one bulk read
```

None of the contracts below diverge between 4.5 LTS and 5.x: the image-pixels and PNG/EXR examples assert identically on both, so no version branch is needed in image code. (If unrelated code in the same script must branch, use the `bpy.app.version` tuple, never `version_string`.)

## Pixel layout

- `Image.pixels` is a **flat, row-major float sequence**, `len == width * height * 4`. Pixel `(x, y)` starts at index `(y * width + x) * 4`.
- It is **always RGBA**: `img.channels == 4` even when created with `alpha=False`. A `foreach_set` with a `W * H * 3` list raises `TypeError` rather than writing.
- The origin is **bottom-left**. PNG stores the top row first, so buffer row 0 is the **last** row of the saved file. Writing a card top-down (row 0 = top) produces a vertically flipped file.
- A `foreach_set` then `foreach_get` round trip reads back the order it wrote, so it cannot detect a flipped layout. Check orientation through a saved file or a known corner pixel.
- `Image.scale(w, h)` **reallocates** the buffer. Resize your Python list afterwards; a `foreach_get` into the old-size list raises `TypeError`.
- Use `foreach_set` / `foreach_get` for whole-buffer work: the testcard writes all 589,824 floats of a 512 x 288 image in one call. Indexing `img.pixels[i]` in a loop is the per-element path to avoid.

## Byte vs float storage

| `images.new(..., float_buffer=)` | `is_float` | Storage | Write/read round trip |
| --- | --- | --- | --- |
| `False` (default) | `False` | 8 bits per channel | error up to 0.5/255, and strictly > 0 for values off the 1/255 grid |
| `True` | `True` | float32 | ~1e-7 |

`pixels` reads and writes Python floats for both; the difference is what survives storage. A byte image keeps steps of 1/255 only.

**Colorspace:** set `img.colorspace_settings.name = "Non-Color"` for data images (masks, normal maps, lookup tables) so values are not treated as color. A default byte image is sRGB; saved to PNG and reloaded it matches the authored values at quantization tolerance. After `bpy.data.images.load(path)`, set the loaded image's colorspace too (the PNG/EXR example sets `"Non-Color"` on both the source and the reload).

**Alpha:** the `pixels` API authors **straight** (unassociated) RGBA. That matters for float PNG, below.

<!-- smoke: run -->
```python
import os
import tempfile
import bpy

W, H = 4, 2
rgb_only = bpy.data.images.new("SmokeRGB", W, H, alpha=False)
assert rgb_only.channels == 4 and len(rgb_only.pixels) == W * H * 4
try:
    rgb_only.pixels.foreach_set([0.0] * (W * H * 3))  # RGB stride
    raise AssertionError("RGB-stride foreach_set was accepted")
except TypeError:
    pass

img = bpy.data.images.new("SmokeCard", W, H, alpha=True)
buf = [0.0, 0.0, 0.0, 1.0] * (W * H)
buf[0:4] = [1.0, 0.25, 0.0, 1.0]           # (0, 0) = bottom-left
img.pixels.foreach_set(buf)
got = [0.0] * (W * H * 4)
img.pixels.foreach_get(got)
assert 0.0 < abs(got[1] - 0.25) <= 0.5 / 255   # 8-bit storage quantizes

img.save_render(os.path.join(tempfile.gettempdir(), "smoke_keep.png"))
assert img.source == "GENERATED"                # save_render keeps the buffer

path = os.path.join(tempfile.gettempdir(), "smoke_card.png")
img.filepath_raw = path
img.file_format = "PNG"
img.save()
assert img.source == "FILE" and img.has_data   # byte image: source flips, buffer kept

back = bpy.data.images.load(path)
px = [0.0] * (W * H * 4)
back.pixels.foreach_get(px)
assert abs(px[0] - 1.0) <= 0.5 / 255 and abs(px[1] - 0.25) <= 0.5 / 255

fimg = bpy.data.images.new("SmokeFloat", W, H, alpha=True, float_buffer=True)
assert fimg.is_float
fimg.pixels.foreach_set([0.1, 0.2, 0.3, 0.4] * (W * H))
fpx = [0.0] * (W * H * 4)
fimg.pixels.foreach_get(fpx)
assert abs(fpx[2] - 0.3) < 1e-6
```

## Saving: `save()` vs `save_render()`

| | `Image.save()` | `Image.save_render(filepath, scene=...)` |
| --- | --- | --- |
| Destination | `img.filepath_raw` | the `filepath` argument |
| Format from | `img.file_format` | the **scene's** `render.image_settings` (`file_format`, `color_mode`) |
| Ignores | the scene's `render.image_settings` | `img.file_format` |
| On a `GENERATED` image | flips `source` to `'FILE'`; a float image also drops its buffer (`has_data` `False`; a byte image keeps it, measured on 4.5.14 and 5.2.1) | `source` stays `'GENERATED'`, buffer untouched |

The `save()` trap, for float images: after it, every `pixels` read re-loads from whatever file is at `filepath_raw` now. The testcard example proves this on a `float_buffer=True` image by overwriting the file with a gray image and reading gray back through the original datablock. Code that writes pixels, calls `save()`, then keeps computing on `pixels` is computing on a decoded file. Use `save_render()` when the in-memory buffer must survive (bake targets, iterative edits), and set the scene's format for the call:

```python
import bpy


def save_keep_buffer(image, filepath, file_format="PNG", scene=None):
    scene = scene or bpy.context.scene
    settings = scene.render.image_settings
    previous = settings.file_format
    settings.file_format = file_format   # image.file_format is ignored here
    try:
        image.save_render(filepath, scene=scene)
    finally:
        settings.file_format = previous
    return filepath
```

For exact value round-trips the PNG/EXR example uses `save()` with `filepath_raw` + `file_format`, so the scene's output settings stay out of the file.

## PNG vs OpenEXR with alpha

Measured with `Image.save()` on Non-Color images:

| Source | Format | Written as | Reload vs authored straight RGBA |
| --- | --- | --- | --- |
| `float_buffer=True` | PNG | RGBA **16-bit** | each channel unpremultiplied as if associated: `min(1, c / a)` then 16-bit. Dark color at alpha 1/255 reloads ~white (RGB error 0.98) |
| `float_buffer=True` | OPEN_EXR | float RGBA | within 1e-5 (measured ~3e-8) |
| `float_buffer=False` | PNG | RGBA **8-bit**, straight | per-channel 8-bit quantization only |

```python
import os
import tempfile
import bpy

img = bpy.data.images.new("Mask", 64, 64, alpha=True, float_buffer=True)
img.colorspace_settings.name = "Non-Color"
img.pixels.foreach_set([0.02, 0.02, 0.02, 1.0 / 255.0] * (64 * 64))

img.filepath_raw = os.path.join(tempfile.gettempdir(), "mask.exr")
img.file_format = "OPEN_EXR"   # float + straight alpha survive
img.save()
```

Rules of thumb: float data with meaningful alpha goes to OpenEXR. If it must be PNG, write it from a byte image (`float_buffer=False`), which stores straight alpha. Through `save_render`, `render.image_settings.color_mode = "RGB"` on OPEN_EXR drops alpha: the file reloads with alpha ~1.0.

## Common AI mistakes

1. **RGB-stride buffers.** `[r, g, b] * (W * H)` passed to `foreach_set` raises `TypeError`. The buffer is RGBA even for `alpha=False`.

2. **Top-left origin.** Indexing `(row_from_top * W + x) * 4` flips the image. Row 0 is the bottom.

3. **Per-element loops over `img.pixels[i]`.** Build a flat list, write it with one `foreach_set`, read with one `foreach_get`.

4. **Stale buffer size after `scale()`.** Recompute `W * H * 4` from the new `img.size` before `foreach_get`.

5. **`save()` then reading `pixels` on a float image.** The buffer is gone; reads come from disk. Use `save_render()` or reload deliberately.

6. **Setting `img.file_format` and calling `save_render()`.** It writes the scene's format (PNG on a default scene). Set `scene.render.image_settings.file_format` instead, and restore it.

7. **Float image saved as PNG with alpha.** Straight `c > a` values are unpremultiplied and clamp to white. Use OpenEXR, or a byte image for PNG.

8. **Expecting byte images to round-trip exactly.** 8-bit storage quantizes to 1/255; use `float_buffer=True` for data that needs precision.

9. **Forgetting colorspace on data images and their reloads.** Set `"Non-Color"` on both the source image and the image returned by `bpy.data.images.load`.

## See also

- Example [`examples/image-pixels-testcard/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/image-pixels-testcard) — always-RGBA layout, bottom-left origin proven through an independently decoded PNG, byte vs float round trip, `scale()` reallocation, the `save()` buffer drop vs `save_render()`.
- Example [`examples/png-exr-alpha/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/png-exr-alpha) — float PNG as RGBA16 with false unpremultiply, EXR float fidelity, byte PNG straight alpha, EXR `color_mode='RGB'` alpha drop.
- Snippet [`snippets/save_baked_image.py`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/snippets/save_baked_image.py) — `save_render` with the scene format set and restored.
- Skill `bake-high-to-low` — saving a baked image without losing it.

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`image-pixels-testcard`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/image-pixels-testcard): The Image pixel-buffer contract — a procedural broadcast test card written into bpy.data.images.new() with one pixels.foreach_set (589,824 floats). Falsify: `--wrong-origin` (exit 13).
- [`png-exr-alpha`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/png-exr-alpha): Float-image PNG save trap — float_buffer=True Image.save() writes RGBA16 and unpremultiplies as if associated-alpha. Falsify: `--opaque-alpha` (exit 5).

<!-- examples:end -->

## References

- `bpy.types.Image`: https://docs.blender.org/api/current/bpy.types.Image.html
- 4.5 LTS `Image`: https://docs.blender.org/api/4.5/bpy.types.Image.html
- `bpy.types.BlendDataImages` (`images.new`, `images.load`): https://docs.blender.org/api/current/bpy.types.BlendDataImages.html
- 4.5 LTS `BlendDataImages`: https://docs.blender.org/api/4.5/bpy.types.BlendDataImages.html
- `bpy.types.ImageFormatSettings` (`render.image_settings`): https://docs.blender.org/api/current/bpy.types.ImageFormatSettings.html
- 4.5 LTS `ImageFormatSettings`: https://docs.blender.org/api/4.5/bpy.types.ImageFormatSettings.html
- `bpy_prop_collection.foreach_get` / `foreach_set`: https://docs.blender.org/api/current/bpy.types.bpy_prop_collection.html
