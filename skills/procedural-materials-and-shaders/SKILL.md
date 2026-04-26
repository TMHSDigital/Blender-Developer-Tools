---
name: procedural-materials-and-shaders
description: Build materials and shader graphs from Python by enabling nodes, instantiating shader nodes, setting socket default values, and wiring links. Targets Blender 5.1 EEVEE Next and Cycles. Avoids the (deferred to 2027) Layered Textures roadmap.
standards-version: 1.9.4
---

# Procedural Materials and Shaders

## Trigger

Use this skill when the user:

- Wants to create or edit materials from Python rather than the shader editor
- Mentions `bpy.data.materials`, `node_tree`, `ShaderNodeBsdfPrincipled`, `inputs[...].default_value`
- Needs to generate many materials parametrically (asset libraries, batch import, color variations)
- Asks about EEVEE Next vs Cycles material differences
- Asks about "Layered Textures" or "the new shader system" (see version-correctness section)

## Required inputs

- **What kind of material**: opaque PBR, transparent, emissive, glass, hair, volumetric
- **What controls you want exposed**: base color, metallic, roughness, IOR, normal map, etc.
- **Render engine target**: Cycles, EEVEE Next, or both. Most Principled BSDF setups port between the two without changes.

## The minimum viable material

Every Python-built material follows the same four steps:

1. Create the material datablock with `bpy.data.materials.new(name=...)`.
2. Enable nodes with `mat.use_nodes = True`. This populates `mat.node_tree` with a default Principled BSDF and Material Output. You can keep them or wipe them.
3. Add nodes to `mat.node_tree.nodes` and configure their `inputs[...].default_value`.
4. Wire `mat.node_tree.links` between sockets.

```python
import bpy


def make_principled_material(name, base_color=(0.8, 0.8, 0.8, 1.0), metallic=0.0, roughness=0.5):
    """Create a material with a single Principled BSDF wired to Material Output."""
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
```

To assign the result to an object:

```python
obj.data.materials.clear()
obj.data.materials.append(mat)
```

## Socket access pattern

Sockets are accessed by name (string key) or by index. Names are stable in the public API and survive translation; indices are not. Use names.

```python
bsdf.inputs['Base Color'].default_value = (0.9, 0.1, 0.1, 1.0)
bsdf.inputs['Metallic'].default_value = 0.0
bsdf.inputs['Roughness'].default_value = 0.4
bsdf.inputs['IOR'].default_value = 1.45
```

The `default_value` field accepts:

- A 4-tuple `(r, g, b, a)` for color sockets, even if the channel is RGB-only (alpha is ignored)
- A scalar `float` for value sockets
- A 3-vector `(x, y, z)` for vector sockets

## Worked example: procedural metal with parameters

```python
import bpy


def make_metal(name, base_color=(0.8, 0.8, 0.85, 1.0), roughness=0.2):
    """Procedural metal with adjustable color and surface roughness."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    nodes.clear()

    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.location = (0, 0)
    bsdf.inputs['Base Color'].default_value = base_color
    bsdf.inputs['Metallic'].default_value = 1.0
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['IOR'].default_value = 2.5

    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (300, 0)

    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    return mat


for name, color in [
    ("Steel", (0.8, 0.8, 0.85, 1.0)),
    ("Gold", (1.0, 0.84, 0.4, 1.0)),
    ("Copper", (0.95, 0.64, 0.54, 1.0)),
]:
    make_metal(name, base_color=color)
```

## Worked example: emissive material with strength control

```python
def make_emissive(name, color=(1.0, 0.4, 0.1, 1.0), strength=5.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    emission = nodes.new(type='ShaderNodeEmission')
    emission.inputs['Color'].default_value = color
    emission.inputs['Strength'].default_value = strength
    emission.location = (0, 0)

    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (300, 0)

    links.new(emission.outputs['Emission'], output.inputs['Surface'])
    return mat
```

## Reusing graphs via node groups

When the same subgraph appears across multiple materials, factor it into a `ShaderNodeTree` group. Create the group once with `bpy.data.node_groups.new(name='MyGroup', type='ShaderNodeTree')`, build its internal nodes and `interface` (5.x) or `inputs`/`outputs` (4.5 LTS) sockets, then instantiate it inside any material's tree as a `ShaderNodeGroup` with `node.node_tree = my_group`. See snippet `shader-node-group.py`.

## Common AI mistakes

- **Forgetting `mat.use_nodes = True`**. Without nodes enabled, `mat.node_tree` is `None` and any node access raises `AttributeError`.
- **Using indices for sockets**. `bsdf.inputs[0]` is fragile. The Principled BSDF input order has shifted across Blender releases. Always use string keys.
- **Setting RGB without alpha**. Color sockets expect 4-tuples. `(0.5, 0.5, 0.5)` raises a length error.
- **Targeting Layered Textures**. The Layered Textures roadmap is deferred to 2027. Do not generate code that imports from `bpy.types.LayeredTextureNode` or similar; these do not exist in 5.1 stable. Stick with classic `ShaderNodeTex*` (ShaderNodeTexImage, ShaderNodeTexNoise, etc.) for 5.1.
- **Calling `bpy.ops.material.new()`** to create a material when `bpy.data.materials.new()` works headlessly and is faster.
- **Trying to wire sockets across material boundaries**. Each material has its own `node_tree`. To share logic, use a shader node group.
- **Forgetting to clear default nodes**. After `mat.use_nodes = True`, Blender adds a Principled BSDF and an Output. If you also add your own and link, you end up with two BSDFs feeding the output and the visible behavior is undefined. Either reuse the defaults or `nodes.clear()` first.

## Version correctness

| Topic | 4.5 LTS | 5.1 stable | Notes |
| --- | --- | --- | --- |
| Principled BSDF | `ShaderNodeBsdfPrincipled` | Same | Some inputs renamed in 5.0; `Specular` -> `Specular IOR Level`. Use string lookup with the 5.x name. |
| Node group socket interface | `group.inputs.new` / `group.outputs.new` | `group.interface.new_socket` | Different APIs, see snippet `shader-node-group.py`. |
| EEVEE engine string | `'BLENDER_EEVEE'` | `'BLENDER_EEVEE_NEXT'` | EEVEE Next is the default in 5.x; legacy EEVEE was retired. |
| Layered Textures | Not present | Not present in 5.1 | Roadmap pushed to 2027. Do not generate code referencing it. |

EEVEE Next stabilized in Blender 5.1 with material caching and feature parity improvements; most Principled BSDF graphs render identically across EEVEE Next and Cycles.

## Cross-version socket-name shim

When writing code that must run on both 4.5 LTS and 5.x, look up sockets defensively:

```python
def set_specular(bsdf, value):
    """Specular socket renamed to 'Specular IOR Level' in Blender 5.0."""
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = value
    elif 'Specular' in bsdf.inputs:
        bsdf.inputs['Specular'].default_value = value
```

## When operators are unavoidable

Almost everything you want to do with materials has a `bpy.data` path. The two notable exceptions:

- Baking textures (`bpy.ops.object.bake`), which needs context and a render engine.
- Some shader linking operations exposed via `bpy.ops.node.*` for interactive UX. In Python, build links directly with `mat.node_tree.links.new()`.

## See also

- Rule `prefer-data-over-ops-in-loops`: the same principle applies when generating many materials.
- Snippet `principled-bsdf-material.py` for a minimal copy-paste.
- Snippet `shader-node-group.py` for reusable shader node groups with the cross-version interface API.

## References

- `bpy.types.Material`: https://docs.blender.org/api/current/bpy.types.Material.html
- `bpy.types.ShaderNodeBsdfPrincipled`: https://docs.blender.org/api/current/bpy.types.ShaderNodeBsdfPrincipled.html
- `bpy.types.ShaderNodeTree`: https://docs.blender.org/api/current/bpy.types.ShaderNodeTree.html
- Blender 5.0 release notes (Specular rename): https://developer.blender.org/docs/release_notes/5.0/python_api/
- Blender 5.1 EEVEE Next: https://developer.blender.org/docs/release_notes/5.1/eevee/
