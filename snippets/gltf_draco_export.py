# glTF export with Draco compression, selected-objects-only, and an
# explicit axis flag. glTF RNA exposes axis as export_yup (boolean),
# not FBX-style axis_forward / axis_up. Pass export_yup explicitly.
# export_apply=True ships evaluated (modifier-applied) mesh data.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf

import tempfile

import bpy


def export_gltf_draco(filepath, selected_only=True, yup=True):
    bpy.ops.export_scene.gltf(
        filepath=filepath,
        use_selection=selected_only,
        export_draco_mesh_compression_enable=True,
        export_draco_mesh_compression_level=6,
        export_yup=yup,
        export_apply=True,
    )


if __name__ == "__main__":
    obj = bpy.context.active_object
    if obj is not None and obj.type == "MESH":
        obj.select_set(True)
        path = tempfile.NamedTemporaryFile(suffix=".glb", delete=False).name
        export_gltf_draco(path)
        print(f"wrote {path}")
