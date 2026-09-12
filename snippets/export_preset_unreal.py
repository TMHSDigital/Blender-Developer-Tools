# Unreal presets: centimeter scale. glTF has no global_scale and no
# axis_forward / axis_up; bake 100x then export_yup=True. FBX uses
# global_scale=100.0 plus axis_forward='-Z' and axis_up='Y'. That RNA
# split is the contract. glTF bake mutates selected mesh objects.
# Draco is glTF-only and opt-in; see snippets/gltf_draco_export.py.
#
# Assumption: scene units are meters before the 100x bake / FBX scale.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf
#   https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.fbx

import tempfile

import bpy


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


def export_preset_unreal_gltf(filepath, selected_only=True, draco=False):
    apply_selected_mesh_transforms()
    for obj in list(bpy.context.selected_objects):
        if obj.type != "MESH":
            continue
        obj.scale = (obj.scale[0] * 100.0, obj.scale[1] * 100.0, obj.scale[2] * 100.0)
    apply_selected_mesh_transforms()
    bpy.ops.export_scene.gltf(
        filepath=filepath,
        use_selection=selected_only,
        export_yup=True,
        export_apply=True,
        export_draco_mesh_compression_enable=draco,
        export_animations=False,
    )


def export_preset_unreal_fbx(filepath, selected_only=True):
    apply_selected_mesh_transforms()
    bpy.ops.export_scene.fbx(
        filepath=filepath,
        use_selection=selected_only,
        axis_forward="-Z",
        axis_up="Y",
        global_scale=100.0,
        apply_unit_scale=False,
        use_mesh_modifiers=True,
        bake_anim=False,
    )


if __name__ == "__main__":
    obj = bpy.context.active_object
    if obj is not None and obj.type == "MESH":
        obj.select_set(True)
        path = tempfile.NamedTemporaryFile(suffix=".fbx", delete=False).name
        export_preset_unreal_fbx(path)
        print(f"wrote {path}")
