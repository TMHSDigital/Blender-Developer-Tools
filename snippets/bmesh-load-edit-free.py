# bmesh load/edit/free pattern.
# bmesh.new() allocates C-side memory that Python's garbage collector
# does not reclaim. Always pair with bm.free() in a try/finally.
#
# (For edit-mode bmeshes from bmesh.from_edit_mesh(), do NOT call
# bm.free(): Blender owns those, and freeing double-frees.)
#
# Reference:
#   https://docs.blender.org/api/current/bmesh.html

import bmesh
import bpy


def raise_z_on_mesh(mesh, amount=0.5):
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        for v in bm.verts:
            v.co.z += amount
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()


if __name__ == "__main__":
    obj = bpy.context.active_object
    if obj is not None and obj.type == 'MESH':
        raise_z_on_mesh(obj.data, amount=0.25)
