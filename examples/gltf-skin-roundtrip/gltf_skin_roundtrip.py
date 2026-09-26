"""A rigged mech scorpion round-tripped through glTF skins — a runnable example.

Witnesses the skinned-mesh export contract that gltf-export-roundtrip left
uncovered: bones, hierarchy, weights, and deformation must all survive the
format. (Pipeline arc: modeling/LOD in lod-decimate-chain, weighting in
vertex-weight-limit, export in gltf-export-roundtrip; the tangent frames
those maps need are in triangulate-tangents.)

1. The skeleton round-trips. ``skins[0].joints`` names every bone, and the
   re-imported armature carries the same bones, parent chain, and rest
   matrices within tolerance — the +Y-up conversion applies to bone nodes
   the same way it applies to meshes, whichever way a bone points (the tail
   runs +Y, the claws -Y, the legs +/-X).
2. The weights round-trip. JOINTS_0/WEIGHTS_0 exist per primitive, per-vertex
   weights on disk sum to 1, and the re-imported vertex groups match the
   authored groups weight-for-weight within float tolerances (compared as
   sorted point sets, the same protocol as gltf-export-roundtrip).
3. The deformation round-trips. Posed identically, the re-imported rig's
   evaluated mesh matches the original's — linear blend skinning through
   the file format.
4. The mesh must be parented to the armature. The exporter warns "Armature
   must be the parent of skinned mesh" and picks an armature by name
   otherwise — with more than one rig in the file it can bind the wrong one.

The skins pipeline is stable across Blender 4.5 LTS, 5.1 and 5.2 LTS — the
example runs identically on all three.

``--no-skins`` exports with ``export_skins=False`` and still asserts one
skin on disk. That is the falsifier (``--same-axis`` in export-preset-axis).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still: the authored scorpion in the
guard pose the check compares, facing the re-imported one driven into a
different strike pose through the IMPORTED armature — the skin still deforms
after the round-trip:

    blender --background --python gltf_skin_roundtrip.py --                 # check only
    blender --background --python gltf_skin_roundtrip.py -- --no-skins      # must fail
    blender --background --python gltf_skin_roundtrip.py -- --output s.png  # + render
"""
import bpy, bmesh, sys, os, math, json, struct, shutil, tempfile, argparse
import mathutils
from mathutils import Vector

# shared render-path helpers (the repository's only cross-example import;
# see gallery_framing's docstring). Never used by the check-only path.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

PAINT, GUNMETAL, CHROME, RUBBER, GLOW = 0, 1, 2, 3, 4

# ---------------------------------------------------------------- the rig --
# Rest pose: the body lies level on eight planted legs, the tail runs
# straight back along +Y, the claws reach forward along -Y. Every part of
# the mesh is built around the bone that carries it.
BODY_Z = 0.36
TAIL_LEN = (0.25, 0.24, 0.23, 0.22, 0.21)
STING_LEN = 0.26
TAIL_R = (0.125, 0.112, 0.100, 0.089, 0.079, 0.070)   # radius at each joint
LEG_Y = (-0.26, -0.08, 0.10, 0.28)                     # hip stations
LEG_SPLAY = (-0.30, -0.12, 0.10, 0.30)                 # foot y offset from hip


def _tail_joints():
    ys = [0.50]
    for L in TAIL_LEN:
        ys.append(ys[-1] + L)
    return ys                                          # 6 joint stations


TAIL_Y = _tail_joints()


def claw_points(sx):
    """Shoulder, elbow, wrist, palm end, finger pivot, finger tip."""
    S = Vector((sx * 0.20, -0.44, BODY_Z - 0.02))
    E = Vector((sx * 0.50, -0.66, BODY_Z + 0.10))
    W = Vector((sx * 0.47, -0.94, BODY_Z + 0.04))
    P = Vector((sx * 0.44, -1.20, BODY_Z + 0.03))
    F = P + Vector((sx * 0.065, -0.01, 0.0))
    T = F + Vector((sx * 0.02, -0.31, 0.0))
    return S, E, W, P, F, T


def leg_points(sx, i):
    """Hip, coxa end, knee, ankle, foot (on the floor)."""
    hy = LEG_Y[i]
    fy = hy + LEG_SPLAY[i]
    H = Vector((sx * 0.25, hy, BODY_Z - 0.04))
    C = Vector((sx * 0.36, hy + 0.1 * (fy - hy), BODY_Z - 0.01))
    K = Vector((sx * 0.62, hy + 0.55 * (fy - hy), BODY_Z + 0.15))
    A = Vector((sx * 0.92, fy, 0.08))
    Ft = Vector((sx * 0.94, fy, 0.0))
    return H, C, K, A, Ft


def bone_table():
    """(name, head, tail, parent, connected) — the whole skeleton."""
    t = [("Body", (0.0, -0.40, BODY_Z), (0.0, TAIL_Y[0], BODY_Z), None, False)]
    prev = "Body"
    for i in range(5):
        n = f"Tail_{i + 1}"
        t.append((n, (0.0, TAIL_Y[i], BODY_Z), (0.0, TAIL_Y[i + 1], BODY_Z),
                  prev, True))
        prev = n
    t.append(("Stinger", (0.0, TAIL_Y[5], BODY_Z),
              (0.0, TAIL_Y[5] + STING_LEN, BODY_Z), prev, True))
    for side, sx in (("L", -1), ("R", 1)):
        S, E, W, P, F, T = claw_points(sx)
        t.append((f"Arm_{side}", tuple(S), tuple(W), "Body", False))
        t.append((f"Hand_{side}", tuple(W), tuple(P), f"Arm_{side}", True))
        t.append((f"Finger_{side}", tuple(F), tuple(T), f"Hand_{side}", False))
    for side, sx in (("L", -1), ("R", 1)):
        for i in range(4):
            H, C, K, A, Ft = leg_points(sx, i)
            t.append((f"Leg_{side}{i + 1}", tuple(H), tuple(K), "Body", False))
    return t


BONE_TABLE = bone_table()
BONES = tuple(b[0] for b in BONE_TABLE)

# The pose the check compares (authored vs re-imported): tail coiled tight
# over the back, claws tucked in, pincers shut. Each entry is a
# list of (rest-space axis, degrees), applied in the bone's own rest frame.
X, Z = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)
POSE_GUARD = {
    "Tail_1": [(X, 38.0)], "Tail_2": [(X, 44.0)], "Tail_3": [(X, 44.0)],
    "Tail_4": [(X, 42.0)], "Tail_5": [(X, 36.0)], "Stinger": [(X, 28.0)],
    "Arm_L": [(Z, 16.0)], "Arm_R": [(Z, -16.0)],
    "Hand_L": [(Z, 14.0)], "Hand_R": [(Z, -14.0)],
    "Finger_L": [(Z, 2.0)], "Finger_R": [(Z, -2.0)],
}
# Render staging only (never part of the check): the pose the RE-IMPORTED
# armature is driven into for the still — tail rearing high to strike,
# claws flung wide and raised, pincers gaping. A skin that did not survive
# the file could not follow it.
POSE_STRIKE = {
    "Tail_1": [(X, 78.0)], "Tail_2": [(X, 6.0)], "Tail_3": [(X, 6.0)],
    "Tail_4": [(X, 14.0)], "Tail_5": [(X, 30.0)], "Stinger": [(X, 72.0)],
    "Arm_L": [(Z, -30.0), (X, -34.0)], "Arm_R": [(Z, 30.0), (X, -34.0)],
    "Hand_L": [(Z, 6.0), (X, 10.0)], "Hand_R": [(Z, -6.0), (X, 10.0)],
    "Finger_L": [(Z, -45.0)], "Finger_R": [(Z, 45.0)],
}

POS_TOL = 2e-5                  # float32 on disk vs float32 in Blender
W_TOL = 3e-4                    # weight round-trip tolerance
SUM_TOL = 3e-4                  # disk weight-sum tolerance
REST_TOL = 1e-5                 # rest-matrix round-trip tolerance
KEY_DIGITS = 4
# render staging only: each rig's X offset, and its yaw (head turned toward
# the rival, a little toward the camera so the claws read in depth)
STILL_X = 1.28
STILL_YAW = 64.0

EXPORT_KWARGS = dict(
    export_format='GLTF_SEPARATE',
    export_skins=True,
    export_yup=True,
    export_animations=False,
    export_image_format='NONE',
)


# ------------------------------------------------------------ geometry kit --
def frame_of(d, up=(0.0, 0.0, 1.0)):
    """Side and up axes perpendicular to direction d."""
    d = Vector(d).normalized()
    u = Vector(up)
    if abs(d.dot(u)) > 0.95:
        u = Vector((0.0, 1.0, 0.0))
    side = d.cross(u).normalized()
    upv = side.cross(d).normalized()
    return side, upv


def rrect(w, h, r, seg=2):
    """Rounded rectangle half-extents (w, h), corner radius r, CCW."""
    r = min(r, w * 0.98, h * 0.98)
    pts = []
    for cx, cy, a0 in ((w - r, h - r, 0), (-(w - r), h - r, 90),
                       (-(w - r), -(h - r), 180), (w - r, -(h - r), 270)):
        for k in range(seg + 1):
            a = math.radians(a0 + 90.0 * k / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def ngon(r, n=8, phase=None):
    ph = math.pi / n if phase is None else phase
    return [(r * math.cos(ph + 2 * math.pi * k / n),
             r * math.sin(ph + 2 * math.pi * k / n)) for k in range(n)]


def arch(w, rise, thick, n=10, lip=0.35):
    """Armour plate cross-section: a crowned shell with chamfered lips."""
    outer = [(w * (-1 + 2 * k / n), rise * (1 - (-1 + 2 * k / n) ** 2))
             for k in range(n + 1)]
    inner = [(x * 0.94, y - thick) for x, y in reversed(outer)]
    # chamfer the two lips so no edge meets at a right angle
    outer[0] = (outer[0][0] * 0.97, outer[0][1] - thick * lip)
    outer[-1] = (outer[-1][0] * 0.97, outer[-1][1] - thick * lip)
    return list(reversed(outer)) + list(reversed(inner))


class Kit:
    """bmesh accumulator: every vertex carries its bone weights."""

    def __init__(self):
        self.bm = bmesh.new()
        self.vw = []

    def sweep(self, centers, profiles, mat, weight, dirs=None, up=(0, 0, 1),
              caps=(True, True)):
        """Loft profile i at center i, perpendicular to the path."""
        n = len(centers)
        rows = []
        for i, c in enumerate(centers):
            c = Vector(c)
            if dirs is not None:
                d = Vector(dirs[i])
            elif i == 0:
                d = Vector(centers[1]) - c
            elif i == n - 1:
                d = c - Vector(centers[i - 1])
            else:
                d = Vector(centers[i + 1]) - Vector(centers[i - 1])
            side, upv = frame_of(d, up)
            row = []
            for a, b in profiles[i]:
                p = c + side * a + upv * b
                row.append(self.bm.verts.new(p))
                self.vw.append(weight(i, p) if callable(weight) else weight)
            rows.append(row)
        m = len(rows[0])
        for i in range(n - 1):
            for s in range(m):
                f = self.bm.faces.new((rows[i][s], rows[i][(s + 1) % m],
                                       rows[i + 1][(s + 1) % m], rows[i + 1][s]))
                f.material_index = mat
        for flag, row in zip(caps, (rows[0], rows[-1])):
            if flag:
                self.bm.faces.new(row).material_index = mat
        return rows

    def strut(self, p0, p1, r0, r1, mat, weight, n=8, ch=0.25, up=(0, 0, 1)):
        """Tapered prism with chamfered ends."""
        p0, p1 = Vector(p0), Vector(p1)
        d = (p1 - p0)
        L = d.length
        dn = d / L
        c = min(ch * min(r0, r1), L * 0.2)
        cs = [p0, p0 + dn * c, p1 - dn * c, p1]
        pr = [ngon(r0 * 0.72, n), ngon(r0, n), ngon(r1, n), ngon(r1 * 0.72, n)]
        return self.sweep(cs, pr, mat, weight, dirs=[d] * 4, up=up)

    def disc(self, c, axis, r, t, mat, weight, n=14):
        """Short chamfered cylinder (joint cap, eye lens, foot pad)."""
        c, a = Vector(c), Vector(axis).normalized()
        cs = [c - a * t, c - a * t * 0.6, c + a * t * 0.6, c + a * t]
        pr = [ngon(r * 0.82, n), ngon(r, n), ngon(r, n), ngon(r * 0.82, n)]
        return self.sweep(cs, pr, mat, weight, dirs=[a] * 4)

    def finish(self, me):
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        self.bm.to_mesh(me)


def W1(bone):
    return {bone: 1.0}


def blend(a, b, p0, p1):
    """Weights sliding a -> b along the segment p0 -> p1 (a rubber boot)."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    L2 = d.length_squared

    def w(_i, p):
        t = max(0.0, min(1.0, (Vector(p) - p0).dot(d) / L2))
        t = t * t * (3 - 2 * t)                       # smoothstep
        if t <= 1e-6:
            return {a: 1.0}
        if t >= 1 - 1e-6:
            return {b: 1.0}
        return {a: 1.0 - t, b: t}
    return w


# -------------------------------------------------------------- the model --
def build_body(k):
    z = BODY_Z
    # chassis hull: gunmetal, rounded section swelling mid-body
    stations = [(-0.50, 0.12, 0.07), (-0.44, 0.19, 0.11), (-0.30, 0.25, 0.13),
                (-0.06, 0.28, 0.14), (0.20, 0.26, 0.13), (0.42, 0.19, 0.11),
                (0.52, 0.13, 0.08)]
    k.sweep([(0, y, z) for y, _, _ in stations],
            [rrect(w, h, h * 0.7, 3) for _, w, h in stations],
            GUNMETAL, W1("Body"), dirs=[(0, 1, 0)] * len(stations))
    # carapace shield over the head: crowned, lipped, tapering to the brow
    hs = [(-0.56, 0.15, 0.05), (-0.50, 0.22, 0.07), (-0.36, 0.27, 0.09),
          (-0.20, 0.29, 0.10), (-0.14, 0.28, 0.095)]
    k.sweep([(0, y, z + 0.10) for y, _, _ in hs],
            [arch(w, r, 0.035) for _, w, r in hs], PAINT, W1("Body"),
            dirs=[(0, 1, 0)] * len(hs))
    # five shingled tergite plates down the back, each riding over the last
    for i in range(5):
        y0 = -0.16 + i * 0.135
        y1 = y0 + 0.17
        w = 0.30 - 0.018 * i
        zz = z + 0.105 + 0.006 * i
        ys = [y0, y0 + 0.025, y1 - 0.025, y1]
        k.sweep([(0, y, zz) for y in ys],
                [arch(w * s, 0.075 * s, 0.03) for s in (0.93, 1.0, 1.0, 0.95)],
                PAINT, W1("Body"), dirs=[(0, 1, 0)] * 4)
        # a gunmetal spine stud on each plate
        k.strut((0, y0 + 0.05, zz + 0.07), (0, y1 - 0.04, zz + 0.075),
                0.022, 0.018, GUNMETAL, W1("Body"), n=6)
    # sensor brow: two glowing lenses under the shield's front lip
    for sx in (-1, 1):
        k.disc((sx * 0.075, -0.535, z + 0.07), (0.15 * sx, -1, 0.25), 0.032,
               0.014, GLOW, W1("Body"), n=12)
        k.disc((sx * 0.075, -0.522, z + 0.07), (0.15 * sx, -1, 0.25), 0.042,
               0.012, GUNMETAL, W1("Body"), n=12)
    # chelicerae: two short mandible struts under the brow
    for sx in (-1, 1):
        k.strut((sx * 0.06, -0.46, z - 0.04), (sx * 0.045, -0.60, z - 0.07),
                0.03, 0.018, CHROME, W1("Body"), n=6)
    # belly keel plate
    k.sweep([(0, y, z - 0.14) for y in (-0.36, -0.30, 0.34, 0.40)],
            [rrect(w, 0.02, 0.012, 1) for w in (0.14, 0.18, 0.18, 0.12)],
            RUBBER, W1("Body"), dirs=[(0, 1, 0)] * 4)


def build_legs(k):
    for side, sx in (("L", -1), ("R", 1)):
        for i in range(4):
            b = f"Leg_{side}{i + 1}"
            H, C, K, A, Ft = leg_points(sx, i)
            # hip ball socket and coxa
            k.disc(H, (sx, 0, 0), 0.055, 0.03, GUNMETAL, W1(b), n=12)
            k.strut(H, C, 0.045, 0.04, GUNMETAL, W1(b), n=8)
            # femur: gunmetal beam under a painted armour cover
            k.strut(C, K, 0.056, 0.048, GUNMETAL, W1(b), n=8)
            fd = (K - C)
            side_ax, up_ax = frame_of(fd)
            cov0, cov1 = C + fd * 0.12, C + fd * 0.86
            k.sweep([cov0, cov0 + fd * 0.06, cov1 - fd * 0.06, cov1],
                    [arch(s * 0.088, s * 0.045, 0.024, 6)
                     for s in (0.85, 1.0, 1.0, 0.8)],
                    PAINT, W1(b), dirs=[fd] * 4)
            # hydraulic ram under the femur, chrome rod into gunmetal barrel
            r0 = C + fd * 0.10 - up_ax * 0.07
            r1 = C + fd * 0.72 - up_ax * 0.055
            k.strut(r0, r0.lerp(r1, 0.55), 0.020, 0.020, GUNMETAL, W1(b), n=6)
            k.strut(r0.lerp(r1, 0.5), r1, 0.011, 0.011, CHROME, W1(b), n=6)
            # knee: a pinned joint drum across the leg plane
            kn = fd.cross(A - K).normalized()
            k.disc(K, kn, 0.058, 0.04, GUNMETAL, W1(b), n=12)
            k.disc(K + kn * 0.044, kn, 0.026, 0.008, CHROME, W1(b), n=10)
            # tibia down to the ankle, tapering
            k.strut(K, A, 0.048, 0.03, GUNMETAL, W1(b), n=8)
            # foot: rubber pad planted on the floor
            k.strut(A, Ft + Vector((0, 0, 0.03)), 0.022, 0.03, GUNMETAL, W1(b), n=8)
            k.sweep([Ft + Vector((0, 0, 0.002)), Ft + Vector((0, 0, 0.012)),
                     Ft + Vector((0, 0, 0.030)), Ft + Vector((0, 0, 0.040))],
                    [ngon(0.036, 10), ngon(0.045, 10), ngon(0.045, 10),
                     ngon(0.03, 10)], RUBBER, W1(b), dirs=[(0, 0, 1)] * 4)


def build_claws(k):
    for side, sx in (("L", -1), ("R", 1)):
        arm, hand, fin = f"Arm_{side}", f"Hand_{side}", f"Finger_{side}"
        S, E, W, P, F, T = claw_points(sx)
        # shoulder boot: rubber, blending Body -> Arm
        k.sweep([S + (E - S).normalized() * t for t in (-0.05, -0.02, 0.02, 0.05, 0.08)],
                [ngon(r, 10) for r in (0.045, 0.058, 0.052, 0.058, 0.048)],
                RUBBER, blend("Body", arm, S - (E - S).normalized() * 0.05,
                              S + (E - S).normalized() * 0.08))
        # humerus (painted sleeve over a gunmetal beam) and forearm
        k.strut(S + (E - S) * 0.12, E, 0.05, 0.045, GUNMETAL, W1(arm), n=8)
        ed = E - S
        k.sweep([S + ed * t for t in (0.22, 0.28, 0.80, 0.88)],
                [arch(s * 0.07, s * 0.035, 0.02, 6) for s in (0.85, 1, 1, 0.85)],
                PAINT, W1(arm), dirs=[ed] * 4)
        k.disc(E, (0, 0, 1), 0.06, 0.05, GUNMETAL, W1(arm), n=12)
        k.strut(E, W - (W - E).normalized() * 0.05, 0.045, 0.04, GUNMETAL,
                W1(arm), n=8)
        # wrist boot: rubber, blending Arm -> Hand
        wd = (P - W).normalized()
        k.sweep([W + wd * t for t in (-0.07, -0.04, 0.0, 0.04, 0.07)],
                [ngon(r, 10) for r in (0.040, 0.050, 0.044, 0.050, 0.042)],
                RUBBER, blend(arm, hand, W - wd * 0.07, W + wd * 0.07))

        # chela: a swollen painted hand
        hd = P - W
        ts = (0.10, 0.16, 0.35, 0.62, 0.86, 1.0)
        ws = (0.055, 0.092, 0.135, 0.140, 0.115, 0.090)
        hs = (0.045, 0.072, 0.098, 0.100, 0.084, 0.064)
        k.sweep([W + hd * t for t in ts],
                [rrect(w, h, h * 0.75, 3) for w, h in zip(ws, hs)],
                PAINT, W1(hand), dirs=[hd] * len(ts))
        # fixed finger (inner) — curved, gunmetal, chrome tip
        inner = Vector((-sx, 0, 0))
        base = P + inner * 0.045
        pts = [base + Vector((0, -0.30 * t, 0)) + inner * (0.04 * t * t)
               for t in (0.0, 0.3, 0.6, 0.85, 1.0)]
        k.sweep(pts, [ngon(r, 8) for r in (0.046, 0.040, 0.031, 0.019, 0.007)],
                GUNMETAL, W1(hand))
        # finger pivot pin (hand) and the movable finger (its own bone)
        k.disc(F, (0, 0, 1), 0.036, 0.062, CHROME, W1(hand), n=10)
        fd = T - F
        pts = [F + fd * t - Vector((sx, 0, 0)) * (0.05 * t * t)
               for t in (0.0, 0.3, 0.6, 0.85, 1.0)]
        k.sweep(pts, [ngon(r, 8) for r in (0.044, 0.038, 0.030, 0.018, 0.007)],
                GUNMETAL, W1(fin))


def build_tail(k):
    y, z = TAIL_Y, BODY_Z
    bones = [f"Tail_{i + 1}" for i in range(5)] + ["Stinger"]
    parents = ["Body"] + bones[:-1]
    for i in range(5):
        b = bones[i]
        r0, r1 = TAIL_R[i], TAIL_R[i + 1]
        L = y[i + 1] - y[i]
        # rubber bellows over the joint at the segment's head (parent -> b)
        by = [y[i] - 0.05 + 0.1 * t / 6 for t in range(7)]
        k.sweep([(0, yy, z) for yy in by],
                [ngon(r0 * (0.80 if t % 2 else 0.90), 12) for t in range(7)],
                RUBBER, blend(parents[i], b, (0, y[i] - 0.05, z), (0, y[i] + 0.05, z)),
                dirs=[(0, 1, 0)] * 7)
        # armour collar: painted, hexagonal, chamfered, tapering
        ys = [y[i] + 0.035, y[i] + 0.06, y[i] + L * 0.78, y[i] + L * 0.86]
        rs = [r0 * 0.96, r0 * 1.12, r1 * 1.10, r1 * 0.94]
        k.sweep([(0, yy, z) for yy in ys],
                [[(a, bb * 0.92) for a, bb in ngon(r, 8)] for r in rs],
                PAINT, W1(b), dirs=[(0, 1, 0)] * 4)
        # dorsal keel: a gunmetal fin riding each collar
        k.sweep([(0, yy, z + r0 * 1.02) for yy in (y[i] + 0.07, y[i] + 0.09,
                                                    y[i] + L * 0.66, y[i] + L * 0.76)],
                [[(-0.012, -0.02), (0.012, -0.02), (0.008, h), (-0.008, h)]
                 for h in (0.012, 0.035, 0.03, 0.01)],
                GUNMETAL, W1(b), dirs=[(0, 1, 0)] * 4)
    # stinger: bellows, a gunmetal telson bulb with a glowing venom band, and
    # a chrome needle hooking toward the rest-pose +Z (downward once coiled)
    b = "Stinger"
    y5 = y[5]
    by = [y5 - 0.045 + 0.09 * t / 6 for t in range(7)]
    k.sweep([(0, yy, z) for yy in by],
            [ngon(TAIL_R[5] * (0.80 if t % 2 else 0.90), 12) for t in range(7)],
            RUBBER, blend("Tail_5", b, (0, y5 - 0.045, z), (0, y5 + 0.045, z)),
            dirs=[(0, 1, 0)] * 7)
    ts = (0.03, 0.06, 0.12, 0.20, 0.27, 0.33)
    rs = (0.060, 0.080, 0.100, 0.098, 0.075, 0.040)
    k.sweep([(0, y5 + t, z + 0.02) for t in ts], [ngon(r, 12) for r in rs],
            GUNMETAL, W1(b), dirs=[(0, 1, 0)] * len(ts))
    k.sweep([(0, y5 + t, z + 0.02) for t in (0.145, 0.155, 0.185, 0.195)],
            [ngon(r, 12) for r in (0.100, 0.104, 0.104, 0.100)],
            GLOW, W1(b), dirs=[(0, 1, 0)] * 4)
    pts = []
    for s in (0.0, 0.25, 0.5, 0.75, 1.0):
        a = math.radians(95 * s)
        pts.append((0, y5 + 0.32 + 0.14 * math.sin(a), z + 0.02 + 0.14 * (1 - math.cos(a))))
    k.sweep(pts, [ngon(r, 8) for r in (0.035, 0.028, 0.02, 0.012, 0.004)],
            CHROME, W1(b), up=(1, 0, 0))


def build_scorpion(name="Scorpion"):
    """The mech scorpion: painted plates on a gunmetal chassis, eight legs
    planted on rubber pads, articulated claws, a bellows-jointed tail and a
    chrome stinger — every vertex carrying the weights of the bone it rides
    (two-bone blends only in the rubber boots at the flexing joints)."""
    me = bpy.data.meshes.new(name)
    k = Kit()
    try:
        build_body(k)
        build_legs(k)
        build_claws(k)
        build_tail(k)
        k.finish(me)
    finally:
        k.bm.free()  # the ownership contract, as always
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(40.0))
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj, k.vw


def assign_weights(obj, vw):
    groups = {b: obj.vertex_groups.new(name=b) for b in BONES}
    for idx, w in enumerate(vw):
        for bone, x in w.items():
            groups[bone].add([idx], x, 'REPLACE')
    return groups


def build_rig(obj):
    arm_data = bpy.data.armatures.new("ScorpRig")
    arm = bpy.data.objects.new("ScorpRig", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    ebs = {}
    for name, head, tail, parent, conn in BONE_TABLE:
        eb = arm_data.edit_bones.new(name)
        eb.head, eb.tail, eb.roll = head, tail, 0.0
        if parent is not None:
            eb.parent = ebs[parent]
            eb.use_connect = conn
        ebs[name] = eb
    bpy.ops.object.mode_set(mode='OBJECT')
    # the exporter warns and picks by name otherwise — with two rigs in the
    # file it can bind the WRONG one; parent explicitly
    obj.parent = arm
    mod = obj.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm
    mod.use_vertex_groups = True
    mod.use_bone_envelopes = False
    apply_pose(arm, POSE_GUARD)
    return arm


def apply_pose(arm, pose):
    """Pose by rest-space axes, in quaternions: the glTF importer leaves its
    armature's bones in quaternion mode, so the same call drives both rigs."""
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        q = mathutils.Quaternion()
        rest = pb.bone.matrix_local.to_3x3()
        for axis, deg in pose.get(pb.name, ()):
            local = (rest.inverted() @ Vector(axis)).normalized()
            q = mathutils.Quaternion(local, math.radians(deg)) @ q
        pb.rotation_quaternion = q


def eval_positions(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    ob_eval = obj.evaluated_get(deps)
    me = ob_eval.to_mesh()
    try:
        return [tuple(v.co) for v in me.vertices]
    finally:
        ob_eval.to_mesh_clear()


def key_of(p):
    return tuple(round(c, KEY_DIGITS) for c in p)


_STEPS = sorted(((dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                 for dz in (-1, 0, 1)), key=lambda s: abs(s[0]) + abs(s[1]) + abs(s[2]))


def keys_near(k):
    """The key itself first, then its 26 neighbours ONE rounding step away,
    each re-rounded: a float32 round-trip can land a coordinate on the far
    side of a rounding boundary (straddle-safe). The neighbours must be
    rounded — k + 1e-4 in binary floating point is not a key."""
    step = 10 ** -KEY_DIGITS
    for dx, dy, dz in _STEPS:
        yield key_of((k[0] + dx * step, k[1] + dy * step, k[2] + dz * step))


def read_gltf(path):
    with open(path, encoding="utf-8") as fh:
        g = json.load(fh)
    with open(os.path.join(os.path.dirname(path), g["buffers"][0]["uri"]), "rb") as fh:
        blob = fh.read()

    def accessor_floats(idx, ncomp):
        acc = g["accessors"][idx]
        bv = g["bufferViews"][acc["bufferView"]]
        off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = bv.get("byteStride", 4 * ncomp)
        return [struct.unpack_from(f"<{ncomp}f", blob, off + stride * i)
                for i in range(acc["count"])]

    def accessor_uints(idx, ncomp, ctype):
        acc = g["accessors"][idx]
        bv = g["bufferViews"][acc["bufferView"]]
        off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = bv.get("byteStride", {5121: 1, 5123: 2, 5125: 4}[ctype] * ncomp)
        fmt = {5121: "B", 5123: "H", 5125: "I"}[ctype]
        return [struct.unpack_from(f"<{ncomp}{fmt}", blob, off + stride * i)
                for i in range(acc["count"])]

    return g, accessor_floats, accessor_uints


def check(obj, arm, no_skins=False):
    me = obj.data
    exp_props = {p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties}
    missing = [k for k in EXPORT_KWARGS if k not in exp_props]
    if missing:
        print(f"ERROR: exporter RNA drifted, missing {missing}", file=sys.stderr)
        return 3

    base_verts = len(me.vertices)
    ngroups = len(obj.vertex_groups)
    if ngroups != len(BONES):
        print(f"ERROR: {ngroups} vertex groups != {len(BONES)} bones", file=sys.stderr)
        return 4

    deps = bpy.context.evaluated_depsgraph_get()
    ob_eval = obj.evaluated_get(deps)
    me_eval = ob_eval.to_mesh()
    try:
        eval_loops = len(me_eval.loops)
        pose_orig = [tuple(v.co) for v in me_eval.vertices]
    finally:
        ob_eval.to_mesh_clear()

    rest_orig = [tuple(v.co) for v in me.vertices]
    # snapshot everything the export/import wipe would free: the original
    # datablocks DIE at read_factory_settings (the crate's freed-mesh hazard)
    bone_info = {name: (arm.data.bones[name].parent.name
                        if arm.data.bones[name].parent else None,
                        tuple(tuple(arm.data.bones[name].matrix_local[r][c]
                                    for c in range(4)) for r in range(4)))
                 for name in BONES}

    def weight_map(o):
        names = [g.name for g in o.vertex_groups]
        return {key_of(v.co): tuple(sorted(
            (names[g.group], round(g.weight, 5)) for g in v.groups))
            for v in o.data.vertices}

    want_w = weight_map(obj)

    tmp = tempfile.mkdtemp(prefix="gltf_skin_")
    try:
        path = os.path.join(tmp, "scorp.gltf").replace("\\", "/")
        kw = dict(EXPORT_KWARGS)
        if no_skins:
            kw["export_skins"] = False
        bpy.ops.export_scene.gltf(filepath=path, **kw)

        # contract 1 (on disk): the skin carries every bone, joints named
        g, acc_f, acc_u = read_gltf(path)
        skins = g.get("skins", [])
        if len(skins) != 1:
            print(f"ERROR: {len(skins)} skins on disk, expected 1", file=sys.stderr)
            return 5
        joints = skins[0]["joints"]
        node_names = [g["nodes"][j].get("name", "") for j in joints]
        if len(joints) != len(BONES) or sorted(node_names) != sorted(BONES):
            print(f"ERROR: skin joints {node_names} != bones {sorted(BONES)}",
                  file=sys.stderr)
            return 6
        prim = g["meshes"][0]["primitives"]
        if not all("JOINTS_0" in p["attributes"] and "WEIGHTS_0" in p["attributes"]
                   for p in prim):
            print("ERROR: primitives lack JOINTS_0/WEIGHTS_0", file=sys.stderr)
            return 7
        # contract 2a (on disk): per-vertex weights sum to 1
        disk_verts = 0
        sum_err = 0.0
        blended = 0
        for p in prim:
            a = p["attributes"]
            w = acc_f(a["WEIGHTS_0"], 4)
            j = acc_u(a["JOINTS_0"], 4, g["accessors"][a["JOINTS_0"]]["componentType"])
            # JOINTS_0 and WEIGHTS_0 must cover the same vertices; zip() would
            # otherwise silently score only the shorter accessor
            if len(w) != len(j):
                print(f"ERROR: WEIGHTS_0 count {len(w)} != JOINTS_0 count "
                      f"{len(j)} on a primitive", file=sys.stderr)
                return 7
            disk_verts += len(w)
            for ws, js in zip(w, j):
                total = sum(x for x, ji in zip(ws, js) if ji < len(BONES))
                sum_err = max(sum_err, abs(total - 1.0) if total > 1e-9 else 0.0)
                blended += sum(1 for x in ws if x > 1e-6) > 1
        if sum_err > SUM_TOL:
            print(f"ERROR: disk weight sums deviate {sum_err:.3e} from 1.0",
                  file=sys.stderr)
            return 8
        if disk_verts > eval_loops:
            print(f"ERROR: disk verts {disk_verts} exceed evaluated loops "
                  f"{eval_loops} — the exporter invented vertices",
                  file=sys.stderr)
            return 9

        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # contract 1b: the skeleton round-trips
    arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    if len(arms) != 1:
        print(f"ERROR: {len(arms)} armatures after import, expected 1",
              file=sys.stderr)
        return 10
    ri_arm = arms[0]
    if len(ri_arm.data.bones) != len(BONES):
        print(f"ERROR: {len(ri_arm.data.bones)} bones != {len(BONES)}",
              file=sys.stderr)
        return 11
    rest_err = 0.0
    for name in BONES:
        b1 = ri_arm.data.bones.get(name)
        if b1 is None:
            print(f"ERROR: bone {name} lost in round-trip", file=sys.stderr)
            return 12
        p0, m0 = bone_info[name]
        p1 = b1.parent.name if b1.parent else None
        if p0 != p1:
            print(f"ERROR: {name} parent {p1} != {p0}", file=sys.stderr)
            return 13
        rest_err = max(rest_err,
                       max(abs(m0[r][c] - b1.matrix_local[r][c])
                           for r in range(4) for c in range(4)))
    if rest_err > REST_TOL:
        print(f"ERROR: rest matrices deviate {rest_err:.3e} on round-trip",
              file=sys.stderr)
        return 14

    # contract 2b: the weights round-trip (sorted point sets, crate protocol)
    ri = [o for o in bpy.data.objects
          if o.type == 'MESH' and o.vertex_groups and o.find_armature()]
    if len(ri) != 1:
        print(f"ERROR: {len(ri)} skinned meshes after import, expected 1",
              file=sys.stderr)
        return 15
    ri = ri[0]
    rme = ri.data
    if len(rme.vertices) != disk_verts:
        print(f"ERROR: re-import has {len(rme.vertices)} verts, expected the "
              f"{disk_verts} on disk (the import must be 1:1 with the file)",
              file=sys.stderr)
        return 16
    if sorted(g.name for g in ri.vertex_groups) != sorted(BONES):
        print("ERROR: vertex group names drifted", file=sys.stderr)
        return 17

    # per-vertex weight vectors, compared at sorted positions
    # EVERY re-imported vertex at a position is kept, not the last one: the
    # exporter splits a vertex per normal/UV, and each split copy carries its
    # own JOINTS_0/WEIGHTS_0 — one bad copy must not hide behind a good twin
    names_ri = [g.name for g in ri.vertex_groups]
    got_w = {}
    for v in rme.vertices:
        got_w.setdefault(key_of(v.co), set()).add(tuple(sorted(
            (names_ri[g.group], round(g.weight, 5)) for g in v.groups)))
    w_err = 0.0
    for p, want in want_w.items():
        gots = next((got_w[k] for k in keys_near(p) if k in got_w), None)
        if gots is None:
            w_err = 1.0
            continue
        for got in gots:
            if got != want:
                w_err = max(w_err, max(abs(dict(want).get(n, 0.0) - dict(got).get(n, 0.0))
                                       for n in set(dict(want)) | set(dict(got))))
    if w_err > W_TOL:
        print(f"ERROR: weight round-trip deviates {w_err:.3e} (tol {W_TOL})",
              file=sys.stderr)
        return 18

    # contract 3: the deformation round-trips (pose the re-imported rig the
    # same way, compare posed positions BY REST-KEY — sorted multisets
    # misalign because the exporter welds duplicate loops)
    apply_pose(ri_arm, POSE_GUARD)
    bpy.context.view_layer.update()
    pose_ri = eval_positions(ri)
    orig_map = {}
    for r, p in zip(rest_orig, pose_orig):
        orig_map.setdefault(key_of(r), []).append(p)
    pos_err = 0.0
    for j, rv in enumerate(rme.vertices):
        cands = []
        for k in keys_near(key_of(rv.co)):
            cands += orig_map.get(k, [])
        best = min((max(abs(pose_ri[j][c] - p[c]) for c in range(3))
                    for p in cands), default=1e30)
        pos_err = max(pos_err, best)
    if pos_err > POS_TOL:
        print(f"ERROR: deformation round-trip deviates {pos_err:.3e} "
              f"(tol {POS_TOL})", file=sys.stderr)
        return 19

    print(f"bones={len(BONES)} verts={base_verts} eval_loops={eval_loops} "
          f"disk_verts={disk_verts} (welded {eval_loops - disk_verts}) "
          f"blended_disk_verts={blended} sum_err={sum_err:.2e}")
    print(f"rest_err={rest_err:.2e} w_err={w_err:.2e} (tol {W_TOL}) "
          f"pos_err={pos_err:.2e} (tol {POS_TOL})")
    return 0


# ------------------------------------------------------------- the still --
def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def make_materials():
    def pbr(name, base, metallic, roughness, emission=None, strength=0.0):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        b = mat.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*base, 1.0)
        b.inputs["Metallic"].default_value = metallic
        b.inputs["Roughness"].default_value = roughness
        if emission is not None:
            sock = b.inputs.get("Emission Color") or b.inputs["Emission"]
            sock.default_value = (*emission, 1.0)
            b.inputs["Emission Strength"].default_value = strength
        return mat
    return [
        pbr("HazardPaint", (0.78, 0.26, 0.05), 0.15, 0.42),
        pbr("Gunmetal", (0.10, 0.11, 0.125), 0.85, 0.36),
        pbr("Chrome", (0.62, 0.64, 0.66), 1.0, 0.18),
        pbr("FlexRubber", (0.035, 0.035, 0.04), 0.0, 0.82),
        pbr("VenomGlow", (0.02, 0.20, 0.22), 0.0, 0.35,
            emission=(0.10, 0.85, 0.80), strength=4.0),
    ]


def render_still(sc, heroes, path, engine):
    import gallery_framing
    import gallery_asset_quality

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = bpy.data.materials.new("Studio")
    fmat.use_nodes = True
    fb = fmat.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.03, 0.032, 0.037, 1.0)
    fb.inputs["Roughness"].default_value = 0.7
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    sc.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 7.5, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    sc.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    sc.world = world

    def light(name, loc, energy, size, col, aim):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        sc.collection.objects.link(ob)

    # shaped warm key, faint cool fill, cool rim, warm wedge on the back wall
    # (docs/VISUAL-STYLE.md)
    light("Key", (-3.5, -4.5, 5.5), 400.0, 4.5, (1.0, 0.96, 0.9), (0, 0, 0.5))
    light("Fill", (4.5, -4.0, 2.2), 90.0, 9.0, (0.75, 0.85, 1.0), (0, 0, 0.5))
    light("Rim", (0.5, 4.0, 4.5), 380.0, 4.0, (0.6, 0.78, 1.0), (0, 0, 0.6))
    light("Wedge", (0.6, 5.2, 0.9), 320.0, 5.0, (1.0, 0.76, 0.5), (0.3, 7.5, 2.4))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -7.6, 2.25)
    sc.collection.objects.link(cam)
    target = bpy.data.objects.new("Aim", None)
    target.location = (0.0, 0.0, 0.58)
    sc.collection.objects.link(target)
    con = cam.constraints.new('TRACK_TO')
    con.target = target
    sc.camera = cam

    sc.render.engine = 'CYCLES' if engine == 'cycles' else eevee_engine_id()
    if engine == 'cycles':
        sc.cycles.samples = 48
    else:
        try:
            sc.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    sc.render.resolution_x = 1280
    sc.render.resolution_y = 720
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = path
    # AgX would wash the hazard paint and venom glow (docs/VISUAL-STYLE.md)
    sc.view_settings.view_transform = 'Standard'
    bpy.context.view_layer.update()

    code = gallery_framing.check_framing(sc, cam, hero=heroes, elements=heroes,
                                         stage=[floor, wall])
    if code:
        return code
    code = gallery_asset_quality.check_asset_quality(sc, cam, hero=heroes[0],
                                                     stage=[floor, wall])
    if code:
        return code
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 20
    return 0


def stage_rig(arm, x, yaw_deg):
    """Place and turn a rig about its own origin, composed into the world
    matrix: the glTF importer leaves its armature in quaternion mode, where
    rotation_euler does nothing."""
    arm.location.x = x
    bpy.context.view_layer.update()
    at = mathutils.Matrix.Translation(arm.matrix_world.translation)
    arm.matrix_world = (at @ mathutils.Matrix.Rotation(math.radians(yaw_deg), 4, 'Z')
                        @ at.inverted() @ arm.matrix_world)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--no-skins", action="store_true",
                   help="export with export_skins=False (must fail)")
    args = p.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj, vw = build_scorpion()
    for m in make_materials():
        obj.data.materials.append(m)
    assign_weights(obj, vw)
    arm = build_rig(obj)
    bpy.context.view_layer.update()
    code = check(obj, arm, no_skins=args.no_skins)
    if code:
        return code

    if args.output:
        # the re-imported rig is still in the file after the check. Drive it
        # into the strike pose through its OWN imported bones; rebuild the
        # authored rig (guard pose, the pose the check compared) to face it.
        roundtrip_mesh = [o for o in bpy.data.objects
                          if o.type == 'MESH' and o.vertex_groups][0]
        roundtrip_arm = [o for o in bpy.data.objects if o.type == 'ARMATURE'][0]
        roundtrip_mesh.name = "ScorpionReimported"
        apply_pose(roundtrip_arm, POSE_STRIKE)
        authored, vw2 = build_scorpion("ScorpionAuthored")
        for m in make_materials():
            authored.data.materials.append(m)
        assign_weights(authored, vw2)
        authored_arm = build_rig(authored)
        # the heads (-Y at rest) turn toward each other and a little toward
        # the camera, so both tails are seen in profile
        stage_rig(authored_arm, -STILL_X, STILL_YAW)
        stage_rig(roundtrip_arm, STILL_X, -STILL_YAW)
        bpy.context.view_layer.update()
        code = render_still(bpy.context.scene, [authored, roundtrip_mesh],
                            os.path.abspath(args.output), args.engine)
        if code:
            return code
        print(f"rendered still {args.output}")

    print("gltf-skin-roundtrip OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
