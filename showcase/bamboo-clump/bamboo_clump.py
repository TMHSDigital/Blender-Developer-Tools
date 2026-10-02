"""Game-ready bamboo clump on a leaf-litter mound — a showcase piece, not an example.

Asserts budget conformance of a procedural bamboo clump after composing
shipped pipeline pieces: bmesh construction, UVs, five materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

A low mound of dark earth holds one clump of seven bamboo culms, 3.0 to
4.5 m tall and 3.5 to 6 cm across at the base, each rooted in a collar of
heaped soil. A culm rises straight out of a flared foot, then leans away
from the clump and arches, tapering to a fine tip. It is ringed with nodes
at an uneven pitch: close together near the foot, long through the middle,
close again toward the tip, each a raised ring with a pale bloom of wax
and a dark scar line either side of it. From the upper nodes, one to a
node and turning round the culm, leafy branches spring up and out: a
slender branch that arches and droops, carrying five slim, pointed,
drooping leaves along its last third. Three young shoots in overlapping
sheaths push out of the earth beside the culms, and thirty-six dry leaves
and five fallen culm sheaths lie in the litter.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates one named budget:
``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh hygiene,
``--lift-z`` and ``--float-culm`` grounding, ``--sunk-nodes`` every node
ring proud of its culm, ``--stray-branches`` every branch springing from
a node, ``--swell-culm`` a culm that only ever tapers, ``--bunch-nodes``
the pitch of the nodes, ``--crowd-culms`` culms that stand clear of each
other, ``--float-litter`` the litter resting in the soil, ``--lift-leaves``
every leaf seated in its branch.

Seeded, not random: ``random.Random(SEED)`` draws the litter before
anything is built, and everything on the culms comes from a closed-form
hash of the node's indices, so flags never shift the stream. DECIMATE
COLLAPSE triangle counts are not byte-identical across Blender versions —
the LOD gate is a ratio band, not an exact count.

    blender --background --python bamboo_clump.py --
    blender --background --python bamboo_clump.py -- --skip-decimate
    blender --background --python bamboo_clump.py -- --output bamboo.png
"""
import argparse
import math
import os
import random
import sys
import tempfile
import traceback

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

# Showcase lives at repo-root/showcase/, not under examples/. The framing
# helper is the repo's only shared import and lives next to the examples;
# resolve the repo root so we do not move gallery_framing.py.
_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402
import gallery_asset_quality  # noqa: E402

SEED = 6203
TAU = 2.0 * math.pi
UP = Vector((0.0, 0.0, 1.0))

# --- Ground ------------------------------------------------------------------
DISC_A = (1.10, 0.98)     # soil disc semi-axes before its wobble, m
DISC_N = {"low": 36, "high": 64}
MOUND_Z = 0.085           # the heap at the clump's centre
COLLAR_Z = 0.022          # soil heaped round every culm's foot
COLLAR_R = 0.060

# --- Culms -------------------------------------------------------------------
# (x, y, length along the axis from the buried foot to the tip, radius at the
#  foot before the flare, lean at the tip deg, bearing of the lean deg,
#  sway deg, sway phase, tone)
CULMS = (
    (0.000, 0.020, 4.60, 0.0300, 12.0, 100.0, 18.0, 0.3, 0.55),
    (0.115, -0.070, 4.20, 0.0285, 34.0, -25.0, 22.0, 1.2, 0.30),
    (-0.120, -0.080, 4.00, 0.0265, 38.0, 212.0, 20.0, 2.0, 0.75),
    (-0.100, 0.140, 3.60, 0.0235, 36.0, 128.0, 24.0, 0.9, 0.45),
    (0.130, 0.130, 3.80, 0.0215, 36.0, 58.0, 18.0, 2.6, 0.20),
    (0.020, -0.170, 3.20, 0.0190, 42.0, 268.0, 22.0, 1.7, 0.85),
    (-0.200, 0.000, 3.00, 0.0175, 44.0, 178.0, 20.0, 0.4, 0.65),
)
DS = 0.01                 # step of the dense axis polyline
CULM_BED = 0.045          # the foot this far under the soil at its centre
CULM_SIDES = {"low": 10, "high": 16}
TAPER = 0.45              # r(tip) = r0 * (1 - TAPER)
FLARE = 0.30              # the foot's flare, and how far up it runs
FLARE_LEN = 0.18
TIP_LEN = 0.07            # the closed cone at the top
NODE_FIRST = 0.14         # first node, along the axis from the buried foot
NODE_END = 0.22           # no node nearer the tip than this
NODE_BASE_L = 0.14        # internode length: base + mid * sin(pi u) ** 0.9
NODE_MID_L = 0.17
RING_H = 0.006            # half height of a node ring
RING_PROUD = 0.0035       # its crest this far outside the culm
RING_BITE = 0.003         # its inner wall this far inside it
RING_SIDES = 10

# --- Branches and leaves -------------------------------------------------------
BR_FROM_U = 0.30          # branches from the nodes above this fraction of the length
BR_TIP_CLEAR = 0.20       # and none this near the tip
BR_R_MIN = 0.0105         # on a culm at least this thick
BR_R0 = 0.0055
BR_BITE = 0.007           # a branch's first ring centre this far inside the culm
BR_SIDES = 6
BR_L0 = 0.42
BR_L1 = 0.40
LEAF_AT = ((0.40, 1.0), (0.48, -1.0), (0.58, 1.0), (0.66, -1.0), (0.76, 1.0), (0.84, -1.0),
           (0.92, 1.0), (1.00, 0.0), (0.96, -0.5))
LEAF_U = (0.0, 0.25, 0.50, 0.75, 0.92)
LEAF_TIP_INSET = 0.002

# --- Shoots and litter ----------------------------------------------------------
# (x, y, height, radius at the foot)
SHOOTS = ((0.250, 0.030, 0.62, 0.021), (-0.030, 0.290, 0.40, 0.018), (0.100, -0.300, 0.27, 0.016))
SHOOT_BED = 0.030
SHOOT_SHEATHS = 7
N_LITTER = 36
N_SHEATH = 5
LITTER_BELLY = 0.0025     # a litter blade's belly this far under the soil, before its stagger
LITTER_HT = 0.0030        # half thickness: the flanks lean 11-15 degrees, steeper than any slope of the mound
SHEATH_HT = 0.0110        # a sheath is wider, so thicker, or its flank lies in the soil's own plane
LITTER_L0, LITTER_L1 = 0.12, 0.10
SHEATH_L0, SHEATH_L1 = 0.34, 0.14

# --- Falsifier magnitudes ------------------------------------------------------------
SUNK_PROUD = 0.0006       # --sunk-nodes: every ring's crest this far outside the culm
STRAY_SHIFT = 0.09        # --stray-branches: culm 0's lowest branch this far up from its node
STRAY_IDX = 0
SWELL = 0.35              # --swell-culm: one culm swells this much about 45% up
SWELL_IDX = 2
BUNCH_IDX = 0             # --bunch-nodes: culm 0's seventh node...
BUNCH_NODE = 6
BUNCH_GAP = 0.07          # ...slid up until it is this far under the next
CROWD_IDX = 0             # --crowd-culms: this culm stood against its neighbour
CROWD_SHIFT = (0.070, -0.060)
FLOAT_CULM_IDX = 5        # --float-culm: this culm raised off the soil
FLOAT_CULM = 0.070
FLOAT_LITTER = 0.025
LIFT_LEAVES = 0.008
LIFT_Z = 0.05

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from the vertices.
OUTER_SIZE = (3.4296, 3.5679, 4.6432)
BASE_TRIS_MIN = 51500
BASE_TRIS_MAX = 53500
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 5
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 80
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
# soil, culm, leaf, shoot sheath, dry leaf
FACE_FLOORS = (2680, 13040, 11670, 450, 740)
SOIL_IDX = 0
CULM_IDX = 1
LEAF_IDX = 2
SHOOT_IDX = 3
DRY_IDX = 4
MAT_LABELS = ("soil", "culm", "leaf", "shoot sheath", "dry leaf")

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05

BED_MIN = 0.020           # every culm's and shoot's lowest vertex under the soil
BED_MAX = 0.075
PROUD_BAND = (0.0025, 0.0048)
BITE_BAND = (0.0020, 0.0060)
BRANCH_BITE_BAND = (0.004, 0.010)
NODE_SLACK = 0.010
LEAF_SEAT_BAND = (0.0010, 0.0052)
CULM_H_BAND = (2.6, 4.7)
CULM_H_SPREAD_MIN = 1.0
CULM_D_BAND = (0.030, 0.062)
TAPER_EPS = 0.0004
TAPER_RATIO_BAND = (0.54, 0.66)
GAP_BAND = (0.12, 0.38)
PITCH_BAND = (0.23, 0.28)
LENGTHEN_MIN = 0.06
NODES_MIN = 10
CLUMP_GAP_MIN = 0.020
REST_BAND = (0.0005, 0.006)
HERO_YAW_DEG = 0.0
WALL_Y = 4.0
CAM_DIST = 13.8
CAM_UP = 1.0
AIM_DZ = 0.0

# part labels (a face attribute): they name a shell, they never measure it
P_SOIL, P_CULM, P_NODE, P_BRANCH, P_LEAF, P_SHOOT, P_LITTER, P_SHEATH = 1, 2, 3, 4, 5, 6, 7, 8
N_PARTS = 8

FLAG_NAMES = ("sunk_nodes", "stray_branches", "swell_culm", "bunch_nodes", "crowd_culms",
              "float_culm", "float_litter", "lift_leaves")

BUILT = {}


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def triangle_count(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def evaluated_triangle_count(obj):
    # Duplicated from snippets/lod_chain.py / decimate_to_budget.py (not a package).
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()
    try:
        eval_mesh.calc_loop_triangles()
        return len(eval_mesh.loop_triangles)
    finally:
        eval_obj.to_mesh_clear()


def smoothstep(x, lo, hi):
    t = min(max((x - lo) / (hi - lo), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def perp_basis(d):
    ref = UP if abs(d.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    e1 = d.cross(ref).normalized()
    return e1, d.cross(e1).normalized()


def hash01(a, b, c):
    """A closed-form draw in [0, 1) from three indices: per-leaflet variety
    that no flag can shift."""
    x = math.sin(a * 12.9898 + b * 78.233 + c * 37.719 + SEED * 0.0137) * 43758.5453
    return x - math.floor(x)


def squircle(i, k, n):
    """A square grid mapped onto the unit disc (its border on the circle)."""
    uu = -1.0 + 2.0 * i / n
    vv = -1.0 + 2.0 * k / n
    return uu * math.sqrt(1.0 - vv * vv / 2.0), vv * math.sqrt(1.0 - uu * uu / 2.0)


def hor(v):
    return Vector((v.x, v.y, 0.0))


def heading(deg):
    a = math.radians(deg)
    return Vector((math.cos(a), math.sin(a), 0.0))


def rotate_about(v, axis, ang):
    return Matrix.Rotation(ang, 3, axis) @ v



def disc_wobble(th):
    return 1.0 + 0.040 * math.sin(3.0 * th + 0.7) + 0.028 * math.sin(5.0 * th + 2.1) \
        + 0.015 * math.sin(8.0 * th + 1.3)


def disc_radius(x, y):
    """Normalised disc radius: 1 on the soil's rim."""
    X, Y = x / DISC_A[0], y / DISC_A[1]
    return math.hypot(X, Y) / disc_wobble(math.atan2(Y, X))



# --------------------------------------------------------------------------
# Construction helpers (shared)
# --------------------------------------------------------------------------

def new_face(bm, verts, mat, L, tone, zone, part):
    out = []
    for v in verts:
        if not out or out[-1] is not v:
            out.append(v)
    if len(out) > 1 and out[0] is out[-1]:
        out.pop()
    f = bm.faces.new(out)
    f.material_index = mat
    f[L["tone"]] = tone
    f[L["zone"]] = zone
    f[L["part"]] = part
    return f


def grid_faces(bm, grid, n, mat, L, tone, part):
    for i in range(n):
        for k in range(n):
            a, b, c, d = grid[i][k], grid[i + 1][k], grid[i + 1][k + 1], grid[i][k + 1]
            if (a.co - c.co).length <= (b.co - d.co).length:
                tris = ((a, b, c), (a, c, d))
            else:
                tris = ((a, b, d), (b, c, d))
            for tri in tris:
                new_face(bm, tri, mat, L, tone, 0.0, part)


def grid_rim(grid, n):
    return ([grid[i][0] for i in range(n)] + [grid[n][k] for k in range(n)]
            + [grid[i][n] for i in range(n, 0, -1)] + [grid[0][k] for k in range(n, 0, -1)])


def add_soil(bm, L, V, n):
    grid = []
    for i in range(n + 1):
        col = []
        for k in range(n + 1):
            X, Y = squircle(i, k, n)
            wob = disc_wobble(math.atan2(Y, X))
            x = DISC_A[0] * X * wob
            y = DISC_A[1] * Y * wob
            on_rim = i in (0, n) or k in (0, n)
            z = 0.0 if on_rim else soil_height(x, y)
            v = bm.verts.new((x, y, z))
            v[V["skirt"]] = smoothstep(disc_radius(x, y), 0.86, 0.93)
            col.append(v)
        grid.append(col)
    grid_faces(bm, grid, n, SOIL_IDX, L, 0.5, P_SOIL)
    new_face(bm, list(reversed(grid_rim(grid, n))), SOIL_IDX, L, 0.5, 0.0, P_SOIL)


def soil_hit(tree, x, y):
    loc, nrm, _i, _d = tree.ray_cast(Vector((x, y, 5.0)), Vector((0.0, 0.0, -1.0)), 20.0)
    if loc is None:
        return Vector((x, y, 0.0)), Vector((0.0, 0.0, 1.0))
    if nrm.z < 0.0:
        nrm = -nrm
    return loc, nrm


def triangulate_ngons(bm):
    faces = [f for f in bm.faces if len(f.verts) > 4]
    if faces:
        bmesh.ops.triangulate(bm, faces=faces)


def pack_uvs(bm, margin=0.08):
    uv = bm.loops.layers.uv.new("UVMap")
    faces = list(bm.faces)
    n = len(faces)
    cols = max(1, math.ceil(math.sqrt(n)))
    rows = max(1, math.ceil(n / cols))
    cell_w = 1.0 / cols
    cell_h = 1.0 / rows
    pad_u = margin * cell_w * 0.5
    pad_v = margin * cell_h * 0.5
    usable_w = cell_w - 2.0 * pad_u
    usable_h = cell_h - 2.0 * pad_v
    for i, face in enumerate(faces):
        col = i % cols
        row = i // cols
        nrm = face.normal
        ax, ay, az = abs(nrm.x), abs(nrm.y), abs(nrm.z)
        coords = []
        for loop in face.loops:
            co = loop.vert.co
            if az >= ax and az >= ay:
                coords.append((co.x, co.y))
            elif ax >= ay:
                coords.append((co.y, co.z))
            else:
                coords.append((co.x, co.z))
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        dx = max(maxx - minx, 1e-8)
        dy = max(maxy - miny, 1e-8)
        origin_u = col * cell_w + pad_u
        origin_v = row * cell_h + pad_v
        for loop, (x, y) in zip(face.loops, coords):
            loop[uv].uv = (
                origin_u + (x - minx) / dx * usable_w,
                origin_v + (y - miny) / dy * usable_h,
            )



# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------

def enabled_socket(sockets, name):
    """The one enabled socket called ``name`` (Mix / Map Range carry one per
    data type under one name; identifiers changed in 5.2)."""
    for sock in sockets:
        if sock.name == name and sock.enabled:
            return sock
    return sockets[name]


def surface(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value = 0.0
    coord = nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    return mat, nt, bsdf, coord


def mapping(nt, vec, scale=(1.0, 1.0, 1.0), rot=(0.0, 0.0, 0.0)):
    node = nt.nodes.new("ShaderNodeMapping")
    node.inputs["Scale"].default_value = scale
    node.inputs["Rotation"].default_value = rot
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Vector"]


def noise(nt, vec, scale, detail, roughness):
    node = nt.nodes.new("ShaderNodeTexNoise")
    node.inputs["Scale"].default_value = scale
    node.inputs["Detail"].default_value = detail
    node.inputs["Roughness"].default_value = roughness
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Fac"]


def wave(nt, vec, scale, distortion, detail):
    node = nt.nodes.new("ShaderNodeTexWave")
    node.wave_type = "BANDS"
    node.bands_direction = "X"
    node.inputs["Scale"].default_value = scale
    node.inputs["Distortion"].default_value = distortion
    node.inputs["Detail"].default_value = detail
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Fac"]


def voronoi_color(nt, vec, scale):
    node = nt.nodes.new("ShaderNodeTexVoronoi")
    node.inputs["Scale"].default_value = scale
    nt.links.new(vec, node.inputs["Vector"])
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(node.outputs["Color"], sep.inputs["Color"])
    return sep.outputs[0], sep.outputs[1], node.outputs["Distance"]


def ramp(nt, fac, stops):
    node = nt.nodes.new("ShaderNodeValToRGB")
    els = node.color_ramp.elements
    els[0].position = stops[0][0]
    els[0].color = (*stops[0][1], 1.0)
    els[1].position = stops[-1][0]
    els[1].color = (*stops[-1][1], 1.0)
    for pos, rgb in stops[1:-1]:
        els.new(pos).color = (*rgb, 1.0)
    nt.links.new(fac, node.inputs["Fac"])
    return node.outputs["Color"]


def remap(nt, value, from_lo, from_hi, to_lo, to_hi):
    node = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(value, enabled_socket(node.inputs, "Value"))
    enabled_socket(node.inputs, "From Min").default_value = from_lo
    enabled_socket(node.inputs, "From Max").default_value = from_hi
    enabled_socket(node.inputs, "To Min").default_value = to_lo
    enabled_socket(node.inputs, "To Max").default_value = to_hi
    return enabled_socket(node.outputs, "Result")


def math_node(nt, op, a, b):
    node = nt.nodes.new("ShaderNodeMath")
    node.operation = op
    for i, value in enumerate((a, b)):
        if isinstance(value, (int, float)):
            node.inputs[i].default_value = value
        else:
            nt.links.new(value, node.inputs[i])
    return node.outputs[0]


def mix_color(nt, a, b, fac):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    if isinstance(fac, (int, float)):
        enabled_socket(node.inputs, "Factor").default_value = fac
    else:
        nt.links.new(fac, enabled_socket(node.inputs, "Factor"))
    for nm, value in (("A", a), ("B", b)):
        sock = enabled_socket(node.inputs, nm)
        if isinstance(value, tuple):
            sock.default_value = (*value, 1.0)
        else:
            nt.links.new(value, sock)
    return enabled_socket(node.outputs, "Result")


def attr(nt, name):
    node = nt.nodes.new("ShaderNodeAttribute")
    node.attribute_type = "GEOMETRY"
    node.attribute_name = name
    return node.outputs["Fac"]


def height(nt, coord):
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord, sep.inputs["Vector"])
    return sep.outputs["Z"]


def bump(nt, bsdf, h, strength, distance):
    node = nt.nodes.new("ShaderNodeBump")
    node.inputs["Strength"].default_value = strength
    node.inputs["Distance"].default_value = distance
    nt.links.new(h, node.inputs["Height"])
    nt.links.new(node.outputs["Normal"], bsdf.inputs["Normal"])


def band(nt, value, lo, hi):
    """1 across [lo, hi] of ``value`` with soft shoulders, 0 elsewhere."""
    return math_node(nt, "MULTIPLY", remap(nt, value, lo - 0.45, lo - 0.05, 0.0, 1.0),
                     remap(nt, value, hi + 0.05, hi + 0.45, 1.0, 0.0))



# --------------------------------------------------------------------------
# The ground as a function of plan position
# --------------------------------------------------------------------------

def soil_height(x, y):
    rr = disc_radius(x, y)
    z = MOUND_Z * (1.0 - smoothstep(rr, 0.20, 1.0))
    z += 0.0045 * math.sin(x * 7.3 + 1.1) * math.sin(y * 6.1 + 0.4) * (1.0 - smoothstep(rr, 0.70, 1.0))
    for cx, cy, *_rest in CULMS:
        d2 = (x - cx) ** 2 + (y - cy) ** 2
        z += COLLAR_Z * math.exp(-d2 / (2.0 * COLLAR_R ** 2))
    return max(z, 0.0)


# --------------------------------------------------------------------------
# Construction helpers
# --------------------------------------------------------------------------

def path_rows(pts, radii, alongs):
    """Rows (centre, e1, e2, radius, along, nd) along ``pts`` with parallel-
    transported frames."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    tans = [(pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(n)]
    e1, _e2 = perp_basis(tans[0])
    rows = []
    for p, t, r, al in zip(pts, tans, radii, alongs):
        e1 = (e1 - t * e1.dot(t)).normalized()
        rows.append((p, e1.copy(), t.cross(e1), r, al, 1.0))
    return rows


def add_rows(bm, rows, sides, mat, L, V, tone, zone, part, tip=None):
    """A closed tube through ``rows``: flat base cap, and either a flat top
    cap or a point at ``tip``."""
    rings = []
    for c, e1, e2, r, al, nd in rows:
        ring = []
        for k in range(sides):
            a = TAU * k / sides
            v = bm.verts.new(c + r * (e1 * math.cos(a) + e2 * math.sin(a)))
            v[V["along"]] = al
            v[V["nd"]] = nd
            ring.append(v)
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            m = (k + 1) % sides
            new_face(bm, (r0[k], r0[m], r1[m], r1[k]), mat, L, tone, zone, part)
    new_face(bm, tuple(reversed(rings[0])), mat, L, tone, zone, part)
    if tip is None:
        new_face(bm, tuple(rings[-1]), mat, L, tone, zone, part)
    else:
        tv = bm.verts.new(tip)
        tv[V["along"]] = 1.0
        for k in range(sides):
            new_face(bm, (rings[-1][k], rings[-1][(k + 1) % sides], tv), mat, L, tone, zone, part)
    return rings


def add_blade(bm, pts, hws, ht, wd, mat, L, V, tone, part, along_of):
    """A slim closed blade: a diamond section (left, top, right, bottom)
    swept along ``pts`` (the last point is the tip), ``hws`` half widths."""
    rings = []
    n = len(pts) - 1
    for i in range(n):
        p = Vector(pts[i])
        t = (Vector(pts[i + 1]) - Vector(pts[max(i - 1, 0)])).normalized()
        w = wd - t * wd.dot(t)
        if w.length < 1e-6:
            w = perp_basis(t)[0]
        w = w.normalized()
        nrm = t.cross(w).normalized()
        if nrm.z < 0.0:
            nrm = -nrm
        hw = hws[i]
        quad = ((p - w * hw, -1.0), (p + nrm * ht, 0.0), (p + w * hw, 1.0), (p - nrm * ht, 0.0))
        ring = []
        for co, sd in quad:
            v = bm.verts.new(co)
            v[V["along"]] = along_of(i)
            v[V["side"]] = sd
            ring.append(v)
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(4):
            m = (k + 1) % 4
            new_face(bm, (r0[k], r0[m], r1[m], r1[k]), mat, L, tone, 0.0, part)
    new_face(bm, tuple(reversed(rings[0])), mat, L, tone, 0.0, part)
    tv = bm.verts.new(pts[-1])
    tv[V["along"]] = 1.0
    for k in range(4):
        new_face(bm, (rings[-1][k], rings[-1][(k + 1) % 4], tv), mat, L, tone, 0.0, part)


def leaf_widths(hw):
    out = []
    for u in LEAF_U:
        out.append(max(hw * math.sin(math.pi * min(u + 0.04, 1.0) ** 0.75), 0.0012))
    return out


# --------------------------------------------------------------------------
# Culms
# --------------------------------------------------------------------------

class Culm:
    """The axis of one culm as a dense polyline with parallel-transported
    frames, and the radius as a function of the arc length ``s`` from the
    buried foot."""

    def __init__(self, idx, spec, dx=0.0, dy=0.0, dz=0.0, swell=False):
        self.idx = idx
        x, y, self.L, self.r0, lean, az0, sway, phase, self.tone = spec
        self.swell = swell
        x += dx
        y += dy
        lean = math.radians(lean)
        az0 = math.radians(az0)
        sway = math.radians(sway)
        n = int(self.L / DS) + 3
        p = Vector((x, y, soil_height(x, y) - CULM_BED + dz))
        self.p = [p.copy()]
        for i in range(n - 1):
            u = min((i + 0.5) * DS / self.L, 1.0)
            th = lean * (0.35 * u + 0.65 * u * u)
            az = az0 + sway * math.sin(2.2 * u + phase)
            d = Vector((math.sin(th) * math.cos(az), math.sin(th) * math.sin(az), math.cos(th)))
            p = p + d * DS
            self.p.append(p.copy())
        m = len(self.p)
        self.t = [(self.p[min(i + 1, m - 1)] - self.p[max(i - 1, 0)]).normalized() for i in range(m)]
        e1, _e2 = perp_basis(self.t[0])
        self.e1, self.e2 = [], []
        for t in self.t:
            e1 = (e1 - t * e1.dot(t)).normalized()
            self.e1.append(e1.copy())
            self.e2.append(t.cross(e1))

    def radius(self, s):
        u = min(max(s / self.L, 0.0), 1.0)
        r = self.r0 * (1.0 - TAPER * u ** 1.2)
        r *= 1.0 + FLARE * max(0.0, 1.0 - s / FLARE_LEN) ** 2
        if self.swell:
            r *= 1.0 + SWELL * math.exp(-(((u - 0.45) / 0.07) ** 2))
        return r

    def at(self, s):
        i = min(max(int(s / DS), 0), len(self.p) - 2)
        f = (s - i * DS) / DS
        p = self.p[i].lerp(self.p[i + 1], f)
        t = self.t[i].lerp(self.t[i + 1], f).normalized()
        e1 = self.e1[i].lerp(self.e1[i + 1], f)
        e1 = (e1 - t * e1.dot(t)).normalized()
        return p, t, e1, t.cross(e1)


def node_stations(idx, L, bunch):
    out = []
    s = NODE_FIRST
    while s <= L - NODE_END:
        out.append(s)
        u = s / L
        step = NODE_BASE_L + NODE_MID_L * math.sin(math.pi * u) ** 0.9
        step *= 1.0 + 0.16 * (hash01(idx, len(out), 7) - 0.5)
        s += step
    if bunch and idx == BUNCH_IDX and len(out) > BUNCH_NODE + 1:
        out[BUNCH_NODE] = out[BUNCH_NODE + 1] - BUNCH_GAP
    return out


def culm_stations(L, nodes):
    anchors = [0.0] + list(nodes) + [L - TIP_LEN]
    out = {0.0, L - TIP_LEN}
    for a, b in zip(anchors, anchors[1:]):
        out.add(round(a, 5))
        out.add(round(b, 5))
        gap = b - a
        if a in nodes:
            out.add(round(a + 0.012, 5))
        if b in nodes:
            out.add(round(b - 0.012, 5))
        k = max(int(gap / 0.085), 1)
        for j in range(1, k):
            out.add(round(a + gap * j / k, 5))
    return sorted(out)


def add_culm(bm, L, V, culm, nodes, detail):
    sides = CULM_SIDES[detail]
    rows = []
    for s in culm_stations(culm.L, nodes):
        p, _t, e1, e2 = culm.at(s)
        nd = min(abs(s - n) for n in nodes)
        rows.append((p, e1, e2, culm.radius(s), s / culm.L, nd))
    tip = culm.at(culm.L)[0]
    add_rows(bm, rows, sides, CULM_IDX, L, V, culm.tone, 0.0, P_CULM, tip=tip)


def add_node_ring(bm, L, V, culm, s, proud, sides):
    p, _t, e1, e2 = culm.at(s)
    r = culm.radius(s)
    profile = ((-RING_BITE, -RING_H), (0.0016, -RING_H), (proud, -0.55 * RING_H),
               (proud, 0.55 * RING_H), (0.0016, RING_H), (-RING_BITE, RING_H))
    t = culm.at(s)[1]
    rings = []
    for dr, da in profile:
        ring = []
        for k in range(sides):
            a = TAU * k / sides
            v = bm.verts.new(p + t * da + (r + dr) * (e1 * math.cos(a) + e2 * math.sin(a)))
            v[V["along"]] = s / culm.L
            v[V["nd"]] = 0.0
            ring.append(v)
        rings.append(ring)
    for i in range(len(profile)):
        r0, r1 = rings[i], rings[(i + 1) % len(profile)]
        for k in range(sides):
            m = (k + 1) % sides
            new_face(bm, (r0[k], r0[m], r1[m], r1[k]), CULM_IDX, L, culm.tone, 1.0, P_NODE)


def add_branches(bm, L, V, culm, nodes, stray, lift_leaves):
    n_branch = n_leaf = 0
    for k, s_node in enumerate(nodes):
        if s_node / culm.L < BR_FROM_U or s_node > culm.L - BR_TIP_CLEAR:
            continue
        if culm.radius(s_node) < BR_R_MIN:
            continue
        s_b = s_node + (STRAY_SHIFT if stray and n_branch == 0 else 0.0)
        pc, t, e1, e2 = culm.at(s_b)
        r_c = culm.radius(s_b)
        az = k * 2.39996 + 1.2 * hash01(culm.idx, k, 1)
        radial = e1 * math.cos(az) + e2 * math.sin(az)
        phi = math.radians(46.0 + 20.0 * hash01(culm.idx, k, 2))
        d0 = t * math.cos(phi) + radial * math.sin(phi)
        lb = BR_L0 + BR_L1 * hash01(culm.idx, k, 3)
        p0 = pc + radial * (r_c - BR_BITE)
        pts, radii, alongs = [], [], []
        for j in range(7):
            v = j / 6.0
            pts.append(p0 + d0 * (lb * v) + radial * (0.10 * lb * v * v) + Vector((0.0, 0.0, -0.34 * lb * v * v)))
            radii.append(BR_R0 * (1.0 - 0.45 * v))
            alongs.append(v)
        rows = path_rows(pts, radii, alongs)
        add_rows(bm, rows, BR_SIDES, CULM_IDX, L, V, culm.tone, 2.0, P_BRANCH)
        n_branch += 1
        tans = [(pts[min(j + 1, 6)] - pts[max(j - 1, 0)]).normalized() for j in range(7)]
        for li, (v, side) in enumerate(LEAF_AT):
            j = v * 6.0
            j0 = min(int(j), 5)
            f = j - j0
            base = pts[j0].lerp(pts[j0 + 1], f)
            tb = tans[j0].lerp(tans[j0 + 1], f).normalized()
            if v >= 1.0:
                base = base - tb * LEAF_TIP_INSET
            sp = tb.cross(UP)
            sp = sp.normalized() if sp.length > 1e-6 else Vector((1.0, 0.0, 0.0))
            if side == 0.0:
                dl = (tb * 0.9 + UP * 0.1).normalized()
            else:
                dl = (tb * 0.5 + sp * (0.72 * side) + UP * 0.10).normalized()
            h = hash01(culm.idx * 31 + k, li, 4)
            ll = 0.21 + 0.12 * h
            hw = 0.0165 + 0.005 * hash01(culm.idx * 31 + k, li, 5)
            droop = 0.75 * (0.6 + 0.8 * hash01(culm.idx * 31 + k, li, 6))
            if lift_leaves:
                base = base + Vector((0.0, 0.0, LIFT_LEAVES))
            lp = [base + dl * ll * u + Vector((0.0, 0.0, -droop * ll * u * u)) for u in LEAF_U + (1.0,)]
            wd = dl.cross(UP)
            wd = wd.normalized() if wd.length > 1e-6 else Vector((1.0, 0.0, 0.0))
            add_blade(bm, lp, leaf_widths(hw), 0.0012, wd, LEAF_IDX, L, V,
                      0.15 + 0.7 * hash01(culm.idx * 31 + k, li, 8), P_LEAF,
                      lambda i: LEAF_U[i])
            n_leaf += 1
    return n_branch, n_leaf


# --------------------------------------------------------------------------
# Ground, shoots, litter
# --------------------------------------------------------------------------

def add_shoot(bm, L, V, tree, spec, detail):
    x, y, h, r = spec
    z0 = soil_hit(tree, x, y)[0].z - SHOOT_BED
    pts, radii, alongs = [], [], []
    bed = SHOOT_BED
    total = h + bed
    for k in range(SHOOT_SHEATHS):
        a = total * k / SHOOT_SHEATHS
        b = total * (k + 1) / SHOOT_SHEATHS
        for s, f in ((a + 0.004, 1.00), (b, 0.82)):
            u = min(s / total, 1.0)
            pts.append((x + 0.012 * math.sin(3.0 * u), y + 0.010 * math.sin(2.0 * u + 1.0), z0 + s))
            radii.append(r * (1.0 - 0.70 * u) * f * (1.12 if k else 1.0))
            alongs.append(u)
    rows = path_rows(pts, radii, alongs)
    tip = Vector((x + 0.012 * math.sin(3.0), y + 0.010 * math.sin(3.0), z0 + total + 0.05))
    add_rows(bm, rows, 8 if detail == "low" else 12, SHOOT_IDX, L, V, 0.5, 0.0, P_SHOOT, tip=tip)


def add_litter_blade(bm, L, V, tree, x, y, yaw, length, hw, ht, mat, part, tone, lift, stagger):
    d = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    pts = []
    for u in LEAF_U + (1.0,):
        px, py = x + d.x * length * u, y + d.y * length * u
        z = soil_hit(tree, px, py)[0].z + ht - LITTER_BELLY + stagger + lift
        pts.append(Vector((px, py, z)))
    wd = d.cross(UP).normalized()
    add_blade(bm, pts, leaf_widths(hw), ht, wd, mat, L, V, tone, part, lambda i: LEAF_U[i])


def plan_clump():
    rng = random.Random(SEED)
    keep = [(c[0], c[1], 0.06 + c[3]) for c in CULMS] + [(s[0], s[1], 0.06 + s[3]) for s in SHOOTS]
    litter, sheaths = [], []
    while len(litter) < N_LITTER or len(sheaths) < N_SHEATH:
        rad = 0.20 + 0.72 * math.sqrt(rng.random())
        th = rng.random() * TAU
        x, y = DISC_A[0] * 0.92 * rad * math.cos(th), DISC_A[1] * 0.92 * rad * math.sin(th)
        draw = (x, y, rng.random() * TAU, rng.random(), rng.random())
        length = LITTER_L0 + LITTER_L1 * draw[3] if len(litter) < N_LITTER else SHEATH_L0 + SHEATH_L1 * draw[3]
        ex, ey = x + math.cos(draw[2]) * length, y + math.sin(draw[2]) * length
        if (disc_radius(x, y) > 0.80 or disc_radius(ex, ey) > 0.80
                or any(math.hypot(x - kx, y - ky) < kr + 0.05 for kx, ky, kr in keep)):
            continue
        if len(litter) < N_LITTER:
            litter.append(draw)
        else:
            sheaths.append(draw)
    return {"litter": litter, "sheaths": sheaths}


def build_clump_mesh(name, plan, detail="low", sunk_nodes=False, stray_branches=False,
                     swell_culm=False, bunch_nodes=False, crowd_culms=False, float_culm=False,
                     float_litter=False, lift_leaves=False):
    bm = bmesh.new()
    try:
        L = {"tone": bm.faces.layers.float.new("Tone"),
             "zone": bm.faces.layers.float.new("Zone"),
             "part": bm.faces.layers.int.new("Part")}
        V = {"skirt": bm.verts.layers.float.new("Skirt"),
             "along": bm.verts.layers.float.new("Along"),
             "nd": bm.verts.layers.float.new("Nd"),
             "side": bm.verts.layers.float.new("Side")}

        add_soil(bm, L, V, DISC_N[detail])
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        tree = BVHTree.FromBMesh(bm)

        n_ring = n_branch = n_leaf = 0
        for i, spec in enumerate(CULMS):
            dx, dy = CROWD_SHIFT if (crowd_culms and i == CROWD_IDX) else (0.0, 0.0)
            dz = FLOAT_CULM if (float_culm and i == FLOAT_CULM_IDX) else 0.0
            culm = Culm(i, spec, dx, dy, dz, swell=(swell_culm and i == SWELL_IDX))
            nodes = node_stations(i, culm.L, bunch_nodes)
            add_culm(bm, L, V, culm, nodes, detail)
            for s in nodes:
                add_node_ring(bm, L, V, culm, s, SUNK_PROUD if sunk_nodes else RING_PROUD, RING_SIDES)
            n_ring += len(nodes)
            nb, nl = add_branches(bm, L, V, culm, nodes, stray_branches and i == STRAY_IDX, lift_leaves)
            n_branch += nb
            n_leaf += nl
        for spec in SHOOTS:
            add_shoot(bm, L, V, tree, spec, detail)
        lift = FLOAT_LITTER if float_litter else 0.0
        for k, (x, y, yaw, a, b) in enumerate(plan["litter"]):
            add_litter_blade(bm, L, V, tree, x, y, yaw, LITTER_L0 + LITTER_L1 * a, 0.011 + 0.004 * b,
                             LITTER_HT, DRY_IDX, P_LITTER, a, lift, 0.0007 * (k % 3))
        for k, (x, y, yaw, a, b) in enumerate(plan["sheaths"]):
            add_litter_blade(bm, L, V, tree, x, y, yaw, SHEATH_L0 + SHEATH_L1 * a, 0.045 + 0.015 * b,
                             SHEATH_HT, SHOOT_IDX, P_SHEATH, 0.2 + 0.5 * b, lift, 0.0007 * (k % 3))
        BUILT.update(rings=n_ring, branches=n_branch, leaves=n_leaf)

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        triangulate_ngons(bm)
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        zmin = min(v.co.z for v in bm.verts)
        BUILT["shift"] = (cx, cy, zmin)
        for v in bm.verts:
            v.co.x -= cx
            v.co.y -= cy
            v.co.z -= zmin

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.normal_update()
        # Everything smooth-shaded; every material boundary and every fold
        # sharper than 62 degrees a hard edge, so a leaf's edges and a node
        # ring's shoulders stay crisp while a ten-sided culm stays round.
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            mats_ = {f.material_index for f in edge.link_faces}
            if len(mats_) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            else:
                edge.smooth = edge.calc_face_angle() < math.radians(62.0)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def build_collider_source(name, low):
    """The lower 1.2 m of the clump, coarse: a player walks the litter and
    brushes through the leaves, but not through the culms."""
    cx, cy, zmin = BUILT["shift"]
    bm = bmesh.new()
    try:
        for i, spec in enumerate(CULMS):
            culm = Culm(i, spec)
            for s in (0.1, 1.25):
                p, _t, e1, e2 = culm.at(s)
                r = culm.radius(s) * 1.05
                for j in range(5):
                    a = TAU * j / 5
                    co = p + r * (e1 * math.cos(a) + e2 * math.sin(a))
                    bm.verts.new((co.x - cx, co.y - cy, co.z - zmin))
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj



def soil_material():
    mat, nt, bsdf, coord = surface("LitterSoil")
    drift = noise(nt, coord, 7.0, 5.0, 0.55)
    col = ramp(nt, drift, ((0.30, (0.040, 0.029, 0.020)), (0.60, (0.070, 0.050, 0.033)),
                           (0.85, (0.105, 0.077, 0.050))))
    # crumb and leaf-litter flecks
    g0, g1, _gd = voronoi_color(nt, coord, 60.0)
    col = mix_color(nt, col, (0.190, 0.130, 0.065), remap(nt, g0, 0.90, 0.95, 0.0, 0.50))
    col = mix_color(nt, col, (0.022, 0.018, 0.013), remap(nt, g1, 0.90, 0.95, 0.0, 0.45))
    # the disc's cut edge: damp, darker earth
    wob = noise(nt, coord, 5.0, 3.0, 0.5)
    hz = math_node(nt, "ADD", remap(nt, height(nt, coord), 0.0, MOUND_Z * 0.7, 0.0, 1.0),
                   remap(nt, wob, 0.0, 1.0, -0.08, 0.08))
    prof = ramp(nt, hz, ((0.00, (0.022, 0.018, 0.013)), (0.35, (0.036, 0.028, 0.020)),
                         (0.70, (0.062, 0.046, 0.031)), (1.00, (0.080, 0.059, 0.039))))
    col = mix_color(nt, col, prof, attr(nt, "Skirt"))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.96
    bump(nt, bsdf, math_node(nt, "ADD", math_node(nt, "MULTIPLY", drift, 0.7),
                             remap(nt, g0, 0.90, 0.95, 0.0, 0.5)), 0.45, 0.005)
    return mat


def culm_material():
    """Bamboo, one substance: zone 0 the culm, 1 a node ring, 2 a branch."""
    mat, nt, bsdf, coord = surface("BambooCulm")
    tone = attr(nt, "Tone")
    zone = attr(nt, "Zone")
    along = attr(nt, "Along")
    nd = attr(nt, "Nd")
    # fine vertical streaks: noise stretched along the culm
    streak = noise(nt, mapping(nt, coord, scale=(34.0, 34.0, 1.4)), 3.0, 4.0, 0.6)
    base = ramp(nt, tone, ((0.0, (0.105, 0.165, 0.030)), (0.5, (0.160, 0.225, 0.045)),
                           (1.0, (0.215, 0.270, 0.055))))
    col = mix_color(nt, base, ramp(nt, streak, ((0.30, (0.060, 0.105, 0.016)), (0.85, (0.200, 0.260, 0.060)))), 0.40)
    # older wood is yellower toward the foot, and dusted with earth
    col = mix_color(nt, col, (0.300, 0.265, 0.060), remap(nt, along, 0.0, 0.40, 0.60, 0.0))
    col = mix_color(nt, col, (0.060, 0.045, 0.030), remap(nt, along, 0.04, 0.0, 0.0, 0.55))
    # the wax bloom round every node, and the dark scar line at its crown
    col = mix_color(nt, col, (0.420, 0.470, 0.290), remap(nt, nd, 0.0, 0.055, 0.50, 0.0))
    col = mix_color(nt, col, (0.045, 0.036, 0.012), remap(nt, nd, 0.0, 0.008, 0.85, 0.0))
    # node ring: a pale tan collar with a dark lip
    ring = mix_color(nt, (0.300, 0.270, 0.105), (0.115, 0.095, 0.035), remap(nt, tone, 0.0, 1.0, 0.1, 0.6))
    col = mix_color(nt, col, ring, band(nt, zone, 1.0, 1.0))
    # branches: thinner, darker olive
    col = mix_color(nt, col, (0.085, 0.115, 0.028), math_node(nt, "MULTIPLY", band(nt, zone, 2.0, 2.0), 0.85))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.42
    bump(nt, bsdf, math_node(nt, "ADD", streak, math_node(nt, "MULTIPLY", band(nt, zone, 1.0, 1.0), 1.5)),
         0.35, 0.003)
    return mat


def leaf_material():
    mat, nt, bsdf, coord = surface("BambooLeaf")
    tone = attr(nt, "Tone")
    along = attr(nt, "Along")
    side = attr(nt, "Side")
    leaf = ramp(nt, tone, ((0.0, (0.050, 0.115, 0.016)), (0.5, (0.075, 0.160, 0.024)),
                           (1.0, (0.115, 0.210, 0.034))))
    # a pale midrib, and the tips going straw
    mid = remap(nt, math_node(nt, "ABSOLUTE", side, 0.0), 0.0, 0.5, 0.55, 0.0)
    leaf = mix_color(nt, leaf, (0.190, 0.290, 0.085), mid)
    leaf = mix_color(nt, leaf, (0.240, 0.250, 0.050), remap(nt, along, 0.80, 1.0, 0.0, 0.55))
    fine = noise(nt, mapping(nt, coord, scale=(60.0, 60.0, 60.0)), 2.0, 3.0, 0.5)
    leaf = mix_color(nt, leaf, (0.040, 0.085, 0.012), remap(nt, fine, 0.4, 0.7, 0.0, 0.25))
    nt.links.new(leaf, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.46
    bump(nt, bsdf, mid, 0.25, 0.002)
    return mat


def shoot_material():
    """Culm sheath: a young shoot's overlapping husks and the fallen ones."""
    mat, nt, bsdf, coord = surface("BambooSheath")
    tone = attr(nt, "Tone")
    along = attr(nt, "Along")
    sheath = ramp(nt, tone, ((0.0, (0.250, 0.175, 0.075)), (0.5, (0.330, 0.245, 0.115)),
                             (1.0, (0.410, 0.320, 0.170))))
    fib = noise(nt, mapping(nt, coord, scale=(55.0, 55.0, 7.0)), 2.0, 4.0, 0.6)
    sheath = mix_color(nt, sheath, (0.060, 0.038, 0.018), remap(nt, fib, 0.35, 0.80, 0.0, 0.65))
    # a young shoot's tip greens
    sheath = mix_color(nt, sheath, (0.090, 0.150, 0.030), remap(nt, along, 0.80, 1.0, 0.0, 0.8))
    nt.links.new(sheath, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.78
    bump(nt, bsdf, fib, 0.5, 0.003)
    return mat


def dry_material():
    mat, nt, bsdf, coord = surface("DryLeaf")
    tone = attr(nt, "Tone")
    side = attr(nt, "Side")
    col = ramp(nt, tone, ((0.0, (0.130, 0.075, 0.025)), (0.5, (0.230, 0.150, 0.055)),
                          (1.0, (0.330, 0.250, 0.110))))
    vein = remap(nt, math_node(nt, "ABSOLUTE", side, 0.0), 0.0, 0.4, 0.5, 0.0)
    col = mix_color(nt, col, (0.080, 0.045, 0.015), vein)
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    bump(nt, bsdf, vein, 0.3, 0.002)
    return mat


def clump_materials():
    """Five slots, in index order: shared by the check and the render."""
    return (soil_material(), culm_material(), leaf_material(), shoot_material(), dry_material())



def assign_slots(obj, wanted):
    # Do not materials.clear() — that resets polygon material_index to 0.
    mats = obj.data.materials
    for i, mat in enumerate(wanted):
        if i < len(mats):
            mats[i] = mat
        else:
            mats.append(mat)



# --------------------------------------------------------------------------
# Audits
# --------------------------------------------------------------------------

def vertex_bbox(me):
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def uv_stats(mesh):
    uv = mesh.uv_layers.active
    if uv is None:
        return 0.0, 0.0, 1.0, 1.0, 0, 1.0
    data = uv.data
    us = [loop.uv[0] for loop in data]
    vs = [loop.uv[1] for loop in data]
    aabbs = []
    for poly in mesh.polygons:
        pu = [data[i].uv[0] for i in poly.loop_indices]
        pv = [data[i].uv[1] for i in poly.loop_indices]
        aabbs.append((min(pu), min(pv), max(pu), max(pv)))
    aabbs.sort()
    overlap = 0.0
    for i, a in enumerate(aabbs):
        for j in range(i + 1, len(aabbs)):
            b = aabbs[j]
            if b[0] >= a[2]:
                break
            if b[1] >= a[3] or a[1] >= b[3]:
                continue
            x0 = max(a[0], b[0])
            y0 = max(a[1], b[1])
            x1 = min(a[2], b[2])
            y1 = min(a[3], b[3])
            overlap += max(0.0, x1 - x0) * max(0.0, y1 - y0)
    return min(us), min(vs), max(us), max(vs), overlap, len(aabbs)


def face_area(me, poly):
    vs = [me.vertices[i].co for i in poly.vertices]
    if len(vs) < 3:
        return 0.0
    v0 = vs[0]
    area = 0.0
    for i in range(1, len(vs) - 1):
        area += (vs[i] - v0).cross(vs[i + 1] - v0).length * 0.5
    return area


def hygiene_audit(me):
    # Combinatorics match examples/mesh-hygiene-audit.audit (copied, not imported).
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
    return {"ngons": ngons, "loose_v": loose_v, "loose_e": loose_e, "nonman": nonman,
            "zero_area": zero_area, "doubles": doubles}


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


def zfight_pairs(me, groups, report=None):
    """Coplanar face pairs from *different shells* (copied from showcase/grindstone)."""
    owner = {}
    for si, g in enumerate(groups):
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
            if report is not None and len(report) < 20:
                report.append((si, sj, tuple(round(c, 3) for c in ci)))
    return hits


class Shell:
    def __init__(self, me, idx, verts, polys, part):
        self.idx = idx
        self.verts = verts
        pts = [me.vertices[i].co.copy() for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        self.size = self.hi - self.lo
        self.part = part
        remap_ = {vi: n for n, vi in enumerate(verts)}
        self.faces = [[remap_[v] for v in p.vertices] for p in polys]
        self.tree = BVHTree.FromPolygons([tuple(p) for p in pts], self.faces)
        self.centre = sum(pts, Vector()) / len(pts)

    def volume(self):
        """Signed volume and volume centroid of the closed shell."""
        vol = 0.0
        acc = Vector()
        for f in self.faces:
            a = self.pts[f[0]]
            for i in range(1, len(f) - 1):
                b, c = self.pts[f[i]], self.pts[f[i + 1]]
                v6 = a.dot(b.cross(c))
                vol += v6
                acc += (a + b + c) * v6
        if abs(vol) < 1e-15:
            return 0.0, self.centre
        return vol / 6.0, acc / (4.0 * vol)


def classify(me):
    groups = shells(me)
    owner = [0] * len(me.vertices)
    for si, g in enumerate(groups):
        for vi in g:
            owner[vi] = si
    part_attr = me.attributes.get("Part")
    pvals = [0] * len(me.polygons)
    if part_attr is not None:
        part_attr.data.foreach_get("value", pvals)
    polys = [[] for _ in groups]
    votes = [{} for _ in groups]
    for p, pv in zip(me.polygons, pvals):
        s = owner[p.vertices[0]]
        polys[s].append(p)
        votes[s][pv] = votes[s].get(pv, 0) + 1
    parts = []
    for i, g in enumerate(groups):
        part = max(votes[i], key=votes[i].get) if votes[i] else 0
        parts.append(Shell(me, i, g, polys[i], part))
    out = {"all": parts, "groups": groups}
    for pid in range(1, N_PARTS + 1):
        out[pid] = [s for s in parts if s.part == pid]
    return out


def ray_down(tree, x, y):
    loc, _n, _i, _d = tree.ray_cast(Vector((x, y, 8.0)), Vector((0.0, 0.0, -1.0)), 20.0)
    return None if loc is None else loc.z


PARITY_DIRS = (Vector((0.31, 0.47, 0.83)).normalized(), Vector((-0.62, 0.21, -0.75)).normalized(),
               Vector((0.55, -0.79, 0.27)).normalized())


def inside(tree, p):
    """Ray parity, by majority over three directions: an odd number of
    crossings out of a closed shell. One ray that grazes an edge counts it
    twice; three rays do not all graze."""
    votes = 0
    for d in PARITY_DIRS:
        count, o = 0, p.copy()
        for _ in range(64):
            loc, _n, _i, _d = tree.ray_cast(o, d, 20.0)
            if loc is None:
                break
            count += 1
            o = loc + d * 1e-6
        votes += count % 2
    return votes >= 2


def signed_depth(tree, p):
    """How far ``p`` lies inside the closed shell of ``tree`` (negative outside)."""
    loc, _nrm, _i, dist = tree.find_nearest(p)
    if loc is None:
        return -9.0
    return dist if inside(tree, p) else -dist


def near_box(s, lo, hi, pad):
    return not (s.hi.x < lo.x - pad or s.lo.x > hi.x + pad or s.hi.y < lo.y - pad or s.lo.y > hi.y + pad
                or s.hi.z < lo.z - pad or s.lo.z > hi.z + pad)


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, 0.5))
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


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


def convex_hull_collider(obj, name):
    # Duplicated from snippets/convex_hull_collider.py (not a package).
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        result = bmesh.ops.convex_hull(bm, input=list(bm.verts))
        interior = result.get("geom_interior") or []
        unused = result.get("geom_unused") or []
        if interior:
            bmesh.ops.delete(bm, geom=interior, context="VERTS")
        unused = [v for v in unused if v.is_valid]
        if unused:
            bmesh.ops.delete(bm, geom=unused, context="VERTS")
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()
    collider = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(collider)
    collider.matrix_world = obj.matrix_world.copy()
    return collider


def setup_bake_image(obj, target_mat, size=BAKE_RES):
    # Adapted from snippets/setup_bake_target_image.py — do not replace slots.
    if not obj.data.uv_layers:
        return None, None
    img = bpy.data.images.new("BambooNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = SOIL_IDX
    return img, tex


def bake_normal(high, low):
    # Duplicated from snippets/bake_normal_high_to_low.py (not a package).
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
        type="NORMAL",
        use_selected_to_active=True,
        cage_extrusion=CAGE_EXTRUSION,
        use_cage=False,
        normal_space="TANGENT",
        margin=4,
        margin_type="ADJACENT_FACES",
        use_clear=True,
        target="IMAGE_TEXTURES",
    )


def export_unity(path, objects):
    # Duplicated from snippets/export_preset_unity.py (not a package).
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(
        filepath=path,
        use_selection=True,
        export_yup=True,
        export_apply=True,
        export_draco_mesh_compression_enable=False,
        export_animations=False,
    )



# --------------------------------------------------------------------------
# Organic audits (all recomputed from the generated mesh)
# --------------------------------------------------------------------------

def point_attr(me, name):
    vals = [0.0] * len(me.vertices)
    me.attributes[name].data.foreach_get("value", vals)
    return vals


def base_centre(me, shell, along):
    pts = [me.vertices[i].co for i in shell.verts if along[i] < 1e-6]
    return sum(pts, Vector()) / len(pts) if pts else None


def host_of(candidates, p, pad=0.05):
    """The shell ``p`` lies deepest inside, and how deep (negative outside)."""
    best, best_d = None, -9.0
    for s in candidates:
        if not near_box(s, p, p, pad):
            continue
        d = signed_depth(s.tree, p)
        if d > best_d:
            best, best_d = s, d
    return best, best_d


def soil_z_under(soil, v):
    z = ray_down(soil.tree, v.x, v.y)
    return 0.0 if z is None else z


def lowest(shell):
    return min(shell.pts, key=lambda p: p.z)


def buried(soil, shell):
    """How far the shell's deepest vertex lies under the soil straight above it."""
    return max(soil_z_under(soil, p) - p.z for p in shell.pts)


def bed_audit(shells_, soil):
    """Each shell's lowest vertex under the soil straight above it."""
    return [soil_z_under(soil, lowest(s)) - lowest(s).z for s in shells_]


def ring_audit(rings, culms):
    """(host culm, ring centre, proud, bite) per node ring. The centre of a
    ring lies on its culm's axis, so a ray from it towards each ring vertex
    meets the culm surface at the culm's own radius in that direction."""
    out = []
    for r in rings:
        c = r.centre
        # the culm the ring's centre lies inside: not the nearest surface, which
        # an overlapping neighbour can be
        host, _depth = host_of(culms, c)
        if host is None:
            continue
        proud = bite = -9.0
        for p in r.pts:
            d = p - c
            rho = d.length
            if rho < 1e-9:
                continue
            loc, _n, _i, dist = host.tree.ray_cast(c, d / rho, 1.0)
            if loc is None:
                continue
            proud = max(proud, rho - dist)
            bite = max(bite, dist - rho)
        out.append((host, c, proud, bite))
    return out


def culm_report(culms, info, soil):
    """Per culm, in plan order of height: radius at each node ring up the
    culm, the gaps between rings, the height above the soil."""
    per = {id(s): [] for s in culms}
    for host, c, _p, _b in info:
        per[id(host)].append(c)
    out = []
    for s in culms:
        cs = sorted(per[id(s)], key=lambda v: v.z)
        radii = [s.tree.find_nearest(c)[3] for c in cs]
        gaps = [(b - a).length for a, b in zip(cs, cs[1:])]
        low_v = lowest(s)
        height = s.hi.z - soil_z_under(soil, low_v)
        out.append({"shell": s, "n": len(cs), "radii": radii, "gaps": gaps, "height": height})
    return out


def mean(vals):
    return sum(vals) / len(vals) if vals else 0.0


def thirds(gaps):
    k = len(gaps) // 3
    return gaps[:k], gaps[k:len(gaps) - k]


def clump_audit(culms):
    gap, overlaps = 9.0, 0
    for i, a in enumerate(culms):
        for b in culms[i + 1:]:
            overlaps += len(a.tree.overlap(b.tree))
            for p in a.pts:
                gap = min(gap, b.tree.find_nearest(p)[3])
            for p in b.pts:
                gap = min(gap, a.tree.find_nearest(p)[3])
    return overlaps, gap


def branch_audit(me, branches, culms, info, along):
    """Each branch's first ring centre inside its host culm, and how far it
    stands from the nearest node ring."""
    bites, reach = [], []
    rings_of = {id(s): [] for s in culms}
    for host, c, _p, _b in info:
        rings_of[id(host)].append((c, host.tree.find_nearest(c)[3]))
    for b in branches:
        base = base_centre(me, b, along)
        host, depth = host_of(culms, base)
        bites.append(depth)
        if host is None:
            reach.append(9.0)
            continue
        c, r_c = min(rings_of[id(host)], key=lambda cr: (cr[0] - base).length)
        reach.append((base - c).length - r_c)
    return bites, reach


def leaf_audit(me, leaves, branches, along):
    seats = []
    for lf in leaves:
        base = base_centre(me, lf, along)
        _host, depth = host_of(branches, base, pad=0.01)
        seats.append(depth)
    return seats


def rng_(vals):
    return f"[{min(vals):.4f},{max(vals):.4f}]" if vals else "[]"


def check(skip_decimate, lift_z=False, stray_vert=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    plan = plan_clump()
    low = build_clump_mesh("BambooLow", plan, "low", **flags)
    counts = dict(BUILT)
    high = build_clump_mesh("BambooHigh", plan, "high", **flags)
    mats = clump_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    soil_mat = mats[SOIL_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none2 = (None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("bamboo mesh did not build", 3),) + none2

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat = len(slots)
    distinct_mats = len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    print(f"measured mat_index_counts={dict(sorted(idx_counts.items()))}")
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = vertex_bbox(low.data)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]
    hyg = hygiene_audit(low.data)
    cls = classify(low.data)
    zrep = []
    zf = zfight_pairs(low.data, cls["groups"], zrep)
    want = {P_SOIL: 1, P_CULM: len(CULMS), P_NODE: counts["rings"], P_BRANCH: counts["branches"],
            P_LEAF: counts["leaves"], P_SHOOT: len(SHOOTS), P_LITTER: N_LITTER, P_SHEATH: N_SHEATH}
    got = {pid: len(cls[pid]) for pid in want}
    if got != want:
        return (fail(f"shell counts {got} != planned {want}", 3),) + none2
    soil = cls[P_SOIL][0]
    culms = cls[P_CULM]
    along = point_attr(low.data, "Along")

    beds = bed_audit(culms + cls[P_SHOOT], soil)
    info = ring_audit(cls[P_NODE], culms)
    proud = [p for _h, _c, p, _b in info]
    bite = [b for _h, _c, _p, b in info]
    rep = culm_report(culms, info, soil)
    heights = [r["height"] for r in rep]
    diams = [2.0 * r["radii"][0] for r in rep if r["radii"]]
    ratios = [r["radii"][-1] / r["radii"][0] for r in rep if r["radii"]]
    worst_rise = max((b - a for r in rep for a, b in zip(r["radii"], r["radii"][1:])), default=9.0)
    pitches = [mean(r["gaps"]) for r in rep]
    all_gaps = [g for r in rep for g in r["gaps"]]
    lengthen = []
    for r in rep:
        first, mid = thirds(r["gaps"])
        lengthen.append(mean(mid) - mean(first))
    clump_overlaps, clump_gap = clump_audit(culms)
    br_bites, br_reach = branch_audit(low.data, cls[P_BRANCH], culms, info, along)
    leaf_seats = leaf_audit(low.data, cls[P_LEAF], cls[P_BRANCH], along)
    rests = [buried(soil, sh) for sh in cls[P_LITTER] + cls[P_SHEATH]]

    img, tex = setup_bake_image(low, soil_mat)
    if img is None:
        return (fail("bamboo has no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "BambooLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "BambooLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_collider_source("BambooColSrc", low)
    collider = convex_hull_collider(collider_src, "BambooCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_bamboo_clump_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    # every piece-specific budget, pass or fail, so a falsifier run shows
    # that it breaks exactly one
    budgets = {
        "grounded": bb[2] <= ZMIN_EPS and bool(beds) and BED_MIN <= min(beds) and max(beds) <= BED_MAX,
        "nodes": len(info) == counts["rings"] and PROUD_BAND[0] <= min(proud) and max(proud) <= PROUD_BAND[1]
        and BITE_BAND[0] <= min(bite) and max(bite) <= BITE_BAND[1],
        "branches": len(br_bites) == counts["branches"] and BRANCH_BITE_BAND[0] <= min(br_bites)
        and max(br_bites) <= BRANCH_BITE_BAND[1] and max(br_reach) <= NODE_SLACK,
        "size": len(rep) == len(CULMS) and CULM_H_BAND[0] <= min(heights) and max(heights) <= CULM_H_BAND[1]
        and max(heights) - min(heights) >= CULM_H_SPREAD_MIN
        and CULM_D_BAND[0] <= min(diams) and max(diams) <= CULM_D_BAND[1]
        and worst_rise <= TAPER_EPS and TAPER_RATIO_BAND[0] <= min(ratios) and max(ratios) <= TAPER_RATIO_BAND[1],
        "pitch": all(r["n"] >= NODES_MIN for r in rep) and GAP_BAND[0] <= min(all_gaps)
        and max(all_gaps) <= GAP_BAND[1] and PITCH_BAND[0] <= min(pitches) and max(pitches) <= PITCH_BAND[1]
        and min(lengthen) >= LENGTHEN_MIN,
        "clump": clump_overlaps == 0 and clump_gap >= CLUMP_GAP_MIN,
        "litter": len(rests) == N_LITTER + N_SHEATH and REST_BAND[0] <= min(rests) and max(rests) <= REST_BAND[1],
        "leaves": len(leaf_seats) == counts["leaves"] and LEAF_SEAT_BAND[0] <= min(leaf_seats)
        and max(leaf_seats) <= LEAF_SEAT_BAND[1],
    }

    print(f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}")
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
    zkinds = {}
    for si, sj, at in zrep:
        key = tuple(sorted((cls['all'][si].part, cls['all'][sj].part)))
        zkinds.setdefault(key, [0, at])[0] += 1
    for key, (n, at) in sorted(zkinds.items()):
        print(f"measured zfight_pairs parts={key} n={n} e.g. at {at}")
    print(f"measured shells={len(cls['all'])} {got}")
    print(f"measured bed culms+shoots={rng_(beds)} litter={rng_(rests)}")
    print(f"measured nodes proud={rng_(proud)} bite={rng_(bite)}")
    print(f"measured culms heights={rng_(heights)} diameters={rng_(diams)} taper_ratio={rng_(ratios)} "
          f"worst_rise={worst_rise:.5f}")
    print(f"measured nodes per culm={[r['n'] for r in rep]} gaps={rng_(all_gaps)} "
          f"pitches={rng_(pitches)} lengthen={rng_(lengthen)}")
    print(f"measured clump overlaps={clump_overlaps} gap={clump_gap:.4f}")
    print(f"measured branches bite={rng_(br_bites)} node_reach={rng_(br_reach)} "
          f"leaf_seat={rng_(leaf_seats)}")
    print(f"measured budget_fails={[k for k, ok in budgets.items() if not ok]}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none2
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none2
    for idx, (floor, label) in enumerate(zip(FACE_FLOORS, MAT_LABELS)):
        if idx_counts.get(idx, 0) < floor:
            return (fail(f"{label} faces {idx_counts.get(idx, 0)} < {floor}", 5),) + none2
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return (fail(f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})", 6),) + none2
    if overlap > UV_OVERLAP_MAX:
        return (fail(f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}", 7),) + none2
    if (abs(size_x - OUTER_SIZE[0]) > BBOX_TOL or abs(size_y - OUTER_SIZE[1]) > BBOX_TOL
            or abs(size_z - OUTER_SIZE[2]) > BBOX_TOL):
        return (fail(f"bbox ({size_x:.4f},{size_y:.4f},{size_z:.4f}) off outer {OUTER_SIZE}", 8),) + none2
    if not (LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX):
        return (fail(f"LOD1 ratio {r1:.4f} not in [{LOD1_RATIO_MIN}, {LOD1_RATIO_MAX}] "
                     "(--skip-decimate is the designed fail)", 9),) + none2
    if not (LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX):
        return (fail(f"LOD2 ratio {r2:.4f} not in [{LOD2_RATIO_MIN}, {LOD2_RATIO_MAX}]", 9),) + none2
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 11),) + none2
    if bake_result != {"FINISHED"} or not img.has_data:
        return (fail(f"bake failed result={bake_result} has_data={img.has_data}", 12),) + none2
    if export_size <= 0:
        return (fail("export file missing or empty", 13),) + none2
    if (hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
            or hyg["doubles"] or hyg["ngons"] or zf):
        return (fail(f"hygiene {hyg} zfight={zf}", 15),) + none2
    if not budgets["grounded"]:
        return (fail(f"grounded: zmin={bb[2]:.5f}, culms and shoots bedded {rng_(beds)} m under the soil "
                     f"(band [{BED_MIN}, {BED_MAX}])", 16),) + none2
    if not budgets["nodes"]:
        return (fail(f"nodes: {len(info)}/{counts['rings']} rings, crest outside the culm {rng_(proud)} m "
                     f"(band {PROUD_BAND}), inner wall inside it {rng_(bite)} m (band {BITE_BAND})", 17),) + none2
    if not budgets["branches"]:
        return (fail(f"branches: {len(br_bites)}/{counts['branches']}, first ring inside the culm "
                     f"{rng_(br_bites)} m (band {BRANCH_BITE_BAND}), off its node by {rng_(br_reach)} m "
                     f"(max {NODE_SLACK})", 18),) + none2
    if not budgets["size"]:
        return (fail(f"size: heights {rng_(heights)} m (band {CULM_H_BAND}, spread >= {CULM_H_SPREAD_MIN}), "
                     f"diameters {rng_(diams)} m (band {CULM_D_BAND}), worst radius rise up a culm "
                     f"{worst_rise:.5f} m (max {TAPER_EPS}), taper ratio {rng_(ratios)} "
                     f"(band {TAPER_RATIO_BAND})", 19),) + none2
    if not budgets["pitch"]:
        return (fail(f"pitch: nodes per culm {[r['n'] for r in rep]} (min {NODES_MIN}), gaps {rng_(all_gaps)} "
                     f"(band {GAP_BAND}), mean pitch {rng_(pitches)} (band {PITCH_BAND}), mid minus base "
                     f"{rng_(lengthen)} (min {LENGTHEN_MIN})", 20),) + none2
    if not budgets["clump"]:
        return (fail(f"clump: {clump_overlaps} intersecting triangle pairs between culms, closest approach "
                     f"{clump_gap:.4f} m (min {CLUMP_GAP_MIN})", 21),) + none2
    if not budgets["litter"]:
        return (fail(f"litter: lowest point under the soil {rng_(rests)} m, not all in {REST_BAND}", 22),) + none2
    if not budgets["leaves"]:
        return (fail(f"leaves: {len(leaf_seats)}/{counts['leaves']}, base inside its branch "
                     f"{rng_(leaf_seats)} m (band {LEAF_SEAT_BAND})", 23),) + none2
    return 0, low, soil_mat


def render_still(low, path, engine):
    scene = bpy.context.scene
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    low.rotation_euler.z = math.radians(HERO_YAW_DEG)
    bpy.context.view_layer.update()
    bb = vertex_bbox(low.data)
    centre = Vector((0.5 * (bb[0] + bb[3]), 0.5 * (bb[1] + bb[4]), 0.5 * (bb[2] + bb[5])))

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
    floor.location.z = -0.0005
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, centre.y + WALL_Y, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.100, 0.102, 0.116, 1.0)
    scene.world = world

    def light(name, offset, energy, size, col, target=None, spread=None):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        if spread is not None:
            ld.spread = math.radians(spread)
        ob = bpy.data.objects.new(name, ld)
        ob.location = centre + Vector(offset)
        aim_at = centre if target is None else Vector(target)
        ob.rotation_euler = (aim_at - ob.location).normalized().to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(ob)

    # The house rig scaled to a 4.5 m clump: warm key upper left, cool fill low
    # right, cool rim behind, warm wedge pooled on the back wall.
    light("Key", (-5.5, -7.0, 5.0), 720.0, 3.5, (1.0, 0.93, 0.83), spread=75.0)
    light("Fill", (8.0, -5.0, -0.5), 70.0, 8.0, (0.72, 0.82, 1.0))
    light("Rim", (-2.5, 3.2, 3.5), 400.0, 3.0, (0.62, 0.78, 1.0))
    light("Wedge", (6.0, 2.2, -0.2), 560.0, 3.5, (1.0, 0.70, 0.45),
          target=(centre.x + 5.0, centre.y + WALL_Y, 1.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.36, -0.93, 0.0)).normalized()
    cam.location = centre + view * CAM_DIST + Vector((0.0, 0.0, CAM_UP))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, AIM_DZ))
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
    # Standard, not AgX: AgX lifts the stage toward grey and pastels the fronds.
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low],
                                          stage=[floor, wall])
    if fcode:
        return fcode
    # asset-quality floors return 11, which this piece spends on the
    # collider ceiling; remap at the call site
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall]):
        return 24
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
    p.add_argument("--sunk-nodes", action="store_true")
    p.add_argument("--stray-branches", action="store_true")
    p.add_argument("--swell-culm", action="store_true")
    p.add_argument("--bunch-nodes", action="store_true")
    p.add_argument("--crowd-culms", action="store_true")
    p.add_argument("--float-culm", action="store_true")
    p.add_argument("--float-litter", action="store_true")
    p.add_argument("--lift-leaves", action="store_true")
    args = p.parse_args(argv)

    flags = {name: getattr(args, name) for name in FLAG_NAMES}
    code, low, _soil = check(args.skip_decimate, lift_z=args.lift_z, stray_vert=args.stray_vert, **flags)
    if code:
        return code
    if args.output:
        rcode = render_still(low, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("bamboo-clump OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
