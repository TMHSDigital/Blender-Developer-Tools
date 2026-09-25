"""Game-ready butter churn — a showcase piece, not an example.

Asserts budget conformance of a procedural plunge churn: a tall staved
body that narrows toward the top, three iron hoops, a bottom of three
boards set in a croze, a lid of two boards with a hole for the handle,
and a cross dasher whose handle runs up through the lid. Carried through
UVs, three materials (oak, maple, iron), a high-to-low normal bake, an
LOD chain, a compound convex collider, and a Unity glTF export.

The budget that matters here is the one a churn fails invisibly: the
dasher has to plunge. The body narrows toward the top, so a plunger that
clears the staves at rest can jam a hand's width up the stroke. It still
sits inside the body without touching it, the handle still clears the lid
and the bounding box does not move; only the stroke knows. The piece
reads the inner wall off the staves and the plunger's reach off the
dasher, and asserts how far the plunger can travel before it would meet
the wall or the lid.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--short-stave`` the named staves,
``--one-piece-bottom`` the bottom boards, ``--short-handle`` the handle
bite, ``--float-hoops`` the hoop seat, ``--float-lid`` the lid seat,
``--tight-hole`` the handle clearance, ``--wide-dasher`` the stroke.

No randomness: every stave's tone is a closed-form term of its index.
DECIMATE COLLAPSE triangle counts are not byte-identical across Blender
versions — the LOD gate is a ratio band.

    blender --background --python butter_churn.py --
    blender --background --python butter_churn.py -- --wide-dasher
    blender --background --python butter_churn.py -- --output butter_churn.png
"""
import argparse
import math
import os
import sys
import tempfile
import traceback

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

# The body: sixteen staves on a straight taper, wider at the foot.
HEIGHT = 0.750
R_BOT = 0.170
R_TOP = 0.120
N_STAVES = 16
STAVE_T = 0.018
STAVE_GAP = 0.0008
STAVE_FRACS = (0.0, 0.25, 0.75, 1.0)
BODY_RINGS = 6
CHAMFER = 0.0015
SHORT_STAVE = 0.006
# Each stave's foot and top are cut sloping inward, so the churn stands on
# its outer edges. Alternate staves take a double cant: at one cant, two
# neighbours' end faces are only 5.6 degrees apart in bearing and still
# match as one plane.
END_CANT = 0.0015

# Hoops: banded iron sampled at each stave's interior vertices, so every
# hoop vertex sits radially over a stave vertex at the same height.
HOOP_ZS = (0.060, 0.360, 0.655)
HOOP_H = 0.024
HOOP_BITE = 0.0025
HOOP_PROUD = 0.005
HOOP_CH = 0.0015
FLOAT_HOOP = 0.004

# Bottom: three boards in a croze cut into the staves' inner face.
BOTTOM_Z = 0.012
BOTTOM_T = 0.022
CROZE = 0.0035
N_BOARDS = 3
BOARD_SEAM = 0.0012
DISK_SEG = 48
BOARD_STEP = 0.0006

# Lid: two boards resting on the stave tops, a hole for the handle.
LID_T = 0.022
LID_SEAT = 0.002
LID_OVER = 0.008
LID_SEAM = 0.0012
HOLE_CLEAR = 0.005
TIGHT_HOLE = -0.002
FLOAT_LID = 0.005
LID_ARC = 24
LID_STEP = 0.0006

# Dasher: a round maple handle through the lid, two crossed slats below.
HANDLE_R = 0.016
HANDLE_TOP = 1.050
HANDLE_BITE = 0.014
SHORT_HANDLE = -0.005
PLUNGER_Z = BOTTOM_Z + BOTTOM_T + 0.050
SLAT_REACH = 0.100
WIDE_REACH = 0.125
SLAT_W = 0.024
SLAT_T = 0.020
SLAT_STEP = 0.004
WALL_CLEAR = 0.010

BBOX_TOL = 0.020
OUTER_SIZE = (0.340, 0.340, 1.050)

BASE_TRIS_MIN = 5000
BASE_TRIS_MAX = 6500
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
FACE_FLOORS = {0: 2000, 1: 140, 2: 500}
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 200
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
STAVE_Z_MAX = 1e-4
BOARD_SEAM_MIN = 0.0006
BOARD_SEAM_MAX = 0.0025
HANDLE_BITE_MIN = 0.008
HANDLE_BITE_MAX = 0.020
HOOP_BITE_MIN = 0.0010
HOOP_BITE_MAX = 0.0045
HOOP_PROUD_MIN = 0.0030
LID_SEAT_MIN = 0.0010
LID_SEAT_MAX = 0.0040
HOLE_CLEAR_MIN = 0.002
HOLE_CLEAR_MAX = 0.010
STROKE_MIN = 0.400

OAK_IDX = 0
MAPLE_IDX = 1
IRON_IDX = 2


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


def r_out(z):
    return R_BOT + (R_TOP - R_BOT) * z / HEIGHT


def r_in(z):
    return r_out(z) - STAVE_T


def stave_angles(k):
    """Angles of stave ``k``'s vertices across its width, gap split either side."""
    span = 2.0 * math.pi / N_STAVES
    gap = STAVE_GAP / R_TOP
    a0 = k * span + gap * 0.5
    width = span - gap
    return [a0 + width * f for f in STAVE_FRACS]


def ring_zs():
    """Stave ring heights: a uniform run plus both edges of every hoop and the croze."""
    zs = {round(HEIGHT * k / BODY_RINGS, 6) for k in range(BODY_RINGS + 1)}
    for z in HOOP_ZS:
        zs |= {round(z, 6), round(z + HOOP_H, 6)}
    zs |= {round(BOTTOM_Z, 6), round(BOTTOM_Z + BOTTOM_T, 6)}
    return sorted(zs)


# --- construction -----------------------------------------------------------


def new_island(ctx):
    ctx["next"] += 1
    return ctx["next"]


def stamp(ctx, face, island, uvmap):
    face[ctx["isl"]] = island
    for loop in face.loops:
        loop[ctx["uv"]].uv = uvmap[loop.vert]


def loft(bm, rings, mat_idx, ctx, closed=True):
    """Quads between consecutive rings of equal length; one strip island."""
    island = new_island(ctx)
    n = len(rings[0])
    arc = [0.0]
    for a, b in zip(rings, rings[1:]):
        ca = sum((v.co for v in a), Vector()) / n
        cb = sum((v.co for v in b), Vector()) / n
        arc.append(arc[-1] + (cb - ca).length)
    faces = []
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for i in range(n if closed else n - 1):
            j = (i + 1) % n
            f = bm.faces.new((a[i], a[j], b[j], b[i]))
            f.material_index = mat_idx
            stamp(ctx, f, island, {a[i]: (arc[k], i / n), a[j]: (arc[k], (i + 1) / n),
                                   b[j]: (arc[k + 1], (i + 1) / n), b[i]: (arc[k + 1], i / n)})
            faces.append(f)
    return faces


def add_stave(bm, k, ctx, z0, verts_out):
    """One stave: an annular sector on the taper, capped by quads at both ends."""
    angs = stave_angles(k)
    rings = []
    for z in ring_zs():
        # ``z0`` lifts only the foot ring, so a short stave stops above the
        # floor while its hoop and croze rings stay where the others are.
        zz = z if z > 0.0 else z0
        c = END_CANT * (1 + k % 2)
        cant = c if z <= 0.0 else (-c if z >= HEIGHT else 0.0)
        outer = [Vector((r_out(z) * math.cos(a), r_out(z) * math.sin(a), zz)) for a in angs]
        inner = [Vector((r_in(z) * math.cos(a), r_in(z) * math.sin(a), zz + cant))
                 for a in reversed(angs)]
        rings.append([bm.verts.new(p) for p in outer + inner])
    loft(bm, rings, OAK_IDX, ctx)
    m = len(angs)
    for ring, flip in ((rings[0], True), (rings[-1], False)):
        for i in range(m - 1):
            o0, o1 = ring[i], ring[i + 1]
            i1, i0 = ring[2 * m - 2 - i], ring[2 * m - 1 - i]
            vs = (o0, o1, i1, i0)
            f = bm.faces.new(tuple(reversed(vs)) if flip else vs)
            f.material_index = OAK_IDX
            f[ctx["isl"]] = 0
    for r in rings:
        verts_out.extend(r)


def add_hoop(bm, z, ctx, float_hoop=False):
    """A banded hoop sampled at every stave's interior vertex angles.

    Its inner face sits HOOP_BITE inside the stave's outer face at each
    edge height, read from the same taper, so the band follows the staves.
    """
    angs = [a for k in range(N_STAVES) for a in stave_angles(k)[1:-1]]
    off_in = FLOAT_HOOP if float_hoop else -HOOP_BITE
    sec = [(off_in, 0.0), (HOOP_PROUD - HOOP_CH, 0.0), (HOOP_PROUD, HOOP_CH),
           (HOOP_PROUD, HOOP_H - HOOP_CH), (HOOP_PROUD - HOOP_CH, HOOP_H), (off_in, HOOP_H)]
    cols = []
    for a in angs:
        c, s = math.cos(a), math.sin(a)
        cols.append([bm.verts.new(((r_out(z + dz) + dr) * c, (r_out(z + dz) + dr) * s, z + dz))
                     for dr, dz in sec])
    island = new_island(ctx)
    n, m = len(cols), len(sec)
    for i in range(n):
        a, b = cols[i], cols[(i + 1) % n]
        for j in range(m):
            jj = (j + 1) % m
            f = bm.faces.new((a[j], a[jj], b[jj], b[j]))
            f.material_index = IRON_IDX
            stamp(ctx, f, island, {a[j]: (i / n, j / m), a[jj]: (i / n, (j + 1) / m),
                                   b[jj]: ((i + 1) / n, (j + 1) / m), b[j]: ((i + 1) / n, j / m)})


def clip_x(poly, x0, x1):
    """Clip a convex (x, y) polygon to x0 <= x <= x1 (Sutherland-Hodgman)."""
    def cut(pts, keep, xc):
        out = []
        for i, p in enumerate(pts):
            q = pts[(i + 1) % len(pts)]
            pin, qin = keep(p[0]), keep(q[0])
            if pin:
                out.append(p)
            if pin != qin:
                t = (xc - p[0]) / (q[0] - p[0])
                out.append((xc, p[1] + (q[1] - p[1]) * t))
        return out
    pts = cut(poly, lambda x: x >= x0, x0)
    return cut(pts, lambda x: x <= x1, x1)


def extrude_polygon(bm, poly, z0, z1, mat_idx, verts_out):
    """A board from an (x, y) outline: two n-gon caps and quad sides."""
    lo = [bm.verts.new((x, y, z0)) for x, y in poly]
    hi = [bm.verts.new((x, y, z1)) for x, y in poly]
    faces = [bm.faces.new(lo), bm.faces.new(list(reversed(hi)))]
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        faces.append(bm.faces.new((lo[j], lo[i], hi[i], hi[j])))
    for f in faces:
        f.material_index = mat_idx
    verts_out.extend(lo + hi)


def add_bottom(bm, one_piece, verts_out):
    zm = BOTTOM_Z + BOTTOM_T * 0.5
    rr = r_in(zm) + CROZE
    disk = [(rr * math.cos(2 * math.pi * i / DISK_SEG), rr * math.sin(2 * math.pi * i / DISK_SEG))
            for i in range(DISK_SEG)]
    if one_piece:
        extrude_polygon(bm, disk, BOTTOM_Z, BOTTOM_Z + BOTTOM_T, OAK_IDX, verts_out)
        return
    w = (2.0 * rr - BOARD_SEAM * (N_BOARDS - 1)) / N_BOARDS
    for k in range(N_BOARDS):
        x0 = -rr + k * (w + BOARD_SEAM)
        # Alternate boards step up and in by BOARD_STEP: level with their
        # neighbours, their faces and the rim chord a seam splits would each
        # be one plane shared by two boards.
        step = BOARD_STEP if k % 2 else 0.0
        src = [(x * (rr - step) / rr, y * (rr - step) / rr) for x, y in disk]
        poly = clip_x(src, x0 - (1.0 if k == 0 else 0.0), x0 + w + (1.0 if k == N_BOARDS - 1 else 0.0))
        extrude_polygon(bm, poly, BOTTOM_Z + step, BOTTOM_Z + BOTTOM_T + step, OAK_IDX, verts_out)


def add_lid(bm, hole_r, lift, verts_out):
    """Two half-annulus boards, seam across the hole, resting on the stave tops."""
    ro = r_out(HEIGHT) + LID_OVER
    z0 = HEIGHT - LID_SEAT + lift
    s = LID_SEAM * 0.5
    t_o = math.acos(s / ro)
    t_i = math.acos(s / hole_r)
    for side in (1.0, -1.0):
        outer = [(ro * math.cos(-t_o + 2 * t_o * k / LID_ARC), ro * math.sin(-t_o + 2 * t_o * k / LID_ARC))
                 for k in range(LID_ARC + 1)]
        inner = [(hole_r * math.cos(t_i - 2 * t_i * k / 8), hole_r * math.sin(t_i - 2 * t_i * k / 8))
                 for k in range(9)]
        poly = [(side * x, y) for x, y in outer + inner]
        if side < 0:
            poly.reverse()
        # One board a step proud of the other, so the two do not share a face plane.
        step = LID_STEP if side < 0 else 0.0
        extrude_polygon(bm, poly, z0 + step, z0 + step + LID_T, OAK_IDX, verts_out)


def lathe_z(bm, profile, n, mat_idx, ctx, base):
    """Revolve an (r, z) profile about the vertical axis through ``base``."""
    rings, poles = [], []
    for p in profile:
        if p.x <= 0.0:
            poles.append(bm.verts.new(base + Vector((0.0, 0.0, p.y))))
        else:
            rings.append([bm.verts.new(base + Vector((p.x * math.cos(2 * math.pi * k / n),
                                                       p.x * math.sin(2 * math.pi * k / n), p.y)))
                          for k in range(n)])
    loft(bm, rings, mat_idx, ctx)
    island = new_island(ctx)
    for pole, ring, flip in ((poles[0], rings[0], True), (poles[1], rings[-1], False)):
        for i in range(n):
            j = (i + 1) % n
            vs = (pole, ring[j], ring[i]) if flip else (pole, ring[i], ring[j])
            f = bm.faces.new(vs)
            f.material_index = mat_idx
            stamp(ctx, f, island, {pole: (0.5 if flip else 1.5, (i + 0.5) / n),
                                   ring[i]: (0.0 if flip else 1.0, i / n),
                                   ring[j]: (0.0 if flip else 1.0, (i + 1) / n)})


def handle_profile(z_start, lid_z0):
    """(r, z) from the handle's foot, with rings at both faces of the lid."""
    r = HANDLE_R
    top = HANDLE_TOP - z_start
    rings = [(r * 0.85, 0.0), (r, 0.004), (r, lid_z0 - z_start), (r, lid_z0 + LID_T - z_start),
             (r, top - 0.060), (r * 1.25, top - 0.035), (r * 1.35, top - 0.018), (r * 1.05, top)]
    return [Vector((0.0, 0.0))] + [Vector(p) for p in rings] + [Vector((0.0, top))]


def build_churn_mesh(
    name,
    stray_vert=False,
    short_stave=False,
    one_piece_bottom=False,
    short_handle=False,
    float_hoops=False,
    float_lid=False,
    tight_hole=False,
    wide_dasher=False,
):
    bm = bmesh.new()
    try:
        ctx = {"uv": bm.loops.layers.uv.new("UVMap"),
               "isl": bm.faces.layers.int.new("UVIsland"), "next": 0}
        wood = []
        for k in range(N_STAVES):
            add_stave(bm, k, ctx, SHORT_STAVE if (short_stave and k == 0) else 0.0, wood)
        add_bottom(bm, one_piece_bottom, wood)
        hole_r = HANDLE_R + (TIGHT_HOLE if tight_hole else HOLE_CLEAR)
        lid_lift = FLOAT_LID if float_lid else 0.0
        add_lid(bm, hole_r, lid_lift, wood)
        # Dasher: two crossed slats, the second a step higher so no two of
        # their faces share a plane, and the handle's foot biting both.
        reach = WIDE_REACH if wide_dasher else SLAT_REACH
        maple = []
        extrude_polygon(bm, [(-reach, -SLAT_W / 2), (reach, -SLAT_W / 2), (reach, SLAT_W / 2), (-reach, SLAT_W / 2)],
                PLUNGER_Z, PLUNGER_Z + SLAT_T, MAPLE_IDX, maple)
        extrude_polygon(bm, [(-SLAT_W / 2, -reach), (SLAT_W / 2, -reach), (SLAT_W / 2, reach), (-SLAT_W / 2, reach)],
                PLUNGER_Z + SLAT_STEP, PLUNGER_Z + SLAT_STEP + SLAT_T, MAPLE_IDX, maple)
        # Real edges only (a stave's width and a disk's rim meet at a few
        # degrees), sorted by index, each pass pinned to its own material.
        for verts, mat_idx in ((wood, OAK_IDX), (maple, MAPLE_IDX)):
            bm.edges.index_update()
            edges = sorted({e for v in verts if v.is_valid for e in v.link_edges
                            if e.calc_face_angle(0.0) > math.radians(20.0)},
                           key=lambda e: e.index)
            bmesh.ops.bevel(bm, geom=edges, offset=CHAMFER, segments=1, profile=0.5,
                            affect="EDGES", clamp_overlap=True, material=mat_idx)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
        for z in HOOP_ZS:
            add_hoop(bm, z, ctx, float_hoop=float_hoops)
        z_start = PLUNGER_Z + SLAT_STEP + SLAT_T - (SHORT_HANDLE if short_handle else HANDLE_BITE)
        lathe_z(bm, handle_profile(z_start, HEIGHT - LID_SEAT + lid_lift), 12, MAPLE_IDX, ctx,
                Vector((0.0, 0.0, z_start)))
        if stray_vert:
            bm.verts.new((0.0, 0.0, 0.3))
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for f in bm.faces:
            f.smooth = True
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
    paint_pieces(me)
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


def paint_pieces(me):
    """Per-piece ``PlankTone`` and ``GrainDir`` (each shell's longest extent)."""
    npoly = len(me.polygons)
    tone = [0.5] * npoly
    grain = [(0.0, 0.0, 1.0)] * npoly
    vf = [[] for _ in range(len(me.vertices))]
    for p in me.polygons:
        for i in p.vertices:
            vf[i].append(p.index)
    for k, g in enumerate(shells(me)):
        pts = [me.vertices[i].co for i in g]
        ext = [max(p[a] for p in pts) - min(p[a] for p in pts) for a in range(3)]
        axis = ext.index(max(ext))
        d = tuple(1.0 if a == axis else 0.0 for a in range(3))
        t = 0.5 + 0.34 * (((k * 0.6180339887 + 0.3) % 1.0) - 0.5)
        for fi in {fi for i in g for fi in vf[i]}:
            tone[fi] = t
            grain[fi] = d
    a = me.attributes.new("PlankTone", "FLOAT", "FACE")
    a.data.foreach_set("value", tone)
    b = me.attributes.new("GrainDir", "FLOAT_VECTOR", "FACE")
    b.data.foreach_set("vector", [c for v in grain for c in v])


# --- surface ----------------------------------------------------------------


def _sock(sockets, identifier):
    return next(sk for sk in sockets if sk.identifier == identifier)


def wood_material(name, dark, light, rough=(0.72, 0.52)):
    """Timber whose grain runs along ``GrainDir`` and whose tone varies by piece."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    gdir = nt.nodes.new("ShaderNodeAttribute")
    gdir.attribute_name = "GrainDir"
    tone = nt.nodes.new("ShaderNodeAttribute")
    tone.attribute_name = "PlankTone"
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(coord.outputs["Object"], dot.inputs[0])
    nt.links.new(gdir.outputs["Vector"], dot.inputs[1])
    squash = nt.nodes.new("ShaderNodeMath")
    squash.operation = "MULTIPLY"
    squash.inputs[1].default_value = 0.94
    nt.links.new(dot.outputs["Value"], squash.inputs[0])
    along = nt.nodes.new("ShaderNodeVectorMath")
    along.operation = "SCALE"
    nt.links.new(gdir.outputs["Vector"], along.inputs[0])
    nt.links.new(squash.outputs["Value"], along.inputs["Scale"])
    grain_co = nt.nodes.new("ShaderNodeVectorMath")
    grain_co.operation = "SUBTRACT"
    nt.links.new(coord.outputs["Object"], grain_co.inputs[0])
    nt.links.new(along.outputs["Vector"], grain_co.inputs[1])
    shift = nt.nodes.new("ShaderNodeVectorMath")
    shift.operation = "ADD"
    nt.links.new(grain_co.outputs["Vector"], shift.inputs[0])
    nt.links.new(tone.outputs["Fac"], shift.inputs[1])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 34.0
    noise.inputs["Detail"].default_value = 6.0
    noise.inputs["Roughness"].default_value = 0.62
    nt.links.new(shift.outputs["Vector"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    gain = nt.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY_ADD"
    gain.inputs[1].default_value = 1.2
    gain.inputs[2].default_value = 0.40
    nt.links.new(tone.outputs["Fac"], gain.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    _sock(mix.inputs, "Factor_Float").default_value = 1.0
    nt.links.new(ramp.outputs["Color"], _sock(mix.inputs, "A_Color"))
    nt.links.new(gain.outputs["Value"], _sock(mix.inputs, "B_Color"))
    nt.links.new(_sock(mix.outputs, "Result_Color"), bsdf.inputs["Base Color"])
    rmap = nt.nodes.new("ShaderNodeMapRange")
    rmap.inputs["To Min"].default_value = rough[0]
    rmap.inputs["To Max"].default_value = rough[1]
    nt.links.new(noise.outputs["Fac"], rmap.inputs["Value"])
    nt.links.new(rmap.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def iron_material(name):
    """Forged iron: near-black, rough, rusted in patches. Not chrome."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 40.0
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (0.035, 0.033, 0.031, 1.0)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (0.20, 0.085, 0.035, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 0.65
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.55
    rough.inputs["To Max"].default_value = 0.85
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def churn_materials():
    return (
        wood_material("ChurnOak", (0.085, 0.040, 0.016), (0.28, 0.14, 0.060)),
        wood_material("ChurnMaple", (0.26, 0.17, 0.09), (0.55, 0.40, 0.24), rough=(0.62, 0.45)),
        iron_material("ChurnIron"),
    )


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
    finally:
        bm.free()
    return {"ngons": ngons, "loose_v": loose_v, "loose_e": loose_e,
            "nonman": nonman, "zero_area": zero_area, "doubles": doubles}


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
    mats = {}
    for p in me.polygons:
        for i in p.vertices:
            mats.setdefault(i, p.material_index)
    out = {"stave": [], "board": [], "lid": [], "hoop": [], "slat": [], "handle": [], "other": []}
    for g in shells(me):
        pts = [me.vertices[i].co.copy() for i in g]
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        rec = {"g": g, "pts": pts, "lo": lo, "hi": hi, "ext": hi - lo,
               "c": sum(pts, Vector()) / len(pts)}
        m = mats.get(g[0], -1)
        e = rec["ext"]
        if m == OAK_IDX:
            if e.z > HEIGHT * 0.5:
                out["stave"].append(rec)
            elif lo.z > HEIGHT * 0.5:
                out["lid"].append(rec)
            else:
                out["board"].append(rec)
        elif m == MAPLE_IDX:
            out["handle" if e.z > 0.3 else "slat"].append(rec)
        elif m == IRON_IDX:
            out["hoop"].append(rec)
        else:
            out["other"].append(rec)
    return out


def radial(p):
    return math.hypot(p.x, p.y)


def churn_audit(me):
    parts = classify(me)
    out = {k: len(v) for k, v in parts.items()}
    staves = parts["stave"]
    out["stave_z"] = max((r["lo"].z for r in staves), default=99.0)

    # Bottom boards: count and the seams between neighbours.
    boards = sorted(parts["board"], key=lambda r: r["c"].x)
    seams = [b["lo"].x - a["hi"].x for a, b in zip(boards, boards[1:])]
    out["seam"] = (min(seams, default=-99.0), max(seams, default=99.0))

    # Hoops on the staves: every hoop vertex against the stave vertex it
    # was built over, measured radially.
    spts = [p for r in staves for p in r["pts"]]
    kd = KDTree(len(spts))
    for i, p in enumerate(spts):
        kd.insert(p, i)
    kd.balance()
    bites, prouds = [], []
    for h in parts["hoop"]:
        ds = sorted(radial(kd.find(p)[0]) - radial(p) for p in h["pts"])
        n_in = len(ds) // 3
        bites.append(min(ds[-n_in:]))
        prouds.append(-max(ds[:n_in]))
    out["hoop_bite"] = (min(bites, default=-99.0), max(bites, default=99.0))
    out["hoop_proud"] = min(prouds, default=-99.0)

    # The lid rests on the stave tops; the handle clears the lid's hole.
    top = max((r["hi"].z for r in staves), default=0.0)
    lids = parts["lid"]
    seats = [top - r["lo"].z for r in lids]
    out["lid_seat"] = (min(seats, default=-99.0), max(seats, default=99.0))
    out["hole_clear"] = -99.0
    handle = parts["handle"][0] if parts["handle"] else None
    if handle and lids:
        lz0 = min(r["lo"].z for r in lids)
        lz1 = max(r["hi"].z for r in lids)
        hr = max((radial(p) for p in handle["pts"] if lz0 - 1e-6 <= p.z <= lz1 + 1e-6), default=99.0)
        lr = min(radial(p) for r in lids for p in r["pts"])
        out["hole_clear"] = lr - hr

    # The handle's foot bites the slats.
    slats = parts["slat"]
    out["handle_bite"] = -99.0
    if handle and slats:
        out["handle_bite"] = max(r["hi"].z for r in slats) - handle["lo"].z

    # Stroke: the inner wall read off the staves, ring by ring, against the
    # plunger's reach about the handle's axis.
    out["stroke"] = -99.0
    if slats and staves:
        reach = max(radial(p) for r in slats for p in r["pts"])
        p_top = max(r["hi"].z for r in slats)
        walls = {}
        for p in spts:
            z = round(p.z, 5)
            walls[z] = min(walls.get(z, 99.0), radial(p))
        table = sorted(walls.items())
        need = reach + WALL_CLEAR
        limit = min((r["lo"].z for r in lids), default=top)
        z_ok = None
        for (za, ra), (zb, rb) in zip(table, table[1:]):
            if za < p_top - 1e-6:
                continue
            if rb >= need:
                continue
            if ra >= need:
                z_ok = za + (zb - za) * (ra - need) / (ra - rb)
            else:
                z_ok = za
            break
        if z_ok is None:
            z_ok = limit
        out["reach"] = reach
        out["stroke"] = min(z_ok, limit) - p_top
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
    """Compound collider: one hull for the staves and lid, one for the handle above it.

    The hoops stand 5 mm proud of the staves and are left out: in the hull
    they add triangles and nothing a character could collide with.
    """
    me = obj.data
    parts = classify(me)
    body = [p for k in ("stave", "lid") for r in parts[k] for p in r["pts"]]
    body = [p for i, p in enumerate(body) if i % 3 == 0]
    groups = [body]
    if parts["handle"]:
        top = max(p.z for r in parts["lid"] for p in r["pts"]) if parts["lid"] else HEIGHT
        groups.append([p for p in parts["handle"][0]["pts"] if p.z >= top - 0.01])
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for pts in groups:
            tmp = bmesh.new()
            try:
                vs = [tmp.verts.new(p) for p in pts]
                bmesh.ops.convex_hull(tmp, input=vs)
                bmesh.ops.dissolve_limit(tmp, angle_limit=math.radians(4.0),
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
    img = bpy.data.images.new("ChurnNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = OAK_IDX
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
    bpy.ops.export_scene.gltf(
        filepath=path, use_selection=True, export_yup=True, export_apply=True,
        export_draco_mesh_compression_enable=False, export_animations=False,
    )


def check(skip_decimate, lift_z=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nothing = (None,) * 5
    low = build_churn_mesh("ChurnLow", **flags)
    hi_flags = {k: v for k, v in flags.items() if k != "stray_vert"}
    high = build_churn_mesh("ChurnHigh", **hi_flags)
    mats = churn_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()
    if len(low.data.polygons) < 6 or not low.data.uv_layers:
        return (fail("churn mesh did not build, or has no UV layer", 3),) + nothing

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat, distinct = len(slots), len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]

    img, tex = setup_bake_image(low, mats[OAK_IDX], BAKE_RES)
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "ChurnLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "ChurnLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = hull_collider(high, "ChurnCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_churn_{os.getpid()}.glb")
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
    ca = churn_audit(low.data)

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
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}")
    print(f"measured parts staves={ca['stave']} boards={ca['board']} lid={ca['lid']} "
          f"hoops={ca['hoop']} slats={ca['slat']} handle={ca['handle']} other={ca['other']} "
          f"stave_z={ca['stave_z']:.5f}")
    print(f"measured joints seam=({ca['seam'][0]:.5f},{ca['seam'][1]:.5f}) "
          f"handle_bite={ca['handle_bite']:.5f}")
    print(f"measured seats hoop_bite=({ca['hoop_bite'][0]:.5f},{ca['hoop_bite'][1]:.5f}) "
          f"hoop_proud={ca['hoop_proud']:.5f} lid=({ca['lid_seat'][0]:.5f},{ca['lid_seat'][1]:.5f}) "
          f"hole_clear={ca['hole_clear']:.5f}")
    print(f"measured stroke={ca['stroke']:.5f} reach={ca.get('reach', 0.0):.5f}")

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
        return (fail(f"hygiene {hyg} zfight={zf} (--stray-vert is the designed fail)", 15),) + nothing
    if abs(bb[2]) > ZMIN_EPS:
        return (fail(f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
                     "(--lift-z is the designed fail)", 16),) + nothing
    if ca["stave"] != N_STAVES or ca["stave_z"] > STAVE_Z_MAX:
        return (fail(f"staves: {ca['stave']} of {N_STAVES}, worst stave z={ca['stave_z']:.5f} "
                     f"> {STAVE_Z_MAX} (--short-stave is the designed fail)", 16),) + nothing
    if (ca["board"] != N_BOARDS or ca["seam"][0] < BOARD_SEAM_MIN
            or ca["seam"][1] > BOARD_SEAM_MAX):
        return (fail(f"{ca['board']} of {N_BOARDS} bottom boards, seams {ca['seam']} outside "
                     f"[{BOARD_SEAM_MIN}, {BOARD_SEAM_MAX}] (--one-piece-bottom is the designed fail)",
                     17),) + nothing
    if not (HANDLE_BITE_MIN <= ca["handle_bite"] <= HANDLE_BITE_MAX):
        return (fail(f"handle bite {ca['handle_bite']:.5f} outside [{HANDLE_BITE_MIN}, "
                     f"{HANDLE_BITE_MAX}] (--short-handle is the designed fail)", 17),) + nothing
    if (ca["hoop"] != len(HOOP_ZS) or ca["hoop_bite"][0] < HOOP_BITE_MIN
            or ca["hoop_bite"][1] > HOOP_BITE_MAX or ca["hoop_proud"] < HOOP_PROUD_MIN):
        return (fail(f"{ca['hoop']} of {len(HOOP_ZS)} hoops, bite {ca['hoop_bite']} outside "
                     f"[{HOOP_BITE_MIN}, {HOOP_BITE_MAX}] or proud {ca['hoop_proud']:.5f} < "
                     f"{HOOP_PROUD_MIN} (--float-hoops is the designed fail)", 18),) + nothing
    if (ca["lid"] != 2 or ca["lid_seat"][0] < LID_SEAT_MIN or ca["lid_seat"][1] > LID_SEAT_MAX):
        return (fail(f"{ca['lid']} of 2 lid boards, seat {ca['lid_seat']} outside "
                     f"[{LID_SEAT_MIN}, {LID_SEAT_MAX}] (--float-lid is the designed fail)", 18),) + nothing
    if not (HOLE_CLEAR_MIN <= ca["hole_clear"] <= HOLE_CLEAR_MAX):
        return (fail(f"handle clears the lid hole by {ca['hole_clear']:.5f}, outside "
                     f"[{HOLE_CLEAR_MIN}, {HOLE_CLEAR_MAX}] (--tight-hole is the designed fail)",
                     18),) + nothing
    if ca["stroke"] < STROKE_MIN:
        return (fail(f"plunge stroke {ca['stroke']:.5f} < {STROKE_MIN} "
                     "(--wide-dasher is the designed fail)", 20),) + nothing
    return 0, low, high, mats, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])


def render_still(low, mats, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(mats[OAK_IDX], tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True
    # Level on the floor: turned about Z only.
    low.rotation_euler.z = math.radians(10.0)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=60.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = bpy.data.materials.new("Floor")
    fmat.use_nodes = True
    fb = fmat.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.03, 0.032, 0.037, 1.0)
    fb.inputs["Roughness"].default_value = 0.7
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 8.5, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, kind, loc, energy, size, col, rot=(0, 0, 0)):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        if kind == "AREA":
            ld.size = size
        else:
            ld.shadow_soft_size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    light("Key", "AREA", (-2.4, -3.2, 3.2), 360.0, 3.0, (1.0, 0.95, 0.88), (50, 0, -35))
    light("Fill", "AREA", (3.2, -2.6, 1.6), 60.0, 5.0, (0.74, 0.84, 1.0), (68, 0, 50))
    light("Rim", "AREA", (-1.6, 2.6, 2.4), 220.0, 3.0, (0.62, 0.78, 1.0), (-55, 0, 200))
    ld = bpy.data.lights.new("Wedge", "SPOT")
    ld.energy, ld.color = 220.0, (1.0, 0.66, 0.34)
    ld.spot_size, ld.spot_blend, ld.shadow_soft_size = math.radians(50.0), 1.0, 0.3
    wedge = bpy.data.objects.new("Wedge", ld)
    wedge.location = (0.5, 1.6, 2.0)
    wedge.rotation_euler = (Vector((0.25, 0.5, 0.0)) - wedge.location).to_track_quat(
        "-Z", "Y").to_euler()
    scene.collection.objects.link(wedge)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.23, -2.86, 1.28)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.52)
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
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low], stage=[floor, wall])
    if fcode:
        return fcode
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
    p.add_argument("--short-stave", action="store_true")
    p.add_argument("--one-piece-bottom", action="store_true")
    p.add_argument("--short-handle", action="store_true")
    p.add_argument("--float-hoops", action="store_true")
    p.add_argument("--float-lid", action="store_true")
    p.add_argument("--tight-hole", action="store_true")
    p.add_argument("--wide-dasher", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, mats, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        short_stave=args.short_stave,
        one_piece_bottom=args.one_piece_bottom,
        short_handle=args.short_handle,
        float_hoops=args.float_hoops,
        float_lid=args.float_lid,
        tight_hole=args.tight_hole,
        wide_dasher=args.wide_dasher,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, mats, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("butter churn OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
