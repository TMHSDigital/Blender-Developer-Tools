# Application handler registration with @persistent and proper unregister.
# Without @persistent, the handler is dropped on next file load.
# See skill: drivers-and-app-handlers.
# Refs: docs.blender.org/api/current/bpy.app.handlers.html

import bpy
from bpy.app.handlers import persistent


@persistent
def on_save_pre(filepath, *args):
    """Strip ephemeral cache before save.

    save_pre passes the file path being saved (a string), NOT a Scene -- the
    same is true on 4.5 LTS and 5.x. Reach the scene(s) via bpy.data; never
    treat the first argument as a Scene. Verified on Blender 4.5.10 and 5.1.1.
    """
    for scene in bpy.data.scenes:
        if 'my_addon_cache' in scene:
            del scene['my_addon_cache']


def register():
    if on_save_pre not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(on_save_pre)


def unregister():
    if on_save_pre in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(on_save_pre)
