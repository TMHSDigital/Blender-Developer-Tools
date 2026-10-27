---
name: gpu-drawing-and-overlays
description: "Draw viewport overlays and offscreen images with the gpu module instead of the removed bgl: SpaceView3D.draw_handler_add/remove symmetry, gpu.shader.from_builtin names, gpu_extras.batch.batch_for_shader, gpu.state for blending, depth and line width (POLYLINE shaders), blf text, tag_redraw, and GPUOffScreen with gpu.init() for --background on 5.2. Use when the user wants a viewport overlay, measurement readout, guide lines, debug visualization or an offscreen render from Python, or hits ModuleNotFoundError: No module named 'bgl' or 'GPU functions for drawing are not available in background mode'. Targets 5.2 LTS with 4.5 LTS fallback."
standards-version: 1.10.0
---

# GPU Drawing and Overlays

## Trigger

Use this skill when the user:

- Wants to draw lines, points, shapes or text over the 3D viewport or an image editor from an add-on
- Has add-on code with `import bgl`, `bgl.glEnable`, `bgl.glLineWidth`, or gets `ModuleNotFoundError: No module named 'bgl'` on 5.x
- Wants to render something with the GPU into an image from a script, including headless
- Sees `SystemError: GPU functions for drawing are not available in background mode`

## `bgl` is gone

`bgl` wrapped raw OpenGL calls, which Blender's Metal and Vulkan backends cannot honour. It is deprecated on 4.5 LTS and removed in 5.x. Measured: `importlib.util.find_spec('bgl')` is `None` on 5.0.1, 5.1.2 and 5.2.1, and still present on 4.5.14. Code that imports it does not register on 5.x at all. Everything below uses `gpu`, `gpu_extras` and `blf`, which work on both 4.5 and 5.x, so no version branch is needed for drawing itself. The `no-bgl` rule flags leftovers.

## The overlay pattern: register, draw, unregister

```python
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

_handle = None


def draw_guides():
    obj = bpy.context.active_object
    if obj is None:
        return
    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    origin = obj.matrix_world.translation
    tip = origin + obj.matrix_world.to_3x3().col[2].normalized()
    batch = batch_for_shader(shader, "LINES", {"pos": [origin, tip]})
    region = bpy.context.region
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", 3.0)
    shader.uniform_float("color", (1.0, 0.6, 0.1, 0.9))
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("LESS_EQUAL")
    batch.draw(shader)
    gpu.state.depth_test_set("NONE")
    gpu.state.blend_set("NONE")


def register():
    global _handle
    _handle = bpy.types.SpaceView3D.draw_handler_add(draw_guides, (), "WINDOW", "POST_VIEW")


def unregister():
    global _handle
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, "WINDOW")
        _handle = None
```

- **Keep the handle.** `draw_handler_add` returns it; `draw_handler_remove(handle, region_type)` needs it. A handler added without storing the handle cannot be removed, and it keeps drawing after the add-on is disabled. On re-enable you get two.
- **Remove in `unregister()`,** symmetric with `register()` (see `addon-scaffolding`).
- **`args` is a tuple** passed to the callback: `(self, context)` from a modal operator, `()` for a module-level function.
- **Draw types.** `POST_VIEW` draws in 3D world space under the view matrices (positions are world coordinates). `POST_PIXEL` draws in region pixels with an orthographic matrix (positions are `(x, y)` in pixels, origin bottom-left), which is where text and HUD panels go. `PRE_VIEW` draws under the scene.
- **The callback runs on every redraw** of every 3D viewport. Keep it cheap: build batches from cached data, not by walking `bpy.data`. Guard `context.active_object` against `None` (see `type-annotate-props-and-defend-context`).
- **Nothing redraws by itself.** After your data changes, call `area.tag_redraw()` for the areas that show it, for example from a timer or a depsgraph handler (see `drivers-and-app-handlers`, `timers-modal-and-threading`).
- **Copy-paste version:** [`snippets/gpu-draw-handler.py`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/snippets/gpu-draw-handler.py) is this pattern reduced to one fixed line.

## Builtin shaders

`gpu.shader.from_builtin(name)` takes one of these names on both 4.5 LTS and 5.2:

| Name | Attributes | Uniforms |
| --- | --- | --- |
| `UNIFORM_COLOR` | `pos` | `color` |
| `FLAT_COLOR`, `SMOOTH_COLOR` | `pos`, `color` | — |
| `IMAGE` | `pos`, `texCoord` | `image` |
| `IMAGE_COLOR` | `pos`, `texCoord` | `image`, `color` |
| `POLYLINE_UNIFORM_COLOR` | `pos` | `viewportSize`, `lineWidth`, `color` |
| `POLYLINE_FLAT_COLOR`, `POLYLINE_SMOOTH_COLOR` | `pos`, `color` | `viewportSize`, `lineWidth` |
| `POINT_UNIFORM_COLOR` | `pos` | `color`, `size` |
| `POINT_FLAT_COLOR` | `pos`, `color` | `size` |

5.2 adds `IMAGE_SCENE_LINEAR_TO_REC709_SRGB` and `IMAGE_COLOR_SCENE_LINEAR_TO_REC709_SRGB` for scene-linear images. The `2D_` / `3D_` prefixed names from 2.8–3.x (`2D_UNIFORM_COLOR`, `3D_SMOOTH_COLOR`) are rejected on 5.2: `ValueError: expected a string in ('FLAT_COLOR', 'IMAGE', ...)`. One shader handles 2D and 3D: pass 2-component or 3-component `pos`.

## `gpu.state` replaces the `bgl` state calls

| `bgl` | `gpu` |
| --- | --- |
| `glEnable(GL_BLEND)` / `glDisable(GL_BLEND)` | `gpu.state.blend_set('ALPHA')` / `blend_set('NONE')` |
| `glLineWidth(w)` | a `POLYLINE_*` shader's `lineWidth` and `viewportSize` uniforms |
| `glPointSize(s)` | `POINT_*` shader `size` uniform, or `gpu.state.point_size_set(s)` |
| `glEnable(GL_DEPTH_TEST)`, `glDepthFunc` | `gpu.state.depth_test_set('LESS_EQUAL')`; `'NONE'` to disable |
| `glDepthMask` | `gpu.state.depth_mask_set(True)` |
| `glReadPixels` | `gpu.state.active_framebuffer_get().read_color(x, y, w, h, 4, 0, 'FLOAT')` |
| `bgl.Buffer` | `gpu.types.Buffer` |

Two traps:

- **Blending is off by default.** Measured in [`examples/gpu-offscreen-draw`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/gpu-offscreen-draw): red at alpha 0.5 over opaque blue gives the mix (0.498, 0, 0.502) with `blend_set('ALPHA')`, and overwrites the target with (1, 0, 0, 0.498) without it. An overlay that "ignores alpha" is missing this call.
- **Wide lines need a `POLYLINE_*` shader.** `lineWidth` 6 drew a 7 px line (one antialiased edge pixel); `lineWidth` 1 drew 2 px. `gpu.state.line_width_set` with a non-polyline shader depends on the backend, because core OpenGL, Metal and Vulkan do not guarantee wide-line rasterization. `POLYLINE_*` builds the width in geometry, so it looks the same everywhere. It needs `viewportSize` in pixels: `(region.width, region.height)` in a draw callback, or the offscreen size.

Restore every state you set before returning. Draw callbacks share GPU state with the rest of the editor, so a leftover `blend_set('ALPHA')` or depth test changes how the next overlay draws.

## Text with `blf`

```python
import blf

def draw_label():          # register with draw type "POST_PIXEL"
    font_id = 0            # the default UI font
    blf.size(font_id, 16)  # 4.0+: (fontid, size); the dpi argument is gone
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    blf.position(font_id, 20, 30, 0)   # region pixels, origin bottom-left
    blf.draw(font_id, "Edges: 128")
```

`blf.size(font_id, size, dpi)` from 3.x raises a `TypeError` on 4.0 and later. Measure text with `blf.dimensions(font_id, text)` before laying it out.

## Offscreen: drawing into an image, also headless

```python
import gpu
from gpu_extras.batch import batch_for_shader

if bpy.app.version >= (5, 2, 0):
    gpu.init()          # 5.2+: makes drawing available under --background

off = gpu.types.GPUOffScreen(256, 256)
try:
    with off.bind():
        fb = gpu.state.active_framebuffer_get()
        fb.clear(color=(0.0, 0.0, 0.0, 0.0))
        gpu.matrix.load_identity()          # NDC: -1..1 covers the image
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        batch = batch_for_shader(shader, "TRI_FAN",
                                 {"pos": [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]})
        shader.uniform_float("color", (1.0, 0.0, 0.0, 1.0))
        batch.draw(shader)
        buf = fb.read_color(0, 0, 256, 256, 4, 0, "FLOAT")
finally:
    off.free()
```

- **Headless drawing is new in 5.2.** `gpu.init()` "initializes the GPU module for background use". On 5.1, 5.0 and 4.5 LTS there is no `gpu.init`, and any draw under `--background` raises `SystemError: GPU functions for drawing are not available in background mode`. On those versions, offscreen drawing works only in a session with a window.
- **Let go of GPU objects before exit.** A 5.2.1 probe that called `sys.exit` at module level while its batch, shader and framebuffer were still referenced crashed Blender on shutdown (`EXCEPTION_ACCESS_VIOLATION`, exit 5). The same drawing done inside a function, so those references were gone on return, exited 0. Free the offscreen in a `finally`, and keep the GPU objects local.
- To save the result as an image, copy `buf` into an `Image`'s `pixels` with `foreach_set` (see `use-foreach-set-for-bulk-data`).
- To draw the scene itself into an offscreen in a UI session, use `off.draw_view3d(scene, view_layer, view3d, region, view_matrix, projection_matrix)`.

## Common AI mistakes

| Mistake | Consequence | Do instead |
| --- | --- | --- |
| `import bgl` | Import fails on 5.x; the add-on never registers | `gpu.state`, `POLYLINE_*` shaders |
| `from_builtin('3D_UNIFORM_COLOR')` | `ValueError` on 5.2 | `UNIFORM_COLOR` |
| Not storing the `draw_handler_add` handle | Overlay keeps drawing after disable; doubles on re-enable | Store it, remove it in `unregister()` |
| Expecting alpha without `blend_set` | Transparent colours draw opaque-over | `gpu.state.blend_set('ALPHA')`, then `'NONE'` |
| `line_width_set` for thick lines | Thin lines on core-profile backends | `POLYLINE_*` with `lineWidth` |
| `blf.size(id, size, 72)` | `TypeError` on 4.0+ | `blf.size(id, size)` |
| Drawing under `--background` on 4.5 / 5.1 | `SystemError` | Run with a window, or require 5.2 and call `gpu.init()` |

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`gpu-offscreen-draw`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/gpu-offscreen-draw): Check-only witness for drawing with the `gpu` module, the replacement for the `bgl` module that 5.x removed. Blender 5.2+. Falsify: `--skip-blend` (exit 5).

<!-- examples:end -->

## References

- `gpu`: https://docs.blender.org/api/current/gpu.html ([4.5 LTS](https://docs.blender.org/api/4.5/gpu.html))
- `gpu.shader`: https://docs.blender.org/api/current/gpu.shader.html ([4.5 LTS](https://docs.blender.org/api/4.5/gpu.shader.html))
- `gpu.state`: https://docs.blender.org/api/current/gpu.state.html
- `gpu_extras.batch`: https://docs.blender.org/api/current/gpu_extras.batch.html
- `blf`: https://docs.blender.org/api/current/blf.html
- `SpaceView3D.draw_handler_add`: https://docs.blender.org/api/current/bpy.types.Space.html#bpy.types.Space.draw_handler_add
