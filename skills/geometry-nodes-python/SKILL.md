---
name: geometry-nodes-python
description: Programmatically construct Geometry Nodes trees in Blender 5.x via bpy.data.node_groups, interface socket creation, node instantiation by RNA name, link wiring, and applying as a NODES modifier. Includes Bundles for grouped sockets.
standards-version: 1.9.1
---

# Geometry Nodes in Python

## Trigger

Use this skill when the user:

- Wants to build a Geometry Nodes tree from a script rather than the editor
- Mentions `GeometryNodeTree`, `node_groups.new`, `tree.interface`, `tree.links.new`
- Needs to apply a generated GN tree as a modifier on an object
- Asks about Bundles, Repeat Zones, or for-each Element zones from Python

## High-level shape

The Python pattern for building a Geometry Nodes tree has four phases:

1. Create the node group and its interface (input and output sockets).
2. Instantiate nodes by their exact RNA bl_idname.
3. Wire nodes with `tree.links.new`.
4. Add a NODES modifier on the target object that points at the group.

```python
import bpy


def build_displace_tree():
    tree = bpy.data.node_groups.new(name="MyDisplace", type='GeometryNodeTree')

    tree.interface.new_socket(
        name="Geometry",
        in_out='INPUT',
        socket_type='NodeSocketGeometry',
    )
    tree.interface.new_socket(
        name="Strength",
        in_out='INPUT',
        socket_type='NodeSocketFloat',
    )
    tree.interface.new_socket(
        name="Geometry",
        in_out='OUTPUT',
        socket_type='NodeSocketGeometry',
    )

    group_in = tree.nodes.new('NodeGroupInput')
    group_out = tree.nodes.new('NodeGroupOutput')
    set_pos = tree.nodes.new('GeometryNodeSetPosition')
    noise = tree.nodes.new('ShaderNodeTexNoise')
    multiply = tree.nodes.new('ShaderNodeMath')
    multiply.operation = 'MULTIPLY'

    group_in.location = (-400, 0)
    set_pos.location = (200, 0)
    group_out.location = (600, 0)
    noise.location = (-200, -200)
    multiply.location = (0, -100)

    tree.links.new(group_in.outputs["Geometry"], set_pos.inputs["Geometry"])
    tree.links.new(set_pos.outputs["Geometry"], group_out.inputs["Geometry"])

    tree.links.new(noise.outputs["Fac"], multiply.inputs[0])
    tree.links.new(group_in.outputs["Strength"], multiply.inputs[1])
    tree.links.new(multiply.outputs[0], set_pos.inputs["Offset"])

    return tree


def attach_tree_to_object(obj, tree):
    mod = obj.modifiers.new(name="MyDisplace", type='NODES')
    mod.node_group = tree
    return mod


tree = build_displace_tree()
obj = bpy.context.active_object
mod = attach_tree_to_object(obj, tree)
```

## Creating the node group

```python
tree = bpy.data.node_groups.new(name="MyDisplace", type='GeometryNodeTree')
```

The `type` argument is the RNA `bl_idname` of the tree class. The Geometry Nodes tree type is `'GeometryNodeTree'`. Other useful types:

| Type | Used for |
| --- | --- |
| `'GeometryNodeTree'` | Geometry Nodes |
| `'ShaderNodeTree'` | Material shaders |
| `'CompositorNodeTree'` | Compositor |

## Interface sockets (5.x model)

Pre-4.0 used the legacy `inputs` and `outputs` collections. **5.x uses `tree.interface`**, which is unified across input and output sockets and supports panels, descriptions, and default values.

```python
tree.interface.new_socket(
    name="Strength",
    in_out='INPUT',
    socket_type='NodeSocketFloat',
)
```

`in_out` is `'INPUT'` or `'OUTPUT'`. `socket_type` is the RNA name of the socket class:

| socket_type | Carries |
| --- | --- |
| `'NodeSocketGeometry'` | Geometry (mesh, curve, instances, volume) |
| `'NodeSocketFloat'` | Single float |
| `'NodeSocketInt'` | Single int |
| `'NodeSocketBool'` | Single bool |
| `'NodeSocketVector'` | 3-float vector |
| `'NodeSocketColor'` | RGBA color |
| `'NodeSocketString'` | String |
| `'NodeSocketObject'` / `'NodeSocketCollection'` / `'NodeSocketImage'` / `'NodeSocketMaterial'` | Datablock pointers |
| `'NodeSocketBundle'` (5.0+) | A bundle of multiple typed sockets in one connection |

Set defaults and ranges after creation:

```python
strength_socket = tree.interface.new_socket(
    name="Strength",
    in_out='INPUT',
    socket_type='NodeSocketFloat',
)
strength_socket.default_value = 1.0
strength_socket.min_value = 0.0
strength_socket.max_value = 10.0
strength_socket.description = "Displacement amount along normals"
```

## Instantiating nodes

```python
node = tree.nodes.new('GeometryNodeSetPosition')
```

The argument is the exact RNA `bl_idname` of the node class. A few you'll reach for often:

| Node | bl_idname |
| --- | --- |
| Group Input | `NodeGroupInput` |
| Group Output | `NodeGroupOutput` |
| Set Position | `GeometryNodeSetPosition` |
| Position (input) | `GeometryNodeInputPosition` |
| Normal (input) | `GeometryNodeInputNormal` |
| Math | `ShaderNodeMath` |
| Vector Math | `ShaderNodeVectorMath` |
| Mix | `ShaderNodeMix` |
| Noise Texture | `ShaderNodeTexNoise` |
| Mesh to SDF Grid (5.0+) | `GeometryNodeMeshToSDFGrid` |
| SDF Grid to Mesh / Volume to Mesh | `GeometryNodeVolumeToMesh` |
| Repeat Input / Output | `GeometryNodeRepeatInput`, `GeometryNodeRepeatOutput` |
| For Each Element Input / Output (5.0+) | `GeometryNodeForeachGeometryElementInput`, `GeometryNodeForeachGeometryElementOutput` |

To list all available Geometry node types in your Blender version:

```python
import bpy
for cls in bpy.types.GeometryNode.__subclasses__():
    print(cls.bl_idname)
```

## Wiring nodes

```python
tree.links.new(from_socket, to_socket)
```

You can address sockets by name or by index:

```python
tree.links.new(group_in.outputs["Geometry"], set_pos.inputs["Geometry"])
tree.links.new(noise.outputs["Fac"], multiply.inputs[0])  # by index
```

Index is reliable for Math nodes whose two value inputs share the name `'Value'`.

## Setting input defaults on a node

For nodes that have inputs without an incoming link:

```python
multiply = tree.nodes.new('ShaderNodeMath')
multiply.operation = 'MULTIPLY'
multiply.inputs[0].default_value = 0.5
```

Some nodes have `bpy.props`-like attributes for their mode (e.g. `multiply.operation = 'MULTIPLY'`, `mix.data_type = 'VECTOR'`, `noise.noise_dimensions = '3D'`). Inspect with `dir(node)` if you're not sure.

## Applying as a NODES modifier

```python
mod = obj.modifiers.new(name="MyDisplace", type='NODES')
mod.node_group = tree
```

To set the tree's input values per-modifier (each modifier has its own copies of the tree's exposed inputs):

```python
mod["Input_2"] = 2.5  # the "Strength" input via its identifier
```

Modifier inputs are addressed by their socket identifier, not their display name. Find identifiers via:

```python
for item in tree.interface.items_tree:
    if item.in_out == 'INPUT':
        print(item.identifier, item.name, item.socket_type)
```

In the 5.x interface, `item.identifier` is what you key into `mod[...]` with.

## Bundles (5.0+)

Bundles let one socket carry a set of typed values, similar to a struct. Useful for passing multiple related fields between subtrees:

```python
bundle_socket = tree.interface.new_socket(
    name="Surface Data",
    in_out='OUTPUT',
    socket_type='NodeSocketBundle',
)
```

You then build a bundle inside the tree using the `Combine Bundle` node (`GeometryNodeCombineBundle`) with named slots, and unpack it with `Separate Bundle` (`GeometryNodeSeparateBundle`).

Bundles are 5.0+ only; on 4.5 LTS you fall back to multiple separate sockets.

## Detecting Geometry Nodes feature support

```python
import bpy

def has_bundles():
    major, _minor, _patch = bpy.app.version
    return major >= 5

def has_for_each_element():
    major, _minor, _patch = bpy.app.version
    return major >= 5
```

## Common AI mistakes

1. **Using `tree.inputs.new` / `tree.outputs.new`** (legacy 3.x API). 5.x uses `tree.interface.new_socket(...)` exclusively for new code.

2. **Wrong RNA name for nodes**:

   ```python
   tree.nodes.new('GeometrySetPosition')  # WRONG, missing 'Node' prefix
   tree.nodes.new('GeometryNodeSetPosition')  # RIGHT
   ```

   When in doubt, list `bpy.types.GeometryNode.__subclasses__()` and grep.

3. **Linking nodes by name when both inputs share a name** (`Value`, `Vector`, `Geometry`) and getting the wrong one. Use indices or the named inputs of the parent node.

4. **Setting modifier inputs by display name**:

   ```python
   mod["Strength"] = 2.5  # WRONG, that's the display name
   mod["Input_2"] = 2.5   # RIGHT, that's the identifier
   ```

5. **Forgetting to assign `mod.node_group`** after creating the modifier. The modifier exists but does nothing.

6. **Building the tree without group input/output nodes**. The tree's interface sockets only matter once you have `NodeGroupInput` and `NodeGroupOutput` instances connected to actual nodes inside the tree.

## Worked example: replicate the "Mesh to SDF then Volume to Mesh" pipeline

```python
import bpy


def build_remesh_via_sdf(voxel_size=0.05, threshold=0.5):
    tree = bpy.data.node_groups.new(name="SDFRemesh", type='GeometryNodeTree')

    tree.interface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    tree.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    grp_in = tree.nodes.new('NodeGroupInput')
    grp_out = tree.nodes.new('NodeGroupOutput')
    mesh_to_sdf = tree.nodes.new('GeometryNodeMeshToSDFGrid')
    volume_to_mesh = tree.nodes.new('GeometryNodeVolumeToMesh')

    mesh_to_sdf.inputs["Voxel Size"].default_value = voxel_size
    volume_to_mesh.inputs["Threshold"].default_value = threshold

    grp_in.location = (-400, 0)
    mesh_to_sdf.location = (-150, 0)
    volume_to_mesh.location = (150, 0)
    grp_out.location = (400, 0)

    tree.links.new(grp_in.outputs["Geometry"], mesh_to_sdf.inputs["Mesh"])
    tree.links.new(mesh_to_sdf.outputs["SDF Grid"], volume_to_mesh.inputs["Volume"])
    tree.links.new(volume_to_mesh.outputs["Mesh"], grp_out.inputs["Geometry"])

    return tree
```

## Related

- `addon-scaffolding` for shipping a tree-building script as part of an extension
- `mesh-editing-and-bmesh` for reading the modifier-applied result via depsgraph

## References

- `bpy.data.node_groups`: https://docs.blender.org/api/current/bpy.types.BlendDataNodeTrees.html
- `bpy.types.NodeTreeInterface`: https://docs.blender.org/api/current/bpy.types.NodeTreeInterface.html
- Geometry Nodes types index: https://docs.blender.org/api/current/bpy.types.GeometryNode.html
- 5.x release notes (Bundles, Repeat Zones, For Each): https://developer.blender.org/
