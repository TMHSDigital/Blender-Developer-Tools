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
    """EEVEE engine identifier across versions.

    Legacy EEVEE was removed in 4.2; EEVEE Next used the id 'BLENDER_EEVEE_NEXT'
    on 4.2 through 4.5 LTS, then reclaimed the plain 'BLENDER_EEVEE' id in 5.0.
    """
    if bpy.app.version >= (5, 0, 0):
        return 'BLENDER_EEVEE'
    return 'BLENDER_EEVEE_NEXT'
