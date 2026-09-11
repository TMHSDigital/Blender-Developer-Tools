---
name: ai-mesh-cleanup
description: Ordered cleanup for an imported generated mesh. Unit scale, transform apply, origin, normals, evaluated triangle count, decimate to budget, convex collider. Targets 5.2 LTS with 4.5 LTS fallback.
standards-version: 1.10.0
---

# AI Mesh Cleanup

## Trigger

Use this skill when the user:

- Has a generated or scanned GLB/glTF/FBX that is not engine-ready
- Mentions unit scale, unapplied transforms, triangle budget, LOD, or a collision hull
- Wants a headless cleanup pass (import in, cleaned mesh out)
- Is about to run mesh operators on an import without checking scale

This skill is the ordered pipeline. It composes `depsgraph-and-evaluated-data` and `mesh-editing-and-bmesh`; it does not replace them. It does not generate meshes and does not call any generation vendor.

## The core misunderstanding

An imported generated mesh is not a game asset. Typical residue: object scale not identity, scene units not meters, origin in the wrong place, inverted normals, triangle soup over budget, no collider. Running decimate or export on that state bakes the pathology in.

Do the cleanup in this order. Skipping a step makes later measurements lie.

## The canonical pattern

```python
import bmesh
import bpy


def imported_meshes():
    return [o for o in bpy.context.selected_objects if o.type == "MESH"]


def scene_units_are_meters(scene):
    units = scene.unit_settings
    if units.system not in {"METRIC", "NONE"}:
        return False
    return abs(units.scale_length - 1.0) < 1e-6


def scale_is_identity(obj, tol=1e-6):
    sx, sy, sz = obj.scale
    return abs(sx - 1.0) < tol and abs(sy - 1.0) < tol and abs(sz - 1.0) < tol


def apply_object_transform(obj):
    with bpy.context.temp_override(
        object=obj,
        active_object=obj,
        selected_objects=[obj],
    ):
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def origin_to_base(obj):
    mesh = obj.data
    n = len(mesh.vertices)
    flat = [0.0] * (n * 3)
    mesh.vertices.foreach_get("co", flat)
    min_z = min(flat[2::3])
    for i in range(n):
        flat[i * 3 + 2] -= min_z
    mesh.vertices.foreach_set("co", flat)
    mesh.update()
    obj.location.z += min_z


def recalc_normals(obj):
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
        obj.data.update()
    finally:
        bm.free()
```

Import, then those helpers, then budget and collider (snippets below).

### 1. Import

```python
bpy.ops.import_scene.gltf(filepath=path)
```

glTF import RNA has no `global_scale` on 4.5 LTS or 5.x. Scale after import lives on the object (`obj.scale`) and in `scene.unit_settings.scale_length`.

FBX does take a scale kwarg:

```python
bpy.ops.import_scene.fbx(filepath=path, global_scale=1.0)
```

Default `import_select_created_objects=True` leaves the new meshes selected. Iterate `imported_meshes()`; do not assume `context.active_object` is the only import.

### 2. Verify and correct unit scale

Blender's default is metric, `scale_length == 1.0` (meters). Generated files often arrive with `obj.scale` of 0.01 (centimeters written as meters) or a non-1.0 scene scale.

```python
scene = bpy.context.scene
if not scene_units_are_meters(scene):
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

for obj in imported_meshes():
    if not scale_is_identity(obj):
        apply_object_transform(obj)
```

`export_apply=True` on glTF applies **modifiers**, not object scale. Unapplied object scale lands on the glTF node. Witness: `examples/unapplied-scale-gltf/`.

### 3. Apply transforms

`transform_apply` needs a real object in context. Use `temp_override`, not `bpy.context.copy()`. After apply, `obj.scale` is `(1, 1, 1)` and `obj.data` vertex positions hold the world size.

### 4. Set origin

Origin at the lowest Z of the mesh (sit-on-ground) via `foreach_get` / `foreach_set`, not a Python loop on `mesh.vertices`. See `examples/prop-origin-transform/` for origin-to-base plus `matrix_parent_inverse`.

### 5. Recalculate normals

`Mesh.calc_normals()` was removed in Blender 4.0. On 4.5 LTS and 5.x, use `bmesh.ops.recalc_face_normals`. `bm.normal_update()` does not fix inward winding.

### 6. Measure evaluated triangle count

`obj.data` is the authored mesh. A DECIMATE modifier does not change `obj.data`. Count triangles on the evaluated mesh, and call `calc_loop_triangles()` first. Tessellation is not implicit on 4.5 or 5.x.

```python
def evaluated_triangle_count(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()
    try:
        eval_mesh.calc_loop_triangles()
        return len(eval_mesh.loop_triangles)
    finally:
        eval_obj.to_mesh_clear()
```

Always pair `to_mesh()` with `to_mesh_clear()`.

### 7. Decimate to budget

Add `DECIMATE` with `decimate_type='COLLAPSE'` and `ratio = min(1.0, target_tris / current)`. Return `None` when already under budget. The modifier is non-destructive; `obj.data` keeps the dense mesh. Witness: `examples/lod-decimate-chain/`.

Snippet: `snippets/decimate_to_budget.py`. LOD set from successive budgets: `snippets/lod_chain.py` (helper duplicated; snippets are not a package).

### 8. Generate collider

Convex hull via `bmesh.ops.convex_hull`, then delete `geom_interior` and `geom_unused`. Copy `matrix_world` onto the collider. Hull a coarse cage when the render mesh would blow a per-piece face budget. Witness: `examples/collision-hull-proxy/`.

Snippet: `snippets/convex_hull_collider.py`.

### Export (when shipping)

Draco, selected-only, explicit `export_yup`, and `export_apply=True` so the decimate modifier ships. Snippet: `snippets/gltf_draco_export.py`. glTF RNA has `export_yup`, not FBX `axis_forward` / `axis_up`.

## Common AI mistakes

1. **Decimate ratio against `len(obj.data.polygons)`**. That ignores modifiers already on the stack and counts n-gons as one. Use evaluated `loop_triangles`.
2. **Skipping `calc_loop_triangles()`**. `loop_triangles` can be empty or stale. Required on 4.5 LTS and 5.x.
3. **`export_apply=True` as "apply object transforms".** It applies modifiers excluding armatures. Apply object scale first.
4. **Hulling the dense render mesh.** Over budget. Hull a coarse cage.
5. **`bm.normal_update()` for flipped faces.** Use `recalc_face_normals`.
6. **Import then `bpy.ops.mesh.*` with no scale check.** Rule `validate-imported-mesh-scale`.
7. **Export with a live DECIMATE and `export_apply=False`.** The engine gets the dense mesh. Rule `no-unapplied-modifiers-on-export`.

## Version correctness

The cleanup sequence is the same on 4.5 LTS and 5.x:

- `Mesh.calc_loop_triangles()` is still required before `mesh.loop_triangles` on 4.5 LTS, 5.1, and 5.2. Not implicit. Verified: https://docs.blender.org/api/5.1/bpy.types.Mesh.html#bpy.types.Mesh.calc_loop_triangles and https://docs.blender.org/api/4.5/bpy.types.Mesh.html#bpy.types.Mesh.calc_loop_triangles. The 5.1 bmesh module still says tessellation "needs to be called explicitly": https://docs.blender.org/api/5.1/bmesh.html
- `Mesh.calc_normals()` is gone since 4.0. `bmesh.ops.recalc_face_normals` on both LTS lines.
- glTF import has no `global_scale` on either line. FBX does.
- `DecimateModifier.decimate_type='COLLAPSE'` and `ratio` are stable across 4.5 LTS and 5.x.

Branch on `bpy.app.version` only when an API actually diverges. Do not use `hasattr` as a substitute for checking the docs.

## Related

- Skill `depsgraph-and-evaluated-data` for `evaluated_get` / `to_mesh` / `to_mesh_clear`
- Skill `mesh-editing-and-bmesh` for bmesh load-edit-free
- Skill `headless-batch-scripting` for `temp_override` and argparse after `--`
- Rule `validate-imported-mesh-scale`
- Rule `no-unapplied-modifiers-on-export`
- Rule `always-free-bmesh`
- Snippet `snippets/decimate_to_budget.py`
- Snippet `snippets/convex_hull_collider.py`
- Snippet `snippets/lod_chain.py`
- Snippet `snippets/gltf_draco_export.py`
- Example `unapplied-scale-gltf` for object scale vs `export_apply`
- Example `lod-decimate-chain` for COLLAPSE ratio vs evaluated tris
- Example `collision-hull-proxy` for hull-from-cage vs hull-from-render
- Example `prop-origin-transform` for origin-to-base
- Example `mesh-hygiene-audit` for engine-ingest topology checks

## References

- `bpy.ops.import_scene.gltf`: https://docs.blender.org/api/current/bpy.ops.import_scene.html#bpy.ops.import_scene.gltf
- `bpy.ops.export_scene.gltf`: https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf
- `Mesh.calc_loop_triangles` (5.1): https://docs.blender.org/api/5.1/bpy.types.Mesh.html#bpy.types.Mesh.calc_loop_triangles
- `DecimateModifier`: https://docs.blender.org/api/current/bpy.types.DecimateModifier.html
- `bmesh.ops.convex_hull`: https://docs.blender.org/api/current/bmesh.ops.html#bmesh.ops.convex_hull
- `Object.evaluated_get`: https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.evaluated_get
