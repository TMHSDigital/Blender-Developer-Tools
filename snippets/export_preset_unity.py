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


def export_preset_unity(filepath, selected_only=True, draco=False):
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
        export_preset_unity(path)
        print(f"wrote {path}")
