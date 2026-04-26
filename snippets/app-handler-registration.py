# Application handler registration with @persistent and proper unregister.
# Without @persistent, the handler is dropped on next file load.
# See skill: drivers-and-app-handlers.
# Refs: docs.blender.org/api/current/bpy.app.handlers.html

import bpy
from bpy.app.handlers import persistent


@persistent
def on_save_pre(scene, *args):
    """Strip ephemeral cache before save. Signature is defensive against
    the (scene) vs (scene, filepath) variation across 4.x and 5.x."""
    if 'my_addon_cache' in scene:
        del scene['my_addon_cache']


def register():
    if on_save_pre not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(on_save_pre)


def unregister():
    if on_save_pre in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(on_save_pre)
