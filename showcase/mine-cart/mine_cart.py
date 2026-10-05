"""Game-ready mine cart on a rail segment — a showcase piece, not an example.

Asserts budget conformance of a procedural narrow-gauge mine cart: a riveted
steel tub with a rolled lip, stiffener ribs, a base strap and end grab
handles, on two timber sills and buffer beams, carried by four flanged
wheels on two axles in iron axle boxes, standing on a short straight track:
two 30 lb rails on tie plates, spiked to four sleepers bedded in ballast.
Carried through UVs, four materials (painted steel, iron, timber, ballast),
a high-to-low normal bake, an LOD chain, a compound convex collider, and a
Unity glTF export.

The budget that matters here is the one a cart on rails fails invisibly:
it has to run on the track. A wheel hovering 6 mm over the railhead, an
axle skewed a degree and a half, or a wheel set whose flanges have climbed
into the railheads all fit the bounding box and pass every mesh-hygiene
check. Only the geometry knows. The piece measures, off the finished mesh:

- every wheel's tread resting on its railhead: the tread's lowest point
  over the head within a band of the rail top (seated, not floating, not
  sunk), and the flange reaching below the rail top far enough to guide;
- every flange clearing its railhead's inner face by a gauge band;
- both axles square to the rails and parallel to each other, the wheelbase,
  the track gauge, the rail height and the wheel diameter at real size.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-wheel`` the wheel seat,
``--skew-axle`` the axles' squareness, ``--wide-gauge`` the flange clearance.

No randomness: the ballast's surface jitter is a fixed hash of grid
indices. DECIMATE COLLAPSE triangle counts are not byte-identical across
Blender versions — the LOD gate is a ratio band.

    blender --background --python mine_cart.py --
    blender --background --python mine_cart.py -- --wide-gauge
    blender --background --python mine_cart.py -- --output mine-cart.webp
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
import gallery_asset_quality  # noqa: E402
import gallery_framing  # noqa: E402

# --- track: 600 mm gauge, 30 lb/yd ASCE rail --------------------------------
GAUGE = 0.600                     # between the railheads' inner faces
RAIL_H = 0.079                    # 3 1/8 in
RAIL_HEAD_W = 0.043               # 1 11/16 in
RAIL_HEAD_D = 0.0175
RAIL_Y = GAUGE / 2 + RAIL_HEAD_W / 2   # rail centreline
RAIL_X = 1.10                     # a 2.2 m rail segment
RAIL_Z0 = 0.133                   # rail foot, 3 mm into the tie plate
RAIL_TOP = RAIL_Z0 + RAIL_H
# Half-section (u across, z up from the foot), counter-clockwise. The foot's
# top slopes up to the web, so no spike head bears on a plane the rail shares.
RAIL_SECTION = [
    (-0.0395, 0.0), (0.0395, 0.0), (0.0395, 0.006), (0.0075, 0.016), (0.004, 0.022),
    (0.004, 0.055), (0.008, 0.0605), (0.0215, 0.0615), (0.0215, 0.0755), (0.0185, 0.079),
    (-0.0185, 0.079), (-0.0215, 0.0755), (-0.0215, 0.0615), (-0.008, 0.0605),
    (-0.004, 0.055), (-0.004, 0.022), (-0.0075, 0.016), (-0.0395, 0.006),
]
SLEEPER_XS = (-0.825, -0.275, 0.275, 0.825)
SLEEPER_HX, SLEEPER_HY = 0.070, 0.550
SLEEPER_Z = (0.040, 0.130)
PLATE_HX, PLATE_HY = 0.065, 0.100
PLATE_Z = (0.126, 0.136)
SPIKE_U = 0.055                   # spike centre off the rail centreline
SPIKE_DX = 0.035                  # inner and outer spikes staggered along the rail
BED_BOTTOM = (1.20, 0.75)         # half extents at z = 0
BED_TOP = (1.12, 0.65)
BED_Z = 0.070
BED_NX, BED_NY = 28, 16
BED_JITTER = 0.006

# --- running gear ------------------------------------------------------------
WHEEL_R = 0.180                   # tread radius: a 0.36 m wheel
FLANGE_R = 0.200                  # 20 mm flange
SEAT_BITE = 0.0005                # tread sits 0.5 mm into the railhead
WHEEL_CZ = RAIL_TOP + WHEEL_R - SEAT_BITE
AXLE_XS = (-0.300, 0.300)         # 0.60 m wheelbase
AXLE_R = 0.030
AXLE_HALF = 0.330                 # axle ends buried in the hubs
FLANGE_CLEAR = 0.006              # flange face to railhead inner face
# Wheel half-section (radius, y) for the +y wheel, a closed loop: bore, hub,
# dished web, rim, flange on the gauge side, tread over the railhead.
_YF = GAUGE / 2 - FLANGE_CLEAR    # the flange face that looks at the rail
WHEEL_PROFILE = [
    (0.014, 0.262), (0.062, 0.262), (0.070, 0.270), (0.075, 0.306), (0.138, 0.296),
    (0.150, 0.282), (0.152, 0.279), (0.194, 0.279), (FLANGE_R, 0.2845),
    (0.196, 0.2915), (0.186, _YF), (0.181, _YF + 0.0035), (WHEEL_R, GAUGE / 2),
    (WHEEL_R, RAIL_Y), (WHEEL_R, 0.364), (0.175, 0.369), (0.150, 0.369),
    (0.146, 0.362), (0.080, 0.340), (0.070, 0.345), (0.070, 0.388), (0.062, 0.395),
    (0.014, 0.395),
]
WHEEL_SEG, WHEEL_SEG_HI = 24, 48
FLOAT_WHEEL = 0.006
WIDE_GAUGE = 0.012
SKEW_DEG = 1.5

# --- body ----------------------------------------------------------------------
SILL_HX, SILL_Y, SILL_HW = 0.680, 0.210, 0.050
SILL_Z = (0.445, 0.565)
BEAM_X, BEAM_HX, BEAM_HY = 0.700, 0.050, 0.400
BEAM_Z = (0.430, 0.580)
BOX_HX, BOX_HY = 0.060, 0.045
BOX_Z = (0.330, 0.455)
TUB_Z0, TUB_Z1 = 0.555, 1.040
TUB_BOT = (1.10, 0.70, 0.070)     # length, width, corner radius
TUB_TOP = (1.30, 0.85, 0.090)
TUB_T = 0.010
TUB_CS = 3
LIP_R = 0.014
STRAP_DZ = 0.022
RIB_XS = (-0.40, 0.0, 0.40)
RIB_YS = (-0.20, 0.20)
RIB_HW = 0.0225
RIVET_R = 0.008
# The load: heaped ore, its edge 50 mm below the rim, crowning above it.
ORE_RIM_Z = TUB_Z1 - 0.050
ORE_BASE_Z = TUB_Z1 - 0.130
ORE_PEAK = 0.150
ORE_LUMP = 0.016
ORE_RINGS, ORE_RINGS_HI = 6, 9

# --- budgets -------------------------------------------------------------------
BBOX_TOL = 0.020
OUTER_SIZE = (2.400, 1.500, 1.152)
BASE_TRIS_MIN = 12600
BASE_TRIS_MAX = 14200
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 4
FACE_FLOORS = {0: 700, 1: 4400, 2: 180, 3: 1150}
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 1700
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05

SEAT_GAP_MIN, SEAT_GAP_MAX = -0.0015, 0.0005   # tread low point minus rail top
FLANGE_DEPTH_MIN = 0.012                       # flange below the rail top
CLEAR_MIN, CLEAR_MAX = 0.003, 0.010            # flange face to railhead inner face
SQUARE_TOL_DEG = 0.10
WHEELBASE = 0.600
WHEELBASE_TOL = 0.003
GAUGE_TOL = 0.001
RAIL_H_TOL = 0.001
WHEEL_DIA_TOL = 0.004

STEEL_IDX = 0
IRON_IDX = 1
TIMBER_IDX = 2
BALLAST_IDX = 3

# Face tags (the "Part" face attribute). Every id is >= 1; 0 means untagged.
P_BED, P_SLEEPER, P_PLATE, P_SPIKE = 1, 2, 3, 4
P_TUB, P_RIVET, P_HANDLE, P_FRAME, P_COUPLING = 5, 6, 7, 8, 9
P_ORE = 14
P_WHEEL0 = 10                      # 10..13: axle * 2 + side (0 = -y, 1 = +y)
P_RAIL0 = 20                       # 20 = -y rail, 21 = +y rail
P_AXLE0 = 30                       # 30, 31
SMOOTH_PARTS = {P_RIVET, P_HANDLE, P_COUPLING, P_ORE, 10, 11, 12, 13, 30, 31}

Z = Vector((0.0, 0.0, 1.0))


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


# --- construction helpers -------------------------------------------------------


class Builder:
    """One bmesh plus the face tags every audit reads.

    Each component is built, then ``tag`` stamps its part id (and timber
    tone) on every face still carrying 0, so faces a bevel adds inherit the
    component they belong to.
    """

    def __init__(self):
        self.bm = bmesh.new()
        self.part = self.bm.faces.layers.int.new("Part")
        self.wood = self.bm.faces.layers.float.new("WoodTone")
        self.grime = self.bm.faces.layers.float.new("Grime")
        self.ore = self.bm.faces.layers.float.new("Ore")
        # Grain space for timber: (across, across, along) in metres, each
        # member offset so its pith sits off the piece and no two match.
        self.grain = self.bm.verts.layers.float_vector.new("GrainCo")
        self.members = 0

    def tag(self, part, wood=0.0):
        for f in self.bm.faces:
            if f[self.part] == 0:
                f[self.part] = part
                f[self.wood] = wood

    def quad_strip(self, rings, mat, closed_rings=True, closed_path=False):
        """Faces between consecutive vertex rings (all the same length)."""
        bm = self.bm
        n = len(rings[0])
        last = len(rings) if closed_path else len(rings) - 1
        faces = []
        for i in range(last):
            a, b = rings[i], rings[(i + 1) % len(rings)]
            for k in range(n if closed_rings else n - 1):
                k2 = (k + 1) % n
                f = bm.faces.new((a[k], b[k], b[k2], a[k2]))
                f.material_index = mat
                faces.append(f)
        return faces

    def cap(self, ring, mat):
        f = self.bm.faces.new(ring)
        f.material_index = mat
        return f

    def chamfer(self, faces, offset, mat):
        """One-segment chamfer on the shell's near-right-angle edges only
        (the sundial's helper): inputs sorted, ``material=`` passed."""
        bm = self.bm
        bmesh.ops.recalc_face_normals(bm, faces=faces)
        own = set(faces)
        bm.edges.index_update()
        edges = sorted({e for f in faces for e in f.edges}, key=lambda e: e.index)
        pick = [e for e in edges
                if len(e.link_faces) == 2 and all(lf in own for lf in e.link_faces)
                and math.radians(60.0) <= e.calc_face_angle(0.0) <= math.radians(120.0)]
        if pick:
            bmesh.ops.bevel(bm, geom=pick, offset=offset, segments=1, profile=0.5,
                            affect="EDGES", clamp_overlap=True, material=mat)

    def box(self, c, half, mat, axes=None, cham=0.0, grain=False):
        """Oriented box: centre ``c``, half extents along ``axes`` (default XYZ).

        ``grain`` stamps ``GrainCo`` on the box's verts (chamfer verts too):
        the longest axis is the grain direction, the other two are across it.
        """
        ex, ey, ez = axes or (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
        hx, hy, hz = half
        c = Vector(c)
        before = len(self.bm.verts)
        bottom = [self.bm.verts.new(c + ex * sx * hx + ey * sy * hy - ez * hz)
                  for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        top = [self.bm.verts.new(c + ex * sx * hx + ey * sy * hy + ez * hz)
               for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        faces = self.quad_strip([bottom, top], mat)
        faces.append(self.cap(bottom[::-1], mat))
        faces.append(self.cap(top, mat))
        if cham > 0.0:
            self.chamfer(faces, cham, mat)
        if grain:
            self.stamp_grain(c, (ex, ey, ez), half, before)
        return faces

    def stamp_grain(self, c, axes, half, first_vert):
        """Member-local grain coordinates on every vert added since ``first_vert``."""
        order = sorted(range(3), key=lambda k: -half[k])
        along, a1, a2 = (axes[k] for k in order)
        k = self.members
        self.members += 1
        # The pith 0.12-0.30 m off the member: flat-sawn arches, not targets.
        off = Vector((0.12 + 0.09 * (1 + jitter(k, 3)), 0.05 * jitter(k, 7), 1.7 * k))
        self.bm.verts.ensure_lookup_table()
        for i in range(first_vert, len(self.bm.verts)):
            v = self.bm.verts[i]
            d = v.co - c
            v[self.grain] = Vector((d.dot(a1), d.dot(a2), d.dot(along))) + off

    def lathe(self, profile, centre, axis, u, v, seg, mat, phase=0.0, closed=True):
        """Revolve (radius, height) ``profile`` about ``axis`` through ``centre``.

        ``u``/``v`` span the plane normal to the axis; angle 0 is ``u``.
        """
        rings = []
        for k in range(seg):
            t = phase + 2.0 * math.pi * k / seg
            d = u * math.cos(t) + v * math.sin(t)
            rings.append([self.bm.verts.new(centre + d * r + axis * h) for r, h in profile])
        # rings run around the axis; profile points run along each ring
        return self.quad_strip(rings, mat, closed_rings=closed, closed_path=True), rings

    def sweep(self, path, frames, profile, mat, closed=True):
        """Sweep a 2D profile along ``path``; ``frames`` gives (a, b) per point."""
        rings = [[self.bm.verts.new(p + a * pa + b * pb) for pa, pb in profile]
                 for p, (a, b) in zip(path, frames)]
        faces = self.quad_strip(rings, mat, closed_rings=True, closed_path=closed)
        if not closed:
            faces.append(self.cap(rings[0][::-1], mat))
            faces.append(self.cap(rings[-1], mat))
        return faces


def circle(r, n, phase=0.0):
    return [(r * math.cos(phase + 2 * math.pi * k / n), r * math.sin(phase + 2 * math.pi * k / n))
            for k in range(n)]


def rrect(length, width, rc, cs):
    """Rounded rectangle, counter-clockwise, ``cs + 1`` points per corner."""
    hx, hy = length / 2 - rc, width / 2 - rc
    pts = []
    for qi, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        for k in range(cs + 1):
            a = math.pi / 2 * (qi + k / cs)
            pts.append(Vector((sx * hx + rc * math.cos(a), sy * hy + rc * math.sin(a), 0.0)))
    return pts


def tub_ring(t, inset=0.0, cs=TUB_CS):
    """The tub's outer wall section at fraction ``t`` of its height."""
    length = TUB_BOT[0] + (TUB_TOP[0] - TUB_BOT[0]) * t - 2 * inset
    width = TUB_BOT[1] + (TUB_TOP[1] - TUB_BOT[1]) * t - 2 * inset
    rc = TUB_BOT[2] + (TUB_TOP[2] - TUB_BOT[2]) * t - inset
    z = TUB_Z0 + (TUB_Z1 - TUB_Z0) * t
    return [p + Z * z for p in rrect(length, width, rc, cs)]


def outward(path):
    """Horizontal outward normal at each point of a closed CCW path."""
    out = []
    for i in range(len(path)):
        t = path[(i + 1) % len(path)] - path[i - 1]
        n = Vector((t.y, -t.x, 0.0))
        out.append(n.normalized())
    return out


def side_normal(horizontal, grow):
    """Outward normal of a tub wall that leans out ``grow`` m over its height."""
    return (horizontal * (TUB_Z1 - TUB_Z0) - Z * grow).normalized()


def jitter(i, j):
    h = math.sin(i * 12.9898 + j * 78.233) * 43758.5453
    return (h - math.floor(h)) * 2.0 - 1.0


# --- components -------------------------------------------------------------------


def build_bed(b):
    """Ballast: a jittered top grid over sloped shoulders, flat underneath."""
    bm = b.bm
    tx, ty = BED_TOP
    grid = []
    for j in range(BED_NY + 1):
        row = []
        for i in range(BED_NX + 1):
            x = -tx + 2 * tx * i / BED_NX
            y = -ty + 2 * ty * j / BED_NY
            border = i in (0, BED_NX) or j in (0, BED_NY)
            z = BED_Z if border else BED_Z + BED_JITTER * jitter(i, j)
            row.append(bm.verts.new((x, y, z)))
        grid.append(row)
    for j in range(BED_NY):
        for i in range(BED_NX):
            f = bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
            f.material_index = BALLAST_IDX
    # the top border, counter-clockwise, and a matching ring at the foot
    border = ([grid[0][i] for i in range(BED_NX)] + [grid[j][BED_NX] for j in range(BED_NY)]
              + [grid[BED_NY][i] for i in range(BED_NX, 0, -1)]
              + [grid[j][0] for j in range(BED_NY, 0, -1)])
    bx, by = BED_BOTTOM
    foot = [bm.verts.new((v.co.x * bx / tx, v.co.y * by / ty, 0.0)) for v in border]
    b.quad_strip([foot, border], BALLAST_IDX)
    b.cap(foot[::-1], BALLAST_IDX)
    b.tag(P_BED)


def build_rail(b, side):
    """One rail: the 18-point section swept straight along X."""
    y0 = side * RAIL_Y
    rings = [[b.bm.verts.new((x, y0 + u, RAIL_Z0 + z)) for u, z in RAIL_SECTION]
             for x in (-RAIL_X, -RAIL_X / 2, 0.0, RAIL_X / 2, RAIL_X)]
    b.quad_strip(rings, IRON_IDX)
    b.cap(rings[0][::-1], IRON_IDX)
    b.cap(rings[-1], IRON_IDX)
    b.tag(P_RAIL0 + (0 if side < 0 else 1))


def build_track(b):
    for xs in SLEEPER_XS:
        zc = (SLEEPER_Z[0] + SLEEPER_Z[1]) / 2
        b.box((xs, 0.0, zc), (SLEEPER_HX, SLEEPER_HY, (SLEEPER_Z[1] - SLEEPER_Z[0]) / 2),
              TIMBER_IDX, cham=0.008, grain=True)
        b.tag(P_SLEEPER, wood=0.0)
    for side in (-1, 1):
        for xs in SLEEPER_XS:
            zc = (PLATE_Z[0] + PLATE_Z[1]) / 2
            b.box((xs, side * RAIL_Y, zc), (PLATE_HX, PLATE_HY, (PLATE_Z[1] - PLATE_Z[0]) / 2),
                  IRON_IDX, cham=0.003)
            b.tag(P_PLATE)
            # Dog spikes: a square shank driven into the sleeper and a head
            # that reaches over the rail foot, staggered along the rail.
            for s, dx in ((-1, SPIKE_DX), (1, -SPIKE_DX)):
                cy = side * RAIL_Y + s * SPIKE_U
                b.box((xs + dx, cy, 0.105), (0.007, 0.007, 0.042), IRON_IDX)
                head_y = cy - s * 0.008
                b.box((xs + dx, head_y, 0.1435), (0.010, 0.016, 0.0055), IRON_IDX, cham=0.002)
                b.tag(P_SPIKE)
        build_rail(b, side)
    build_bed(b)


def build_wheel(b, axle, side, seg, float_wheel, wide_gauge, skew):
    ax = AXLE_XS[axle]
    sgn = -1 if side == 0 else 1
    dy = WIDE_GAUGE if wide_gauge else 0.0
    profile = [(r, sgn * (y + dy)) for r, y in WHEEL_PROFILE]
    lift = FLOAT_WHEEL if (float_wheel and axle == 0 and side == 0) else 0.0
    centre = Vector((ax, 0.0, WHEEL_CZ + lift))
    # Angle 0 points straight down (u = -Z), so a vertex, not a face, is the
    # tread's lowest point: no wheel face lies in the railhead's plane.
    b.lathe(profile, centre, Vector((0, 1, 0)), -Z, Vector((1, 0, 0)), seg, IRON_IDX)
    # hub nut on the outer face: a hexagonal prism, half buried
    hub_y = sgn * (0.395 + dy)
    hexa = [(0.030 * math.cos(math.pi / 3 * k + math.pi / 6),
             0.030 * math.sin(math.pi / 3 * k + math.pi / 6)) for k in range(6)]
    ring0 = [b.bm.verts.new((ax + x, hub_y - sgn * 0.006, WHEEL_CZ + lift + z)) for x, z in hexa]
    ring1 = [b.bm.verts.new((ax + x, hub_y + sgn * 0.016, WHEEL_CZ + lift + z)) for x, z in hexa]
    b.quad_strip([ring0, ring1], IRON_IDX)
    b.cap(ring0[::-1], IRON_IDX)
    b.cap(ring1, IRON_IDX)
    if skew:
        rotate_part(b, axle)
    b.tag(P_WHEEL0 + axle * 2 + side)


def rotate_part(b, axle):
    """Rotate every untagged vertex about Z through the axle's centre."""
    ax = AXLE_XS[axle]
    rot = Matrix.Rotation(math.radians(SKEW_DEG), 3, "Z")
    verts = {v for f in b.bm.faces if f[b.part] == 0 for v in f.verts}
    for v in verts:
        p = v.co - Vector((ax, 0.0, 0.0))
        v.co = rot @ p + Vector((ax, 0.0, 0.0))


def build_running_gear(b, hi, float_wheel, wide_gauge, skew_axle):
    seg = WHEEL_SEG_HI if hi else WHEEL_SEG
    aseg = 32 if hi else 16
    for axle in (0, 1):
        skew = skew_axle and axle == 1
        for side in (0, 1):
            build_wheel(b, axle, side, seg, float_wheel, wide_gauge, skew)
        ax = AXLE_XS[axle]
        prof = [(AXLE_R, -AXLE_HALF), (AXLE_R, AXLE_HALF)]
        centre = Vector((ax, 0.0, WHEEL_CZ))
        # Half a step of phase: no axle face looks straight up or down.
        _faces, rings = b.lathe(prof, centre, Vector((0, 1, 0)), -Z, Vector((1, 0, 0)), aseg,
                                IRON_IDX, phase=math.pi / aseg, closed=False)
        b.cap([r[0] for r in rings][::-1], IRON_IDX)
        b.cap([r[1] for r in rings], IRON_IDX)
        if skew:
            rotate_part(b, axle)
        b.tag(P_AXLE0 + axle)


def build_frame(b):
    for sy in (-1, 1):
        zc = (SILL_Z[0] + SILL_Z[1]) / 2
        b.box((0.0, sy * SILL_Y, zc), (SILL_HX, SILL_HW, (SILL_Z[1] - SILL_Z[0]) / 2),
              TIMBER_IDX, cham=0.008, grain=True)
    for sx in (-1, 1):
        zc = (BEAM_Z[0] + BEAM_Z[1]) / 2
        b.box((sx * BEAM_X, 0.0, zc), (BEAM_HX, BEAM_HY, (BEAM_Z[1] - BEAM_Z[0]) / 2),
              TIMBER_IDX, cham=0.010, grain=True)
    b.tag(P_FRAME, wood=1.0)
    for ax in AXLE_XS:
        for sy in (-1, 1):
            zc = (BOX_Z[0] + BOX_Z[1]) / 2
            b.box((ax, sy * SILL_Y, zc), (BOX_HX, BOX_HY, (BOX_Z[1] - BOX_Z[0]) / 2),
                  IRON_IDX, cham=0.008)
    b.tag(P_FRAME)


def build_coupling(b, hi):
    seg, pseg = (24, 10) if hi else (14, 6)
    for sx in (-1, 1):
        b.box((sx * 0.760, 0.0, 0.505), (0.022, 0.034, 0.050), IRON_IDX, cham=0.004)
        c = Vector((sx * 0.776, 0.0, 0.458))
        path = [c + Vector((math.cos(t), 0.0, math.sin(t))) * 0.048
                for t in (2 * math.pi * k / seg for k in range(seg))]
        frames = [((p - c).normalized(), Vector((0, 1, 0))) for p in path]
        b.sweep(path, frames, circle(0.009, pseg), IRON_IDX)
    b.tag(P_COUPLING)


def build_tub(b, hi):
    """Riveted steel tub: walls with a 10 mm skin, rolled lip, base strap, ribs."""
    outer_b, outer_t = tub_ring(0.0), tub_ring(1.0)
    inner_t = tub_ring(1.0, inset=TUB_T)
    inner_b = [p + Z * TUB_T for p in tub_ring(0.0, inset=TUB_T)]
    rings = [[b.bm.verts.new(p) for p in r] for r in (outer_b, outer_t, inner_t, inner_b)]
    walls = b.quad_strip(rings, STEEL_IDX)
    b.cap(rings[0][::-1], STEEL_IDX)
    floor = b.cap(rings[3], STEEL_IDX)
    # The inside carries the load: ore dust and rust, read by the steel shader.
    n = len(rings[0])
    for f in walls[2 * n:] + [floor]:
        f[b.grime] = 1.0

    # Rolled lip: a tube along the rim, rolled to the outside.
    cs = 8 if hi else 5
    path = []
    top = rrect(TUB_TOP[0], TUB_TOP[1], TUB_TOP[2], cs)
    for i, p in enumerate(top):
        q = top[(i + 1) % len(top)]
        steps = 1 if (p - q).length < 0.1 else 6
        for s in range(steps):
            path.append(p.lerp(q, s / steps))
    norms = outward(path)
    path = [p + n * 0.004 + Z * (TUB_Z1 - 0.004) for p, n in zip(path, norms)]
    b.sweep(path, [(n, Z) for n in norms], circle(LIP_R, 10 if hi else 6), STEEL_IDX)

    # Base strap: a flat band round the bottom of the walls.
    ts = STRAP_DZ / (TUB_Z1 - TUB_Z0)
    bot = rrect(TUB_BOT[0] + (TUB_TOP[0] - TUB_BOT[0]) * ts,
                TUB_BOT[1] + (TUB_TOP[1] - TUB_BOT[1]) * ts,
                TUB_BOT[2] + (TUB_TOP[2] - TUB_BOT[2]) * ts, cs)
    spath = []
    for i, p in enumerate(bot):
        q = bot[(i + 1) % len(bot)]
        steps = 1 if (p - q).length < 0.1 else 4
        for s in range(steps):
            spath.append(p.lerp(q, s / steps))
    snorm = outward(spath)
    spath = [p + Z * (TUB_Z0 + STRAP_DZ) for p in spath]
    strap = [(-0.003, -0.018), (0.006, -0.018), (0.007, -0.015), (0.007, 0.015),
             (0.006, 0.018), (-0.003, 0.018)]
    b.sweep(spath, [(n, Z) for n in snorm], strap, STEEL_IDX)

    # Ribs: angle-iron stiffeners following the leaning walls.
    grow_y = (TUB_TOP[1] - TUB_BOT[1]) / 2
    grow_x = (TUB_TOP[0] - TUB_BOT[0]) / 2
    ribs = []
    for sy in (-1, 1):
        n = side_normal(Vector((0, sy, 0)), grow_y)
        for x in RIB_XS:
            p0 = Vector((x, sy * TUB_BOT[1] / 2, TUB_Z0))
            p1 = Vector((x, sy * TUB_TOP[1] / 2, TUB_Z1))
            ribs.append((p0, p1, Vector((1, 0, 0)), n))
    for sx in (-1, 1):
        n = side_normal(Vector((sx, 0, 0)), grow_x)
        for y in RIB_YS:
            p0 = Vector((sx * TUB_BOT[0] / 2, y, TUB_Z0))
            p1 = Vector((sx * TUB_TOP[0] / 2, y, TUB_Z1))
            ribs.append((p0, p1, Vector((0, 1, 0)), n))
    for p0, p1, across, n in ribs:
        a = p0.lerp(p1, 0.075)
        c = p0.lerp(p1, 0.94)
        along = (c - a).normalized()
        mid = (a + c) / 2 + n * 0.0035
        b.box(mid, (RIB_HW, (c - a).length / 2, 0.0065), STEEL_IDX,
              axes=(across, along, n), cham=0.0025)
    b.tag(P_TUB)
    return ribs, spath, snorm


def build_rivets(b, ribs, spath, snorm, hi):
    seg = 10 if hi else 6
    prof = [(RIVET_R, -0.003), (RIVET_R, 0.001), (0.0068, 0.0042), (0.0042, 0.0062)]
    apex_h = 0.0070

    def rivet(c, axis):
        axis = axis.normalized()
        u = axis.orthogonal().normalized()
        v = axis.cross(u)
        rings = []
        for k in range(seg):
            t = 2 * math.pi * k / seg
            d = u * math.cos(t) + v * math.sin(t)
            rings.append([b.bm.verts.new(c + d * r + axis * h) for r, h in prof])
        cols = [[rings[k][i] for k in range(seg)] for i in range(len(prof))]
        b.quad_strip(cols, IRON_IDX)
        apex = b.bm.verts.new(c + axis * apex_h)
        for k in range(seg):
            f = b.bm.faces.new((cols[-1][k], cols[-1][(k + 1) % seg], apex))
            f.material_index = IRON_IDX
        b.cap(cols[0][::-1], IRON_IDX)

    for p0, p1, _across, n in ribs:
        for t in (0.16, 0.40, 0.64, 0.86):
            rivet(p0.lerp(p1, t) + n * 0.0100, n)
    # strap rivets along the straight runs, between the ribs
    for i, (p, n) in enumerate(zip(spath, snorm)):
        if abs(n.x) > 0.99 or abs(n.y) > 0.99:
            if i % 2 == 1:
                rivet(p + n * 0.007, n)
    b.tag(P_RIVET)


def build_handles(b, hi):
    """A round grab bar on each end wall."""
    pseg = 10 if hi else 6
    grow_x = (TUB_TOP[0] - TUB_BOT[0]) / 2
    for sx in (-1, 1):
        n = side_normal(Vector((sx, 0, 0)), grow_x)
        plane = n.cross(Vector((0, 1, 0))).normalized()
        t = 0.80
        base_x = sx * (TUB_BOT[0] + (TUB_TOP[0] - TUB_BOT[0]) * t) / 2
        z = TUB_Z0 + (TUB_Z1 - TUB_Z0) * t
        w = Vector((base_x, 0.0, z))
        pts = []
        for y, out in ((-0.14, -0.012), (-0.14, 0.030), (-0.125, 0.052), (-0.09, 0.060),
                       (0.09, 0.060), (0.125, 0.052), (0.14, 0.030), (0.14, -0.012)):
            pts.append(w + Vector((0, y, 0)) + n * out)
        frames = []
        for i, p in enumerate(pts):
            tan = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
            frames.append((tan.cross(plane).normalized(), plane))
        b.sweep(pts, frames, circle(0.010, pseg), IRON_IDX, closed=False)
    b.tag(P_HANDLE)


def resample(path, step):
    """A closed path with extra points so no segment is longer than ``step``."""
    out = []
    for i, p in enumerate(path):
        q = path[(i + 1) % len(path)]
        n = max(1, math.ceil((q - p).length / step))
        out.extend(p.lerp(q, s / n) for s in range(n))
    return out


def build_ore(b, hi):
    """A heaped load of ore: concentric rings inside the rim, rising to a
    lumpy crown above it, closed underneath where the walls hide it. Its own
    shell (the walls are never touched: a 6 mm gap to the inner skin)."""
    gap = TUB_T + 0.006
    rim_t = (ORE_RIM_Z - TUB_Z0) / (TUB_Z1 - TUB_Z0)
    length = TUB_BOT[0] + (TUB_TOP[0] - TUB_BOT[0]) * rim_t - 2 * gap
    width = TUB_BOT[1] + (TUB_TOP[1] - TUB_BOT[1]) * rim_t - 2 * gap
    rc = TUB_BOT[2] + (TUB_TOP[2] - TUB_BOT[2]) * rim_t - gap
    outline = resample(rrect(length, width, rc, 4), 0.035 if hi else 0.06)
    nr = ORE_RINGS_HI if hi else ORE_RINGS
    rings = []
    for r in range(nr):
        s = 1.0 - r / nr                       # 1 at the rim, toward 0 at the crown
        crown = (1.0 - s * s)                  # a soft dome
        ring = []
        for i, p in enumerate(outline):
            lump = 0.0 if r == 0 else ORE_LUMP * jitter(i * 7 + r, r * 13 + 5)
            z = ORE_RIM_Z + ORE_PEAK * crown + lump
            ring.append(b.bm.verts.new(Vector((p.x * s, p.y * s, z))))
        rings.append(ring)
    # The walls lean out, so lower down the skirt has to draw in with them.
    base_t = (ORE_BASE_Z - TUB_Z0) / (TUB_Z1 - TUB_Z0)
    kx = (TUB_BOT[0] + (TUB_TOP[0] - TUB_BOT[0]) * base_t - 2 * gap) / length
    ky = (TUB_BOT[1] + (TUB_TOP[1] - TUB_BOT[1]) * base_t - 2 * gap) / width
    skirt = [b.bm.verts.new(Vector((v.co.x * kx, v.co.y * ky, ORE_BASE_Z))) for v in rings[0]]
    faces = b.quad_strip([skirt] + rings, BALLAST_IDX)
    b.cap(skirt[::-1], BALLAST_IDX)
    apex = b.bm.verts.new(Vector((0.0, 0.0, ORE_RIM_Z + ORE_PEAK + ORE_LUMP * 0.5)))
    inner = rings[-1]
    for i in range(len(inner)):
        f = b.bm.faces.new((inner[i], inner[(i + 1) % len(inner)], apex))
        f.material_index = BALLAST_IDX
        faces.append(f)
    for f in b.bm.faces:
        if f[b.part] == 0:
            f[b.ore] = 1.0
    b.tag(P_ORE)


def build_mine_cart_mesh(name, hi=False, stray_vert=False, float_wheel=False,
                         wide_gauge=False, skew_axle=False):
    b = Builder()
    try:
        build_track(b)
        build_frame(b)
        build_coupling(b, hi)
        ribs, spath, snorm = build_tub(b, hi)
        build_rivets(b, ribs, spath, snorm, hi)
        build_handles(b, hi)
        build_ore(b, hi)
        build_running_gear(b, hi, float_wheel, wide_gauge, skew_axle)
        bm = b.bm
        if stray_vert:
            bm.verts.new((0.0, 0.0, 0.80))
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        big = [f for f in bm.faces if len(f.verts) > 4]
        bmesh.ops.triangulate(bm, faces=big, quad_method="BEAUTY", ngon_method="EAR_CLIP")
        for f in bm.faces:
            f.smooth = f[b.part] in SMOOTH_PARTS
        for e in bm.edges:
            if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(35.0):
                e.smooth = False
        pack_uvs(bm)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        b.bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def pack_uvs(bm, margin=0.08):
    """One grid cell per face, box-projected on the face's dominant axis."""
    uv = bm.loops.layers.uv.new("UVMap")
    faces = list(bm.faces)
    cols = max(1, math.ceil(math.sqrt(len(faces))))
    rows = max(1, math.ceil(len(faces) / cols))
    cw, ch = 1.0 / cols, 1.0 / rows
    pu, pv = margin * cw * 0.5, margin * ch * 0.5
    for i, face in enumerate(faces):
        ax, ay, az = abs(face.normal.x), abs(face.normal.y), abs(face.normal.z)
        coords = []
        for loop in face.loops:
            co = loop.vert.co
            if az >= ax and az >= ay:
                coords.append((co.x, co.y))
            elif ax >= ay:
                coords.append((co.y, co.z))
            else:
                coords.append((co.x, co.z))
        minx, maxx = min(c[0] for c in coords), max(c[0] for c in coords)
        miny, maxy = min(c[1] for c in coords), max(c[1] for c in coords)
        dx, dy = max(maxx - minx, 1e-8), max(maxy - miny, 1e-8)
        ou, ov = (i % cols) * cw + pu, (i // cols) * ch + pv
        for loop, (x, y) in zip(face.loops, coords):
            loop[uv].uv = (ou + (x - minx) / dx * (cw - 2 * pu),
                           ov + (y - miny) / dy * (ch - 2 * pv))


# --- surface ------------------------------------------------------------------------


def _sock(sockets, identifier):
    return next(sk for sk in sockets if sk.identifier == identifier)


def _mix(nt, blend, a, b, fac):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    node.blend_type = blend
    fsock = _sock(node.inputs, "Factor_Float")
    if isinstance(fac, (int, float)):
        fsock.default_value = fac
    else:
        nt.links.new(fac, fsock)
    for ident, src in (("A_Color", a), ("B_Color", b)):
        if isinstance(src, tuple):
            _sock(node.inputs, ident).default_value = (*src, 1.0)
        else:
            nt.links.new(src, _sock(node.inputs, ident))
    return _sock(node.outputs, "Result_Color")


def _noise(nt, coord, scale, detail, stretch=None):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    src = coord
    if stretch is not None:
        m = nt.nodes.new("ShaderNodeMapping")
        m.inputs["Scale"].default_value = stretch
        nt.links.new(coord, m.inputs["Vector"])
        src = m.outputs["Vector"]
    nt.links.new(src, n.inputs["Vector"])
    return n.outputs["Fac"]


def _range(nt, value, a, b, c=0.0, d=1.0, smooth=True):
    m = nt.nodes.new("ShaderNodeMapRange")
    if smooth:
        m.interpolation_type = "SMOOTHSTEP"
    m.inputs["From Min"].default_value = a
    m.inputs["From Max"].default_value = b
    m.inputs["To Min"].default_value = c
    m.inputs["To Max"].default_value = d
    nt.links.new(value, m.inputs["Value"])
    return m.outputs["Result"]


def _math(nt, op, a, b):
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = op
    for i, s in enumerate((a, b)):
        if isinstance(s, (int, float)):
            m.inputs[i].default_value = s
        else:
            nt.links.new(s, m.inputs[i])
    return m.outputs["Value"]


def steel_material(name):
    """Red-oxide paint gone to rust: run-off streaks, a rusted foot and rim,
    and an inside caked with ore dust (the ``Grime`` face attribute)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    co = nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(co, sep.inputs["Vector"])
    grime = nt.nodes.new("ShaderNodeAttribute")
    grime.attribute_name = "Grime"
    tone = _noise(nt, co, 7.0, 6.0)
    paint = _mix(nt, "MIX", (0.135, 0.030, 0.020), (0.205, 0.050, 0.030), tone)
    # Sun-faded toward the top: the oxide red chalks and lightens.
    fade = _range(nt, sep.outputs["Z"], TUB_Z0 + 0.10, TUB_Z1, 0.0, 0.55)
    fade = _math(nt, "MULTIPLY", fade, _range(nt, _noise(nt, co, 2.5, 3.0), 0.3, 0.7, 0.4, 1.0))
    paint = _mix(nt, "MIX", paint, (0.235, 0.098, 0.072), fade)
    streak = _range(nt, _noise(nt, co, 3.0, 5.0, stretch=(26.0, 26.0, 1.0)), 0.47, 0.64)
    foot = _range(nt, sep.outputs["Z"], TUB_Z0 + 0.26, TUB_Z0 + 0.02)
    rim = _range(nt, sep.outputs["Z"], TUB_Z1 - 0.07, TUB_Z1 - 0.005)
    patches = _range(nt, _noise(nt, co, 11.0, 8.0), 0.46, 0.62)
    edge_rust = _math(nt, "MULTIPLY", _math(nt, "MAXIMUM", foot, rim), patches)
    rust_f = _math(nt, "MAXIMUM", _math(nt, "MULTIPLY", streak, 0.8), edge_rust)
    rust_col = _mix(nt, "MIX", (0.075, 0.032, 0.014), (0.20, 0.085, 0.030),
                    _noise(nt, co, 35.0, 5.0))
    base = _mix(nt, "MIX", paint, rust_col, rust_f)
    # Chipped paint: small flakes down to dark bare steel, thickest where
    # shovels and knocks land, at the rim and the foot.
    flake_n = _noise(nt, co, 30.0, 10.0)
    wear_zone = _math(nt, "ADD", 0.08, _math(nt, "MAXIMUM", foot, rim))
    chip = _math(nt, "MULTIPLY", _range(nt, flake_n, 0.60, 0.64), _math(nt, "MINIMUM", wear_zone, 1.0))
    base = _mix(nt, "MIX", base, (0.040, 0.034, 0.030), chip)
    dust = _mix(nt, "MIX", (0.050, 0.036, 0.026), (0.095, 0.060, 0.035),
                _noise(nt, co, 22.0, 6.0))
    base = _mix(nt, "MIX", base, dust, _math(nt, "MULTIPLY", grime.outputs["Fac"], 0.9))
    nt.links.new(base, bsdf.inputs["Base Color"])
    wear = _math(nt, "MAXIMUM", rust_f, grime.outputs["Fac"])
    rough = _range(nt, wear, 0.0, 1.0, 0.58, 0.9, smooth=False)
    nt.links.new(rough, bsdf.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.002
    # Pitting where it has rusted, a step down at every chip, and a few
    # broad, shallow dents from tipping loads.
    height = _math(nt, "MULTIPLY", wear, _noise(nt, co, 80.0, 4.0))
    height = _math(nt, "SUBTRACT", height, _math(nt, "MULTIPLY", chip, 0.6))
    height = _math(nt, "ADD", height, _math(nt, "MULTIPLY", _noise(nt, co, 3.2, 2.0), 1.4))
    nt.links.new(height, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def iron_material(name):
    """Weathered iron: an even dull rust with fine mottling, darker toward
    the ground; the railheads' running band and the wheels' treads and
    flange tips worn bright where they run."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    co = nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(co, sep.inputs["Vector"])
    x, y, z = sep.outputs["X"], sep.outputs["Y"], sep.outputs["Z"]
    # Rust everywhere, mottled at small scales and low contrast (large
    # high-contrast patches read as camouflage), with a little mill scale
    # showing through in specks.
    mottle = _noise(nt, co, 45.0, 8.0)
    fleck = _noise(nt, co, 140.0, 4.0)
    rust = _mix(nt, "MIX", (0.058, 0.034, 0.021), (0.076, 0.043, 0.025), mottle)
    rust = _mix(nt, "MIX", rust, (0.048, 0.030, 0.020), _range(nt, fleck, 0.45, 0.65))
    scale_spot = _range(nt, _noise(nt, co, 70.0, 6.0), 0.64, 0.70)
    base = _mix(nt, "MIX", rust, (0.040, 0.038, 0.037), _math(nt, "MULTIPLY", scale_spot, 0.6))
    # Darker toward the foot, where damp and dirt sit against the sleepers.
    low = _range(nt, z, SLEEPER_Z[1] + 0.06, SLEEPER_Z[1], 0.0, 0.45)
    base = _mix(nt, "MULTIPLY", base, (0.55, 0.52, 0.50), low)

    # The rails' running band: a continuous polished strip over the head.
    dz = _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", z, RAIL_TOP - 0.002), 0.0)
    rail_band = _range(nt, dz, 0.0042, 0.0022)
    # The wheels' treads and flange tips: radius off the nearer axle,
    # above the rail top (below it is flange face against the head).
    dx = _math(nt, "SUBTRACT", _math(nt, "ABSOLUTE", x, 0.0), AXLE_XS[1])
    rz = _math(nt, "SUBTRACT", z, WHEEL_CZ)
    radius = _math(nt, "POWER", _math(nt, "ADD", _math(nt, "MULTIPLY", dx, dx),
                                      _math(nt, "MULTIPLY", rz, rz)), 0.5)
    rim = _range(nt, radius, WHEEL_R - 0.006, WHEEL_R - 0.002)
    on_wheel = _range(nt, _math(nt, "ABSOLUTE", y, 0.0), GAUGE / 2 - 0.03, GAUGE / 2 - 0.02)
    on_wheel = _math(nt, "MULTIPLY", on_wheel,
                     _range(nt, _math(nt, "ABSOLUTE", y, 0.0), 0.372, 0.366))
    above = _range(nt, z, RAIL_TOP + 0.002, RAIL_TOP + 0.010)
    tread = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", rim, on_wheel), above)
    shine = _math(nt, "MAXIMUM", rail_band, tread)
    base = _mix(nt, "MIX", base, (0.56, 0.56, 0.57), shine)
    nt.links.new(base, bsdf.inputs["Base Color"])
    metal = _range(nt, shine, 0.0, 1.0, 0.25, 1.0, smooth=False)
    nt.links.new(metal, bsdf.inputs["Metallic"])
    rough = _range(nt, shine, 0.0, 1.0, 0.82, 0.22, smooth=False)
    rough = _math(nt, "ADD", rough, _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", fleck, 0.5), 0.08))
    nt.links.new(rough, bsdf.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.001
    nt.links.new(_math(nt, "MULTIPLY", _math(nt, "SUBTRACT", 1.0, shine), fleck), bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def timber_material(name):
    """Creosoted sleepers (tone 0) and weathered oak frame (tone 1).

    Everything reads the ``GrainCo`` vertex attribute: member-local
    (across, across, along) coordinates. Growth rings wrap the along axis
    (so the long faces show flat-sawn arches and the ends show ring arcs),
    fibre streaks are noise squeezed along it, and sparse drying checks run
    with it; a slow noise shifts each member's tone.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tone = nt.nodes.new("ShaderNodeAttribute")
    tone.attribute_name = "WoodTone"
    gattr = nt.nodes.new("ShaderNodeAttribute")
    gattr.attribute_name = "GrainCo"
    g = gattr.outputs["Vector"]

    rings = nt.nodes.new("ShaderNodeTexWave")
    rings.wave_type = "RINGS"
    rings.rings_direction = "Z"
    rings.inputs["Scale"].default_value = 22.0
    rings.inputs["Distortion"].default_value = 3.0
    rings.inputs["Detail"].default_value = 3.0
    rings.inputs["Detail Scale"].default_value = 1.2
    nt.links.new(g, rings.inputs["Vector"])
    late = _range(nt, rings.outputs["Fac"], 0.55, 0.95)

    fibre = _range(nt, _noise(nt, g, 55.0, 6.0, stretch=(1.0, 1.0, 0.03)), 0.38, 0.62)
    check_n = _noise(nt, g, 22.0, 2.0, stretch=(1.0, 1.0, 0.012))
    crack = _range(nt, _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", check_n, 0.5), 0.0),
                   0.010, 0.0)
    crack = _math(nt, "MULTIPLY", crack, _range(nt, _noise(nt, g, 3.0, 2.0), 0.52, 0.62))
    member = _noise(nt, g, 0.35, 1.0)

    creo = _mix(nt, "MIX", (0.046, 0.032, 0.022), (0.017, 0.012, 0.009), late)
    oak = _mix(nt, "MIX", (0.098, 0.072, 0.050), (0.052, 0.037, 0.025), late)
    oak = _mix(nt, "MULTIPLY", oak, (0.78, 0.80, 0.84), _range(nt, member, 0.35, 0.65))
    base = _mix(nt, "MIX", creo, oak, tone.outputs["Fac"])
    base = _mix(nt, "MULTIPLY", base, (0.86, 0.85, 0.84), fibre)
    base = _mix(nt, "MIX", base, (0.008, 0.006, 0.005), _math(nt, "MULTIPLY", crack, 0.85))
    nt.links.new(base, bsdf.inputs["Base Color"])

    # Tar sheen on the creosote; dry, open-grained oak.
    rough = _range(nt, tone.outputs["Fac"], 0.0, 1.0, 0.58, 0.80, smooth=False)
    rough = _math(nt, "ADD", rough, _math(nt, "MULTIPLY", fibre, 0.10))
    nt.links.new(rough, bsdf.inputs["Roughness"])
    height = _math(nt, "ADD", _math(nt, "MULTIPLY", late, 0.35),
                   _math(nt, "MULTIPLY", fibre, 0.30))
    height = _math(nt, "SUBTRACT", height, crack)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.003
    nt.links.new(height, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def ballast_material(name):
    """Crushed stone: two sizes of voronoi chips in mixed greys, each chip
    domed by its distance to the cell edge, dark voids between them."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    co = nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    heights, colours = [], []
    for scale in (34.0, 71.0):
        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.inputs["Scale"].default_value = scale
        vor.inputs["Randomness"].default_value = 1.0
        nt.links.new(co, vor.inputs["Vector"])
        edge = nt.nodes.new("ShaderNodeTexVoronoi")
        edge.feature = "DISTANCE_TO_EDGE"
        edge.inputs["Scale"].default_value = scale
        edge.inputs["Randomness"].default_value = 1.0
        nt.links.new(co, edge.inputs["Vector"])
        heights.append(_range(nt, edge.outputs["Distance"], 0.0, 0.16))
        colours.append(vor.outputs["Color"])
    cell = nt.nodes.new("ShaderNodeValToRGB")
    cell.color_ramp.elements[0].position = 0.0
    cell.color_ramp.elements[0].color = (0.040, 0.038, 0.036, 1.0)
    mid = cell.color_ramp.elements.new(0.5)
    mid.color = (0.095, 0.090, 0.082, 1.0)
    cell.color_ramp.elements[2].position = 1.0
    cell.color_ramp.elements[2].color = (0.17, 0.155, 0.135, 1.0)
    nt.links.new(colours[0], cell.inputs["Fac"])
    small = nt.nodes.new("ShaderNodeValToRGB")
    small.color_ramp.elements[0].color = (0.05, 0.047, 0.043, 1.0)
    small.color_ramp.elements[1].color = (0.15, 0.14, 0.125, 1.0)
    nt.links.new(colours[1], small.inputs["Fac"])
    big_on = _range(nt, heights[0], 0.25, 0.6)
    base = _mix(nt, "MIX", small.outputs["Color"], cell.outputs["Color"], big_on)
    voids = _math(nt, "MAXIMUM", heights[0], heights[1])
    base = _mix(nt, "MULTIPLY", base, (0.15, 0.15, 0.15), _range(nt, voids, 0.18, 0.0))
    rust_dust = _range(nt, _noise(nt, co, 3.0, 4.0), 0.55, 0.75, 0.0, 0.35)
    base = _mix(nt, "MIX", base, (0.11, 0.065, 0.035), rust_dust)
    # The load (``Ore`` face attribute): the same chips, but dark iron ore
    # with hematite-red lumps and the odd glinting crystal face.
    ore = nt.nodes.new("ShaderNodeAttribute")
    ore.attribute_name = "Ore"
    ore_f = ore.outputs["Fac"]
    ore_ramp = nt.nodes.new("ShaderNodeValToRGB")
    ore_ramp.color_ramp.elements[0].color = (0.022, 0.020, 0.019, 1.0)
    ore_ramp.color_ramp.elements[1].position = 0.75
    ore_ramp.color_ramp.elements[1].color = (0.060, 0.050, 0.045, 1.0)
    red = ore_ramp.color_ramp.elements.new(0.9)
    red.color = (0.150, 0.048, 0.026, 1.0)
    lump = nt.nodes.new("ShaderNodeTexVoronoi")
    lump.inputs["Scale"].default_value = 13.0
    lump.inputs["Randomness"].default_value = 1.0
    nt.links.new(co, lump.inputs["Vector"])
    lump_e = nt.nodes.new("ShaderNodeTexVoronoi")
    lump_e.feature = "DISTANCE_TO_EDGE"
    lump_e.inputs["Scale"].default_value = 13.0
    lump_e.inputs["Randomness"].default_value = 1.0
    nt.links.new(co, lump_e.inputs["Vector"])
    lump_h = _range(nt, lump_e.outputs["Distance"], 0.0, 0.22)
    nt.links.new(lump.outputs["Color"], ore_ramp.inputs["Fac"])
    ore_col = _mix(nt, "MULTIPLY", ore_ramp.outputs["Color"], (0.15, 0.15, 0.15),
                   _range(nt, lump_h, 0.20, 0.0))
    ore_col = _mix(nt, "MULTIPLY", ore_col, (0.7, 0.7, 0.7), _range(nt, heights[1], 0.5, 0.0))
    base = _mix(nt, "MIX", base, ore_col, ore_f)
    nt.links.new(base, bsdf.inputs["Base Color"])
    glint = _math(nt, "MULTIPLY", ore_f, _range(nt, _noise(nt, co, 160.0, 2.0), 0.70, 0.74))
    nt.links.new(_math(nt, "MULTIPLY", glint, 0.9), bsdf.inputs["Metallic"])
    nt.links.new(_range(nt, _math(nt, "MAXIMUM", glint, _math(nt, "MULTIPLY", ore_f, 0.25)),
                        0.0, 1.0, 0.93, 0.35, smooth=False), bsdf.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.9
    bump.inputs["Distance"].default_value = 0.02
    stone_h = _math(nt, "ADD", heights[0], _math(nt, "MULTIPLY", heights[1], 0.5))
    ore_h = _math(nt, "ADD", _math(nt, "MULTIPLY", lump_h, 2.2), _math(nt, "MULTIPLY", heights[1], 0.4))
    nt.links.new(_mix(nt, "MIX", stone_h, ore_h, ore_f), bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def cart_materials():
    return (steel_material("CartSteel"), iron_material("CartIron"),
            timber_material("CartTimber"), ballast_material("CartBallast"))


def assign_slots(obj, mats):
    slots = obj.data.materials
    for i, mat in enumerate(mats):
        if i < len(slots):
            slots[i] = mat
        else:
            slots.append(mat)


# --- measurement ---------------------------------------------------------------------


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


def part_points(me):
    """Vertex positions per ``Part`` tag, read back off the finished mesh."""
    tags = [0] * len(me.polygons)
    me.attributes["Part"].data.foreach_get("value", tags)
    verts = {}
    for p, t in zip(me.polygons, tags):
        verts.setdefault(t, set()).update(p.vertices)
    return {t: [me.vertices[i].co.copy() for i in sorted(vs)] for t, vs in verts.items()}


def cart_audit(me):
    """Wheel seat, flange clearance, axle squareness, gauge and sizes."""
    pts = part_points(me)
    out = {"wheels": sum(1 for t in pts if 10 <= t <= 13),
           "rails": sum(1 for t in pts if t in (20, 21)),
           "axles": sum(1 for t in pts if t in (30, 31))}
    if out["wheels"] != 4 or out["rails"] != 2 or out["axles"] != 2:
        return out
    rail = {}
    for side, tag in ((0, 20), (1, 21)):
        rp = pts[tag]
        top = max(p.z for p in rp)
        head = [p for p in rp if p.z > top - RAIL_HEAD_D + 1e-4]
        rail[side] = {"top": top, "bottom": min(p.z for p in rp),
                      "inner": min(abs(p.y) for p in head),
                      "outer": max(abs(p.y) for p in head)}
    out["gauge"] = rail[0]["inner"] + rail[1]["inner"]
    out["rail_h"] = max(r["top"] - r["bottom"] for r in rail.values())
    gaps, clears, depths, dias, centres = [], [], [], [], {}
    for tag in range(10, 14):
        wp = pts[tag]
        side = (tag - 10) % 2
        r = rail[side]
        # A lathe's vertices are evenly spread round its axis: their mean
        # is the axle centre in x and z.
        cx = sum(p.x for p in wp) / len(wp)
        cz = sum(p.z for p in wp) / len(wp)
        cy = sum(p.y for p in wp) / len(wp)
        centres[tag] = Vector((cx, cy, cz))
        radial = [(math.hypot(p.x - cx, p.z - cz), p) for p in wp]
        # The tread is the wheel's running surface: no farther out than the
        # tread radius (so not the flange), and over this railhead.
        tread = [(rr, p) for rr, p in radial
                 if rr <= WHEEL_R + 0.0005 and r["inner"] - 1e-6 <= abs(p.y) <= r["outer"]]
        gaps.append(min(p.z for _rr, p in tread) - r["top"] if tread else 1.0)
        dias.append(2.0 * max(rr for rr, _p in tread) if tread else 0.0)
        flange = [p for rr, p in radial if rr > WHEEL_R + 0.003]
        clears.append(r["inner"] - max(abs(p.y) for p in flange))
        depths.append(r["top"] - min(p.z for p in flange))
    out["seat_gap"] = (min(gaps), max(gaps))
    out["clearance"] = (min(clears), max(clears))
    out["flange_depth"] = min(depths)
    out["wheel_dia"] = (min(dias), max(dias))
    square, mids = [], []
    for axle in (0, 1):
        a, b = centres[10 + axle * 2], centres[11 + axle * 2]
        d = b - a
        # atan2, not acos(d.y / |d|): acos near 1 turns float32 noise into 0.01 deg.
        square.append(math.degrees(math.atan2(math.hypot(d.x, d.z), abs(d.y))))
        mids.append((a + b) / 2)
    out["square_deg"] = max(square)
    out["wheelbase"] = abs(mids[1].x - mids[0].x)
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
    """Compound collider: a hull per sleeper, rail, wheel and axle box run,
    one for the ballast, one for the tub, one for the frame. Plates, spikes,
    rivets and the couplings are left out: millimetres of relief on surfaces
    a hull already covers."""
    me = obj.data
    pts = part_points(me)
    groups = []
    # The ballast's hull is its shoulders: the jittered top only adds faces.
    groups.append([p for p in pts.get(P_BED, []) if p.z <= BED_Z + 1e-6])
    # The tub's hull takes the ore's crown with it: one hull for the load.
    groups.append(pts.get(P_TUB, []) + pts.get(P_ORE, []))
    for tag in (P_FRAME, 20, 21, 10, 11, 12, 13):
        if tag in pts:
            groups.append(pts[tag])
    sleeper_pts = pts.get(P_SLEEPER, [])
    for xs in SLEEPER_XS:
        groups.append([p for p in sleeper_pts if abs(p.x - xs) < 0.2])
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for g in groups:
            if len(g) < 4:
                continue
            tmp = bmesh.new()
            try:
                vs = [tmp.verts.new(p) for p in g]
                bmesh.ops.convex_hull(tmp, input=vs)
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
    img = bpy.data.images.new("MineCartNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = IRON_IDX
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


def check(skip_decimate, lift_z=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nothing = (None,) * 5
    low = build_mine_cart_mesh("MineCartLow", **flags)
    hi_flags = {k: v for k, v in flags.items() if k != "stray_vert"}
    high = build_mine_cart_mesh("MineCartHigh", hi=True, **hi_flags)
    mats = cart_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()
    if len(low.data.polygons) < 6 or not low.data.uv_layers:
        return (fail("mine cart mesh did not build, or has no UV layer", 3),) + nothing

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat, distinct = len(slots), len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]

    img, tex = setup_bake_image(low, mats[IRON_IDX], BAKE_RES)
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "MineCartLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "MineCartLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = hull_collider(low, "MineCartCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_mine_cart_{os.getpid()}.glb")
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
    ca = cart_audit(low.data)

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
    print(f"measured parts wheels={ca['wheels']} rails={ca['rails']} axles={ca['axles']}")
    if "seat_gap" in ca:
        print(f"measured seat_gap=({ca['seat_gap'][0]:.5f},{ca['seat_gap'][1]:.5f}) "
              f"flange_depth={ca['flange_depth']:.5f} "
              f"clearance=({ca['clearance'][0]:.5f},{ca['clearance'][1]:.5f})")
        print(f"measured square={ca['square_deg']:.4f}deg wheelbase={ca['wheelbase']:.5f} "
              f"gauge={ca['gauge']:.5f} rail_h={ca['rail_h']:.5f} "
              f"wheel_dia=({ca['wheel_dia'][0]:.5f},{ca['wheel_dia'][1]:.5f})")

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
    if ca["wheels"] != 4 or ca["rails"] != 2 or ca["axles"] != 2:
        return (fail(f"parts: wheels {ca['wheels']}/4 rails {ca['rails']}/2 "
                     f"axles {ca['axles']}/2", 3),) + nothing
    g0, g1 = ca["seat_gap"]
    if g0 < SEAT_GAP_MIN or g1 > SEAT_GAP_MAX:
        return (fail(f"wheel seat: tread low point {g0 * 1000:.2f}..{g1 * 1000:.2f} mm off the "
                     f"rail top, band [{SEAT_GAP_MIN * 1000:.1f}, {SEAT_GAP_MAX * 1000:.1f}] mm "
                     "(--float-wheel is the designed fail)", 18),) + nothing
    if ca["flange_depth"] < FLANGE_DEPTH_MIN:
        return (fail(f"flange reaches {ca['flange_depth'] * 1000:.1f} mm below the rail top "
                     f"(< {FLANGE_DEPTH_MIN * 1000:.0f} mm): it cannot guide", 18),) + nothing
    if ca["square_deg"] > SQUARE_TOL_DEG:
        return (fail(f"axle {ca['square_deg']:.3f} deg off square to the rails "
                     f"(> {SQUARE_TOL_DEG}) (--skew-axle is the designed fail)", 19),) + nothing
    d0, d1 = ca["wheel_dia"]
    if (abs(ca["wheelbase"] - WHEELBASE) > WHEELBASE_TOL
            or abs(ca["gauge"] - GAUGE) > GAUGE_TOL
            or abs(ca["rail_h"] - RAIL_H) > RAIL_H_TOL
            or abs(d0 - 2 * WHEEL_R) > WHEEL_DIA_TOL or abs(d1 - 2 * WHEEL_R) > WHEEL_DIA_TOL):
        return (fail(f"real-world size: wheelbase {ca['wheelbase']:.4f} (want {WHEELBASE}), "
                     f"gauge {ca['gauge']:.4f} (want {GAUGE}), rail {ca['rail_h']:.4f} "
                     f"(want {RAIL_H}), wheel {d0:.4f}..{d1:.4f} (want {2 * WHEEL_R})", 19),) + nothing
    c0, c1 = ca["clearance"]
    if c0 < CLEAR_MIN or c1 > CLEAR_MAX:
        return (fail(f"flange clearance {c0 * 1000:.2f}..{c1 * 1000:.2f} mm to the railhead, "
                     f"band [{CLEAR_MIN * 1000:.0f}, {CLEAR_MAX * 1000:.0f}] mm "
                     "(--wide-gauge is the designed fail)", 20),) + nothing
    return 0, low, high, mats, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])


def render_still(low, mats, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(mats[IRON_IDX], tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True
    # Level on the floor: turned about Z only, so the cart's side, its wheels
    # on the railheads and one end with its coupling ring all face the camera.
    low.rotation_euler.z = math.radians(RENDER_YAW)

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

    light("Key", "AREA", (-3.6, -3.9, 4.6), 650.0, 1.4, (1.0, 0.95, 0.88), (42, 0, -42))
    light("Fill", "AREA", (4.6, -3.6, 2.0), 130.0, 6.0, (0.74, 0.84, 1.0), (70, 0, 50))
    light("Rim", "AREA", (-2.4, 3.8, 3.2), 420.0, 3.5, (0.62, 0.78, 1.0), (-55, 0, 200))
    ld = bpy.data.lights.new("Wedge", "SPOT")
    ld.energy, ld.color = 520.0, (1.0, 0.66, 0.34)
    ld.spot_size, ld.spot_blend, ld.shadow_soft_size = math.radians(55.0), 1.0, 0.4
    wedge = bpy.data.objects.new("Wedge", ld)
    wedge.location = (0.9, 2.9, 2.6)
    wedge.rotation_euler = (Vector((0.3, 0.9, 0.2)) - wedge.location).to_track_quat(
        "-Z", "Y").to_euler()
    scene.collection.objects.link(wedge)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = RENDER_LENS
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = RENDER_CAM
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = RENDER_AIM
    scene.collection.objects.link(aim)
    con = cam.constraints.new("TRACK_TO")
    con.target = aim
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    scene.camera = cam

    scene.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        scene.cycles.samples = 48
        scene.cycles.device = "CPU"
    else:
        scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "WEBP" if path.lower().endswith(".webp") else "PNG"
    if path.lower().endswith(".webp"):
        scene.render.image_settings.quality = 90
    scene.render.filepath = path
    # Standard, not Filmic/AgX: the stage stays near-black and the railheads'
    # polish reads as a highlight, not a grey wash.
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low], stage=[floor, wall])
    if fcode:
        return fcode
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall]):
        return 21
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return fail("render produced no file", 14)
    return 0


RENDER_YAW = -28.0
RENDER_LENS = 50.0
RENDER_CAM = (0.0, -4.9, 2.4)
RENDER_AIM = (0.0, 0.0, 0.37)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true",
                   help="falsification: LOD1/LOD2 keep every triangle")
    p.add_argument("--stray-vert", action="store_true",
                   help="falsification: one loose vertex inside the tub")
    p.add_argument("--lift-z", action="store_true",
                   help="falsification: lift the whole mesh 50 mm")
    p.add_argument("--float-wheel", action="store_true",
                   help="falsification: one wheel hovers 6 mm over its railhead")
    p.add_argument("--skew-axle", action="store_true",
                   help="falsification: one axle and its wheels yawed 1.5 degrees")
    p.add_argument("--wide-gauge", action="store_true",
                   help="falsification: every wheel 12 mm outboard, flanges into the railheads")
    args = p.parse_args(argv)

    code, low, _high, mats, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_wheel=args.float_wheel,
        skew_axle=args.skew_axle,
        wide_gauge=args.wide_gauge,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, mats, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("mine cart OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
