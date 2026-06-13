# Reusable shader node group with the cross-version interface API.
# 4.5 LTS uses group.inputs/outputs; 5.x uses group.interface.new_socket.
# See skill: procedural-materials-and-shaders.
# Refs: docs.blender.org/api/current/bpy.types.ShaderNodeTree.html

import bpy


def make_tint_group(name="Tint"):
    group = bpy.data.node_groups.new(name=name, type='ShaderNodeTree')

    if hasattr(group, 'interface'):
        group.interface.new_socket(name='Color', in_out='INPUT', socket_type='NodeSocketColor')
        group.interface.new_socket(name='Strength', in_out='INPUT', socket_type='NodeSocketFloat')
        group.interface.new_socket(name='Result', in_out='OUTPUT', socket_type='NodeSocketColor')
    else:
        group.inputs.new('NodeSocketColor', 'Color')
        group.inputs.new('NodeSocketFloat', 'Strength')
        group.outputs.new('NodeSocketColor', 'Result')

    nodes = group.nodes
    links = group.links

    group_in = nodes.new('NodeGroupInput')
    group_out = nodes.new('NodeGroupOutput')
    mix = nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'

    # ShaderNodeMix shares socket names (Factor/A/B/Result) across every
    # data_type, so name lookup is ambiguous. Wire the RGBA sockets by index:
    #   inputs[0]=Factor (Float), inputs[6]=A (Color), inputs[7]=B (Color)
    #   outputs[2]=Result (Color)
    links.new(group_in.outputs['Strength'], mix.inputs[0])
    links.new(group_in.outputs['Color'], mix.inputs[6])
    links.new(mix.outputs[2], group_out.inputs['Result'])
    return group
