# Canonical bpy.app.version branching skeleton.
# Use this for any API that diverged between 4.5 LTS and 5.x.
# Pin the comparison tuple precisely; do not compare against a single int.

import bpy


def clear_property(obj, key):
    """Delete a custom property cross-version.

    Blender 5.0 introduced property_unset() as the supported path; on 4.5 LTS
    fall back to del obj[key]. Either form raises if key is absent, so check first.
    """
    if key not in obj:
        return False

    if bpy.app.version >= (5, 0, 0):
        obj.property_unset(f'["{key}"]')
    else:
        del obj[key]
    return True


def get_eevee_engine_id():
    """EEVEE engine identifier renamed from BLENDER_EEVEE to BLENDER_EEVEE_NEXT in 5.x."""
    if bpy.app.version >= (5, 0, 0):
        return 'BLENDER_EEVEE_NEXT'
    return 'BLENDER_EEVEE'
