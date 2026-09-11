# Unity glTF preset: Y-up, meter scale, selected objects only.
# Apply object rotation and scale before export so they do not land on the
# glTF node. Axis is export_yup=True. glTF RNA has no axis_forward / axis_up.
# Draco is opt-in; see snippets/gltf_draco_export.py for the compression-only
# helper this does not duplicate.
#
# Assumption: scene units are meters (scale_length == 1.0).
#
# Reference:
#   https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf

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


def export_preset_unity(filepath, selected_only=True, draco=False):
    apply_selected_mesh_transforms()
    bpy.ops.export_scene.gltf(
        filepath=filepath,
        use_selection=selected_only,
        export_yup=True,
        export_apply=True,
        export_draco_mesh_compression_enable=draco,
        export_animations=False,
    )


if __name__ == "__main__":
    obj = bpy.context.active_object
    if obj is not None and obj.type == "MESH":
        obj.select_set(True)
        path = tempfile.NamedTemporaryFile(suffix=".glb", delete=False).name
        export_preset_unity(path)
        print(f"wrote {path}")
