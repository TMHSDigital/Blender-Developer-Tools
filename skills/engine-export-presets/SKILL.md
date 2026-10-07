---
name: engine-export-presets
description: "Export presets for Unity, Godot and Unreal. glTF is +Y up and meters by spec, so every engine gets export_yup=True with no scale bake (Unreal converts to centimeters on import); FBX takes axis_forward/axis_up plus global_scale. Use when the user exports for a game engine, mentions export_yup, axis_forward, axis_up, global_scale, Y-up or centimeters, passes FBX axis kwargs to export_scene.gltf, or gets a model that imports lying on its back or 100x too large. Targets 5.2 LTS with 4.5 LTS fallback."
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
    # One operator call for the whole selection. transform_apply reads
    # selected_editable_objects, so that is the key to override. It refuses
    # shared (glTF-instanced) mesh data, so copy it per object first, and
    # unparent keeping the world placement, or a rotated root stays on the node.
    meshes = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    if not meshes:
        return
    for o in meshes:
        if o.data.users > 1:
            o.data = o.data.copy()
        if o.parent is not None:
            world = o.matrix_world.copy()
            o.parent = None
            o.matrix_world = world
    with bpy.context.temp_override(
        object=meshes[0], active_object=meshes[0], selected_editable_objects=meshes
    ):
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
```

The two guards are for ordinary imports. Instanced glTF nodes come back as several objects sharing one Mesh, and `transform_apply` then raises `Cannot apply to a multi user` (4.5.11 and 5.2.1). A mesh under a rotated root has an identity `matrix_basis`. Applying it leaves the root's rotation in `matrix_world`, and `use_selection=True` writes that rotation onto the exported node. Copying the data means instances no longer share one mesh. That is the cost of baking transforms into vertices.

`use_selection=True` on every preset. Draco is opt-in on glTF; do not copy `gltf_draco_export.py` wholesale.

## glTF is the same for every engine

The glTF 2.0 spec fixes the coordinate system: **+Y up, right-handed, units in meters**. Unity, Godot and Unreal all import glTF against that spec, so the correct glTF export is the same call for all three: `export_yup=True`, meters, transforms applied. The engines differ in what they do on import (Unreal converts meters to centimeters itself; Godot reads node-name import hints), not in the file you should write.

## Unity (Y-up, meters, glTF)

```python
bpy.ops.export_scene.gltf(
    filepath=path,
    export_format="GLB",
    use_selection=True,
    export_yup=True,
    export_apply=True,
    export_draco_mesh_compression_enable=draco,
    export_animations=False,
)
```

`export_yup=True` bakes `(x, y, z) -> (x, z, -y)` into POSITION with no node rotation. Witness: [`examples/gltf-export-roundtrip/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/gltf-export-roundtrip) and [`examples/export-preset-axis/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/export-preset-axis).

Snippet: [`snippets/export_preset_unity.py`](${CLAUDE_PLUGIN_ROOT}/snippets/export_preset_unity.py).

## Godot (Y-up glTF, meters)

Godot is right-handed and Y-up, and its importer reads glTF as the spec says. The export is the Unity call: `export_yup=True`, meters, `.glb`. What is Godot-specific happens on import, through **node-name suffixes** the importer reads as hints: a mesh named `Crate-convcolonly` becomes a convex collision shape with no visible mesh, `-colonly` a trimesh collision shape, `-col` / `-convcol` add collision to a visible mesh, and `-rigid` makes a rigid body. Name the collider object accordingly before export instead of changing axes. See Godot's [node type customization](https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/node_type_customization.html) docs.

`export_yup=False` is **wrong for Godot**, as for every glTF consumer: it writes Blender's Z-up POSITION into a file the importer reads as Y-up, so the model arrives rotated -90° about X (lying on its back). [`examples/export-preset-axis/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/export-preset-axis) measures exactly that.

Snippet: [`snippets/export_preset_godot.py`](${CLAUDE_PLUGIN_ROOT}/snippets/export_preset_godot.py).

## Unreal (centimeters)

Unreal works in centimeters, but **do not bake 100x into a glTF**. glTF units are meters by spec, and Unreal's glTF importer (Interchange) applies its own meters-to-centimeters conversion (`import_scale`, default 100). A 1 m crate exported with a 100x bake imports 100 m wide. Export Unreal glTF exactly like Unity: `export_yup=True`, meters.

FBX is where Unreal needs explicit axis and scale kwargs. It keeps the meter mesh and scales on the way out:

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

Snippet: [`snippets/export_preset_unreal.py`](${CLAUDE_PLUGIN_ROOT}/snippets/export_preset_unreal.py).

## Common AI mistakes

1. **`export_scene.gltf(..., axis_forward="-Z", axis_up="Y")`.** Those names are FBX. Rule `use-correct-axis-rna-per-exporter`.
2. **`export_scene.fbx(..., export_yup=True)`.** Same rule, other direction.
3. **Skipping `transform_apply`.** `export_apply` is modifiers, not object scale. [`examples/unapplied-scale-gltf/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/unapplied-scale-gltf).
4. **`export_yup=False` for any engine.** glTF is Y-up by spec; a Z-up file imports lying on its back in Unity, Godot and Unreal alike. [`examples/export-preset-axis/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/export-preset-axis) re-imports both and measures the -90° tilt.
5. **Baking 100x into an Unreal glTF.** glTF is meters by spec and Unreal's glTF importer already scales by 100 on import, so a baked file lands 100x too large. The 100x belongs on the FBX path (`global_scale`).
6. **Changing axes to express engine differences.** Engine-specific behaviour for glTF lives in import settings and node names (Godot `-convcolonly`, `-rigid`), not in `export_yup`.

## Version correctness

Probed on 4.5 LTS, 5.1, and 5.2: `export_yup` on glTF and `axis_forward` / `axis_up` / `global_scale` on FBX are present on all three. No version branch for the axis kwargs. Guard by requiring those names in operator RNA so a future rename fails loudly, as [`examples/gltf-export-roundtrip/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/gltf-export-roundtrip) does.

Always pass `export_format` on glTF and make the filepath suffix match it. The operator does **not** infer the format from the suffix: `export_scene.gltf(filepath="x.gltf")` with no `export_format` writes a binary `x.glb`, so the requested path never exists (measured on 4.5.11 and 5.2.1). Use `export_format="GLB"` with `.glb`, or `"GLTF_SEPARATE"` with `.gltf`.

## Related

- Skill `ai-mesh-cleanup`
- Skill `depsgraph-and-evaluated-data`
- Rule `use-correct-axis-rna-per-exporter`
- Rule `no-unapplied-modifiers-on-export`
- Rule `validate-imported-mesh-scale`
- Snippet [`snippets/export_preset_unity.py`](${CLAUDE_PLUGIN_ROOT}/snippets/export_preset_unity.py)
- Snippet [`snippets/export_preset_godot.py`](${CLAUDE_PLUGIN_ROOT}/snippets/export_preset_godot.py)
- Snippet [`snippets/export_preset_unreal.py`](${CLAUDE_PLUGIN_ROOT}/snippets/export_preset_unreal.py)
- Snippet [`snippets/gltf_draco_export.py`](${CLAUDE_PLUGIN_ROOT}/snippets/gltf_draco_export.py)
- Example `export-preset-axis`
- Example `gltf-export-roundtrip`
- Example `unapplied-scale-gltf`

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`export-preset-axis`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/export-preset-axis): A radio mast exported once with the engine glTF preset (export_yup=True, shared by Unity, Godot and Unreal) and once naively Z-up, then re-imported: the Z-up file lies on its back Falsify: `--same-axis` (exit 9).
- [`gltf-export-roundtrip`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/gltf-export-roundtrip): A sci-fi supply crate exported to glTF and re-imported, verifying the round-trip against the depsgraph-evaluated mesh within float tolerances. Falsify: `--no-yup` (exit 9).
- [`gltf-skin-roundtrip`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/gltf-skin-roundtrip): A rigged mech scorpion exported to glTF with skins and re-imported, verifying the skinning contract the geometry round-trip left uncovered. Falsify: `--no-skins` (exit 5).
- [`unapplied-scale-gltf`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/unapplied-scale-gltf): Synthesizes unapplied non-uniform object scale on a unit cube, then asserts the glTF exporter contract. Falsify: `--identity` (exit 3).

<!-- examples:end -->

## References

- `bpy.ops.export_scene.gltf`: https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf
- `bpy.ops.export_scene.fbx`: https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.fbx
- glTF 5.1: https://docs.blender.org/api/5.1/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf
- FBX 5.1: https://docs.blender.org/api/5.1/bpy.ops.export_scene.html#bpy.ops.export_scene.fbx
