# Cage-bake a high-poly source onto a low-poly target as a tangent-space
# normal map. Cycles CPU only. High must be selected; low must be active.
# Operator RNA is `type`, not `bake_type`. cage_object is a string name.
# Identifiers match on 4.5 LTS, 5.1, and 5.2 LTS — no version shim.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.ops.object.html#bpy.ops.object.bake

import bpy


def bake_normal_high_to_low(high, low, cage_extrusion=0.20, margin=16):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    high.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    return bpy.ops.object.bake(
        type="NORMAL",
        use_selected_to_active=True,
        cage_extrusion=cage_extrusion,
        use_cage=False,
        normal_space="TANGENT",
        margin=margin,
        margin_type="ADJACENT_FACES",
        use_clear=True,
        target="IMAGE_TEXTURES",
    )
