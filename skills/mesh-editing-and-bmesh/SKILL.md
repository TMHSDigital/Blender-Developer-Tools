---
name: mesh-editing-and-bmesh
description: "Create, edit and read meshes efficiently: when to use bpy.data, bpy.ops or bmesh, the bmesh.new / try / finally / free pattern, foreach_get and foreach_set for bulk data, and evaluated meshes for modifier results. Use when the user writes mesh-generating or mesh-editing Python, mentions bmesh, from_pydata, foreach_set or mesh.vertices, has a slow script looping over bpy.ops.mesh or per-vertex assignments, or a bmesh script that misbehaves on its second run. Targets 5.2 LTS."
standards-version: 1.10.0
---

# Mesh Editing and bmesh

## Trigger

Use this skill when the user:

- Wants to create, modify, or read mesh geometry from Python
- Mentions `bmesh`, `mesh.vertices`, `foreach_set`, `from_pydata`, `evaluated_get`
- Has a script that's slow and uses `bpy.ops.mesh.*` in a loop
- Needs the mesh after modifiers (subdivision surface, mirror, geometry nodes) have been applied
- Asks why their bmesh script crashes on the second run

## Three layers, three use cases

There are three ways to touch mesh data and each is right in a specific situation.

### Layer 1: `bpy.data.meshes` and direct vertex/edge/face access

For creating new meshes from scratch or reading static geometry:

```python
import bpy

mesh = bpy.data.meshes.new("MyMesh")
verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
faces = [(0, 1, 2, 3)]
mesh.from_pydata(verts, [], faces)
mesh.update()

obj = bpy.data.objects.new("MyObject", mesh)
bpy.context.scene.collection.objects.link(obj)
```

Use this layer when:

- You're constructing a mesh from a list of vertices and faces.
- You're reading vertex coordinates, normals, or face indices from an existing static mesh.
- You're doing one-shot bulk operations.

### Layer 2: `bmesh` for editable mesh structure

For surgical edits (extrude, subdivide, dissolve, build n-gons by walking edges) where you need a real edit-mode-style data structure:

```python
import bmesh

bm = bmesh.new()
try:
    bm.from_mesh(mesh)

    for v in bm.verts:
        v.co.z += 0.1

    bm.to_mesh(mesh)
    mesh.update()
finally:
    bm.free()
```

Use this layer when:

- You need adjacency (which faces share an edge, which edges meet at a vertex).
- You're doing structural edits (split edges, merge verts, dissolve faces).
- You need iteration order to be stable mid-edit.

The `try`/`finally` with `bm.free()` is **mandatory**. `bmesh.new()` allocates C-side storage that is released only when the wrapper is collected, and a traceback, global, closure or modal operator can keep it alive for the whole session. `free()` in `finally` releases it on every path and makes any later use of `bm` raise `ReferenceError`. See the rule `always-free-bmesh`.

### Layer 3: `bpy.ops.mesh.*` operators

Use only for one-shot user-facing actions, never in a loop:

```python
# Acceptable: one-shot, user just clicked something.
bpy.ops.mesh.primitive_cube_add(size=2.0)
```

```python
# WRONG: every bpy.ops call triggers a full depsgraph evaluation and UI redraw.
for obj in bpy.context.selected_objects:
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.subdivide()
    bpy.ops.object.mode_set(mode='OBJECT')
```

This is the single biggest performance trap in Blender Python. See the rule `prefer-data-over-ops-in-loops`.

## The canonical create-an-object pattern

```python
import bpy

mesh = bpy.data.meshes.new("Cube")
verts = [
    (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
    (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
]
faces = [
    (0, 1, 2, 3), (4, 5, 6, 7),
    (0, 1, 5, 4), (1, 2, 6, 5),
    (2, 3, 7, 6), (3, 0, 4, 7),
]
mesh.from_pydata(verts, [], faces)
mesh.update()

obj = bpy.data.objects.new("Cube", mesh)
bpy.context.scene.collection.objects.link(obj)
```

Three steps:
1. Create the mesh datablock.
2. Create the object datablock pointing at the mesh.
3. Link the object into a collection so it appears in the scene.

Skipping step 3 creates the object but never shows it. The collection link is what puts it in the scene.

The deletion mirror image:

```python
obj = bpy.data.objects["Cube"]
bpy.data.objects.remove(obj, do_unlink=True)
```

`do_unlink=True` removes the object from any collections it was linked into before deleting it. It is already the default (`remove(object, *, do_unlink=True, ...)`); passing it explicitly documents intent. With `do_unlink=False`, Blender refuses to delete an object that is still referenced.

## `foreach_set` for bulk vertex injection

For setting many vertex coordinates fast, `foreach_set` is one to two orders of magnitude faster than a Python loop:

```python
import numpy as np

n_verts = len(mesh.vertices)
flat = np.empty(n_verts * 3, dtype=np.float32)
flat[0::3] = xs  # array of x coords
flat[1::3] = ys
flat[2::3] = zs

mesh.vertices.foreach_set("co", flat)
mesh.update()
```

The flat array layout `[x0, y0, z0, x1, y1, z1, ...]` is what `foreach_set` expects for `'co'`. Use `dtype=np.float32`, not `float64`; Blender expects 32-bit floats here.

`foreach_get` is the symmetric reader:

```python
flat = np.empty(n_verts * 3, dtype=np.float32)
mesh.vertices.foreach_get("co", flat)
xs = flat[0::3]
ys = flat[1::3]
zs = flat[2::3]
```

## Depsgraph evaluation: getting the modifier-applied mesh

Reading `obj.data` returns the **base** mesh, before modifiers. To read what the user sees after the modifier stack runs:

```python
depsgraph = bpy.context.evaluated_depsgraph_get()
eval_obj = obj.evaluated_get(depsgraph)
eval_mesh = eval_obj.to_mesh()

try:
    for v in eval_mesh.vertices:
        ...  # modifier-applied coords
finally:
    eval_obj.to_mesh_clear()
```

`to_mesh()` returns a temporary mesh datablock. `to_mesh_clear()` releases it. Skipping the cleanup leaks like skipping `bm.free()`.

This is the only way to:
- Read the post-subdivision-surface vertex count and positions
- Capture geometry-nodes-generated geometry from Python
- Export the mesh as the user sees it without baking modifiers first

## bmesh idioms

### Iterating in a stable order

```python
for face in bm.faces:
    if face.select:
        face.smooth = True
```

bmesh iteration is stable as long as you don't mutate the structure (add or remove elements). To mutate during iteration, copy the iterable first:

```python
for face in list(bm.faces):
    if face.calc_area() < 0.01:
        bm.faces.remove(face)
```

### `bmesh.ops`: the high-level bmesh functions

```python
import bmesh

bm = bmesh.new()
try:
    bm.from_mesh(mesh)

    bmesh.ops.subdivide_edges(
        bm,
        edges=bm.edges,
        cuts=2,
        use_grid_fill=True,
    )

    bm.to_mesh(mesh)
    mesh.update()
finally:
    bm.free()
```

`bmesh.ops.*` functions take the bmesh and keyword args. They are the Python equivalent of edit-mode operators but operate directly on the bmesh structure without round-tripping through `bpy.ops`.

## Working with selection

bmesh tracks selection via `.select` on each element:

```python
bm = bmesh.new()
try:
    bm.from_mesh(mesh)

    selected_verts = [v for v in bm.verts if v.select]
    for v in selected_verts:
        v.co.z += 0.5

    bm.to_mesh(mesh)
finally:
    bm.free()
```

After mutating selection, call `bm.select_flush_mode()` if you've changed individual element selection and want it to propagate (e.g. selecting verts should select connected edges).

## Common AI mistakes

1. **`bpy.ops.mesh.*` in a loop**. See the canonical example above. Move to `bpy.data` plus `bmesh`.

2. **Forgetting `bm.free()`**. Crashes Blender after enough runs. Use the `try`/`finally` form unconditionally.

3. **Forgetting `to_mesh_clear()`**. Leaks evaluated meshes. Same `try`/`finally` discipline applies.

4. **Reading `obj.data` and expecting modifiers**:

   ```python
   for v in obj.data.vertices:  # base mesh, no modifiers
       ...
   ```

   Use `evaluated_get(depsgraph).to_mesh()` instead.

5. **Mutating bmesh structure mid-iteration** without copying the iterable first. Crashes or skips elements.

6. **Skipping `mesh.update()`** after `foreach_set` or vertex coordinate edits. The mesh stays out of date until the next depsgraph cycle.

7. **Mismatched dtype in `foreach_set`** (a `float64` buffer for a float32 attribute). The values are converted correctly (round-trip error about 1e-7, float32 precision, on 4.5.11 and 5.2.1), but slower: 38 ms vs 21 ms for 361k vertices on 5.2.1 (34 vs 24 ms on 4.5.11). Match the attribute's type (`float32` for `co`) for bulk speed.

8. **Trusting glTF as an n-gon witness.** The exporter always triangulates. A cube and a hexagon-from-dissolved-edge both ship 12 tris. Hygiene (`len(poly.vertices) <= 4`) and `Mesh.calc_tangents` (aborts on n-gons) must run on the Blender mesh. Witness: [`examples/ngon-triangulate/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/ngon-triangulate).

9. **Treating coincident duplicate shells as non-manifold.** Two cubes occupying the same space are still valence-2. They ship as extra glTF triangles until `bmesh.ops.remove_doubles`. Witness: [`examples/coincident-vert-weld/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/coincident-vert-weld).

## Related

- `headless-batch-scripting` for using these patterns in CLI scripts
- `geometry-nodes-python` for programmatic GN tree construction
- Rule `prefer-data-over-ops-in-loops`
- Rule `always-free-bmesh`
- Snippet `canonical-object-creation.py`, `canonical-object-deletion.py`, `bmesh-load-edit-free.py`, `depsgraph-evaluated-mesh.py`, `foreach-set-vertices.py`
- Example `ngon-triangulate` for synthesized n-gons vs `calc_tangents` / triangulate
- Example `coincident-vert-weld` for authored duplicate shells vs glTF

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`armature-bend`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/armature-bend): Rigging end to end in the data API — edit_bones chain construction, name-bound vertex groups with smoothstep blend zones, posing, and depsgraph evaluation. Falsify: `--zero-curl` (exit 8).
- [`attribute-domain-shear`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/attribute-domain-shear): POINT vs CORNER color-attribute domains on a shared-vertex fan: CORNER stays exact per face while a naive per-wedge POINT loop shears to the last write at the hub. Falsify: `--no-overwrite` (exit 5).
- [`bmesh-gear`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/bmesh-gear): A 14-tooth gear built entirely with bmesh — profile ring, face, extrude — with bm.free() in a try/finally, exactly as the ownership contract demands. Falsify: `--no-extrude` (exit 3).
- [`boolean-exact-volume`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/boolean-exact-volume): The Boolean modifier on the EXACT solver. Falsify: `--float-solver` (exit 3).
- [`collision-hull-proxy`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/collision-hull-proxy): A fire hydrant street prop inside its compound collision shell: four convex pieces hulled by bmesh.ops.convex_hull from a coarse inflated cage. Falsify: `--shrink-hull` (exit 3).
- [`color-attribute-wheel`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/color-attribute-wheel): The modern color-attributes API — mesh.color_attributes.new() on the CORNER domain. Falsify: `--point-domain` (exit 5).
- [`custom-normals-shade`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/custom-normals-shade): A jerry can prop shaded three ways to prove the post-4.1 shading contract: hard edges are mesh data, landing exactly where the dihedral crosses. Falsify: `--mismatch-angle` (exit 5).
- [`degenerate-bevel-weld`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/degenerate-bevel-weld): Bevel offset >= half the min box dimension collapses the band into zero-area faces — and they ship: a stdlib GLB re-parse counts the degenerate triangles crossing the export boundary. Falsify: `--both-safe` (exit 4).
- [`lattice-deform`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/lattice-deform): A 2x2x2 Lattice modifier set to KEY_LINEAR on all three axes, with two top control points moved through LatticePoint.co_deform, read back through the depsgraph (evaluated_get, to_mesh, to_mesh_clear). Falsify: `--bspline` (exit 4).
- [`lightmap-uv-channel`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/lightmap-uv-channel): A market cart carrying the two-channel UV contract for baked lighting: UV0 untouched, UVLight packed with no overlaps and a respected margin. Falsify: `--overlap-islands` (exit 7).
- [`lod-decimate-chain`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/lod-decimate-chain): A retro rocket at LOD0/1/2 via the Decimate modifier evaluated through the depsgraph, with a wireframe of each evaluated mesh. Falsify: `--no-decimate` (exit 6).
- [`mesh-hygiene-audit`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/mesh-hygiene-audit): Engine-ingest mesh hygiene on every part of a flanged street valve: no ngons, no loose verts, manifold edges, no zero-area faces, contiguous and outward winding, Euler V-E+F==2 on the body casting. Falsify: `--inject ngon` (exit 3).
- [`modular-kit-snap`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/modular-kit-snap): A tiling corridor kit whose open-end boundary verts snap to the tile grid, so instances at 4 m multiples join with zero gap or overlap. Falsify: `--seam-gap` (exit 5).
- [`ngon-triangulate`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/ngon-triangulate): Synthesizes one hexagon by dissolving a cube edge, then asserts the hygiene / tangent contracts on that defective mesh. Falsify: `--no-dissolve` (exit 3).
- [`shape-key-blend`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/shape-key-blend): A relative Tall shape key that turns a squat ceramic jar into a trumpet vase. Falsify: `--zero-blend` (exit 5).
- [`soccer-ball-goldberg`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/soccer-ball-goldberg): A soccer ball as a Goldberg polyhedron: a bmesh icosphere truncated at 1/3 per edge, faces ordered by link-topology walks, panels bound by face vertex count. Falsify: `--invert-bind` (exit 13).
- [`solidify-even-thickness`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/solidify-even-thickness): Solidify's use_even_offset on a folded strip. Falsify: `--no-even` (exit 4).
- [`triangulate-tangents`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/triangulate-tangents): A machined buckler verifying the tangent-space contract a game engine's normal mapping depends on. Falsify: `--zero-uv` (exit 4).
- [`uv-layer-grid`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/uv-layer-grid): The UV-layer authoring hazard — bmesh.ops.create_grid(..., calc_uvs=True) is a silent no-op unless a UV layer already exists; without one an Image Texture samples texel (0,0) everywhere. Falsify: `--precreate-on-hazard` (exit 3).
- [`vertex-color-ao`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/vertex-color-ao): A stone well carrying baked ambient occlusion in a colour attribute, with the bake held to the closed-form hemisphere integral rather than to a captured value. Falsify: `--uniform-hemisphere` (exit 3).
- [`vertex-weight-limit`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/vertex-weight-limit): A rigged industrial robot arm pruned to the game-engine cap of four bone influences per vertex, through the data API. Falsify: `--skip-limit` (exit 4).
- [`wave-displace`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/wave-displace): Bulk vertex IO at real scale — 9,409 vertices displaced into a standing wave with one foreach_get and one foreach_set, no per-vertex access. Falsify: `--flat` (exit 4).

<!-- examples:end -->

## References

- `bpy.types.Mesh`: https://docs.blender.org/api/current/bpy.types.Mesh.html
- `bmesh` module: https://docs.blender.org/api/current/bmesh.html
- `bmesh.ops`: https://docs.blender.org/api/current/bmesh.ops.html
- Depsgraph: https://docs.blender.org/api/current/bpy.types.Depsgraph.html
