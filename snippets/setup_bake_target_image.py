# Target setup for bpy.ops.object.bake: generated image, Non-Color,
# a material whose Image Texture node is nodes.active, UV layer present.
# The texture does not need a link into Principled. If it is not active,
# the bake finishes and writes nowhere.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.ops.object.html#bpy.ops.object.bake
#   https://docs.blender.org/api/current/bpy.types.Image.html
#   https://docs.blender.org/api/current/bpy.types.ShaderNodeTree.html

import bpy


def setup_bake_target_image(obj, name="BakeNrm", size=128):
    if not obj.data.uv_layers:
        raise ValueError(f"{obj.name} has no UV layer")
    img = bpy.data.images.new(name, size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    mat = bpy.data.materials.new(name + "Mat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    return img, mat, tex
