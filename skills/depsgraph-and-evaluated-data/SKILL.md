---
name: depsgraph-and-evaluated-data
description: "Read the evaluated geometry the user actually sees through the dependency graph instead of raw obj.data: evaluated_depsgraph_get, evaluated_get, to_mesh and to_mesh_clear lifetimes. Use when the user writes an exporter, measurement or inspection script, reports that modifiers, shape keys, armatures or geometry nodes are missing from exported or measured geometry, or reads obj.data.vertices and gets the undeformed base mesh. Targets 5.2 LTS."
standards-version: 1.10.0
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

Every `to_mesh()` must be paired with a `to_mesh_clear()`. One temporary mesh is held per evaluated object until `to_mesh_clear()` or re-evaluation. A second `to_mesh()` on the same object frees the previous temporary mesh and returns a fresh one, so the earlier Python reference raises `ReferenceError` (measured on 4.5.11 and 5.2.1). A missing clear therefore does not multiply per call on one object. Looping over *many objects* without clearing holds one per object. If you skip the clear:

- That temporary mesh stays allocated until the object is re-evaluated or freed, once per evaluated object you touched (a whole-scene exporter holds a full copy of every mesh)
- Code that keeps using the mesh after the next depsgraph update reads freed data; clearing at a known point makes the lifetime explicit

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

## Evaluation mode for exporters

The USD and Alembic exporters take `evaluation_mode`; the OBJ exporter's equivalent is `export_eval_mode` with different values. Passing `evaluation_mode=` to `wm.obj_export` raises `TypeError`.

| Exporter | Parameter | Values | Default |
| --- | --- | --- | --- |
| `wm.usd_export` | `evaluation_mode` | `'RENDER'`, `'VIEWPORT'` | `'RENDER'` |
| `wm.alembic_export` | `evaluation_mode` | `'RENDER'`, `'VIEWPORT'` | `'RENDER'` |
| `wm.obj_export` | `export_eval_mode` | `'DAG_EVAL_RENDER'`, `'DAG_EVAL_VIEWPORT'` | `'DAG_EVAL_VIEWPORT'` |

- Render: modifiers at render levels (subsurf `render_levels`, render-only modifiers). Use for final exports.
- Viewport: modifiers at viewport levels. Use for fast preview exports.

Note the OBJ default is the opposite of USD's.

Default `export_subdivision='BEST_MATCH'` writes the **cage** plus
`subdivisionScheme = catmullClark`. VIEWPORT and RENDER files are then
identical — `evaluation_mode` is silent. Pass `export_subdivision='TESSELLATE'`
to make the mode observable. Catmull-Clark on a cube is closed form:
verts = `2 + 6 × 4^n` (n=1 → 26, n=2 → 98).

```python
bpy.ops.wm.usd_export(
    filepath="/tmp/scene.usdc",
    evaluation_mode='RENDER',
    export_subdivision='TESSELLATE',
)
```

When you build your own exporter on top of `evaluated_depsgraph_get()`, the depsgraph defaults to viewport evaluation. Switch to render evaluation by getting the depsgraph from a temporary scene render context (advanced; for most cases the viewport depsgraph is fine).

## Common AI mistakes

- **Reading `obj.data.vertices` and calling it "what the user sees"**. It is not. This is the single most common AI exporter bug.
- **Forgetting `to_mesh_clear`**. Each evaluated object keeps its temporary mesh until it is re-evaluated or freed. Across a whole-scene export that is a second copy of every mesh held at once.
- **Storing `mesh_eval` past the cleanup point**. Once `to_mesh_clear` runs, the mesh datablock is freed. Any references become dangling.
- **Calling `evaluated_get` without the depsgraph argument**. The signature is `obj.evaluated_get(depsgraph)`; passing nothing raises a `TypeError`.
- **Treating `obj.data` as identical to `obj_eval.data`**. They are different mesh datablocks. The first is the source; the second is post-evaluation.
- **Using the raw object's `matrix_world` after evaluating**. `obj.matrix_world` and `obj_eval.matrix_world` may differ (parent constraints evaluate during depsgraph). Use `obj_eval.matrix_world` for world-space positions.
- **Looping over many objects with `to_mesh()` and no clear**. One temporary mesh is held per evaluated object until `to_mesh_clear()` or re-evaluation, so a scene-wide loop ends up holding an evaluated copy of every mesh at once. Repeated calls on the *same* object do not stack; each frees the previous one.
- **USD `evaluation_mode` without `export_subdivision='TESSELLATE'`**. Default `BEST_MATCH` writes the cage plus `subdivisionScheme = catmullClark`, so RENDER and VIEWPORT files match and the mode looks like a no-op.
- **`export_apply=True` as "apply object transforms".** RNA is "Apply modifiers (excluding Armatures) to mesh objects". Unapplied non-uniform object scale lands on the glTF node, Y-up permuted `(sx, sz, sy)`; POSITION stays local. Witness: [`examples/unapplied-scale-gltf/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/unapplied-scale-gltf).

## Version correctness

The depsgraph API has been stable since 2.80. The patterns shown here work identically on 4.5 LTS and 5.1.

In 5.0 the underlying Animation 2025 work changed how armature evaluation interacts with the depsgraph in some edge cases (multi-data-block animation via slotted actions). For mesh deformation specifically, the API surface and behavior shown here are unchanged.

## See also

- Rule `prefer-data-over-ops-in-loops`: same principle, different motivation.
- Skill `mesh-editing-and-bmesh`: bmesh has its own load-edit-free contract.
- Snippet `depsgraph-evaluated-mesh.py` for the minimal copy-paste pattern.
- Snippet `usd-export-evaluation-mode.py` for the exporter parameter.
- Example `usd-export-evaluation-mode` for the TESSELLATE closed form versus the BEST_MATCH cage.
- Example `unapplied-scale-gltf` for object scale vs `export_apply` (modifiers only).

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`armature-bend`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/armature-bend): Rigging end to end in the data API — edit_bones chain construction, name-bound vertex groups with smoothstep blend zones, posing, and depsgraph evaluation. Falsify: `--zero-curl` (exit 8).
- [`boolean-exact-volume`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/boolean-exact-volume): The Boolean modifier on the EXACT solver. Falsify: `--float-solver` (exit 3).
- [`car-mirror-symmetry`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/car-mirror-symmetry): A stylized hatchback lofted as one half (52 stations, 13-point rings) and completed by the Mirror modifier, evaluated through the depsgraph. Falsify: `--no-mirror` (exit 5).
- [`depsgraph-export`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/depsgraph-export): The depsgraph lifetime contract — evaluated_get().to_mesh() paired with to_mesh_clear() — measured against an OBJ export of the same object. Falsify: `--unevaluated` (exit 5).
- [`eval-mesh-datablock-name`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/eval-mesh-datablock-name): Pathology witness for the 5.2 change in `Object.evaluated_get(depsgraph).data.name`. Falsify: `--assume-distinct-names` (exit 6).
- [`gltf-export-roundtrip`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/gltf-export-roundtrip): A sci-fi supply crate exported to glTF and re-imported, verifying the round-trip against the depsgraph-evaluated mesh within float tolerances. Falsify: `--no-yup` (exit 9).
- [`gltf-skin-roundtrip`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/gltf-skin-roundtrip): A rigged mech scorpion exported to glTF with skins and re-imported, verifying the skinning contract the geometry round-trip left uncovered. Falsify: `--no-skins` (exit 5).
- [`lattice-deform`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/lattice-deform): A 2x2x2 Lattice modifier set to KEY_LINEAR on all three axes, with two top control points moved through LatticePoint.co_deform, read back through the depsgraph (evaluated_get, to_mesh, to_mesh_clear). Falsify: `--bspline` (exit 4).
- [`lod-decimate-chain`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/lod-decimate-chain): A retro rocket at LOD0/1/2 via the Decimate modifier evaluated through the depsgraph, with a wireframe of each evaluated mesh. Falsify: `--no-decimate` (exit 6).
- [`ray-cast-space`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/ray-cast-space): Object.ray_cast is object-local while Scene.ray_cast is world space. Falsify: `--world-to-object` (exit 4).
- [`soccer-ball-goldberg`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/soccer-ball-goldberg): A soccer ball as a Goldberg polyhedron: a bmesh icosphere truncated at 1/3 per edge, faces ordered by link-topology walks, panels bound by face vertex count. Falsify: `--invert-bind` (exit 13).
- [`solidify-even-thickness`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/solidify-even-thickness): Solidify's use_even_offset on a folded strip. Falsify: `--no-even` (exit 4).
- [`usd-export-evaluation-mode`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/usd-export-evaluation-mode): The USD exporter evaluation_mode chooses viewport versus render modifier quality. Falsify: `--subdivision BEST_MATCH` (exit 4).

<!-- examples:end -->

## References

- `bpy.types.Object.evaluated_get`: https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.evaluated_get
- `bpy.types.Object.to_mesh`: https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.to_mesh
- `bpy.types.Object.to_mesh_clear`: https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.to_mesh_clear
- `bpy.types.Depsgraph`: https://docs.blender.org/api/current/bpy.types.Depsgraph.html
- `bpy.context.evaluated_depsgraph_get`: https://docs.blender.org/api/current/bpy.context.html
