"""Assert the ai-asset-pipeline template kept every part of a GLB in place.

    blender --background --python check_pipeline_glb.py -- SOURCE.glb LOD0.glb

Re-imports both files and compares them in world space (#462, #467):

  3  LOD0 has a different number of mesh objects than one (parts not joined)
  4  LOD0's world bbox differs from the source's (a part was dropped or moved)
  5  LOD0's origin is not on its world minimum Z (grounded along a local axis)
  6  LOD0's node carries rotation or scale (transforms not applied)

The fixture (make_pipeline_glb.py --parented) stays under every LOD budget, so
LOD0 is undecimated and its bbox must match the source exactly.
"""
import sys

import bpy

TOL = 1e-4


def import_glb(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path.replace("\\", "/"))
    bpy.context.view_layer.update()
    return [o for o in bpy.data.objects if o.type == "MESH"]


def world_points(objs):
    return [o.matrix_world @ v.co for o in objs for v in o.data.vertices]


def bbox(points):
    return [min(p[a] for p in points) for a in range(3)] + [
        max(p[a] for p in points) for a in range(3)
    ]


def main():
    src_path, lod_path = sys.argv[sys.argv.index("--") + 1:][:2]
    src = import_glb(src_path)
    src_box = bbox(world_points(src))
    print(f"source: {len(src)} mesh object(s), world bbox {[round(c, 4) for c in src_box]}")

    lod = import_glb(lod_path)
    if len(lod) != 1:
        print(f"FAIL: lod0 has {len(lod)} mesh objects, expected 1", file=sys.stderr)
        return 3
    obj = lod[0]
    points = world_points(lod)
    lod_box = bbox(points)
    print(f"lod0: {obj.name}, world bbox {[round(c, 4) for c in lod_box]}")
    drift = max(abs(a - b) for a, b in zip(src_box, lod_box))
    if drift > TOL:
        print(f"FAIL: lod0 world bbox differs from source by {drift:.4f}", file=sys.stderr)
        return 4
    origin_z = obj.matrix_world.translation.z
    print(f"lod0 origin z={origin_z:.4f}, world min z={lod_box[2]:.4f}")
    if abs(origin_z - lod_box[2]) > TOL:
        print("FAIL: lod0 origin is not on its world minimum Z", file=sys.stderr)
        return 5
    m = obj.matrix_world.to_3x3()
    off = max(abs(m[i][j] - (1.0 if i == j else 0.0)) for i in range(3) for j in range(3))
    if off > TOL:
        print(f"FAIL: lod0 node has rotation/scale (max off-identity {off:.4f})", file=sys.stderr)
        return 6
    print("OK: lod0 keeps every part, grounded, transforms applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
