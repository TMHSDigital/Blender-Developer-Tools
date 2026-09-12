"""Unity vs Godot glTF presets: a runnable example.

Same source mesh, two presets. Unity is Y-up (`export_yup=True`). Godot in this
repo is Z-up glTF (`export_yup=False`). Re-importing each file through Blender's
Y-up glTF importer proves the axis conversion actually happened: Unity stands
(mast along +Z, original coords), Godot lies (mast along -Y). The check is on
re-imported coordinates, not a screenshot.

Closed form (Blender Z-up source `(x, y, z)`):

* `export_yup=True` disk POSITION: `(x, z, -y)`
* `export_yup=False` disk POSITION: `(x, y, z)`
* Blender importer always treats the file as Y-up:
  `blender = (gltf.x, -gltf.z, gltf.y)`
  so Unity round-trips to `(x, y, z)` and Godot becomes `(x, -z, y)`.

`--same-axis` exports both with `export_yup=True`. Both reimports stand, the
"orientations differ" check exits 9. That is the falsifier.

By default it runs only the correctness check (no render) - the CI smoke
check. Pass --output to also render a still:

    blender --background --python export_preset_axis.py --
    blender --background --python export_preset_axis.py -- --output p.png
    blender --background --python export_preset_axis.py -- --same-axis
"""
import argparse
import json
import math
import os
import sys
import tempfile

import bpy
import bmesh
from mathutils import Vector

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True
import gallery_framing

EPS = 2e-4
SPAN_GAP = 0.4

# Full extents (not half-sizes). create_cube(size=1) verts are +/- 0.5.
PARTS = (
    ("base", (0.0, 0.0, 0.08), (0.90, 0.90, 0.16)),
    ("step", (0.0, -0.51, 0.04), (0.28, 0.12, 0.08)),
    ("pedestal", (0.0, 0.0, 0.26), (0.26, 0.26, 0.20)),
    ("mast", (0.0, 0.0, 1.21), (0.09, 0.09, 1.70)),
    ("yard", (0.31, 0.0, 1.85), (0.62, 0.07, 0.07)),
    ("dish", (0.73, 0.0, 1.85), (0.22, 0.28, 0.28)),
    ("cap", (0.0, 0.0, 2.11), (0.14, 0.14, 0.10)),
)

CAP_Z = 2.06
TIP = Vector((0.07, 0.07, 2.16))

UNITY_KWARGS = dict(
    export_format="GLTF_SEPARATE",
    use_selection=True,
    export_yup=True,
    export_apply=True,
    export_texcoords=False,
    export_normals=True,
    export_materials="EXPORT",
    export_animations=False,
    export_image_format="NONE",
)
GODOT_KWARGS = dict(UNITY_KWARGS)
GODOT_KWARGS["export_yup"] = False


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def aabb_of(points):
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    zs = [p.z for p in points]
    return (
        (min(xs), max(xs)),
        (min(ys), max(ys)),
        (min(zs), max(zs)),
    )


def span(lohi):
    return lohi[1] - lohi[0]


def world_points(obj):
    mw = obj.matrix_world
    return [mw @ v.co.copy() for v in obj.data.vertices]


def position_minmax(gltf_path):
    g = json.load(open(gltf_path, encoding="utf-8"))
    mins = []
    maxs = []
    for mesh in g["meshes"]:
        for prim in mesh["primitives"]:
            acc = g["accessors"][prim["attributes"]["POSITION"]]
            mins.append(acc["min"])
            maxs.append(acc["max"])
    umin = tuple(min(m[i] for m in mins) for i in range(3))
    umax = tuple(max(m[i] for m in maxs) for i in range(3))
    node = g["nodes"][0]
    return g, umin, umax, node


def add_box(bm, center, size):
    geom = bmesh.ops.create_cube(bm, size=1.0)
    cx, cy, cz = center
    sx, sy, sz = size
    for vert in geom["verts"]:
        vert.co.x = vert.co.x * sx + cx
        vert.co.y = vert.co.y * sy + cy
        vert.co.z = vert.co.z * sz + cz


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("Beacon")
    bm = bmesh.new()
    try:
        for _name, center, size in PARTS:
            add_box(bm, center, size)
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new("Beacon", me)
    bpy.context.collection.objects.link(obj)
    hull = principled("Hull", (0.22, 0.28, 0.18, 1.0), 0.35, 0.38)
    glow = principled("Beacon", (0.02, 0.55, 0.48, 1.0), 0.0, 0.22)
    emit = (0.05, 1.0, 0.75, 1.0)
    bsdf = glow.node_tree.nodes["Principled BSDF"]
    sock = bsdf.inputs.get("Emission Color") or bsdf.inputs["Emission"]
    sock.default_value = emit
    bsdf.inputs["Emission Strength"].default_value = 4.0
    me.materials.append(hull)
    me.materials.append(glow)
    for poly in me.polygons:
        poly.use_smooth = True
        poly.material_index = 1 if poly.center.z > CAP_Z else 0
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


def principled(name, color, metallic, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def apply_selected_mesh_transforms():
    for obj in list(bpy.context.selected_objects):
        if obj.type != "MESH":
            continue
        with bpy.context.temp_override(
            object=obj, active_object=obj, selected_objects=[obj]
        ):
            bpy.ops.object.transform_apply(
                location=False, rotation=True, scale=True
            )


def export_selected(path, kwargs):
    apply_selected_mesh_transforms()
    bpy.ops.export_scene.gltf(filepath=path, **kwargs)


def import_gltf_meshes(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    added = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    return added or None


def all_world_points(objs):
    pts = []
    for obj in objs:
        pts.extend(world_points(obj))
    return pts


def node_has_rotation(node):
    rot = node.get("rotation")
    if not rot:
        return False
    return (
        abs(rot[0]) > EPS
        or abs(rot[1]) > EPS
        or abs(rot[2]) > EPS
        or abs(rot[3] - 1.0) > EPS
    )


def near(a, b, eps=EPS):
    return abs(a - b) <= eps


def check(src, same_axis):
    exp_props = {
        p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties
    }
    missing = [k for k in UNITY_KWARGS if k not in exp_props]
    if missing:
        print(f"ERROR: exporter RNA drifted, missing {missing}", file=sys.stderr)
        return 2, None, None

    pts = world_points(src)
    sx, sy, sz = aabb_of(pts)
    z_span, y_span, x_span = span(sz), span(sy), span(sx)
    print(
        f"source_aabb x={sx[0]:.4f}..{sx[1]:.4f} "
        f"y={sy[0]:.4f}..{sy[1]:.4f} z={sz[0]:.4f}..{sz[1]:.4f}"
    )
    if not (z_span > y_span + SPAN_GAP and z_span > x_span + SPAN_GAP):
        print(
            f"ERROR: source mast is not Z-dominant z_span={z_span:.4f} "
            f"y_span={y_span:.4f} x_span={x_span:.4f}",
            file=sys.stderr,
        )
        return 3, None, None
    tip_err = min((p - TIP).length for p in pts)
    if tip_err > 1e-5:
        print(f"ERROR: source tip drifted {tip_err:.3e} from {tuple(TIP)}", file=sys.stderr)
        return 3, None, None

    tmp = tempfile.mkdtemp(prefix="export_preset_axis_")
    unity_path = os.path.join(tmp, "unity.gltf").replace("\\", "/")
    godot_path = os.path.join(tmp, "godot.gltf").replace("\\", "/")
    godot_kwargs = dict(GODOT_KWARGS)
    if same_axis:
        godot_kwargs["export_yup"] = True

    src.select_set(True)
    bpy.context.view_layer.objects.active = src
    export_selected(unity_path, UNITY_KWARGS)
    export_selected(godot_path, godot_kwargs)

    _ug, u_min, u_max, u_node = position_minmax(unity_path)
    _gg, g_min, g_max, g_node = position_minmax(godot_path)
    print(f"unity_disk min={u_min} max={u_max} node_rot={u_node.get('rotation')}")
    print(f"godot_disk min={g_min} max={g_max} node_rot={g_node.get('rotation')}")

    # Unity disk Y is source Z; disk Z is -source Y.
    if not (
        near(u_min[1], sz[0])
        and near(u_max[1], sz[1])
        and near(u_min[2], -sy[1])
        and near(u_max[2], -sy[0])
    ):
        print(
            f"ERROR: Unity disk POSITION is not (x, z, -y) "
            f"u_min={u_min} u_max={u_max} source_z={sz} source_y={sy}",
            file=sys.stderr,
        )
        return 5, None, None
    if node_has_rotation(u_node):
        print(f"ERROR: Unity node has rotation {u_node.get('rotation')}", file=sys.stderr)
        return 5, None, None

    if not same_axis:
        if not (near(g_min[2], sz[0]) and near(g_max[2], sz[1])):
            print(
                f"ERROR: Godot disk POSITION is not raw Z-up "
                f"g_min={g_min} g_max={g_max} source_z={sz}",
                file=sys.stderr,
            )
            return 6, None, None

    unity_objs = import_gltf_meshes(unity_path)
    godot_objs = import_gltf_meshes(godot_path)
    if unity_objs is None or godot_objs is None:
        print("ERROR: expected a mesh per glTF import", file=sys.stderr)
        return 4, None, None

    u_pts = all_world_points(unity_objs)
    g_pts = all_world_points(godot_objs)
    ux, uy, uz = aabb_of(u_pts)
    gx, gy, gz = aabb_of(g_pts)
    print(
        f"unity_reimport x={ux[0]:.4f}..{ux[1]:.4f} "
        f"y={uy[0]:.4f}..{uy[1]:.4f} z={uz[0]:.4f}..{uz[1]:.4f}"
    )
    print(
        f"godot_reimport x={gx[0]:.4f}..{gx[1]:.4f} "
        f"y={gy[0]:.4f}..{gy[1]:.4f} z={gz[0]:.4f}..{gz[1]:.4f}"
    )

    if not (
        near(span(uz), z_span)
        and near(span(uy), y_span)
        and span(uz) > span(uy) + SPAN_GAP
    ):
        print(
            f"ERROR: Unity reimport is not standing "
            f"z_span={span(uz):.4f} y_span={span(uy):.4f} source_z={z_span:.4f}",
            file=sys.stderr,
        )
        return 7, unity_objs, godot_objs

    godot_lying = (
        near(span(gy), z_span)
        and near(span(gz), y_span)
        and span(gy) > span(gz) + SPAN_GAP
    )
    orientations_differ = abs(span(uz) - span(gz)) > SPAN_GAP and abs(
        span(uy) - span(gy)
    ) > SPAN_GAP

    if same_axis:
        if orientations_differ:
            print(
                "ERROR: --same-axis did not collapse the axis difference",
                file=sys.stderr,
            )
            return 11, unity_objs, godot_objs
        print("ERROR: orientations did not differ", file=sys.stderr)
        return 9, unity_objs, godot_objs

    if not godot_lying:
        print(
            f"ERROR: Godot reimport is not lying along Y "
            f"y_span={span(gy):.4f} z_span={span(gz):.4f} source_z={z_span:.4f}",
            file=sys.stderr,
        )
        return 8, unity_objs, godot_objs

    expected_godot_tip = Vector((TIP.x, -TIP.z, TIP.y))
    godot_tip_err = min((p - expected_godot_tip).length for p in g_pts)
    unity_tip_err = min((p - TIP).length for p in u_pts)
    print(f"unity_tip_err={unity_tip_err:.3e} godot_tip_err={godot_tip_err:.3e}")
    if unity_tip_err > 5e-4 or godot_tip_err > 5e-4:
        print(
            f"ERROR: reimported tip mismatch unity={unity_tip_err:.3e} "
            f"godot={godot_tip_err:.3e} expected_godot={tuple(expected_godot_tip)}",
            file=sys.stderr,
        )
        return 8, unity_objs, godot_objs

    if not orientations_differ:
        print(
            f"ERROR: reimported orientations did not differ "
            f"unity_z={span(uz):.4f} godot_z={span(gz):.4f}",
            file=sys.stderr,
        )
        return 9, unity_objs, godot_objs

    return 0, unity_objs, godot_objs


def sit_on_floor(objs, x, y):
    bpy.context.view_layer.update()
    pts = all_world_points(objs)
    min_x = min(p.x for p in pts)
    max_x = max(p.x for p in pts)
    min_y = min(p.y for p in pts)
    max_y = max(p.y for p in pts)
    min_z = min(p.z for p in pts)
    dx = x - 0.5 * (min_x + max_x)
    dy = y - 0.5 * (min_y + max_y)
    dz = -min_z
    for obj in objs:
        obj.location.x += dx
        obj.location.y += dy
        obj.location.z += dz
    bpy.context.view_layer.update()


def light(scene, name, loc, energy, size, col, rot):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.size = size
    ld.color = col
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    ob.rotation_euler = tuple(math.radians(a) for a in rot)
    scene.collection.objects.link(ob)


def render_still(source, unity_objs, godot_objs, path, engine):
    scene = bpy.context.scene
    source.hide_render = True
    source.hide_viewport = True
    sit_on_floor(unity_objs, -2.15, 0.0)
    sit_on_floor(godot_objs, 1.95, 0.0)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    floor_me.materials.append(principled("Studio", (0.03, 0.032, 0.037, 1.0), 0.0, 0.7))
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.data.materials.clear()
    wall.data.materials.append(principled("Wall", (0.03, 0.032, 0.037, 1.0), 0.0, 0.7))
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.pi / 2, 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.02,
        0.021,
        0.025,
        1.0,
    )
    scene.world = world

    light(scene, "Key", (-4.0, -5.0, 6.0), 650.0, 5.0, (1.0, 0.96, 0.9), (46, 0, -35))
    light(scene, "Fill", (5.0, -3.5, 3.0), 120.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light(scene, "Wedge", (2.5, 5.5, 4.0), 380.0, 6.0, (1.0, 0.76, 0.5), (-68, 0, 190))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (3.12, -8.15, 2.45)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.85)
    scene.collection.objects.link(aim)
    con = cam.constraints.new("TRACK_TO")
    con.target = aim
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    scene.camera = cam

    scene.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        scene.cycles.samples = 32
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(
        scene,
        cam,
        hero=unity_objs + godot_objs,
        elements=unity_objs + godot_objs,
        stage=[floor, wall],
    )
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 6
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument(
        "--engine",
        default="eevee",
        choices=("eevee", "cycles"),
        help="render engine for --output",
    )
    p.add_argument(
        "--same-axis",
        action="store_true",
        help="export both presets with export_yup=True (must fail)",
    )
    args = p.parse_args(argv)

    src = build()
    code, unity_objs, godot_objs = check(src, args.same_axis)
    if code:
        return code

    if args.output:
        rcode = render_still(
            src, unity_objs, godot_objs, os.path.abspath(args.output), args.engine
        )
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("export-preset-axis OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
