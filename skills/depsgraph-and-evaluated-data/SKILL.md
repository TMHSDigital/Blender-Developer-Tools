---
name: depsgraph-and-evaluated-data
description: Read the actual evaluated geometry the user sees by going through the dependency graph rather than reading raw `obj.data`. Covers `evaluated_get`, `to_mesh`, `to_mesh_clear`, and the lifetime rules that prevent crashes and memory leaks. Targets Blender 5.1.
standards-version: 1.9.4
---

# Depsgraph and Evaluated Data

## Trigger

Use this skill when the user:

- Is writing an exporter, measurement script, or inspection tool
- Reports that "modifiers are missing from my export" or "the vertex positions don't match what I see"
- Mentions `evaluated_depsgraph_get`, `evaluated_get`, `to_mesh`, `to_mesh_clear`
- Reads from `obj.data.vertices` and gets unexpectedly raw geometry
- Needs final positions after armature deformation, shape keys, modifiers, or geometry nodes

## The core misunderstanding

`bpy.data.objects['Cube'].data.vertices` does not return what the user sees in the viewport. It returns the **mesh datablock as authored**, before any modifier, armature, shape key, or geometry nodes evaluation.

The viewport shows **evaluated** geometry: the result of running the full dependency graph. Anything that downstream code consumes (renderers, exporters, measurement tools) almost always wants the evaluated form, not the raw form.

```
authored mesh (obj.data)
        |
        v
  modifier stack
  shape keys
  armature deform
  geometry nodes
        |
        v
evaluated mesh (what you see)
```

## The canonical pattern

```python
import bpy


def get_evaluated_mesh(obj):
    """Return a temporary mesh datablock with all modifiers applied.

    The caller must call obj_eval.to_mesh_clear() when done to free the
    temporary mesh. Do not store this mesh; treat it as read-only and
    short-lived.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh_eval = obj_eval.to_mesh()
    return obj_eval, mesh_eval
```

Three steps:

1. **Get the depsgraph**. `bpy.context.evaluated_depsgraph_get()` returns the current depsgraph and forces an evaluation if anything is dirty. There is no "the depsgraph"; each scene has its own, and switching view layers gives you a different one.
2. **Evaluate the object**. `obj.evaluated_get(depsgraph)` returns an evaluated proxy. The proxy has `.data`, `.matrix_world`, etc. just like a normal object, but they reflect post-modifier state.
3. **Read the mesh**. `obj_eval.to_mesh()` returns a temporary mesh datablock. It is owned by the depsgraph and remains valid only until you call `obj_eval.to_mesh_clear()` or the depsgraph re-evaluates.

## The lifetime rule (critical)

Every `to_mesh()` must be paired with a `to_mesh_clear()`. If you skip the clear:

- The temporary mesh leaks for the lifetime of the depsgraph (typically the session)
- Repeated calls accumulate memory
- In some 5.x builds the next depsgraph evaluation crashes if too many temp meshes are outstanding

```python
obj_eval, mesh_eval = get_evaluated_mesh(obj)
try:
    for v in mesh_eval.vertices:
        process(v.co)
finally:
    obj_eval.to_mesh_clear()
```

Use `try/finally`. Do not rely on garbage collection; `bpy_struct` references do not trigger Python finalization.

## Worked example: a minimal OBJ-style exporter

This exporter writes vertex positions and triangle indices for the evaluated geometry of every selected mesh object. It applies all modifiers, armature deformation, and geometry nodes, and uses `obj.matrix_world` so positions are in world space.

```python
import bpy


def export_evaluated_geometry(filepath):
    depsgraph = bpy.context.evaluated_depsgraph_get()

    with open(filepath, 'w', encoding='utf-8') as f:
        vertex_offset = 1

        for obj in bpy.context.selected_objects:
            if obj.type != 'MESH':
                continue

            obj_eval = obj.evaluated_get(depsgraph)
            mesh_eval = obj_eval.to_mesh()
            try:
                mesh_eval.calc_loop_triangles()

                world_matrix = obj_eval.matrix_world
                for v in mesh_eval.vertices:
                    co = world_matrix @ v.co
                    f.write(f"v {co.x} {co.y} {co.z}\n")

                for tri in mesh_eval.loop_triangles:
                    indices = [tri.vertices[i] + vertex_offset for i in range(3)]
                    f.write(f"f {indices[0]} {indices[1]} {indices[2]}\n")

                vertex_offset += len(mesh_eval.vertices)
            finally:
                obj_eval.to_mesh_clear()

    print(f"Wrote {filepath}")
```

## Worked example: measuring deformed-armature vertex positions

```python
import bpy


def get_world_position(obj, vertex_index):
    """Return the world-space position of a vertex after armature deformation."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh_eval = obj_eval.to_mesh()
    try:
        local = mesh_eval.vertices[vertex_index].co
        return obj_eval.matrix_world @ local
    finally:
        obj_eval.to_mesh_clear()
```

## When to skip the depsgraph

Read raw `obj.data` directly when:

- You are editing the source mesh (modifying topology, adding shape keys, painting weights)
- The object has no modifiers and is not parented to an armature
- You explicitly want to ignore deformations (e.g., showing the rest pose)

For most read paths, prefer the depsgraph route. The cost is one indirection; the safety is enormous.

## `evaluation_mode` for exporters

The USD, Alembic, and OBJ exporters in 5.x accept an `evaluation_mode` parameter that controls how Blender evaluates the scene before exporting:

- `'RENDER'`: include render-only modifiers (subsurf at render levels, etc.). Use for final exports.
- `'VIEWPORT'`: use viewport modifier levels. Use for fast preview exports.

```python
bpy.ops.wm.usd_export(
    filepath="/tmp/scene.usdc",
    evaluation_mode='RENDER',
)
```

When you build your own exporter on top of `evaluated_depsgraph_get()`, the depsgraph defaults to viewport evaluation. Switch to render evaluation by getting the depsgraph from a temporary scene render context (advanced; for most cases the viewport depsgraph is fine).

## Common AI mistakes

- **Reading `obj.data.vertices` and calling it "what the user sees"**. It is not. This is the single most common AI exporter bug.
- **Forgetting `to_mesh_clear`**. The temporary mesh leaks. Cumulative leaks degrade Blender's memory headroom and can crash long-running batch jobs.
- **Storing `mesh_eval` past the cleanup point**. Once `to_mesh_clear` runs, the mesh datablock is freed. Any references become dangling.
- **Calling `evaluated_get` without the depsgraph argument**. The signature is `obj.evaluated_get(depsgraph)`; passing nothing raises a `TypeError`.
- **Treating `obj.data` as identical to `obj_eval.data`**. They are different mesh datablocks. The first is the source; the second is post-evaluation.
- **Using the raw object's `matrix_world` after evaluating**. `obj.matrix_world` and `obj_eval.matrix_world` may differ (parent constraints evaluate during depsgraph). Use `obj_eval.matrix_world` for world-space positions.
- **Calling `to_mesh()` inside a tight loop without clearing**. Each iteration leaks a temp mesh. Even with the right intent, this exhausts memory fast.

## Version correctness

The depsgraph API has been stable since 2.80. The patterns shown here work identically on 4.5 LTS and 5.1.

In 5.0 the underlying Animation 2025 work changed how armature evaluation interacts with the depsgraph in some edge cases (multi-data-block animation via slotted actions). For mesh deformation specifically, the API surface and behavior shown here are unchanged.

## See also

- Rule `prefer-data-over-ops-in-loops`: same principle, different motivation.
- Skill `mesh-editing-and-bmesh`: bmesh has its own load-edit-free contract.
- Snippet `depsgraph-evaluated-mesh.py` for the minimal copy-paste pattern.
- Snippet `usd-export-evaluation-mode.py` for the exporter parameter.

## References

- `bpy.types.Object.evaluated_get`: https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.evaluated_get
- `bpy.types.Object.to_mesh`: https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.to_mesh
- `bpy.types.Object.to_mesh_clear`: https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.to_mesh_clear
- `bpy.types.Depsgraph`: https://docs.blender.org/api/current/bpy.types.Depsgraph.html
- `bpy.context.evaluated_depsgraph_get`: https://docs.blender.org/api/current/bpy.context.html
