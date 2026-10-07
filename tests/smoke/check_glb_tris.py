"""Assert a GLB's total triangle count (headless template modifier order, #468).

    blender --background --python check_glb_tris.py -- FILE.glb EXPECTED_TRIS

Exit 3 when the re-imported triangle count differs. For stack.blend (a cube
with a live SUBSURF levels 1) run through script.py --apply-modifier
TRIANGULATE, the existing stack first then the new modifier gives 48 tris;
the reversed order that a non-first modifier_apply produces gives 72.
"""
import sys

import bpy

path, expected = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=path.replace("\\", "/"))
tris = 0
for obj in bpy.data.objects:
    if obj.type == "MESH":
        tris += len(obj.data.loop_triangles)
print(f"{path}: {tris} triangles (expected {expected})")
sys.exit(0 if tris == int(expected) else 3)
