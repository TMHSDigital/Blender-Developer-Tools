"""Game-ready moka pot — a showcase piece, not an example.

Asserts budget conformance of a procedural eight-sided aluminium stovetop
coffee maker: a tapered lower boiler, an upper collector that flares back
out from the waist, a faceted lid under a bakelite knob, a pinched pour
spout, and a bakelite handle carried on a riveted bracket, with a brass
safety valve on the boiler. Carried through UVs, three materials
(aluminium, bakelite, brass), a high-to-low normal bake, an LOD chain, a
compound convex collider, and a Unity glTF export.

The budget that matters here is the one a moka pot fails invisibly: it
has to be an octagon *all the way up*. Eight flats, one per facet, every
ring of the boiler and the collector the same size on all eight sides and
every ring centred on one vertical axis. A body that is a hair out of
round, or leans two millimetres at the lid, still passes the bounding
box, the triangle band and the hygiene audit; only a per-ring comparison
of the eight sectors, and a plumb line from foot to lid, see it. The
piece reads both off the generated vertices and asserts the size in
metres against the figures a three-cup pot has in a kitchen.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--flush-joint`` the coplanar
budget at the boiler-collector joint, ``--short-handle`` the handle's
bite into its bracket, ``--float-knob`` the knob seat, ``--float-spout``
the spout seat, ``--float-valve`` the valve seat, ``--lean-pot`` the plumb
line, ``--odd-facet`` the eight-fold symmetry.

No randomness. DECIMATE COLLAPSE triangle counts are not byte-identical
across Blender versions — the LOD gate is a ratio band.

    blender --background --python moka_pot.py --
    blender --background --python moka_pot.py -- --lean-pot
    blender --background --python moka_pot.py -- --output moka_pot.webp
"""
import argparse
import math
import os
import sys
import tempfile
import traceback

import bmesh
import bpy
from mathutils import Quaternion, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_asset_quality  # noqa: E402
import gallery_framing  # noqa: E402

# Eight flats, one facet each. A vertex every 45 degrees offset by half a
# step puts a flat square on each axis, so the handle bracket sits on a
# flat and the spout opposite it on another.
SIDES = 8
PHASE = math.pi / SIDES
COS_HALF = math.cos(math.pi / SIDES)

# Profiles are (apothem, z): the distance from the axis to the middle of a
# flat, which is what a ruler across the pot reads. Both ends of each list
# are the flat caps.
# The Moka Express is an hourglass: the boiler flares out to its foot and
# the collector flares out to its rim, both pinching to the screw joint,
# where the collector's threaded skirt stands proud as a grip band. The
# waist reads about three quarters of the foot (0.76 here).
BOILER = [(0.0395, 0.0000), (0.0414, 0.0025), (0.0416, 0.0045), (0.0312, 0.0615),
          (0.0318, 0.0630), (0.0318, 0.0660)]
BOILER_TAPER = (2, 3)  # the rings bounding the boiler's flank
UPPER = [(0.0330, 0.0625), (0.0338, 0.0638), (0.0338, 0.0700), (0.0326, 0.0714),
         (0.0397, 0.1290), (0.0401, 0.1303), (0.0401, 0.1318), (0.0395, 0.1333)]
UPPER_FLARE = (3, 4)  # the rings bounding the collector's flank
LID = [(0.0380, 0.1315), (0.0384, 0.1322), (0.0384, 0.1350), (0.0376, 0.1360),
       (0.0320, 0.1370), (0.0195, 0.1385), (0.0150, 0.1398)]
# Knob: a turned bakelite finial on a neck; (radius, z), round not faceted.
KNOB = [(0.0095, 0.1380), (0.0098, 0.1405), (0.0085, 0.1420), (0.0115, 0.1445),
        (0.0135, 0.1485), (0.0136, 0.1520), (0.0124, 0.1555), (0.0090, 0.1585),
        (0.0050, 0.1600)]
KNOB_SIDES = 12
CHAMFER = 0.0007
CHAMFER_ANGLE = math.radians(30.0)
CAP_ANGLE = math.radians(60.0)
CHAMFER_BAKE = 0.0012
CHAMFER_BRASS = 0.0004

# Spout: a V beak pinched out of the -x flat at the rim. In plan a
# triangle whose base spans the flat and whose apex is a sharp vertical
# edge; its underside sweeps down the wall, its lip rises to the tip.
SPOUT_BITE = 0.0015
SPOUT_REACH = 0.0125
SPOUT_TOP = 0.1300
SPOUT_LIP = 0.1312
SPOUT_BASE_BOT = 0.1090
SPOUT_TIP_BOT = 0.1272
SPOUT_HALF_BASE = 0.0150
FLOAT_SPOUT = 0.0040  # outward, off the wall

# Bracket on the +x flat: a fin that follows the wall's flare, with two
# brass rivets between the handle's two roots.
BRACKET_Z = (0.0722, 0.1275)
BRACKET_HALF = 0.0110
BRACKET_BITE = 0.0015
BRACKET_OUT = 0.0045
# One rivet, centred in the D's opening. Two would have to share the fin's
# plane 8.5 mm apart, a cross-shell coplanar pair by the hygiene metric.
RIVET_ZS = (0.1020,)
RIVET = [(0.0030, -0.0012), (0.0030, 0.0004), (0.0024, 0.0014), (0.0014, 0.0018)]
# Handle: a bakelite D loop in the xz plane, rooted in the fin at two
# stations; each root cap is cut parallel to the fin's raked face.
HANDLE_BITE = 0.0025
SHORT_HANDLE = 0.0030
# The D's centreline is a superellipse half: REACH out from the fin, HALF
# up and down from HANDLE_ZC, squared off by HANDLE_POW < 1. Its roots
# leave the fin horizontally at HANDLE_ZC +- HANDLE_HALF.
HANDLE_ZC = 0.1000
HANDLE_HALF = 0.0205
HANDLE_REACH = 0.0340
HANDLE_POW = 0.55
HANDLE_RINGS = 22
HANDLE_SIDES = 12

# Hinge knuckle on top of the fin, joining the lid's edge to the rim.
HINGE_X = (0.0368, 0.0478)
HINGE_Z = (0.1268, 0.1356)
HINGE_HALF = 0.0060

# Safety valve on the boiler's 225-degree flat (front left of the hero).
VALVE_Z = 0.034
VALVE_DEG = 225.0
VALVE = [(0.0050, -0.0016), (0.0052, 0.0014), (0.0046, 0.0030), (0.0028, 0.0043),
         (0.0014, 0.0046)]
FASTENER_SIDES = 12
FLOAT_VALVE = 0.0030
FLOAT_KNOB = 0.0040

# Lean: the falsifier shears the pot sideways in proportion to height.
LEAN = 0.0040
ODD_FACET = 0.0025
BBOX_TOL = 0.006
OUTER_SIZE = (0.1327, 0.0832, 0.1600)

BASE_TRIS_MIN = 1200
BASE_TRIS_MAX = 1400
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
FACE_FLOORS = {0: 160, 1: 280, 2: 100}
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 200
BAKE_RES = 512
CAGE_EXTRUSION = 0.002
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-12
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.02
LIFT_Z = 0.02
SHELLS_EXPECTED = 10
UPPER_SEAT_MIN = 0.0025
UPPER_SEAT_MAX = 0.0045
LID_SEAT_MIN = 0.0010
LID_SEAT_MAX = 0.0030
KNOB_BITE_MIN = 0.0010
KNOB_BITE_MAX = 0.0030
SPOUT_BITE_MIN = 0.0009
SPOUT_BITE_MAX = 0.0030
SPOUT_REACH_MIN = 0.0100
SPOUT_REACH_MAX = 0.0150
BRACKET_BITE_MIN = 0.0009
BRACKET_BITE_MAX = 0.0030
HANDLE_BITE_MIN = 0.0010
HANDLE_BITE_MAX = 0.0030
HINGE_BITE_MIN = 0.0015
HINGE_BITE_MAX = 0.0050
FASTENER_BITE_MIN = 0.0008
FASTENER_BITE_MAX = 0.0025
FASTENER_PROUD_MIN = 0.0012
# Real-world size of a three-cup Moka Express, metres: 16.0 cm tall and
# 9.0 cm across the foot point to point (retailer listings), which is
# 8.32 cm across its flats. The collector rim is read off product photos
# at 0.96 of the foot: 8.02 cm across its flats.
REAL_FOOT_FLATS = 0.0832
REAL_COLLECTOR_FLATS = 0.0802
REAL_TOTAL_H = 0.1600
REAL_TOL = 0.003
PLUMB_MAX = 0.0008
SYM_EPS = 2e-4

ALU_IDX = 0
BAKE_IDX = 1
BRASS_IDX = 2


def eevee_engine_id():
    """EEVEE id: 'BLENDER_EEVEE' on 5.0+, 'BLENDER_EEVEE_NEXT' on 4.2-4.5."""
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def fail(msg, code):
    print(f"FAIL[{code}]: {msg}", file=sys.stderr)
    return code


def triangle_count(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def evaluated_triangle_count(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    mesh = ev.to_mesh()
    try:
        mesh.calc_loop_triangles()
        return len(mesh.loop_triangles)
    finally:
        ev.to_mesh_clear()


def wall_a(profile, z):
    """Apothem of a profile at height ``z``, linear between its rings."""
    for (a0, z0), (a1, z1) in zip(profile, profile[1:]):
        if z0 <= z <= z1 and z1 > z0:
            return a0 + (a1 - a0) * (z - z0) / (z1 - z0)
    raise ValueError(f"z={z} outside profile")


# --- construction -----------------------------------------------------------


def new_island(ctx):
    ctx["next"] += 1
    return ctx["next"]


def stamp(ctx, face, island, uvmap):
    face[ctx["isl"]] = island
    for loop in face.loops:
        loop[ctx["uv"]].uv = uvmap[loop.vert]


def loft(bm, rings, mat_idx, ctx):
    """Quads between consecutive closed rings of equal length; one strip island."""
    island = new_island(ctx)
    n = len(rings[0])
    arc = [0.0]
    for a, b in zip(rings, rings[1:]):
        ca = sum((v.co for v in a), Vector()) / n
        cb = sum((v.co for v in b), Vector()) / n
        arc.append(arc[-1] + (cb - ca).length)
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for i in range(n):
            j = (i + 1) % n
            f = bm.faces.new((a[i], a[j], b[j], b[i]))
            f.material_index = mat_idx
            stamp(ctx, f, island, {a[i]: (arc[k], i / n), a[j]: (arc[k], (i + 1) / n),
                                   b[j]: (arc[k + 1], (i + 1) / n), b[i]: (arc[k + 1], i / n)})


def cap_rings(bm, rings, mat_idx):
    """Close both end rings of a solid with one n-gon each (triangulated later)."""
    for ring, flip in ((rings[0], True), (rings[-1], False)):
        f = bm.faces.new(tuple(reversed(ring)) if flip else tuple(ring))
        f.material_index = mat_idx


def lathe_solid(bm, rings_pts, mat_idx, ctx, verts_out):
    """A closed solid from rings of 3D points; side quads plus two n-gon caps."""
    rings = [[bm.verts.new(p) for p in pts] for pts in rings_pts]
    loft(bm, rings, mat_idx, ctx)
    cap_rings(bm, rings, mat_idx)
    for r in rings:
        verts_out.extend(r)
    return rings


def octagon(a, z, dx=0.0):
    r = a / COS_HALF
    return [(dx + r * math.cos(PHASE + 2.0 * math.pi * k / SIDES),
             r * math.sin(PHASE + 2.0 * math.pi * k / SIDES), z) for k in range(SIDES)]


def add_faceted(bm, profile, ctx, verts_out, odd=False):
    """An eight-flat body of revolution from an (apothem, z) profile."""
    rings_pts = [octagon(a, z) for a, z in profile]
    if odd:
        # Push the +y flat of the mid-height ring out: one facet no longer
        # matches the seven others.
        mid = rings_pts[len(rings_pts) // 2]
        for k, p in enumerate(mid):
            if abs(math.atan2(p[1], p[0]) - math.pi / 2.0) < math.pi / SIDES + 1e-6:
                mid[k] = (p[0], p[1] + ODD_FACET, p[2])
    return lathe_solid(bm, rings_pts, ALU_IDX, ctx, verts_out)


def add_round(bm, profile, ctx, mat_idx, verts_out, lift=0.0):
    """A smooth turned body from an (r, z) profile."""
    rings_pts = [[(r * math.cos(2.0 * math.pi * k / KNOB_SIDES),
                   r * math.sin(2.0 * math.pi * k / KNOB_SIDES), z + lift)
                  for k in range(KNOB_SIDES)] for r, z in profile]
    return lathe_solid(bm, rings_pts, mat_idx, ctx, verts_out)


def add_spout(bm, upper_wall, float_spout, verts_out):
    """A V beak on the -x flat: a triangular prism, base driven SPOUT_BITE into the wall."""
    # A floated spout lifts its base off the wall and leaves the tip where it
    # was, so only the bite moves and the reach stays in its band.
    shift = -FLOAT_SPOUT if float_spout else 0.0
    zb, zt, zk, zl = SPOUT_BASE_BOT, SPOUT_TOP, SPOUT_TIP_BOT, SPOUT_LIP

    def base_x(z):
        return -(wall_a(upper_wall, z) - SPOUT_BITE) + shift

    tip_x = -(wall_a(upper_wall, zt) + SPOUT_REACH)
    hb = SPOUT_HALF_BASE
    # Each triangle CCW from above: -y base, apex, +y base.
    lo = [bm.verts.new(p) for p in ((base_x(zb), -hb, zb), (tip_x, 0.0, zk), (base_x(zb), hb, zb))]
    hi = [bm.verts.new(p) for p in ((base_x(zt), -hb, zt), (tip_x, 0.0, zl), (base_x(zt), hb, zt))]
    faces = [bm.faces.new(tuple(reversed(lo))), bm.faces.new(tuple(hi))]
    for i in range(3):
        j = (i + 1) % 3
        faces.append(bm.faces.new((lo[i], lo[j], hi[j], hi[i])))
    for f in faces:
        f.material_index = ALU_IDX
    verts_out.extend(lo + hi)


def plate_x(z, out):
    return wall_a(UPPER, z) + out


def add_bracket(bm, verts_out):
    """A plate on the +x flat that follows the wall's rake."""
    z0, z1 = BRACKET_Z
    h = BRACKET_HALF
    inner = lambda z: wall_a(UPPER, z) - BRACKET_BITE  # noqa: E731
    outer = lambda z: wall_a(UPPER, z) + BRACKET_OUT  # noqa: E731
    lo = [bm.verts.new(p) for p in ((inner(z0), -h, z0), (outer(z0), -h, z0),
                                   (outer(z0), h, z0), (inner(z0), h, z0))]
    hi = [bm.verts.new(p) for p in ((inner(z1), -h, z1), (outer(z1), -h, z1),
                                   (outer(z1), h, z1), (inner(z1), h, z1))]
    # Quad rings in the xy plane, one at each end, lofted along z.
    faces = [bm.faces.new(tuple(reversed(lo))), bm.faces.new(tuple(hi))]
    for i in range(4):
        j = (i + 1) % 4
        faces.append(bm.faces.new((lo[i], lo[j], hi[j], hi[i])))
    for f in faces:
        f.material_index = ALU_IDX
    verts_out.extend(lo + hi)


def section(t, w):
    """A rounded rectangle, ``t`` thick along the path normal and ``w`` wide in y."""
    pts = []
    for k in range(HANDLE_SIDES):
        ang = 2.0 * math.pi * k / HANDLE_SIDES
        c, s = math.cos(ang), math.sin(ang)
        pts.append((math.copysign(abs(c) ** 0.55, c) * t * 0.5,
                    math.copysign(abs(s) ** 0.55, s) * w * 0.5))
    return pts


def handle_rings(short):
    # Both root caps sit HANDLE_BITE inside the fin's outer face; a short
    # handle stops SHORT_HANDLE outside it instead.
    off = SHORT_HANDLE if short else -HANDLE_BITE

    def centre(theta):
        c, s = math.cos(theta), math.sin(theta)
        z = HANDLE_ZC + HANDLE_HALF * math.copysign(abs(s) ** HANDLE_POW, s)
        return Vector((plate_x(z, BRACKET_OUT) + off + HANDLE_REACH * abs(c) ** HANDLE_POW, z))

    rings = []
    for i in range(HANDLE_RINGS):
        s = i / (HANDLE_RINGS - 1)
        theta = math.pi * (0.5 - s)
        pos = centre(theta)
        # Tangent by central difference; at the roots the fin-ward step is
        # replaced by the outward one so the cap faces straight into the fin.
        h = 1e-4
        tan = (centre(theta - h) - centre(theta + h)).normalized()
        if i in (0, HANDLE_RINGS - 1):
            tan = Vector((1.0 if i == 0 else -1.0, 0.0))
        # Slim at the roots, fuller through the grip at the bottom of the D.
        t = 0.0115 + 0.0030 * math.sin(math.pi * s) + 0.0010 * s
        w = 0.0130 + 0.0030 * math.sin(math.pi * s)
        n = Vector((-tan.y, tan.x))
        pts = []
        for u, v in section(t, w):
            q = pos + n * u
            pts.append([q.x, v, q.y])
        if i in (0, HANDLE_RINGS - 1):
            # Cut the root cap parallel to the fin's raked outer face.
            for p in pts:
                p[0] = plate_x(p[2], BRACKET_OUT) + off
        rings.append([tuple(p) for p in pts])
    return rings


def add_fastener(bm, origin, axis, profile, ctx, mat_idx, verts_out):
    """A turned head whose axis is ``axis`` (the host normal), foot at h < 0."""
    axis = axis.normalized()
    q = Vector((0.0, 0.0, 1.0)).rotation_difference(axis)
    rings = []
    for r, h in profile:
        pts = []
        for k in range(FASTENER_SIDES):
            ang = 2.0 * math.pi * k / FASTENER_SIDES
            pts.append(tuple(origin + q @ Vector((r * math.cos(ang), r * math.sin(ang), h))))
        rings.append(pts)
    lathe_solid(bm, rings, mat_idx, ctx, verts_out)


def add_hinge(bm, verts_out):
    x0, x1 = HINGE_X
    z0, z1 = HINGE_Z
    h = HINGE_HALF
    lo = [bm.verts.new(p) for p in ((x0, -h, z0), (x1, -h, z0), (x1, h, z0), (x0, h, z0))]
    hi = [bm.verts.new(p) for p in ((x0, -h, z1), (x1, -h, z1), (x1, h, z1), (x0, h, z1))]
    faces = [bm.faces.new(tuple(reversed(lo))), bm.faces.new(tuple(hi))]
    for i in range(4):
        j = (i + 1) % 4
        faces.append(bm.faces.new((lo[i], lo[j], hi[j], hi[i])))
    for f in faces:
        f.material_index = ALU_IDX
    verts_out.extend(lo + hi)


def bevel_pass(bm, verts, mat_idx, offset, angle):
    bm.edges.index_update()
    edges = sorted({e for v in verts if v.is_valid for e in v.link_edges
                    if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > angle},
                   key=lambda e: e.index)
    if edges:
        bmesh.ops.bevel(bm, geom=edges, offset=offset, segments=1, profile=0.5,
                        affect="EDGES", clamp_overlap=True, material=mat_idx)


def build_pot_mesh(
    name,
    stray_vert=False,
    flush_joint=False,
    short_handle=False,
    float_knob=False,
    float_spout=False,
    float_valve=False,
    odd_facet=False,
):
    bm = bmesh.new()
    try:
        ctx = {"uv": bm.loops.layers.uv.new("UVMap"),
               "isl": bm.faces.layers.int.new("UVIsland"), "next": 0}
        alu, bake, brass = [], [], []
        boiler = list(BOILER)
        if flush_joint:
            # The boiler's top plane drops onto the collector's floor plane.
            mid = 0.5 * (boiler[-3][1] + UPPER[0][1])
            boiler[-2:] = [(boiler[-1][0], mid), (boiler[-1][0], UPPER[0][1])]
        add_faceted(bm, boiler, ctx, alu)
        add_faceted(bm, UPPER, ctx, alu, odd=odd_facet)
        add_faceted(bm, LID, ctx, alu)
        add_spout(bm, UPPER, float_spout, alu)
        add_bracket(bm, alu)
        add_hinge(bm, alu)
        add_round(bm, KNOB, ctx, BAKE_IDX, bake, lift=FLOAT_KNOB if float_knob else 0.0)
        rings = handle_rings(short_handle)
        lathe_solid(bm, rings, BAKE_IDX, ctx, bake)

        # Rivets on the bracket's outer face, aimed down its normal.
        (a0, z0), (a1, z1) = UPPER[UPPER_FLARE[0]], UPPER[UPPER_FLARE[1]]
        slope = (a1 - a0) / (z1 - z0)
        rake = Vector((1.0, 0.0, -slope))
        for z in RIVET_ZS:
            org = Vector((plate_x(z, BRACKET_OUT), 0.0, z))
            add_fastener(bm, org, rake, RIVET, ctx, BRASS_IDX, brass)
        # Valve on the boiler's 225-degree flat, normal read off the taper.
        ang = math.radians(VALVE_DEG)
        nh = Vector((math.cos(ang), math.sin(ang), 0.0))
        (a0, z0), (a1, z1) = BOILER[BOILER_TAPER[0]], BOILER[BOILER_TAPER[1]]
        bslope = (a1 - a0) / (z1 - z0)
        axis = nh + Vector((0.0, 0.0, -bslope))
        org = nh * wall_a(BOILER, VALVE_Z) + Vector((0.0, 0.0, VALVE_Z))
        if float_valve:
            org = org + axis.normalized() * FLOAT_VALVE
        add_fastener(bm, org, axis, VALVE, ctx, BRASS_IDX, brass)

        bevel_pass(bm, alu, ALU_IDX, CHAMFER, CHAMFER_ANGLE)
        bevel_pass(bm, bake, BAKE_IDX, CHAMFER_BAKE, CAP_ANGLE)
        bevel_pass(bm, brass, BRASS_IDX, CHAMFER_BRASS, CAP_ANGLE)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
        if stray_vert:
            bm.verts.new((0.0, 0.0, 0.05))
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for f in bm.faces:
            # Aluminium is faceted; turned bakelite and brass are smooth.
            f.smooth = f.material_index != ALU_IDX
        for e in bm.edges:
            if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(35.0):
                e.smooth = False
        pack_uvs(bm, ctx)
        bm.faces.layers.int.remove(ctx["isl"])
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def pack_uvs(bm, ctx, margin=0.06):
    """One grid cell per UV island: strip islands by their layer tag, else a face each."""
    uv, isl = ctx["uv"], ctx["isl"]
    bm.faces.index_update()
    islands, order = {}, []
    for face in bm.faces:
        key = ("s", face[isl]) if face[isl] else ("f", face.index)
        if key not in islands:
            islands[key] = []
            order.append(key)
        islands[key].append(face)
    cols = max(1, math.ceil(math.sqrt(len(order))))
    rows = max(1, math.ceil(len(order) / cols))
    cw, ch = 1.0 / cols, 1.0 / rows
    pu, pv = margin * cw * 0.5, margin * ch * 0.5
    for idx, key in enumerate(order):
        faces = islands[key]
        coords = {}
        for face in faces:
            if face[isl]:
                coords[face.index] = [tuple(loop[uv].uv) for loop in face.loops]
                continue
            nrm = face.normal
            ax, ay, az = abs(nrm.x), abs(nrm.y), abs(nrm.z)
            pts = []
            for loop in face.loops:
                co = loop.vert.co
                if az >= ax and az >= ay:
                    pts.append((co.x, co.y))
                elif ax >= ay:
                    pts.append((co.y, co.z))
                else:
                    pts.append((co.x, co.z))
            coords[face.index] = pts
        allc = [c for cs in coords.values() for c in cs]
        minx, maxx = min(c[0] for c in allc), max(c[0] for c in allc)
        miny, maxy = min(c[1] for c in allc), max(c[1] for c in allc)
        dx, dy = max(maxx - minx, 1e-8), max(maxy - miny, 1e-8)
        ou, ov = (idx % cols) * cw + pu, (idx // cols) * ch + pv
        for face in faces:
            for loop, (x, y) in zip(face.loops, coords[face.index]):
                loop[uv].uv = (ou + (x - minx) / dx * (cw - 2 * pu),
                               ov + (y - miny) / dy * (ch - 2 * pv))


# --- surface ----------------------------------------------------------------


def _sock(sockets, identifier):
    return next(sk for sk in sockets if sk.identifier == identifier)


def aluminium_material(name):
    """Cast aluminium: light grey, brushed roughness, a warm cast in the dark."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True  # noqa: deprecated in 6.0, still the only path on 4.5
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    # Brushing: noise stretched hard along Z gives fine vertical streaks.
    # They drive roughness and a faint bump, so the facets catch broken,
    # streaky highlights instead of reading as flat grey planes.
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (260.0, 260.0, 5.0)
    nt.links.new(tc.outputs["Object"], mapping.inputs["Vector"])
    brush = nt.nodes.new("ShaderNodeTexNoise")
    brush.inputs["Scale"].default_value = 1.0
    brush.inputs["Detail"].default_value = 3.0
    nt.links.new(mapping.outputs["Vector"], brush.inputs["Vector"])
    # Broad tone: the uneven sheen of cast metal, at hand scale.
    tone = nt.nodes.new("ShaderNodeTexNoise")
    tone.inputs["Scale"].default_value = 18.0
    tone.inputs["Detail"].default_value = 4.0
    nt.links.new(tc.outputs["Object"], tone.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.38
    ramp.color_ramp.elements[0].color = (0.50, 0.51, 0.53, 1.0)
    ramp.color_ramp.elements[1].position = 0.66
    ramp.color_ramp.elements[1].color = (0.80, 0.80, 0.82, 1.0)
    nt.links.new(tone.outputs["Fac"], ramp.inputs["Fac"])
    # Heat tint: a stovetop pot darkens and warms where the flame reaches,
    # strongest at the base and gone ~4.5 cm up the boiler.
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])
    heat = nt.nodes.new("ShaderNodeMapRange")
    heat.inputs["From Min"].default_value = 0.0
    heat.inputs["From Max"].default_value = 0.045
    heat.inputs["To Min"].default_value = 0.9
    heat.inputs["To Max"].default_value = 0.0
    nt.links.new(sep.outputs["Z"], heat.inputs["Value"])
    scorch = nt.nodes.new("ShaderNodeMix")
    scorch.data_type = "RGBA"
    scorch.inputs["B"].default_value = (0.20, 0.17, 0.14, 1.0)
    nt.links.new(heat.outputs["Result"], scorch.inputs["Factor"])
    nt.links.new(ramp.outputs["Color"], scorch.inputs["A"])
    nt.links.new(scorch.outputs["Result"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 0.85
    rmap = nt.nodes.new("ShaderNodeMapRange")
    rmap.inputs["To Min"].default_value = 0.16
    rmap.inputs["To Max"].default_value = 0.42
    nt.links.new(brush.outputs["Fac"], rmap.inputs["Value"])
    nt.links.new(rmap.outputs["Result"], bsdf.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.06
    bump.inputs["Distance"].default_value = 0.0005
    nt.links.new(brush.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def bakelite_material(name):
    """Bakelite: near-black, glossy, with a faint warm brown in the grazing light."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True  # noqa: deprecated in 6.0, still the only path on 4.5
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 90.0
    noise.inputs["Detail"].default_value = 3.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.40
    ramp.color_ramp.elements[0].color = (0.010, 0.009, 0.009, 1.0)
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = (0.028, 0.024, 0.022, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.14
    rough.inputs["To Max"].default_value = 0.24
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def brass_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True  # noqa: deprecated in 6.0, still the only path on 4.5
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.78, 0.52, 0.17, 1.0)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.34
    return mat


def pot_materials():
    return (aluminium_material("PotAluminium"), bakelite_material("PotBakelite"),
            brass_material("PotBrass"))


def assign_slots(obj, mats):
    slots = obj.data.materials
    for i, mat in enumerate(mats):
        if i < len(slots):
            slots[i] = mat
        else:
            slots.append(mat)


# --- measurement ------------------------------------------------------------


def world_bbox(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs, ys, zs = [c.x for c in corners], [c.y for c in corners], [c.z for c in corners]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def uv_stats(mesh):
    uv = mesh.uv_layers.active
    if uv is None:
        return 0.0, 0.0, 1.0, 1.0, 0.0, 0
    data = uv.data
    us = [loop.uv[0] for loop in data]
    vs = [loop.uv[1] for loop in data]
    aabbs = []
    for poly in mesh.polygons:
        pu = [data[i].uv[0] for i in poly.loop_indices]
        pv = [data[i].uv[1] for i in poly.loop_indices]
        aabbs.append((min(pu), min(pv), max(pu), max(pv)))
    span = max(1e-6, max(a[2] - a[0] for a in aabbs), max(a[3] - a[1] for a in aabbs))
    buckets = {}
    for i, a in enumerate(aabbs):
        for c in range(int(a[0] // span), int(a[2] // span) + 1):
            for r in range(int(a[1] // span), int(a[3] // span) + 1):
                buckets.setdefault((c, r), []).append(i)
    overlap = 0.0
    seen = set()
    for members in buckets.values():
        for ii in range(len(members)):
            for jj in range(ii + 1, len(members)):
                i, j = members[ii], members[jj]
                key = (i, j) if i < j else (j, i)
                if key in seen:
                    continue
                seen.add(key)
                a, b = aabbs[i], aabbs[j]
                overlap += max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
                    0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return min(us), min(vs), max(us), max(vs), overlap, len(aabbs)


def face_area(me, poly):
    idxs = poly.vertices
    v0 = me.vertices[idxs[0]].co
    area = 0.0
    for i in range(1, len(idxs) - 1):
        area += (me.vertices[idxs[i]].co - v0).cross(me.vertices[idxs[i + 1]].co - v0).length * 0.5
    return area


def hygiene_audit(me):
    ngons = sum(1 for p in me.polygons if len(p.vertices) > 4)
    zero_area = sum(1 for p in me.polygons if face_area(me, p) <= AREA_EPS)
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        loose_v = sum(1 for v in bm.verts if len(v.link_edges) == 0)
        loose_e = sum(1 for e in bm.edges if len(e.link_faces) == 0)
        nonman = sum(1 for e in bm.edges if not e.is_manifold)
        ret = bmesh.ops.find_doubles(bm, verts=list(bm.verts), dist=DOUBLES_EPS)
        doubles = len(ret.get("targetmap") or {})
        edge90 = 0
        for e in bm.edges:
            if len(e.link_faces) == 2 and abs(
                    math.degrees(e.calc_face_angle(0.0)) - 90.0) < 5.0:
                edge90 += 1
    finally:
        bm.free()
    return {"ngons": ngons, "loose_v": loose_v, "loose_e": loose_e,
            "nonman": nonman, "zero_area": zero_area, "doubles": doubles,
            "edge90": edge90}


def shells(me):
    neighbors = [[] for _ in range(len(me.vertices))]
    for edge in me.edges:
        a, b = edge.vertices
        neighbors[a].append(b)
        neighbors[b].append(a)
    seen = [False] * len(me.vertices)
    groups = []
    for start in range(len(me.vertices)):
        if seen[start]:
            continue
        seen[start] = True
        stack = [start]
        group = []
        while stack:
            cur = stack.pop()
            group.append(cur)
            for nxt in neighbors[cur]:
                if not seen[nxt]:
                    seen[nxt] = True
                    stack.append(nxt)
        groups.append(group)
    return groups


def zfight_pairs(me):
    """Coplanar face pairs from *different shells* (copied from showcase/grindstone)."""
    owner = {}
    for si, g in enumerate(shells(me)):
        for vi in g:
            owner[vi] = si
    faces = [(p.normal.copy(), p.center.copy(), owner.get(p.vertices[0], -1))
             for p in me.polygons]
    kd = KDTree(len(faces))
    for i, (_n, c, _s) in enumerate(faces):
        kd.insert(c, i)
    kd.balance()
    hits = 0
    for i, (ni, ci, si) in enumerate(faces):
        for _co, j, _d in kd.find_range(ci, COPLANAR_CENTRE_MAX):
            if j <= i:
                continue
            nj, cj, sj = faces[j]
            if si == sj:
                continue
            if abs(abs(ni.dot(nj)) - 1.0) > COPLANAR_NORMAL_EPS:
                continue
            if abs(ni.dot(cj - ci)) > COPLANAR_PLANE_EPS:
                continue
            hits += 1
    return hits


def classify(me):
    """Name each shell by material and place; ``other`` collects strays."""
    mats = {}
    for p in me.polygons:
        for i in p.vertices:
            mats.setdefault(i, p.material_index)
    names = ("boiler", "upper", "lid", "spout", "bracket", "hinge",
             "knob", "handle", "rivet", "valve", "other")
    out = {k: [] for k in names}
    for g in shells(me):
        pts = [me.vertices[i].co.copy() for i in g]
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        c = sum(pts, Vector()) / len(pts)
        rec = {"g": g, "pts": pts, "lo": lo, "hi": hi, "ext": hi - lo, "c": c}
        e = rec["ext"]
        m = mats.get(g[0], -1)
        if m == ALU_IDX:
            if e.x > 0.06 and e.z > 0.05 and lo.z < 0.001:
                key = "boiler"
            elif e.x > 0.06 and e.z > 0.05:
                key = "upper"
            elif e.x > 0.06 and lo.z > 0.1:
                key = "lid"
            elif c.x < -0.03:
                key = "spout"
            elif c.x > 0.03 and lo.z < 0.1:
                key = "bracket"
            elif c.x > 0.03:
                key = "hinge"
            else:
                key = "other"
        elif m == BAKE_IDX:
            key = "knob" if lo.z > 0.12 else ("handle" if e.x > 0.03 else "other")
        elif m == BRASS_IDX:
            key = "valve" if c.z < 0.06 else "rivet"
        else:
            key = "other"
        out[key].append(rec)
    return out


def shell_bvh(me, rec):
    group = set(rec["g"])
    remap = {v: i for i, v in enumerate(sorted(group))}
    verts = [me.vertices[v].co.copy() for v in sorted(group)]
    polys = [tuple(remap[v] for v in p.vertices) for p in me.polygons
             if all(v in group for v in p.vertices)]
    return BVHTree.FromPolygons(verts, polys)


def depth_along(bvh, origin, direction):
    """Signed distance from ``origin`` out to the host surface along ``direction``.

    Positive when ``origin`` sits inside the host (the ray exits through
    its skin), negative when it is outside and the surface lies behind.
    """
    hit = bvh.ray_cast(origin, direction)
    if hit[0] is not None:
        return hit[3]
    hit = bvh.ray_cast(origin, -direction)
    if hit[0] is not None:
        return -hit[3]
    return -99.0


def depth_band(bvh, pts, direction):
    ds = [depth_along(bvh, p, direction) for p in pts]
    return (min(ds, default=-99.0), max(ds, default=-99.0))


def symmetry_spread(rec):
    """Worst spread between the eight sectors' outermost radius, ring by ring."""
    rings = {}
    for p in rec["pts"]:
        rings.setdefault(round(p.z, 5), []).append(p)
    worst = 0.0
    for pts in rings.values():
        if len(pts) < SIDES:
            continue
        cx = sum(p.x for p in pts) / len(pts)
        cy = sum(p.y for p in pts) / len(pts)
        sect = {}
        for p in pts:
            ang = math.atan2(p.y - cy, p.x - cx) - PHASE
            k = int(round(ang / (2.0 * math.pi / SIDES))) % SIDES
            r = math.hypot(p.x - cx, p.y - cy)
            sect[k] = max(sect.get(k, 0.0), r)
        if len(sect) == SIDES:
            worst = max(worst, max(sect.values()) - min(sect.values()))
    return worst


def slab_centre(pts, z0, z1):
    sel = [p for p in pts if z0 <= p.z <= z1]
    if not sel:
        return None
    return (sum(p.x for p in sel) / len(sel), sum(p.y for p in sel) / len(sel))


def pot_audit(me):
    parts = classify(me)
    out = {k: len(v) for k, v in parts.items()}
    one = {k: (v[0] if v else None) for k, v in parts.items()}
    boiler, upper, lid = one["boiler"], one["upper"], one["lid"]
    out["shells"] = len(shells(me))

    # Joints along the axis: the collector onto the boiler, lid onto the
    # collector, knob into the lid.
    out["upper_seat"] = (boiler["hi"].z - upper["lo"].z) if boiler and upper else -99.0
    out["lid_seat"] = (upper["hi"].z - lid["lo"].z) if upper and lid else -99.0
    out["knob_bite"] = (lid["hi"].z - one["knob"]["lo"].z) if lid and one["knob"] else -99.0

    # Spout, bracket, handle, hinge: rays against the host read off the mesh.
    nox = Vector((-1.0, 0.0, 0.0))
    pox = Vector((1.0, 0.0, 0.0))
    out["spout_bite"] = (-99.0, -99.0)
    out["spout_reach"] = -99.0
    out["bracket_bite"] = (-99.0, -99.0)
    out["handle_bite"] = (-99.0, -99.0)
    out["hinge_bite"] = (-99.0, -99.0)
    if upper:
        ub = shell_bvh(me, upper)
        sp = one["spout"]
        if sp:
            base = [p for p in sp["pts"] if p.x > sp["hi"].x - 0.0025]
            out["spout_bite"] = depth_band(ub, base, nox)
            out["spout_reach"] = upper["lo"].x - sp["lo"].x
        br = one["bracket"]
        if br:
            # The fin rakes further than it is thick, so split its faces by
            # signed distance off the collector's surface, not by world x.
            sd = []
            for p in br["pts"]:
                loc, nrm, _i, _d = ub.find_nearest(p)
                sd.append((p - loc).dot(nrm) if loc is not None else 0.0)
            cut = 0.5 * (min(sd) + max(sd))
            inner = [p for p, s in zip(br["pts"], sd) if s < cut]
            out["bracket_bite"] = depth_band(ub, inner, pox)
        hg = one["hinge"]
        if hg:
            inner = [p for p in hg["pts"] if p.x < hg["lo"].x + 0.0015 and p.z < upper["hi"].z - 0.001]
            out["hinge_bite"] = depth_band(ub, inner, pox)
    br, hd = one["bracket"], one["handle"]
    if br and hd:
        # Each of the D's two roots is read on its own: the handle verts
        # inside the fin, split at the handle's mid height. A root with no
        # vert inside the fin is a float.
        bb = shell_bvh(me, br)
        zmid = 0.5 * (hd["lo"].z + hd["hi"].z)
        bands = []
        for half in ([p for p in hd["pts"] if p.z >= zmid], [p for p in hd["pts"] if p.z < zmid]):
            ds = [d for d in (depth_along(bb, p, pox) for p in half) if d > 0.0]
            bands.append((min(ds), max(ds)) if ds else (-99.0, -99.0))
        out["handle_bite"] = (min(b[0] for b in bands), max(b[1] for b in bands))

    # Fasteners: height of each head above its host's plane, read off the
    # host mesh at the head's own position.
    def fastener_seat(heads, host):
        bites, prouds = [], []
        hb = shell_bvh(me, host)
        for h in heads:
            loc, nrm, _i, _d = hb.find_nearest(h["c"])
            if loc is None:
                return -99.0, -99.0, -99.0
            hs = [(p - loc).dot(nrm) for p in h["pts"]]
            bites.append(-min(hs))
            prouds.append(max(hs))
        return min(bites), max(bites), min(prouds)

    out["valve_seat"] = fastener_seat(parts["valve"], boiler) if boiler and parts["valve"] else (-99.0,) * 3
    out["rivet_seat"] = fastener_seat(parts["rivet"], br) if br and parts["rivet"] else (-99.0,) * 3

    # Real-world size of the body, and plumb.
    out["foot_flats"] = (boiler["hi"].y - boiler["lo"].y) if boiler else 0.0
    out["collector_flats"] = (upper["hi"].y - upper["lo"].y) if upper else 0.0
    out["total_h"] = max((r["hi"].z for rs in parts.values() for r in rs), default=0.0)
    out["plumb"] = 99.0
    if boiler and upper:
        foot = slab_centre(boiler["pts"], 0.0, 0.003)
        top = slab_centre(upper["pts"], upper["hi"].z - 0.003, upper["hi"].z)
        if foot and top:
            out["plumb"] = math.hypot(foot[0] - top[0], foot[1] - top[1])
    out["symmetry"] = max(symmetry_spread(boiler) if boiler else 99.0,
                          symmetry_spread(upper) if upper else 99.0)
    return out


def make_lod(obj, name, ratio, skip_decimate):
    mesh = obj.data.copy()
    lod = bpy.data.objects.new(name, mesh)
    lod.matrix_world = obj.matrix_world.copy()
    bpy.context.scene.collection.objects.link(lod)
    if not skip_decimate and 0.0 < ratio < 1.0:
        mod = lod.modifiers.new("DecimateBudget", "DECIMATE")
        mod.decimate_type = "COLLAPSE"
        mod.ratio = ratio
    return lod


def hull_collider(obj, name):
    """Compound collider: one hull for the body, spout and lid, one for the handle.

    The knob, rivets and valve stand proud by a few millimetres and add
    triangles and nothing a character could collide with; they are left out.
    """
    parts = classify(obj.data)
    body = [p for k in ("boiler", "upper", "lid", "spout") for r in parts[k] for p in r["pts"]]
    body = [p for i, p in enumerate(body) if i % 2 == 0]
    groups = [body]
    if parts["handle"]:
        groups.append(parts["handle"][0]["pts"][::2])
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for pts in groups:
            tmp = bmesh.new()
            try:
                vs = [tmp.verts.new(p) for p in pts]
                bmesh.ops.convex_hull(tmp, input=vs)
                bmesh.ops.dissolve_limit(tmp, angle_limit=math.radians(9.0),
                                         verts=list(tmp.verts), edges=list(tmp.edges))
                bmesh.ops.triangulate(tmp, faces=list(tmp.faces))
                remap = {}
                for f in tmp.faces:
                    for v in f.verts:
                        if v not in remap:
                            remap[v] = bm.verts.new(v.co)
                    bm.faces.new([remap[v] for v in f.verts])
            finally:
                tmp.free()
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()
    col = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(col)
    return col


def setup_bake_image(obj, target_mat, size):
    img = bpy.data.images.new("PotNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = ALU_IDX
    return img, tex


def bake_normal(high, low):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    high.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    return bpy.ops.object.bake(
        type="NORMAL", use_selected_to_active=True, cage_extrusion=CAGE_EXTRUSION,
        use_cage=False, normal_space="TANGENT", margin=4,
        margin_type="ADJACENT_FACES", use_clear=True, target="IMAGE_TEXTURES",
    )


def export_unity(path, objects):
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_yup=True,
                              export_apply=True, export_draco_mesh_compression_enable=False,
                              export_animations=False)


def band_bad(v, lo, hi):
    return not (lo <= v[0] and v[1] <= hi)


def check(skip_decimate, lift_z=False, lean_pot=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nothing = (None,) * 5
    low = build_pot_mesh("PotLow", **flags)
    hi_flags = {k: v for k, v in flags.items() if k != "stray_vert"}
    high = build_pot_mesh("PotHigh", **hi_flags)
    mats = pot_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
    if lean_pot:
        for v in low.data.vertices:
            v.co.x += LEAN * v.co.z / OUTER_SIZE[2]
    if lift_z or lean_pot:
        low.data.update()
        bpy.context.view_layer.update()
    if len(low.data.polygons) < 6 or not low.data.uv_layers:
        return (fail("pot mesh did not build, or has no UV layer", 3),) + nothing

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat, distinct = len(slots), len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]

    img, tex = setup_bake_image(low, mats[ALU_IDX], BAKE_RES)
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "PotLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "PotLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = hull_collider(high, "PotCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_pot_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    # Blender points TMPDIR at its own temp preference, which on a portable
    # build is the working directory, so the export must not outlive this.
    if os.path.isfile(export_path):
        os.remove(export_path)

    hyg = hygiene_audit(low.data)
    zf = zfight_pairs(low.data)
    ca = pot_audit(low.data)

    print(f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}")
    print(f"measured mat_index_counts={dict(sorted(idx_counts.items()))}")
    print(f"measured base_tris={base_tris} lod1_tris={lod1_tris} "
          f"lod2_tris={lod2_tris} r1={r1:.4f} r2={r2:.4f}")
    print(f"measured nmat={nmat} uv=({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f}) "
          f"overlap={overlap:.6f} nfaces={nfaces}")
    print(f"measured bbox=({size_x:.4f},{size_y:.4f},{size_z:.4f}) "
          f"outer={OUTER_SIZE} zmin={bb[2]:.5f}")
    print(f"measured collider_tris={col_tris} bake={bake_result} "
          f"bake_has_data={img.has_data} export_bytes={export_size}")
    print(f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
          f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf} edge90={hyg['edge90']}")
    print(f"measured shells={ca['shells']} " + " ".join(
        f"{k}={ca[k]}" for k in ("boiler", "upper", "lid", "spout", "bracket", "hinge",
                                 "knob", "handle", "rivet", "valve", "other")))
    print(f"measured axial upper_seat={ca['upper_seat']:.5f} lid_seat={ca['lid_seat']:.5f} "
          f"knob_bite={ca['knob_bite']:.5f}")
    print(f"measured rays spout_bite=({ca['spout_bite'][0]:.5f},{ca['spout_bite'][1]:.5f}) "
          f"spout_reach={ca['spout_reach']:.5f} "
          f"bracket_bite=({ca['bracket_bite'][0]:.5f},{ca['bracket_bite'][1]:.5f}) "
          f"handle_bite=({ca['handle_bite'][0]:.5f},{ca['handle_bite'][1]:.5f}) "
          f"hinge_bite=({ca['hinge_bite'][0]:.5f},{ca['hinge_bite'][1]:.5f})")
    print("measured fasteners (bite_min, bite_max, proud_min) "
          f"valve=({ca['valve_seat'][0]:.5f},{ca['valve_seat'][1]:.5f},{ca['valve_seat'][2]:.5f}) "
          f"rivets=({ca['rivet_seat'][0]:.5f},{ca['rivet_seat'][1]:.5f},{ca['rivet_seat'][2]:.5f})")
    print(f"measured size foot_flats={ca['foot_flats']:.5f} collector_flats={ca['collector_flats']:.5f} "
          f"total_h={ca['total_h']:.5f} plumb={ca['plumb']:.6f} symmetry={ca['symmetry']:.6f}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + nothing
    if nmat != MATERIAL_COUNT or distinct != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct} != {MATERIAL_COUNT}", 5),) + nothing
    for idx, floor in FACE_FLOORS.items():
        if idx_counts.get(idx, 0) < floor:
            return (fail(f"material {idx} faces {idx_counts.get(idx, 0)} < {floor}", 5),) + nothing
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return (fail(f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})", 6),) + nothing
    if overlap > UV_OVERLAP_MAX:
        return (fail(f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}", 7),) + nothing
    if (abs(size_x - OUTER_SIZE[0]) > BBOX_TOL or abs(size_y - OUTER_SIZE[1]) > BBOX_TOL
            or abs(size_z - OUTER_SIZE[2]) > BBOX_TOL):
        return (fail(f"bbox ({size_x:.4f},{size_y:.4f},{size_z:.4f}) off outer {OUTER_SIZE}", 8),) + nothing
    if not (LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX):
        return (fail(f"LOD1 ratio {r1:.4f} not in [{LOD1_RATIO_MIN}, {LOD1_RATIO_MAX}] "
                     "(--skip-decimate is the designed fail)", 9),) + nothing
    if not (LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX):
        return (fail(f"LOD2 ratio {r2:.4f} not in [{LOD2_RATIO_MIN}, {LOD2_RATIO_MAX}]", 9),) + nothing
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 11),) + nothing
    if bake_result != {"FINISHED"} or not img.has_data:
        return (fail(f"bake failed result={bake_result} has_data={img.has_data}", 12),) + nothing
    if export_size <= 0:
        return (fail("export file missing or empty", 13),) + nothing
    if (hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
            or hyg["doubles"] or hyg["ngons"] or zf):
        return (fail(f"hygiene {hyg} zfight={zf} (--stray-vert, --flush-joint are the "
                     "designed fails)", 15),) + nothing
    if abs(bb[2]) > ZMIN_EPS or ca["boiler"] != 1 or abs(
            classify(low.data)["boiler"][0]["lo"].z) > ZMIN_EPS:
        return (fail(f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
                     "(--lift-z is the designed fail)", 16),) + nothing
    if ca["shells"] != SHELLS_EXPECTED or ca["other"]:
        return (fail(f"{ca['shells']} shells, {ca['other']} unclassified, expected "
                     f"{SHELLS_EXPECTED}", 17),) + nothing
    if not (UPPER_SEAT_MIN <= ca["upper_seat"] <= UPPER_SEAT_MAX):
        return (fail(f"collector seat {ca['upper_seat']:.5f} outside [{UPPER_SEAT_MIN}, "
                     f"{UPPER_SEAT_MAX}]", 17),) + nothing
    if band_bad(ca["handle_bite"], HANDLE_BITE_MIN, HANDLE_BITE_MAX):
        return (fail(f"handle bite {ca['handle_bite']} outside [{HANDLE_BITE_MIN}, "
                     f"{HANDLE_BITE_MAX}] (--short-handle is the designed fail)", 17),) + nothing
    if not (KNOB_BITE_MIN <= ca["knob_bite"] <= KNOB_BITE_MAX):
        return (fail(f"knob bite {ca['knob_bite']:.5f} outside [{KNOB_BITE_MIN}, "
                     f"{KNOB_BITE_MAX}] (--float-knob is the designed fail)", 18),) + nothing
    if not (LID_SEAT_MIN <= ca["lid_seat"] <= LID_SEAT_MAX):
        return (fail(f"lid seat {ca['lid_seat']:.5f} outside [{LID_SEAT_MIN}, {LID_SEAT_MAX}]", 18),) + nothing
    if (band_bad(ca["spout_bite"], SPOUT_BITE_MIN, SPOUT_BITE_MAX)
            or not (SPOUT_REACH_MIN <= ca["spout_reach"] <= SPOUT_REACH_MAX)):
        return (fail(f"spout bite {ca['spout_bite']} outside [{SPOUT_BITE_MIN}, {SPOUT_BITE_MAX}] "
                     f"or reach {ca['spout_reach']:.5f} outside [{SPOUT_REACH_MIN}, "
                     f"{SPOUT_REACH_MAX}] (--float-spout is the designed fail)", 18),) + nothing
    if band_bad(ca["bracket_bite"], BRACKET_BITE_MIN, BRACKET_BITE_MAX):
        return (fail(f"bracket bite {ca['bracket_bite']} outside [{BRACKET_BITE_MIN}, "
                     f"{BRACKET_BITE_MAX}]", 18),) + nothing
    if band_bad(ca["hinge_bite"], HINGE_BITE_MIN, HINGE_BITE_MAX):
        return (fail(f"hinge bite {ca['hinge_bite']} outside [{HINGE_BITE_MIN}, {HINGE_BITE_MAX}]", 18),) + nothing
    if ca["rivet"] != len(RIVET_ZS) or ca["valve"] != 1:
        return (fail(f"{ca['rivet']} rivets, {ca['valve']} valves", 18),) + nothing
    for label, seat in (("valve", ca["valve_seat"]), ("rivet", ca["rivet_seat"])):
        if (seat[0] < FASTENER_BITE_MIN or seat[1] > FASTENER_BITE_MAX
                or seat[2] < FASTENER_PROUD_MIN):
            return (fail(f"{label} seat (bite min, bite max, proud min) {seat} outside bite "
                         f"[{FASTENER_BITE_MIN}, {FASTENER_BITE_MAX}] or proud < "
                         f"{FASTENER_PROUD_MIN} (--float-valve is the designed fail)", 18),) + nothing
    if (abs(ca["foot_flats"] - REAL_FOOT_FLATS) > REAL_TOL
            or abs(ca["collector_flats"] - REAL_COLLECTOR_FLATS) > REAL_TOL
            or abs(ca["total_h"] - REAL_TOTAL_H) > REAL_TOL):
        return (fail(f"real size foot {ca['foot_flats']:.4f} collector {ca['collector_flats']:.4f} "
                     f"height {ca['total_h']:.4f} off {REAL_FOOT_FLATS}/{REAL_COLLECTOR_FLATS}/"
                     f"{REAL_TOTAL_H} +-{REAL_TOL}", 19),) + nothing
    if ca["plumb"] > PLUMB_MAX:
        return (fail(f"plumb drift {ca['plumb']:.6f} > {PLUMB_MAX} "
                     "(--lean-pot is the designed fail)", 19),) + nothing
    if ca["symmetry"] > SYM_EPS:
        return (fail(f"eight-fold spread {ca['symmetry']:.6f} > {SYM_EPS} "
                     "(--odd-facet is the designed fail)", 19),) + nothing
    return 0, low, high, mats, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])


SC = 0.2  # the stage and rig are the churn's, scaled to a pot a fifth as tall


def render_still(low, mats, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(mats[ALU_IDX], tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True
    # Level on the floor: turned about Z only.
    low.rotation_euler.z = math.radians(24.0)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=60.0 * SC)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = bpy.data.materials.new("Floor")
    fmat.use_nodes = True  # noqa: deprecated in 6.0, still the only path on 4.5
    fb = fmat.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.03, 0.032, 0.037, 1.0)
    fb.inputs["Roughness"].default_value = 0.7
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 8.5 * SC, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, kind, loc, energy, size, col, rot=(0, 0, 0)):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy * SC * SC
        ld.size = size * SC
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = tuple(c * SC for c in loc)
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    light("Key", "AREA", (-2.4, -3.2, 3.2), 360.0, 3.0, (1.0, 0.95, 0.88), (50, 0, -35))
    light("Fill", "AREA", (3.2, -2.6, 1.6), 60.0, 5.0, (0.74, 0.84, 1.0), (68, 0, 50))
    light("Rim", "AREA", (-1.6, 2.6, 2.4), 220.0, 3.0, (0.62, 0.78, 1.0), (-55, 0, 200))
    ld = bpy.data.lights.new("Wedge", "SPOT")
    ld.energy, ld.color = 220.0 * SC * SC, (1.0, 0.66, 0.34)
    ld.spot_size, ld.spot_blend, ld.shadow_soft_size = math.radians(50.0), 1.0, 0.3 * SC
    wedge = bpy.data.objects.new("Wedge", ld)
    wedge.location = (0.5 * SC, 1.6 * SC, 2.0 * SC)
    wedge.rotation_euler = (Vector((0.25 * SC, 0.5 * SC, 0.0)) - wedge.location).to_track_quat(
        "-Z", "Y").to_euler()
    scene.collection.objects.link(wedge)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.0 * SC, -2.25 * SC, 0.95 * SC)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.016, 0.0, 0.080)
    scene.collection.objects.link(aim)
    con = cam.constraints.new("TRACK_TO")
    con.target = aim
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    scene.camera = cam

    scene.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        scene.cycles.samples = 32
        scene.cycles.device = "CPU"
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "WEBP" if path.lower().endswith(".webp") else "PNG"
    if path.lower().endswith(".webp"):
        scene.render.image_settings.quality = 90
    scene.render.filepath = path
    # Standard, not AgX: AgX washes the aluminium toward pastel grey.
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low], stage=[floor, wall])
    if fcode:
        return fcode
    # The asset-quality floors return 11, which this piece spends on the
    # collider ceiling; remap at the call site.
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall]):
        return 21
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return fail("render produced no file", 14)
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--flush-joint", action="store_true")
    p.add_argument("--short-handle", action="store_true")
    p.add_argument("--float-knob", action="store_true")
    p.add_argument("--float-spout", action="store_true")
    p.add_argument("--float-valve", action="store_true")
    p.add_argument("--lean-pot", action="store_true")
    p.add_argument("--odd-facet", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, mats, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        lean_pot=args.lean_pot,
        stray_vert=args.stray_vert,
        flush_joint=args.flush_joint,
        short_handle=args.short_handle,
        float_knob=args.float_knob,
        float_spout=args.float_spout,
        float_valve=args.float_valve,
        odd_facet=args.odd_facet,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, mats, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("moka pot OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
