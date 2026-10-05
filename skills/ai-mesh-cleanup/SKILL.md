---
name: ai-mesh-cleanup
description: "Ordered cleanup for an imported generated or scanned mesh before it goes to an engine: scene units, apply rotation and scale, origin to base, recalculate normals, evaluated triangle count, decimate to a budget, convex collider. Use when the user has a GLB, glTF or FBX that is not engine-ready, mentions unit scale, unapplied transforms, triangle budget, LODs or a collision hull, or is about to run mesh operations on an import without checking its scale. Targets 5.2 LTS with 4.5 LTS fallback."
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


def rot_scale_is_identity(obj, tol=1e-6):
    # Rotation and scale both: origin_to_base() shifts along local Z, which is
    # world Z only once rotation is applied. A GLB node often carries a
    # rotation with identity scale.
    m = obj.matrix_basis.to_3x3()
    return all(
        abs(m[i][j] - (1.0 if i == j else 0.0)) < tol
        for i in range(3)
        for j in range(3)
    )


def apply_transforms(objs):
    # One operator call for the whole list. transform_apply acts on
    # selected_editable_objects, so that is the key to override; overriding
    # selected_objects alone does not narrow it.
    if not objs:
        return
    with bpy.context.temp_override(
        object=objs[0],
        active_object=objs[0],
        selected_editable_objects=list(objs),
    ):
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def origin_to_base(obj):
    # Precondition: rotation and scale applied (local Z == world Z).
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

apply_transforms([o for o in imported_meshes() if not rot_scale_is_identity(o)])
```

`export_apply=True` on glTF applies **modifiers**, not object scale. Unapplied object scale lands on the glTF node. Witness: [`examples/unapplied-scale-gltf/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/unapplied-scale-gltf).

### 3. Apply transforms

`transform_apply` needs a real object in context. Use `temp_override`, not `bpy.context.copy()`. After apply, `obj.scale` is `(1, 1, 1)`, rotation is zero, and `obj.data` vertex positions hold the world size and orientation.

Gate the apply on rotation **and** scale (`rot_scale_is_identity`). Imported glTF nodes often carry a rotation with identity scale; skipping the apply then makes step 4 ground the mesh along its local Z, which moves it in world space (a cube rotated 90° on X at z=5 shifted by −1 in Y and Z).

### 4. Set origin

Origin at the lowest Z of the mesh (sit-on-ground) via `foreach_get` / `foreach_set`, not a Python loop on `mesh.vertices`. This works in local space, so run it only after step 3. See [`examples/prop-origin-transform/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/prop-origin-transform) for origin-to-base plus `matrix_parent_inverse`.

### 5. Recalculate normals

`Mesh.calc_normals()` was removed in Blender 4.0. On 4.5 LTS and 5.x, use `bmesh.ops.recalc_face_normals`. `bm.normal_update()` does not fix inward winding.

### 6. Measure evaluated triangle count

`obj.data` is the authored mesh. A DECIMATE modifier does not change `obj.data`. Count triangles on the evaluated mesh. On 4.5 and 5.x `Mesh.loop_triangles` is computed lazily from the current topology, so `calc_loop_triangles()` is optional (harmless; it matters only on much older builds).

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

Add `DECIMATE` with `decimate_type='COLLAPSE'` and `ratio = min(1.0, target_tris / current)`. Return `None` when already under budget. The modifier is non-destructive; `obj.data` keeps the dense mesh. Witness: [`examples/lod-decimate-chain/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/lod-decimate-chain).

Snippet: [`snippets/decimate_to_budget.py`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/snippets/decimate_to_budget.py). LOD set from successive budgets: [`snippets/lod_chain.py`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/snippets/lod_chain.py) (helper duplicated; snippets are not a package).

### 8. Generate collider

Convex hull via `bmesh.ops.convex_hull` over the points only: remove the source edges first (`bm.edges.remove`, which keeps the verts), hull, then delete verts left with no faces. Hulling a mesh that still has faces keeps every source face lying on the hull, so a cube collider comes out with 18 faces and 12 non-manifold edges instead of 12 closed triangles. Copy `matrix_world` onto the collider. Hull a coarse cage when the render mesh would blow a per-piece face budget. Witness: [`examples/collision-hull-proxy/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/collision-hull-proxy).

Snippet: [`snippets/convex_hull_collider.py`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/snippets/convex_hull_collider.py).

### Export (when shipping)

Draco, selected-only, explicit `export_yup`, and `export_apply=True` so the decimate modifier ships. Snippet: [`snippets/gltf_draco_export.py`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/snippets/gltf_draco_export.py). glTF RNA has `export_yup`, not FBX `axis_forward` / `axis_up`.

## Common AI mistakes

1. **Decimate ratio against `len(obj.data.polygons)`**. That ignores modifiers already on the stack and counts n-gons as one. Use evaluated `loop_triangles`.
2. **Counting triangles on `obj.data`** instead of the evaluated mesh. A DECIMATE modifier does not change `obj.data`, so the count ignores the budget you just applied.
3. **`export_apply=True` as "apply object transforms".** It applies modifiers excluding armatures. Apply object scale first.
4. **Hulling the dense render mesh.** Over budget. Hull a coarse cage.
5. **`bm.normal_update()` for flipped faces.** Use `recalc_face_normals`.
6. **Import then `bpy.ops.mesh.*` with no scale check.** Rule `validate-imported-mesh-scale`.
7. **Export with a live DECIMATE and `export_apply=False`.** The engine gets the dense mesh. Rule `no-unapplied-modifiers-on-export`.

## Version correctness

The cleanup sequence is the same on 4.5 LTS and 5.x:

- `Mesh.loop_triangles` is lazily computed on 4.5 LTS and 5.x: measured on 4.5.11 and 5.2.1, a fresh cube reads 12 without `calc_loop_triangles()`, as do a `to_mesh()` result and a mesh rewritten by bmesh. The "needs to be called explicitly" note in the bmesh docs is about `BMesh.calc_loop_triangles()`, the bmesh-side tessellation, not `Mesh.loop_triangles`.
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
- Snippet [`snippets/decimate_to_budget.py`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/snippets/decimate_to_budget.py)
- Snippet [`snippets/convex_hull_collider.py`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/snippets/convex_hull_collider.py)
- Snippet [`snippets/lod_chain.py`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/snippets/lod_chain.py)
- Snippet [`snippets/gltf_draco_export.py`](https://github.com/TMHSDigital/Blender-Developer-Tools/blob/main/snippets/gltf_draco_export.py)
- Example `unapplied-scale-gltf` for object scale vs `export_apply`
- Example `lod-decimate-chain` for COLLAPSE ratio vs evaluated tris
- Example `collision-hull-proxy` for hull-from-cage vs hull-from-render
- Example `prop-origin-transform` for origin-to-base
- Example `mesh-hygiene-audit` for engine-ingest topology checks

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`coincident-vert-weld`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/coincident-vert-weld): Synthesizes two cubes occupying the same space as one mesh, then asserts the duplicates exist before asserting they cross glTF export. Falsify: `--no-duplicate` (exit 3).
- [`collision-hull-proxy`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/collision-hull-proxy): A fire hydrant street prop inside its compound collision shell: four convex pieces hulled by bmesh.ops.convex_hull from a coarse inflated cage. Falsify: `--shrink-hull` (exit 3).
- [`degenerate-bevel-weld`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/degenerate-bevel-weld): Bevel offset >= half the min box dimension collapses the band into zero-area faces — and they ship: a stdlib GLB re-parse counts the degenerate triangles crossing the export boundary. Falsify: `--both-safe` (exit 4).
- [`lod-decimate-chain`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/lod-decimate-chain): A retro rocket at LOD0/1/2 via the Decimate modifier evaluated through the depsgraph, with a wireframe of each evaluated mesh. Falsify: `--no-decimate` (exit 6).
- [`mesh-hygiene-audit`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/mesh-hygiene-audit): Engine-ingest mesh hygiene on every part of a flanged street valve: no ngons, no loose verts, manifold edges, no zero-area faces, contiguous and outward winding, Euler V-E+F==2 on the body casting. Falsify: `--inject ngon` (exit 3).
- [`modular-kit-snap`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/modular-kit-snap): A tiling corridor kit whose open-end boundary verts snap to the tile grid, so instances at 4 m multiples join with zero gap or overlap. Falsify: `--seam-gap` (exit 5).
- [`ngon-triangulate`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/ngon-triangulate): Synthesizes one hexagon by dissolving a cube edge, then asserts the hygiene / tangent contracts on that defective mesh. Falsify: `--no-dissolve` (exit 3).
- [`prop-origin-transform`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/prop-origin-transform): Street pedestal origin-to-base-center + data-API scale apply + matrix_parent_inverse for a flanged conduit elbow. Falsify: `--skip-mpi` (exit 8).
- [`unapplied-scale-gltf`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/unapplied-scale-gltf): Synthesizes unapplied non-uniform object scale on a unit cube, then asserts the glTF exporter contract. Falsify: `--identity` (exit 3).

<!-- examples:end -->

## References

- `bpy.ops.import_scene.gltf`: https://docs.blender.org/api/current/bpy.ops.import_scene.html#bpy.ops.import_scene.gltf
- `bpy.ops.export_scene.gltf`: https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf
- `Mesh.calc_loop_triangles` (5.1): https://docs.blender.org/api/5.1/bpy.types.Mesh.html#bpy.types.Mesh.calc_loop_triangles
- `DecimateModifier`: https://docs.blender.org/api/current/bpy.types.DecimateModifier.html
- `bmesh.ops.convex_hull`: https://docs.blender.org/api/current/bmesh.ops.html#bmesh.ops.convex_hull
- `Object.evaluated_get`: https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.evaluated_get
