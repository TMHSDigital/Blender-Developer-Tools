---
name: uv-and-mesh-attributes
description: "Author per-loop and per-vertex mesh data from Python: UV layers (mesh.uv_layers.new, bmesh loops.layers.uv, the calc_uvs=True silent no-op), a second lightmap UV channel and its active / active_render flags, loop tangents (calc_tangents, bitangent_sign), color attributes and their CORNER vs POINT domain, shape keys (shape_key_add, key_blocks data), and vertex-group weights capped at four influences. Re-fetch layers by name after CustomData-reallocating calls. Use when the user creates or edits UVs in a script, builds a lightmap channel, computes tangents for normal maps, writes vertex colors, authors shape keys or limits skin weights, or gets a mesh that renders one flat color, a wrong UV channel, a crash or silently wrong values from a held layer. Targets 5.2 LTS with 4.5 LTS fallback."
standards-version: 1.10.0
---

# UV Layers and Mesh Attributes

## Trigger

Use this skill when the user:

- Creates or edits UVs from a script (`mesh.uv_layers`, `bm.loops.layers.uv`, `calc_uvs=True`)
- Builds a second UV channel for baked lighting, or runs `uv.lightmap_pack` / `uv.smart_project` on it
- Computes tangents for a normal-mapped game asset (`calc_tangents`, `bitangent_sign`)
- Writes vertex colors (`color_attributes`, the deprecated `vertex_colors`)
- Authors shape keys or reads a blended shape
- Caps skin weights at four influences per vertex for a game engine
- Reports a textured mesh that renders as one flat color, a UV op that wrecked channel 0, a crash or garbage values after `calc_tangents`, or weights that sum short of one

## High-level shape

Every one of these lives in the mesh's CustomData. Three rules cover most bugs:
create the layer before anything that fills it, address layers **by name**, and
re-fetch a layer by name after any call that can reallocate CustomData.

<!-- smoke: run -->
```python
import bmesh
import bpy

me = bpy.data.meshes.new("Panel")
bm = bmesh.new()
try:
    bm.loops.layers.uv.new("UVMap")  # first: calc_uvs only fills an existing layer
    bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=1.0, calc_uvs=True)
    bm.to_mesh(me)
finally:
    bm.free()

me.uv_layers.new(name="UVLight")      # a second channel does NOT become active
assert me.uv_layers.active.name == "UVMap"
assert me.uv_layers["UVMap"].active_render

me.calc_tangents(uvmap="UVMap")       # reallocates loop CustomData
uv = me.uv_layers["UVMap"].data       # so re-fetch by name after it
co = [0.0] * (len(me.loops) * 2)
uv.foreach_get("uv", co)
assert len(me.loops) == 64 and min(co) >= -1e-6 and max(co) <= 1.0 + 1e-6

col = me.color_attributes.new("Tint", 'FLOAT_COLOR', 'CORNER')
assert len(col.data) == len(me.loops)  # CORNER is per loop, not per vertex
```

## UV layers

- `mesh.uv_layers.new(name="UVMap")` on a Mesh, `bm.loops.layers.uv.new("UVMap")` on a BMesh. Look layers up with `mesh.uv_layers["UVMap"]`, never by index or "the first one".
- **`calc_uvs=True` is a silent no-op without a layer.** `bmesh.ops.create_grid` (and the other primitive ops) only fill a UV layer that already exists on the BMesh. With none, the flag does nothing, `to_mesh` leaves `mesh.uv_layers` empty, and an Image Texture samples texel (0, 0) everywhere: the mesh renders one flat color. Create the layer first, or assign UVs yourself.
- Bulk-read and write UVs with `uv_layer.data.foreach_get("uv", flat)` / `foreach_set`, sized `len(mesh.loops) * 2`. UVs are per loop (face corner), not per vertex.

## A second (lightmap) channel

Engines bake lighting into UV1. Two flags decide which channel a tool touches:

| Flag | Meaning |
| --- | --- |
| `uv_layer.active` (`mesh.uv_layers.active`) | the layer edit-mode UV operators read and write |
| `uv_layer.active_render` | the layer the renderer and exporters treat as the primary UV |

- `uv_layers.new()` does **not** move either flag. The first layer keeps both, so an unwrap or pack after adding `UVLight` runs on channel 0 and destroys it (measured drift 2.068 in `lightmap-uv-channel`). Set `mesh.uv_layers.active = mesh.uv_layers["UVLight"]` before the UV op.
- Edit-mode UV operators **clear both flags**. Re-assert them afterwards: `active` on the channel you edit, `active_render` on `UVMap`.
- `bpy.ops.uv.lightmap_pack` exits OK while packing nothing when its context is wrong; check the result (bounds in `[0, 1]`, non-overlap), not the return value.

## Handle lifetime: re-fetch by name

A `MeshUVLoopLayer`, attribute or color-attribute object is a view into CustomData. Calls that reallocate CustomData leave held views dangling:

- `mesh.calc_tangents()`, `VertexGroup.add()`, adding or removing modifiers or layers, edit-mode UV operators
- On 4.5 LTS a held UV handle read after `calc_tangents` returns tangent floats instead of UVs: **exit 0, silently wrong** (measured in `triangulate-tangents`). Iterating a held `uv_layer.data` after edit-mode UV ops segfaulted 4.5.11 headless (5 of 5 runs). On 5.1 and 5.2 the same stale read survives by memory-layout luck, which hides the bug.

Fetch the layer by name again after each such call, as the block above does.

## Tangents

- `mesh.calc_tangents(uvmap="UVMap")` fills `loop.tangent` and `loop.bitangent_sign`; the bitangent is `bitangent_sign * normal.cross(tangent)`.
- It needs triangles and quads. **One n-gon anywhere aborts the whole call**: triangulate first, or build caps as triangle fans.
- Tangents follow the UVs, so planar UVs on a curved wall collapse the tangent onto the normal. Unwrap the wall instead.
- mikktspace output is identical on 4.5.11, 5.1.2 and 5.2.1; a difference between versions points at a stale handle, not the math.

## Color attributes

- Use `mesh.color_attributes.new(name, type, domain)`. `mesh.vertex_colors` is the deprecated alias.
- The domain sets the length: `'CORNER'` is per loop (`len(mesh.loops)`), `'POINT'` is per vertex. Per-vertex data written to a `CORNER` attribute must be expanded across each vertex's corners.
- A material only shows it through a Shader **Attribute** node (`attribute_type='GEOMETRY'`, `attribute_name` set) wired into Base Color. Without that node the mesh stays gray even when the data is right.

## Shape keys

- `obj.shape_key_add(name="Basis", from_mix=False)` first, then the target key. Write the target with `key_blocks["Tall"].data.foreach_set("co", flat)`.
- A shape key does **not** rewrite `mesh.vertices`: those stay at Basis. Read the blended shape from the evaluated mesh (`obj.evaluated_get(depsgraph).to_mesh()`, then `to_mesh_clear()`), where each vertex is `basis + value * (key - basis)`.

## Skin weights: four influences

- Engines cap skinning at four bone influences per vertex. Enforce it on the data API rather than `bpy.ops.object.vertex_group_limit_total`: read `v.groups`, keep the four heaviest, `VertexGroup.remove([v.index])` the rest, then **renormalize** the survivors to sum to one. Dropping without renormalizing shrinks the mesh toward the origin under load.
- The weights on the mesh (`v.groups`) are the contract, not the weights you meant to write: read them back to check.
- The vertex-group API is the same on 4.5 LTS and 5.2.

## Common AI mistakes

- Trusting `calc_uvs=True` on a BMesh with no UV layer.
- Adding `UVLight` and unwrapping without moving `active`, or forgetting that edit-mode UV ops cleared `active_render`.
- Holding `uv = mesh.uv_layers.active.data` across `calc_tangents()` or other reallocating calls.
- Calling `calc_tangents` on a mesh with an n-gon.
- Sizing `CORNER` color data by vertex count, or never adding the Attribute node.
- Reading shape-key results from `mesh.vertices`.
- Removing extra skin influences without renormalizing.

## See also

- `mesh-editing-and-bmesh`: bmesh ownership, `foreach_get` / `foreach_set`, evaluated meshes
- `depsgraph-and-evaluated-data`: the `to_mesh` / `to_mesh_clear` lifetime
- `engine-export-presets`: exporting UV1, tangents and weights to Unity, Godot and Unreal

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`color-attribute-wheel`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/color-attribute-wheel): The modern color-attributes API — mesh.color_attributes.new() on the CORNER domain. Falsify: `--point-domain` (exit 6).
- [`lightmap-uv-channel`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/lightmap-uv-channel): A market cart carrying the two-channel UV contract for baked lighting: UV0 untouched, UVLight packed with no overlaps and a respected margin. Falsify: `--overlap-islands` (exit 7).
- [`shape-key-blend`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/shape-key-blend): A relative Tall shape key that turns a squat ceramic jar into a trumpet vase. Falsify: `--zero-blend` (exit 5).
- [`triangulate-tangents`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/triangulate-tangents): A machined buckler verifying the tangent-space contract a game engine's normal mapping depends on. Falsify: `--zero-uv` (exit 4).
- [`uv-layer-grid`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/uv-layer-grid): The UV-layer authoring hazard — bmesh.ops.create_grid(..., calc_uvs=True) is a silent no-op unless a UV layer already exists; without one an Image Texture samples texel (0,0) everywhere. Falsify: `--precreate-on-hazard` (exit 3).
- [`vertex-weight-limit`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/vertex-weight-limit): A rigged industrial robot arm pruned to the game-engine cap of four bone influences per vertex, through the data API. Falsify: `--skip-limit` (exit 4).

<!-- examples:end -->

## References

- https://docs.blender.org/api/current/bpy.types.MeshUVLoopLayer.html
- https://docs.blender.org/api/current/bpy.types.Mesh.html#bpy.types.Mesh.calc_tangents
- https://docs.blender.org/api/current/bpy.types.AttributeGroupMesh.html
- https://docs.blender.org/api/current/bpy.types.ShapeKey.html
- https://docs.blender.org/api/current/bpy.types.VertexGroup.html
