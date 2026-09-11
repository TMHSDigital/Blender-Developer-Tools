# Build a convex hull collision mesh via bmesh.ops.convex_hull.
# Delete geom_interior and geom_unused from the result dict so leftover
# input verts do not remain inside the hull. Copy matrix_world onto
# the collider so it sits on the source object.
#
# bmesh.new() must be paired with bm.free() in try/finally.
#
# Reference:
#   https://docs.blender.org/api/current/bmesh.ops.html#bmesh.ops.convex_hull
#   https://docs.blender.org/api/current/bmesh.html

import bmesh
import bpy


def convex_hull_collider(obj, name=None):
    mesh = bpy.data.meshes.new(name or f"{obj.name}_Collider")
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        result = bmesh.ops.convex_hull(bm, input=bm.verts)
        interior = result.get("geom_interior") or []
        unused = result.get("geom_unused") or []
        if interior:
            bmesh.ops.delete(bm, geom=interior, context="VERTS")
        if unused:
            bmesh.ops.delete(bm, geom=unused, context="VERTS")
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()

    collider = bpy.data.objects.new(name or f"{obj.name}_Collider", mesh)
    bpy.context.scene.collection.objects.link(collider)
    collider.matrix_world = obj.matrix_world.copy()
    return collider


if __name__ == "__main__":
    obj = bpy.context.active_object
    if obj is not None and obj.type == "MESH":
        hull = convex_hull_collider(obj)
        print(f"collider: {hull.name} verts={len(hull.data.vertices)}")
