# Cross-version channelbag access for Slotted Actions.
#
# The Slotted Actions data model (Action -> Layers -> Strips -> Channelbags,
# with F-curves living inside a Channelbag keyed by an animation slot) shipped
# in Blender 4.4. Two version paths, branched on bpy.app.version below:
#   - 5.0+: legacy action.fcurves was removed; use the new
#     bpy_extras.anim_utils.action_ensure_channelbag_for_slot(action, slot).
#   - 4.4 / 4.5 LTS: that ensure-helper does NOT exist (no shim). The legacy
#     action.fcurves API is still present, so use it directly.
#
# Verified on Blender 4.5.10 LTS and 5.1.1. Import path (5.0+):
#
# Reference:
#   https://docs.blender.org/api/current/bpy_extras.anim_utils.html
#   https://developer.blender.org/docs/release_notes/5.0/python_api/

import bpy
from bpy_extras import anim_utils


def add_z_keyframe(obj, frame=1, value=0.0):
    if obj.animation_data is None:
        obj.animation_data_create()

    action = obj.animation_data.action
    if action is None:
        action = bpy.data.actions.new(name=f"{obj.name}_Action")
        obj.animation_data.action = action

    if bpy.app.version >= (5, 0, 0):
        slot = obj.animation_data.action_slot
        if slot is None:
            slot = action.slots.new(id_type='OBJECT', name=obj.name)
            obj.animation_data.action_slot = slot
        channelbag = anim_utils.action_ensure_channelbag_for_slot(action, slot)
        fcurve = channelbag.fcurves.find(data_path="location", index=2)
        if fcurve is None:
            fcurve = channelbag.fcurves.new(data_path="location", index=2)
    else:
        fcurve = action.fcurves.find(data_path="location", index=2)
        if fcurve is None:
            fcurve = action.fcurves.new(data_path="location", index=2)

    fcurve.keyframe_points.insert(frame, value)
    fcurve.update()


if __name__ == "__main__":
    obj = bpy.context.active_object
    if obj is not None:
        add_z_keyframe(obj, frame=1, value=0.0)
        add_z_keyframe(obj, frame=24, value=2.0)
