"""Unity vs Godot glTF presets: a runnable example.

Same source mesh, two presets. Unity is Y-up (`export_yup=True`). Godot in this
repo is Z-up glTF (`export_yup=False`). Re-importing each file through Blender's
Y-up glTF importer proves the axis conversion actually happened: Unity stands
(mast along +Z, original coords), Godot lies (mast along -Y). The check is on
re-imported coordinates, not a screenshot.

The source is a radio mast: a stepped concrete footing, a bolted base flange,
a tapered red-and-white aviation-banded mast with steel collars, three sector
panel antennas, a shrouded microwave dish on a side arm, an equipment cabinet,
and a red obstruction lamp under a lightning rod whose point is the witnessed
tip vertex. "Up" is unmistakable on it, which is the whole point.

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
import itertools
import json
import math
import os
import sys
import tempfile

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True
import gallery_framing
import gallery_asset_quality

EPS = 2e-4
SPAN_GAP = 0.4

# Material slots of the source mesh, in order.
(MAT_CONCRETE, MAT_STEEL, MAT_RED, MAT_WHITE, MAT_LAMP, MAT_DARK, MAT_RADOME,
 MAT_CABINET) = range(8)

# Mast geometry (metres, Z-up, origin at the footing's underside).
FOOT_LO = (0.96, 0.18)          # lower footing tier: side, height
FOOT_HI = (0.46, 0.12)          # upper footing tier
FLANGE_Z0 = FOOT_LO[1] + FOOT_HI[1]
FLANGE_H = 0.035
MAST_Z0 = FLANGE_Z0 + FLANGE_H
MAST_Z1 = 2.08
MAST_R0, MAST_R1 = 0.085, 0.05
BANDS = 7
ROD_Z0 = 2.24
TIP = Vector((0.0, 0.0, 2.46))   # lightning-rod point: the witnessed tip vertex

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


# --------------------------------------------------------------------------
# Modelling. Every part is built in one bmesh; each helper tags the faces it
# creates with a material slot and a shading mode.


class Part:
    """Context for one part: new verts/faces are the set difference."""

    def __init__(self, bm):
        self.bm = bm
        self.v0 = set(bm.verts)
        self.f0 = set(bm.faces)

    def verts(self):
        return [v for v in self.bm.verts if v not in self.v0]

    def finish(self, mat, smooth_axis=None):
        for f in self.bm.faces:
            if f in self.f0:
                continue
            f.material_index = mat
            if smooth_axis is None:
                f.smooth = False
            else:
                f.normal_update()
                # Round sides smooth, caps (normal along the axis) flat.
                f.smooth = abs(f.normal.dot(smooth_axis)) < 0.9


def box(bm, center, size, mat, bevel=0.0):
    part = Part(bm)
    geom = bmesh.ops.create_cube(bm, size=1.0)
    for v in geom["verts"]:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2])) + Vector(center)
    if bevel > 0.0:
        edges = list({e for v in geom["verts"] for e in v.link_edges})
        bmesh.ops.bevel(
            bm, geom=edges, offset=bevel, segments=2, profile=0.5, affect="EDGES",
            clamp_overlap=True,
        )
    part.finish(mat)


def _axis_matrix(axis):
    """Rotation taking +Z onto *axis* (a unit Vector)."""
    return Vector((0.0, 0.0, 1.0)).rotation_difference(axis).to_matrix().to_4x4()


def cyl(bm, start, axis, length, r0, r1, mat, segs=24, smooth=True):
    """Frustum from *start* along unit *axis*, radius r0 -> r1."""
    part = Part(bm)
    axis = Vector(axis).normalized()
    bmesh.ops.create_cone(
        bm, cap_ends=True, cap_tris=False, segments=segs,
        radius1=r0, radius2=r1, depth=length,
    )
    mat4 = Matrix.Translation(Vector(start) + axis * (length * 0.5)) @ _axis_matrix(axis)
    bmesh.ops.transform(bm, matrix=mat4, verts=part.verts())
    part.finish(mat, axis if smooth else None)


def mast_radius(z):
    t = (z - MAST_Z0) / (MAST_Z1 - MAST_Z0)
    return MAST_R0 + (MAST_R1 - MAST_R0) * t


def build_mast(bm):
    up = (0.0, 0.0, 1.0)
    # Footing: two chamfered concrete tiers.
    box(bm, (0.0, 0.0, FOOT_LO[1] * 0.5), (FOOT_LO[0], FOOT_LO[0], FOOT_LO[1]),
        MAT_CONCRETE, bevel=0.03)
    box(bm, (0.0, 0.0, FOOT_LO[1] + FOOT_HI[1] * 0.5),
        (FOOT_HI[0], FOOT_HI[0], FOOT_HI[1]), MAT_CONCRETE, bevel=0.02)
    # Base flange with eight anchor nuts.
    cyl(bm, (0, 0, FLANGE_Z0), up, FLANGE_H, 0.175, 0.175, MAT_STEEL, segs=32)
    for i in range(8):
        a = 2.0 * math.pi * (i + 0.5) / 8
        c = (0.135 * math.cos(a), 0.135 * math.sin(a), MAST_Z0)
        cyl(bm, c, up, 0.028, 0.019, 0.019, MAT_DARK, segs=6, smooth=False)
    # Tapered mast in aviation bands, red at base and top, steel collars at
    # every band joint.
    band_h = (MAST_Z1 - MAST_Z0) / BANDS
    for i in range(BANDS):
        z0 = MAST_Z0 + i * band_h
        cyl(bm, (0, 0, z0), up, band_h, mast_radius(z0), mast_radius(z0 + band_h),
            MAT_RED if i % 2 == 0 else MAT_WHITE, segs=24)
    for i in range(BANDS + 1):
        z = MAST_Z0 + i * band_h
        r = mast_radius(z) + 0.012
        cyl(bm, (0, 0, z - 0.018), up, 0.036, r, r, MAT_STEEL, segs=24)
    # Sector panel antennas on standoff brackets, 120 degrees apart.
    for az in (180.0, 60.0, -60.0):
        a = math.radians(az)
        d = Vector((math.cos(a), math.sin(a), 0.0))
        part = Part(bm)
        box(bm, (0, 0, 0), (0.05, 0.12, 0.44), MAT_RADOME, bevel=0.012)
        rot = Matrix.Rotation(a, 4, "Z")
        bmesh.ops.transform(
            bm, matrix=Matrix.Translation(d * 0.155 + Vector((0, 0, 1.80))) @ rot,
            verts=part.verts())
        for zb in (1.64, 1.96):
            cyl(bm, Vector((0, 0, zb)) + d * 0.03, d, 0.105, 0.014, 0.014, MAT_STEEL, segs=8)
    # Microwave link dish on a side arm: shroud drum, back cone, radome face.
    # The dish faces -X, off a side arm to +Y.
    dz = 1.34
    fwd = Vector((-1.0, 0.0, 0.0))
    dish_c = Vector((0.0, 0.44, dz))
    back = dish_c - fwd * 0.07
    cyl(bm, back, fwd, 0.13, 0.215, 0.215, MAT_WHITE, segs=40)
    cyl(bm, back, -fwd, 0.10, 0.215, 0.07, MAT_STEEL, segs=40)
    cyl(bm, dish_c + fwd * 0.06, fwd, 0.018, 0.205, 0.19, MAT_RADOME, segs=40)
    cyl(bm, back, fwd, 0.016, 0.228, 0.228, MAT_DARK, segs=40)
    cyl(bm, back - fwd * 0.10, -fwd, 0.03, 0.05, 0.05, MAT_DARK, segs=16)
    # Clamp collar on the mast and a raked arm to the back of the dish.
    r_dz = mast_radius(dz)
    cyl(bm, (0, 0, dz - 0.05), up, 0.10, r_dz + 0.02, r_dz + 0.02, MAT_DARK, segs=20)
    arm_end = back - fwd * 0.10
    arm = Vector((arm_end.x, arm_end.y, 0.0))
    cyl(bm, (0.0, 0.0, dz), arm.normalized(), arm.length, 0.02, 0.02, MAT_STEEL, segs=12)
    # Equipment cabinet with a rain hood, door handle, and conduit to the mast.
    cab = Vector((-0.30, -0.28, FOOT_LO[1] + 0.17))
    box(bm, tuple(cab), (0.20, 0.26, 0.34), MAT_CABINET, bevel=0.014)
    box(bm, tuple(cab + Vector((0.0, 0.0, 0.185))), (0.24, 0.30, 0.03), MAT_DARK,
        bevel=0.006)
    box(bm, tuple(cab + Vector((-0.104, 0.07, 0.02))), (0.012, 0.022, 0.10), MAT_DARK,
        bevel=0.003)
    c0 = Vector((-0.20, -0.20, 0.44))
    c1 = Vector((-0.06, -0.06, 0.44))
    cyl(bm, c0, (c1 - c0).normalized(), (c1 - c0).length, 0.02, 0.02, MAT_DARK, segs=10)
    # Top: cap plate, obstruction lamp, lightning rod.
    cyl(bm, (0, 0, MAST_Z1), up, 0.03, 0.075, 0.075, MAT_STEEL, segs=24)
    cyl(bm, (0, 0, MAST_Z1 + 0.03), up, 0.04, 0.045, 0.045, MAT_DARK, segs=16)
    cyl(bm, (0, 0, MAST_Z1 + 0.07), up, 0.06, 0.05, 0.05, MAT_LAMP, segs=24)
    cyl(bm, (0, 0, MAST_Z1 + 0.13), up, ROD_Z0 - MAST_Z1 - 0.13, 0.05, 0.02,
        MAT_DARK, segs=16)
    cyl(bm, (0, 0, ROD_Z0), up, TIP.z - ROD_Z0, 0.009, 0.0, MAT_STEEL, segs=8)


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("RadioMast")
    bm = bmesh.new()
    try:
        build_mast(bm)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new("RadioMast", me)
    bpy.context.collection.objects.link(obj)
    mats = (
        principled("Concrete", (0.36, 0.35, 0.33, 1.0), 0.0, 0.85),
        principled("GalvanizedSteel", (0.55, 0.57, 0.6, 1.0), 0.6, 0.38),
        principled("AviationRed", (0.78, 0.07, 0.03, 1.0), 0.0, 0.38),
        principled("AviationWhite", (0.78, 0.78, 0.75, 1.0), 0.0, 0.42),
        principled("ObstructionLamp", (0.9, 0.05, 0.02, 1.0), 0.0, 0.2),
        principled("DarkSteel", (0.05, 0.052, 0.058, 1.0), 0.6, 0.45),
        principled("Radome", (0.62, 0.63, 0.6, 1.0), 0.0, 0.6),
        principled("CabinetPaint", (0.20, 0.30, 0.25, 1.0), 0.0, 0.5),
    )
    bsdf = mats[MAT_LAMP].node_tree.nodes["Principled BSDF"]
    sock = bsdf.inputs.get("Emission Color") or bsdf.inputs["Emission"]
    sock.default_value = (1.0, 0.012, 0.006, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 3.0
    for m in mats:
        me.materials.append(m)
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


# --------------------------------------------------------------------------
# Render path only.


def fitted_rotation(src, objs):
    """The axis-aligned rotation that maps the source onto a re-import.

    Tries all 24 proper signed-permutation matrices and keeps the one whose
    rotated source vertices land closest to the re-imported vertices (worst
    nearest-neighbour distance). The gizmo drawn beside each re-import is
    this measured frame, not a hand-placed one.
    """
    dst = all_world_points(objs)
    tree = KDTree(len(dst))
    for i, p in enumerate(dst):
        tree.insert(p, i)
    tree.balance()
    src_pts = world_points(src)
    best = None
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1.0, -1.0), repeat=3):
            m = Matrix(((0.0,) * 3,) * 3)
            for row, col in enumerate(perm):
                m[row][col] = signs[row]
            if m.determinant() < 0.5:
                continue
            worst = max(tree.find(m @ p)[2] for p in src_pts)
            if best is None or worst < best[0]:
                best = (worst, m)
    return best


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


def light(scene, name, loc, energy, size, col, target):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.size = size
    ld.color = col
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    aim = Vector(target) - Vector(loc)
    ob.rotation_euler = aim.to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(ob)


def gizmo_material(name, color):
    mat = principled(name, color, 0.0, 0.35)
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    sock = bsdf.inputs.get("Emission Color") or bsdf.inputs["Emission"]
    sock.default_value = color
    bsdf.inputs["Emission Strength"].default_value = 0.25
    return mat


def build_gizmo(scene, name, origin, rot, mats, length=0.72):
    """Modelled axis triad: hub plus X/Y/Z arrows along the columns of *rot*."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        part = Part(bm)
        bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=0.075)
        part.finish(3, Vector((0, 0, 1)))
        for i in range(3):
            axis = Vector((rot[0][i], rot[1][i], rot[2][i]))
            shaft = length - 0.2
            cyl(bm, axis * 0.05, axis, shaft - 0.05, 0.03, 0.03, i, segs=20)
            cyl(bm, axis * shaft, axis, 0.2, 0.075, 0.0, i, segs=24)
        bm.to_mesh(me)
    finally:
        bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    ob.location = origin
    scene.collection.objects.link(ob)
    return ob


def render_still(source, unity_objs, godot_objs, path, engine):
    scene = bpy.context.scene
    source.hide_render = True
    source.hide_viewport = True

    # Measure each re-import's frame before moving anything.
    frames = {}
    for key, objs in (("Unity", unity_objs), ("Godot", godot_objs)):
        worst, rot = fitted_rotation(source, objs)
        cols = ["".join(f"{v:+.0f}" for v in (rot[0][i], rot[1][i], rot[2][i]))
                for i in range(3)]
        print(f"{key.lower()}_frame X->{cols[0]} Y->{cols[1]} Z->{cols[2]} "
              f"fit_err={worst:.3e}")
        if worst > 1e-3:
            print(f"ERROR: no axis-aligned rotation maps the source onto the "
                  f"{key} re-import (best {worst:.3e})", file=sys.stderr)
            return 12
        frames[key] = rot
        for i, ob in enumerate(objs):
            ob.name = f"RadioMast.{key}" + (f".{i}" if i else "")

    # The camera looks along +X, so the pair sits side by side along Y and the
    # lying Godot mast (along -Y) shows its full length across the frame.
    sit_on_floor(unity_objs, 0.35, 1.45)
    sit_on_floor(godot_objs, -0.05, -1.15)

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
    wall.location = (7.0, 0.0, 0.0)
    wall.rotation_euler = (0.0, math.pi / 2, 0.0)
    scene.collection.objects.link(wall)

    gmats = (
        gizmo_material("AxisX", (0.9, 0.08, 0.06, 1.0)),
        gizmo_material("AxisY", (0.25, 0.85, 0.08, 1.0)),
        gizmo_material("AxisZ", (0.06, 0.32, 1.0, 1.0)),
        principled("AxisHub", (0.8, 0.8, 0.78, 1.0), 0.0, 0.4),
    )
    giz_u = build_gizmo(scene, "Gizmo.Unity", (-0.85, 2.0, 0.09), frames["Unity"], gmats)
    giz_g = build_gizmo(scene, "Gizmo.Godot", (-0.9, -0.95, 0.09), frames["Godot"], gmats)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.02,
        0.021,
        0.025,
        1.0,
    )
    scene.world = world

    # Rig rotated with the camera: key upper left, fill low right, rim and
    # wedge behind the pair, the wedge raking the back wall at x = 7.
    light(scene, "Key", (-5.0, 4.0, 6.0), 520.0, 5.0, (1.0, 0.96, 0.9), (0, 0, 0.8))
    light(scene, "Fill", (-3.5, -5.5, 2.5), 100.0, 9.0, (0.75, 0.85, 1.0), (0, 0, 0.8))
    light(scene, "Rim", (3.5, -2.5, 4.5), 300.0, 4.0, (0.6, 0.78, 1.0), (0, 0, 0.8))
    light(scene, "Wedge", (4.2, 1.0, 3.2), 320.0, 6.0, (1.0, 0.76, 0.5), (7.0, 0.3, 1.6))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (-7.0, -2.6, 2.6)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.15, 0.92)
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
    # Standard, not AgX: AgX pales the aviation red and lifts the stage.
    scene.view_settings.view_transform = "Standard"

    hero = unity_objs + godot_objs
    fcode = gallery_framing.check_framing(
        scene,
        cam,
        hero=hero,
        elements=hero + [giz_u, giz_g],
        stage=[floor, wall],
    )
    if fcode:
        return fcode
    aqcode = gallery_asset_quality.check_asset_quality(
        scene, cam, hero=unity_objs, stage=[floor, wall])
    if aqcode:
        return aqcode
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
