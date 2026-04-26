# Procedural Principled BSDF material.
# See skill: procedural-materials-and-shaders.
# Refs: docs.blender.org/api/current/bpy.types.ShaderNodeBsdfPrincipled.html

import bpy


def make_principled_material(name, base_color=(0.8, 0.8, 0.8, 1.0), metallic=0.0, roughness=0.5):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.location = (0, 0)
    bsdf.inputs['Base Color'].default_value = base_color
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness

    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (300, 0)

    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    return mat


if __name__ == "__main__":
    mat = make_principled_material("Procedural_Red", base_color=(0.8, 0.1, 0.1, 1.0))
    print(f"Created material: {mat.name}")
