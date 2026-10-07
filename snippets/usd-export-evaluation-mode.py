# USD export with evaluation_mode='RENDER' so modifier-applied geometry ships.
# evaluation_mode='VIEWPORT' uses viewport modifier levels (faster, lower quality).
# Refs: docs.blender.org/api/current/bpy.ops.wm.html#bpy.ops.wm.usd_export

import bpy


def export_usd_with_render_evaluation(filepath, selected_only=False):
    bpy.ops.wm.usd_export(
        filepath=filepath,
        evaluation_mode='RENDER',
        selected_objects_only=selected_only,
        export_animation=False,
        export_hair=False,
        export_uvmaps=True,
        export_normals=True,
        export_materials=True,
    )
