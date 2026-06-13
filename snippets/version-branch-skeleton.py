# Canonical bpy.app.version branching skeleton.
# Use this for any API that diverged between 4.5 LTS and 5.x.
# Pin the comparison tuple precisely; do not compare against a single int.

import bpy


def clear_property(obj, key):
    """Delete a custom ID property.

    NOT version-dependent: del obj[key] works on every Blender version
    (4.5 LTS and 5.x). del raises if key is absent, so check membership first.
    See get_eevee_engine_id() below for the file's genuine version-divergence
    example.
    """
    if key not in obj:
        return False

    del obj[key]
    return True


def get_eevee_engine_id():
    """EEVEE engine identifier renamed from BLENDER_EEVEE to BLENDER_EEVEE_NEXT in 5.x."""
    if bpy.app.version >= (5, 0, 0):
        return 'BLENDER_EEVEE_NEXT'
    return 'BLENDER_EEVEE'
