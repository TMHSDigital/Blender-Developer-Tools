# Viewport overlay with a removable draw handler. Uses gpu, not the bgl module
# removed in 5.x, so it runs unchanged on 4.5 LTS and 5.2.
#
# - Keep the handle draw_handler_add returns: without it the callback cannot be
#   removed, keeps drawing after the add-on is disabled, and doubles on re-enable.
# - POLYLINE_UNIFORM_COLOR is the only way to get a line width (needs the
#   viewportSize and lineWidth uniforms).
# - Restore any GPU state you set; the editor shares it with your callback.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.types.Space.html#bpy.types.Space.draw_handler_add
#   https://docs.blender.org/api/current/gpu.html

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

_handle = None


def draw_line():
    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    batch = batch_for_shader(shader, "LINES", {"pos": [(0, 0, 0), (0, 0, 2)]})
    region = bpy.context.region
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", 3.0)
    shader.uniform_float("color", (1.0, 0.6, 0.1, 0.9))
    gpu.state.blend_set("ALPHA")
    batch.draw(shader)
    gpu.state.blend_set("NONE")


def register():
    global _handle
    if _handle is None:
        _handle = bpy.types.SpaceView3D.draw_handler_add(draw_line, (), "WINDOW", "POST_VIEW")


def unregister():
    global _handle
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, "WINDOW")
        _handle = None
