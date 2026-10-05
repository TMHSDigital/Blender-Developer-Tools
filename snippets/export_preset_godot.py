# Godot glTF preset: +Y up, meter scale, selected objects only.
# Godot is right-handed Y-up and reads glTF per the spec (+Y up, meters), so
# the export is the same call as the Unity preset: export_yup=True. A Z-up
# file (export_yup=False) imports rotated -90 deg about X.
# Godot-specific behaviour is set by node-name import hints instead: name a
# collider "<name>-convcolonly" (convex shape, no mesh) or "-colonly".
# Draco is opt-in; see snippets/gltf_draco_export.py.
#
# Assumption: scene units are meters (scale_length == 1.0).
#
# Reference:
#   https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf

import tempfile

import bpy


def apply_selected_mesh_transforms():
    # One operator call for the whole selection. transform_apply reads
    # selected_editable_objects, so that is the key to override; overriding
    # selected_objects alone does not narrow it.
    meshes = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    if not meshes:
        return
    with bpy.context.temp_override(
        object=meshes[0], active_object=meshes[0], selected_editable_objects=meshes
    ):
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def export_preset_godot(filepath, selected_only=True, draco=False):
    apply_selected_mesh_transforms()
    bpy.ops.export_scene.gltf(
        filepath=filepath,
        export_format="GLB",
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
        export_preset_godot(path)
        print(f"wrote {path}")
