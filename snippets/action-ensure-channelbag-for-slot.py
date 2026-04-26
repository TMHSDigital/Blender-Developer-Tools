# Slotted Actions bridge: action_ensure_channelbag_for_slot.
# In Blender 5.x, an Action contains Layers contain Strips contain
# Channelbags, and F-curves live inside Channelbags keyed by an
# animation slot. The bridging utility ensures the Channelbag exists
# for the slot bound to the given ID and returns it; on 4.x it returns
# a compatibility shim that exposes the same .fcurves.new(...) API.
#
# Verify the import path against your Blender version's docs. The
# canonical location at the time of writing is bpy_extras.anim_utils.
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
