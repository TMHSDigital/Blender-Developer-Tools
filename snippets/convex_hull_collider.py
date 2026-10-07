# Build a convex hull collision mesh via bmesh.ops.convex_hull.
# Strip the source edges/faces first: the op adds hull triangles but keeps
# source faces lying on the hull (a cube came out V8 E18 F18 with 12
# non-manifold edges). Then drop verts left inside the hull. The result is
# a closed, all-triangle hull (cube: F12, 0 non-manifold edges). A flat
# input has no volume and yields an open hull. Copy matrix_world onto the
# collider so it sits on the source object.
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
        # Hull the points, not the surface: convex_hull keeps any source
        # edge or face whose verts lie on the hull, leaving duplicate,
        # non-manifold faces. edges.remove() drops faces but keeps verts.
        for edge in bm.edges[:]:
            bm.edges.remove(edge)
        bmesh.ops.convex_hull(bm, input=bm.verts[:])
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
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
