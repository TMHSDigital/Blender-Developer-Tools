---
name: compositor-nodes
description: "Build and render through the scene compositor from Python across the 4.5 LTS to 5.x split: scene.use_nodes plus scene.node_tree and a Composite node on 4.5, a CompositorNodeTree node group assigned to scene.compositing_node_group with interface sockets and a Group Output on 5.x, a Render Layers to Glare (Fog Glow) chain, the Glare node's move from enum properties to menu input sockets, and render.use_compositing. Use when the user scripts compositor nodes, adds bloom or glow, hits AttributeError on scene.node_tree in 5.x, sets glare_type or quality and gets AttributeError on 5.x, looks for the removed EEVEE use_bloom toggle, or renders and sees no compositor effect. Targets 5.2 LTS with 4.5 LTS fallback."
standards-version: 1.10.0
---

# Compositor Nodes in Python

## Trigger

Use this skill when the user:

- Builds, edits or inspects compositor nodes from a script
- Mentions `scene.node_tree`, `scene.use_nodes`, `compositing_node_group`, `CompositorNodeTree`, `CompositorNodeGlare`, `CompositorNodeRLayers`, or `CompositorNodeComposite`
- Hits `AttributeError` on `scene.node_tree` after moving to 5.x
- Sets `glare.glare_type` / `glare.quality` / `glare.size` on 5.x and gets `AttributeError`
- Wants bloom and reaches for `scene.eevee.use_bloom` (removed in 4.2, absent on 4.5 and 5.x)

## High-level shape

```python
import bpy

scene = bpy.context.scene

if bpy.app.version >= (5, 0, 0):
    # 5.x: the compositor is a node GROUP assigned to the scene
    tree = bpy.data.node_groups.new("Composite", 'CompositorNodeTree')
    tree.interface.new_socket(name="Image", in_out='INPUT', socket_type='NodeSocketColor')
    tree.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    out_node = tree.nodes.new("NodeGroupOutput")
    scene.compositing_node_group = tree
else:
    # 4.5: the scene owns its compositor tree
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    out_node = tree.nodes.new("CompositorNodeComposite")

rl = tree.nodes.new("CompositorNodeRLayers")
tree.links.new(rl.outputs["Image"], out_node.inputs["Image"])
```

Branch on the `bpy.app.version` tuple, never on `bpy.app.version_string` (it reads e.g. `"4.5.11 LTS"`). `hasattr(scene, "node_tree")` is an equivalent probe: it is `True` on 4.5 and `False` on 5.x.

## The tree the scene composites

| | 4.5 LTS | 5.x (5.1, 5.2 LTS) |
| --- | --- | --- |
| Where the tree lives | `scene.node_tree` (created by `scene.use_nodes = True`) | a `bpy.data.node_groups` entry of type `'CompositorNodeTree'`, assigned to `scene.compositing_node_group` |
| `scene.node_tree` | present | `AttributeError` (removed in 5.0) |
| `scene.use_nodes` | turns the compositor on and creates the tree | deprecated flag (removal in 6.0); setting it only warns and creates nothing |
| Final output node | `CompositorNodeComposite` | `NodeGroupOutput`, fed through an `Image` OUTPUT socket declared on `tree.interface` |

On 5.x the group's sockets are declared with `tree.interface.new_socket(...)`, the same interface API shader and geometry node groups use (see [`procedural-materials-and-shaders`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/skills/procedural-materials-and-shaders/SKILL.md) and [`snippets/shader-node-group.py`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/snippets/shader-node-group.py)). Without the `Image` OUTPUT socket the Group Output node has no `Image` input to link to.

To read an existing compositor back:

```python
import bpy


def compositor_tree(scene):
    if bpy.app.version >= (5, 0, 0):
        return scene.compositing_node_group
    return scene.node_tree if scene.use_nodes else None
```

## Glare: enum properties on 4.5, menu sockets on 5.x

The Glare node changed shape in the 5.0 rewrite. On 4.5 Fog Glow is chosen with legacy enum properties; on 5.x those properties are gone and the same choices are input sockets. Menu sockets take the **display name** (`'Fog Glow'`, `'High'`), not the enum identifier, and `Size` becomes a 0..1 factor instead of the old integer kernel size.

```python
import bpy


def configure_fog_glow(glare):
    if bpy.app.version >= (5, 0, 0):
        glare.inputs['Type'].default_value = 'Fog Glow'
        glare.inputs['Quality'].default_value = 'High'
        glare.inputs['Size'].default_value = 0.85
    else:
        glare.glare_type = 'FOG_GLOW'
        glare.quality = 'HIGH'
        glare.size = 6
    # Threshold is an input socket on BOTH versions. The 4.5 `glare.threshold`
    # property is a dead shim (always reads 0.0); writing it changes nothing.
    glare.inputs['Threshold'].default_value = 1.0
```

Only pixels brighter than `Threshold` bloom. In [`compositor-glare`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/compositor-glare) emission strengths of 9 to 18 bloom at `Threshold = 1.0`; raising it to `1000.0` removes the halo entirely.

## Build a Glare chain (smoke-tested)

Render Layers into Glare into the output, on whichever tree the scene actually composites. No render; the asserts pin the wiring.

<!-- smoke: run -->
```python
import bpy

scene = bpy.context.scene
if bpy.app.version >= (5, 0, 0):
    tree = bpy.data.node_groups.new("BloomComposite", 'CompositorNodeTree')
    tree.interface.new_socket(name="Image", in_out='INPUT', socket_type='NodeSocketColor')
    tree.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    out_node = tree.nodes.new("NodeGroupOutput")
    scene.compositing_node_group = tree
else:
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    out_node = tree.nodes.new("CompositorNodeComposite")

rl = tree.nodes.new("CompositorNodeRLayers")
glare = tree.nodes.new("CompositorNodeGlare")
if bpy.app.version >= (5, 0, 0):
    glare.inputs['Type'].default_value = 'Fog Glow'
else:
    glare.glare_type = 'FOG_GLOW'
glare.inputs['Threshold'].default_value = 1.0
tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
tree.links.new(glare.outputs["Image"], out_node.inputs["Image"])

composited = scene.compositing_node_group if bpy.app.version >= (5, 0, 0) else scene.node_tree
assert composited == tree
assert hasattr(scene, "node_tree") == (bpy.app.version < (5, 0, 0))
assert any(l.from_node == rl and l.to_node == glare for l in composited.links)
assert any(l.from_node == glare and l.to_node == out_node for l in composited.links)
assert getattr(getattr(scene, "eevee", None), "use_bloom", None) is None
```

## Rendering through the compositor

The tree only runs when `scene.render.use_compositing` is on. The example renders the same scene with it on and off: the halo outside the emissive silhouette is bright and falls off with distance when on, and exactly zero when off.

```python
import bpy

scene = bpy.context.scene
scene.render.use_compositing = True
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = "/tmp/bloom.png"
bpy.ops.render.render(write_still=True)
```

Bloom comes from the Glare node on EEVEE and Cycles alike; EEVEE has no `use_bloom` toggle on 4.5 or 5.x.

## Common AI mistakes

1. **`scene.node_tree` on 5.x.** `AttributeError`. Build a `'CompositorNodeTree'` group and assign it to `scene.compositing_node_group`.

2. **`scene.use_nodes = True` as the 5.x enable switch.** It is a deprecated flag that only warns; no tree appears. Branch it to `< (5, 0, 0)` only.

3. **Missing interface sockets on the 5.x group.** A Group Output node has no `Image` input until `tree.interface.new_socket(name="Image", in_out='OUTPUT', ...)` declares one.

4. **Building the group but never assigning it.** A compositor group in `bpy.data.node_groups` does nothing until `scene.compositing_node_group = tree`.

5. **`glare.glare_type = 'FOG_GLOW'` on 5.x.** The property is gone; set `glare.inputs['Type'].default_value = 'Fog Glow'`. Same for `quality` and `size`.

6. **Enum identifiers in menu sockets.** 5.x menu sockets take display names (`'Fog Glow'`, `'High'`), not `'FOG_GLOW'` / `'HIGH'`.

7. **Writing `glare.threshold` on 4.5.** Dead shim, always reads 0.0. The threshold is `glare.inputs['Threshold']` on both versions.

8. **`scene.eevee.use_bloom = True`.** Removed in 4.2. Bloom is a compositor Glare node.

9. **Rendering with `scene.render.use_compositing = False`.** The tree is skipped and the output carries no Glare effect.

10. **Branching on `bpy.app.version_string`.** Compare the `bpy.app.version` tuple.

## See also

- Example [`examples/compositor-glare/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/compositor-glare) — the cross-version tree plumbing, Glare property-to-socket move, and a compositing on/off pixel check (`--threshold-high` exits 4).
- Skill [`porting-to-blender-5`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/skills/porting-to-blender-5/SKILL.md) — the `scene.node_tree` and `use_nodes` rows of the 4.x to 5.x break table.
- Skill [`procedural-materials-and-shaders`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/skills/procedural-materials-and-shaders/SKILL.md) — the shared `tree.interface.new_socket` group API and emissive materials that feed bloom.

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`compositor-glare`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/compositor-glare): Bloom where it actually lives — a compositor Glare (Fog Glow) node fed by Render Layers. Falsify: `--threshold-high` (exit 4).

<!-- examples:end -->

## References

- `bpy.types.CompositorNodeTree`: https://docs.blender.org/api/current/bpy.types.CompositorNodeTree.html
- `bpy.types.CompositorNodeGlare`: https://docs.blender.org/api/current/bpy.types.CompositorNodeGlare.html
- `bpy.types.Scene` (`compositing_node_group`): https://docs.blender.org/api/current/bpy.types.Scene.html
- `bpy.types.NodeTreeInterface`: https://docs.blender.org/api/current/bpy.types.NodeTreeInterface.html
- 4.5 LTS `bpy.types.Scene` (`node_tree`, `use_nodes`): https://docs.blender.org/api/4.5/bpy.types.Scene.html
- 4.5 LTS `bpy.types.CompositorNodeGlare`: https://docs.blender.org/api/4.5/bpy.types.CompositorNodeGlare.html
- 4.5 LTS `bpy.types.CompositorNodeComposite`: https://docs.blender.org/api/4.5/bpy.types.CompositorNodeComposite.html
