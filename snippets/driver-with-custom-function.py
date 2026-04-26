# Driver expression calling a custom Python function via driver_namespace.
# Driver expressions block arbitrary Python by default; the namespace is the
# whitelisted escape hatch.
# See skill: drivers-and-app-handlers.
# Refs: docs.blender.org/api/current/bpy.app.html

import bpy


def smooth_step(t):
    """Smoothstep easing: 3t^2 - 2t^3 clamped to [0, 1]."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def register_driver_function():
    bpy.app.driver_namespace['smooth_step'] = smooth_step


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
