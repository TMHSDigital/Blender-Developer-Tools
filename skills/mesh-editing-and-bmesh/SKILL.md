---
name: mesh-editing-and-bmesh
description: Performant mesh manipulation in Blender. When to use bpy.data vs bpy.ops vs bmesh, the canonical bm.new/free pattern, foreach_set bulk vertex injection, and depsgraph evaluation for modifier-applied geometry. Targets 5.1.
standards-version: 1.9.4
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

The `try`/`finally` with `bm.free()` is **mandatory**. `bmesh.new()` allocates memory in the C side that Python's garbage collector cannot reclaim. Forgetting `bm.free()` leaks BMesh structures and eventually crashes Blender. See the rule `always-free-bmesh`.

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

`do_unlink=True` removes the object from any collections it was linked into before deleting it. Skip it and Blender will refuse to delete an object still referenced.

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

7. **Wrong dtype in `foreach_set`** (`float64` instead of `float32`). Silently writes garbage on some platforms.

## Related

- `headless-batch-scripting` for using these patterns in CLI scripts
- `geometry-nodes-python` for programmatic GN tree construction
- Rule `prefer-data-over-ops-in-loops`
- Rule `always-free-bmesh`
- Snippet `canonical-object-creation.py`, `canonical-object-deletion.py`, `bmesh-load-edit-free.py`, `depsgraph-evaluated-mesh.py`, `foreach-set-vertices.py`

## References

- `bpy.types.Mesh`: https://docs.blender.org/api/current/bpy.types.Mesh.html
- `bmesh` module: https://docs.blender.org/api/current/bmesh.html
- `bmesh.ops`: https://docs.blender.org/api/current/bmesh.ops.html
- Depsgraph: https://docs.blender.org/api/current/bpy.types.Depsgraph.html
