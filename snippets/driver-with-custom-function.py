# Driver expression calling a custom Python function via driver_namespace.
# Driver expressions block arbitrary Python by default; the namespace is the
# whitelisted escape hatch.
#
# driver_namespace is reset on every file load. A driver that evaluates while
# its function is missing raises NameError and is disabled (is_valid False),
# and stays disabled after the function comes back. So re-register from a
# @persistent load_post handler and re-enable the drivers there.
# See skill: drivers-and-app-handlers.
# Refs: docs.blender.org/api/current/bpy.app.html

import bpy
from bpy.app.handlers import persistent


def smooth_step(t):
    """Smoothstep easing: 3t^2 - 2t^3 clamped to [0, 1]."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def register_driver_function():
    bpy.app.driver_namespace['smooth_step'] = smooth_step


@persistent
def restore_driver_function(_filepath=None):
    register_driver_function()
    for ids in (bpy.data.objects, bpy.data.shape_keys, bpy.data.materials):
        for id_data in ids:
            anim = id_data.animation_data
            for fcurve in (anim.drivers if anim else ()):
                fcurve.driver.is_valid = True


def register():
    register_driver_function()
    bpy.app.handlers.load_post.append(restore_driver_function)


def unregister():
    if restore_driver_function in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(restore_driver_function)
    bpy.app.driver_namespace.pop('smooth_step', None)


def attach_smoothstep_driver(obj, frame_start=1, frame_end=100, peak=5.0):
    """Drive obj.location.z to smoothstep peak across the given frame range."""
    fcurve = obj.driver_add("location", 2)
    fcurve.driver.type = 'SCRIPTED'

    var = fcurve.driver.variables.new()
    var.name = 'frame'
    var.type = 'SINGLE_PROP'
    var.targets[0].id_type = 'SCENE'
    var.targets[0].id = bpy.context.scene
    var.targets[0].data_path = 'frame_current'

    duration = frame_end - frame_start
    fcurve.driver.expression = f'smooth_step((frame - {frame_start}) / {duration}) * {peak}'
    return fcurve
