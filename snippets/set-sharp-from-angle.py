# Auto smooth after Blender 4.1: mesh.use_auto_smooth, auto_smooth_angle and
# calc_normals_split() are gone (AttributeError on 4.5 LTS and 5.x).
#
# - set_sharp_from_angle marks edges sharper than `angle` in the "sharp_edge"
#   attribute AND turns every face smooth (use_smooth = True), so a mesh that
#   was flat-shaded comes out smooth with hard edges, not flat.
# - corner_normals is always current: no calc_normals_split() before reading
#   it, and no free_normals_split() after.
# - For a non-destructive version use bpy.ops.object.shade_auto_smooth(), which
#   adds the "Smooth by Angle" modifier instead of writing the attribute.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.types.Mesh.html#bpy.types.Mesh.set_sharp_from_angle
#   https://docs.blender.org/api/current/bpy.types.Mesh.html#bpy.types.Mesh.corner_normals

import math

import bpy


def auto_smooth(mesh, degrees=30.0):
    """Smooth-shade `mesh` with hard edges above `degrees`; return its corner normals."""
    mesh.set_sharp_from_angle(angle=math.radians(degrees))
    return [tuple(cn.vector) for cn in mesh.corner_normals]


obj = bpy.context.active_object
if obj is not None and obj.type == "MESH":
    normals = auto_smooth(obj.data)
