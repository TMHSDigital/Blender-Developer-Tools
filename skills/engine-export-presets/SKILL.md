---
name: engine-export-presets
description: Unity, Godot, and Unreal glTF/FBX export presets. glTF uses export_yup; FBX uses axis_forward/axis_up plus centimeter scale. Targets 5.2 LTS with 4.5 LTS fallback.
standards-version: 1.10.0
---

# Engine Export Presets

## Trigger

Use this skill when the user:

- Needs a Unity, Godot, or Unreal export from Blender Python
- Mentions Y-up, Z-up, centimeter scale, `export_yup`, `axis_forward`, or `axis_up`
- Is about to pass FBX axis kwargs to `bpy.ops.export_scene.gltf`
- Wants a headless preset the later `ai-asset-pipeline-template` can call

This skill is the export layer. It composes `ai-mesh-cleanup` (apply transforms, units), `depsgraph-and-evaluated-data` (`export_apply` ships evaluated mesh), and the `unapplied-scale-gltf` witness (`export_apply` does not bake object scale). It does not generate meshes.

## The core misunderstanding

glTF and FBX do not share axis RNA. `bpy.ops.export_scene.gltf` has `export_yup` (boolean, "+Y Up"). It does not have `axis_forward` or `axis_up`. `bpy.ops.export_scene.fbx` has `axis_forward` and `axis_up` (axis enums) and `global_scale`. It does not have `export_yup`. Passing the other exporter's kwargs is a TypeError or a silent no-op depending on how the call is built.

That split is the contract. Verified on current RNA:

- glTF: https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf (`export_yup`, no axis enums)
- FBX: https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.fbx (`axis_forward`, `axis_up`, `global_scale`)

## Shared prelude

Before any preset: meters in the scene (`scale_length == 1.0`), identity object scale via `transform_apply` through `temp_override`, `export_apply=True` / `use_mesh_modifiers=True` so modifiers ship. See `ai-mesh-cleanup` and `unapplied-scale-gltf`.

```python
def apply_selected_mesh_transforms():
    for obj in list(bpy.context.selected_objects):
        if obj.type != "MESH":
            continue
        with bpy.context.temp_override(
            object=obj, active_object=obj, selected_objects=[obj]
        ):
            bpy.ops.object.transform_apply(
                location=False, rotation=True, scale=True
            )
```

`use_selection=True` on every preset. Draco is opt-in on glTF; do not copy `gltf_draco_export.py` wholesale.

## Unity (Y-up, meters, glTF)

```python
bpy.ops.export_scene.gltf(
    filepath=path,
    use_selection=True,
    export_yup=True,
    export_apply=True,
    export_draco_mesh_compression_enable=draco,
    export_animations=False,
)
```

`export_yup=True` bakes `(x, y, z) -> (x, z, -y)` into POSITION with no node rotation. Witness: `examples/gltf-export-roundtrip/` and `examples/export-preset-axis/`.

Snippet: `snippets/export_preset_unity.py`.

## Godot (Z-up glTF, meters)

```python
bpy.ops.export_scene.gltf(
    filepath=path,
    use_selection=True,
    export_yup=False,
    export_apply=True,
    export_draco_mesh_compression_enable=draco,
    export_animations=False,
)
```

`export_yup=False` writes Blender Z-up POSITION. This preset is the Z-up interop path. It is not the Unity kwargs; if both used `export_yup=True` the files would match and the axis contract would be untestable.

Snippet: `snippets/export_preset_godot.py`.

## Unreal (centimeters)

glTF has no `global_scale`. Bake 100x (1 m -> 100 cm) onto the selected meshes, apply, then `export_yup=True`. That mutates the objects; copy first if the source must stay in meters.

FBX keeps the meter mesh and scales on the way out:

```python
bpy.ops.export_scene.fbx(
    filepath=path,
    use_selection=True,
    axis_forward="-Z",
    axis_up="Y",
    global_scale=100.0,
    apply_unit_scale=False,
    use_mesh_modifiers=True,
    bake_anim=False,
)
```

Do not pass `export_yup` to FBX. Do not pass `axis_forward` to glTF.

Snippet: `snippets/export_preset_unreal.py`.

## Common AI mistakes

1. **`export_scene.gltf(..., axis_forward="-Z", axis_up="Y")`.** Those names are FBX. Rule `use-correct-axis-rna-per-exporter`.
2. **`export_scene.fbx(..., export_yup=True)`.** Same rule, other direction.
3. **Skipping `transform_apply`.** `export_apply` is modifiers, not object scale. `examples/unapplied-scale-gltf/`.
4. **Unity and Godot as the same kwargs.** They differ on `export_yup`. `examples/export-preset-axis/` asserts the re-imported orientations diverge.
5. **Unreal glTF without the 100x bake.** glTF has no `global_scale`.

## Version correctness

Probed on 4.5 LTS, 5.1, and 5.2: `export_yup` on glTF and `axis_forward` / `axis_up` / `global_scale` on FBX are present on all three. No version branch for the axis kwargs. Guard by requiring those names in operator RNA so a future rename fails loudly, as `examples/gltf-export-roundtrip/` does.

`export_format` defaults differ by call site; pass the filepath suffix (`.glb` / `.gltf` / `.fbx`) and let the operator infer, or set `export_format` explicitly on glTF.

## Related

- Skill `ai-mesh-cleanup`
- Skill `depsgraph-and-evaluated-data`
- Rule `use-correct-axis-rna-per-exporter`
- Rule `no-unapplied-modifiers-on-export`
- Rule `validate-imported-mesh-scale`
- Snippet `snippets/export_preset_unity.py`
- Snippet `snippets/export_preset_godot.py`
- Snippet `snippets/export_preset_unreal.py`
- Snippet `snippets/gltf_draco_export.py`
- Example `export-preset-axis`
- Example `gltf-export-roundtrip`
- Example `unapplied-scale-gltf`

## References

- `bpy.ops.export_scene.gltf`: https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf
- `bpy.ops.export_scene.fbx`: https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.fbx
- glTF 5.1: https://docs.blender.org/api/5.1/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf
- FBX 5.1: https://docs.blender.org/api/5.1/bpy.ops.export_scene.html#bpy.ops.export_scene.fbx
