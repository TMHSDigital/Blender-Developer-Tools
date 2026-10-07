# Unreal presets. Unreal works in centimeters, but glTF is meters by spec
# and Unreal's glTF importer applies its own x100 (Interchange import_scale,
# default 100), so the glTF export stays in meters, +Y up (no bake; a baked
# file imports 100x too large). FBX is where the scale lives:
# global_scale=100.0 plus axis_forward='-Z' and axis_up='Y'. glTF and FBX
# do not share axis RNA; that split is the contract.
# Draco is glTF-only and opt-in; see snippets/gltf_draco_export.py.
#
# Assumption: scene units are meters (scale_length == 1.0).
#
# Reference:
#   https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf
#   https://docs.blender.org/api/current/bpy.ops.export_scene.html#bpy.ops.export_scene.fbx

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


def export_preset_unreal_gltf(filepath, selected_only=True, draco=False):
    # Meters, like every glTF; Unreal converts to cm on import.
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
