"""A rigged industrial robot arm pruned to the 4-influence game-engine limit — a runnable example.

Witnesses the skinning constraint every game engine enforces and AI-generated
rigging code most often violates silently: **no more than four bone influences
per vertex, weights summing to one**.

1. The limit is enforced through the data API, not the context-heavy
   ``bpy.ops.object.vertex_group_limit_total`` path: read each vertex's groups,
   keep the top four by weight, ``VertexGroup.remove`` the rest, then
   renormalize the survivors to sum 1. Dropping without renormalizing leaves
   sums < 1 and the mesh shrinks toward the origin under load.
2. The armature modifier is still exactly linear blend skinning (the
   armature-bend precedent — built on, not duplicated): after limiting, every
   depsgraph-evaluated vertex equals sum_i w_i (pose.matrix @
   rest_local.inverted()) @ rest with the weights **read back from the mesh's
   own deform layer** (``v.groups``), not from the authoring function. The
   weights on the mesh are the contract, not the weights you meant to write.
3. Pruning must not damage the pose: evaluated positions before and after the
   limit are compared and held within tolerance. The root stays pinned — the
   floor plinth never moves.

The arm is one skinned mesh, as a game character's would be. Armor, motors,
clevis cheeks, the balancer piston and the gripper are rigid (one bone at
weight 1); the two cable runs along its back are the flex parts: they blend
across every joint and carry an auto-weight-style spill onto all five bones —
the five-influence tail the limit prunes.

The vertex-group API (``v.groups``, ``VertexGroup.add``/``remove``) is stable
between Blender 4.5 LTS and 5.2 — the example runs identically on both, which
is itself the version witness.

``--skip-limit`` leaves the five-influence flex weights in place and still
asserts the engine cap. That is the falsifier (``--same-axis`` in
export-preset-axis).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still, which paints the post-limit
weights onto the mesh as a colour attribute (see ``paint_weight_map``):

    blender --background --python vertex_weight_limit.py --                 # check only
    blender --background --python vertex_weight_limit.py -- --skip-limit    # must fail
    blender --background --python vertex_weight_limit.py -- --output a.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse
import mathutils
from mathutils import Matrix, Vector

# Shared Layer 1 framing + asset-quality measurement (render path only) — see
# gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing
import gallery_asset_quality

SIDES = 40
MAX_INFLUENCES = 4              # the engine constraint being witnessed
SPILL = 0.02                    # auto-weight tail on every bone; guarantees 5 pre-limit
LBS_TOL = 5e-4                  # float32 mesh coords vs double pose matrices
SUM_TOL = 1e-5                  # per-vertex weight sum after renormalize
POSE_TOL = 0.05                 # pruning must not move the pose beyond this
BONES = ("Root", "Shoulder", "Elbow", "Wrist", "Claw")
BONE_SPANS = {"Root": (0.0, 0.85), "Shoulder": (0.85, 2.35),
              "Elbow": (2.35, 3.85), "Wrist": (3.85, 4.20), "Claw": (4.20, 4.62)}
BONE_CENTERS = {b: (s[0] + s[1]) / 2 for b, s in BONE_SPANS.items()}
# rest-z ramps where the flex cables hand over from one bone to the next
JOINT_RAMPS = ((0.92, 1.30), (2.12, 2.58), (3.66, 3.96), (4.22, 4.34))
POSE_DEG = {"Shoulder": -45.0, "Elbow": -60.0, "Wrist": -55.0}
FLEX = "FLEX"
FLEX_ID = len(BONES)

# material slots
PAINT, GUNMETAL, STEEL, RUBBER, WEIGHTMAP = range(5)

# one display colour per bone; the render paints sum_i w_i * colour_i from
# the mesh's own post-limit deform layer
BONE_RGB = {"Root": (0.03, 0.16, 1.00), "Shoulder": (0.00, 0.78, 0.55),
            "Elbow": (0.38, 0.06, 1.00), "Wrist": (1.00, 0.03, 0.30),
            "Claw": (0.45, 1.00, 0.00)}

T = Matrix.Translation
TO_X = Matrix.Rotation(math.radians(90.0), 4, 'Y')     # local Z -> world X
# local (X, Y, Z) -> world (Y, Z, X): side plates drawn in the bend plane
YZX = Matrix(((0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 0.0, 0.0),
              (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)))


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def flex_weights(z):
    """Pre-limit weights for a flex vertex at rest height z.

    A smoothstep hand-over between neighbouring bones across each joint (a
    partition of unity), plus the tail every auto-weighting pass leaves: a
    small, distance-ranked spill onto all five bones. The tail is what puts
    five influences on every cable vertex."""
    t = [smooth((z - a) / (b - a)) for a, b in JOINT_RAMPS]
    w = []
    for k in range(len(BONES)):
        lo = 1.0 if k == 0 else t[k - 1]
        hi = 0.0 if k == len(BONES) - 1 else t[k]
        w.append(lo - hi)
    w = [a + SPILL * math.exp(-abs(z - BONE_CENTERS[b])) for a, b in zip(w, BONES)]
    total = sum(w)
    return [x / total for x in w]


# ---------------------------------------------------------------- primitives

def _bridge(bm, rings):
    for a, b in zip(rings, rings[1:]):
        n = len(a)
        for s in range(n):
            bm.faces.new((a[s], a[(s + 1) % n], b[(s + 1) % n], b[s]))


def _close(bm, rings, cap0, cap1):
    _bridge(bm, rings)
    if cap0:
        bm.faces.new(list(reversed(rings[0])))
    if cap1:
        bm.faces.new(rings[-1])


def lathe(bm, profile, m=Matrix(), sides=SIDES, cap0=True, cap1=True, phase=0.0):
    """Revolve (z, r) stations around local Z, outward-facing, capped."""
    angs = [phase + 2 * math.pi * s / sides for s in range(sides)]
    rings = [[bm.verts.new(m @ Vector((r * math.cos(a), r * math.sin(a), z)))
              for a in angs] for z, r in profile]
    _close(bm, rings, cap0, cap1)


def cyl(bm, r, h, m, sides=SIDES, ch=None):
    """Chamfered cylinder centred on m, along local Z."""
    c = min(r, h) * 0.18 if ch is None else ch
    lathe(bm, [(-h / 2, r - c), (-h / 2 + c, r), (h / 2 - c, r), (h / 2, r - c)],
          m, sides)


def hexbolt(bm, r, h, m):
    lathe(bm, [(0.0, r), (h * 0.7, r), (h, r * 0.72)], m, sides=6,
          phase=math.pi / 6)


def _rrect(hw, hd, k, n=4):
    pts = []
    for cx, cy, a0 in ((hw - k, hd - k, 0), (-(hw - k), hd - k, 90),
                       (-(hw - k), -(hd - k), 180), (hw - k, -(hd - k), 270)):
        for i in range(n + 1):
            a = math.radians(a0 + 90.0 * i / n)
            pts.append((cx + k * math.cos(a), cy + k * math.sin(a)))
    return pts


def loft(bm, stations, m=Matrix()):
    """Rounded-rectangle sections (z, half_w, half_d, corner) lofted along Z."""
    rings = [[bm.verts.new(m @ Vector((x, y, z))) for x, y in _rrect(hw, hd, k)]
             for z, hw, hd, k in stations]
    _close(bm, rings, True, True)


def rbox(bm, half, m=Matrix(), bevel=0.02):
    res = bmesh.ops.create_cube(bm, size=2.0, matrix=m @ Matrix.Diagonal((*half, 1.0)))
    edges = list({e for v in res["verts"] for e in v.link_edges})
    if bevel > 0.0:
        bmesh.ops.bevel(bm, geom=edges, offset=bevel, segments=2, profile=0.5,
                        affect='EDGES', clamp_overlap=True)


def plate(bm, poly, t, m, bevel=0.018):
    """A CCW (x, y) outline extruded along local Z by t, rim edges rounded."""
    lo = [bm.verts.new(m @ Vector((x, y, -t / 2))) for x, y in poly]
    hi = [bm.verts.new(m @ Vector((x, y, t / 2))) for x, y in poly]
    _close(bm, [lo, hi], True, True)
    rim = [e for e in bm.edges if (e.verts[0] in lo and e.verts[1] in lo)
           or (e.verts[0] in hi and e.verts[1] in hi)]
    bmesh.ops.bevel(bm, geom=rim, offset=bevel, segments=2, profile=0.5,
                    affect='EDGES', clamp_overlap=True)


def clevis_outline(radius, drop, n=16):
    """Cheek-plate outline around a joint at the origin: square foot, round head."""
    pts = [(-radius, -drop), (radius, -drop)]
    pts += [(radius * math.cos(math.pi * i / n), radius * math.sin(math.pi * i / n))
            for i in range(n + 1)]
    return pts


def tube(bm, path, r, sides=14):
    """Capped tube along a polyline with parallel-transported frames."""
    rings, nrm = [], None
    for i, p in enumerate(path):
        a, b = path[max(i - 1, 0)], path[min(i + 1, len(path) - 1)]
        t = (b - a).normalized()
        nrm = t.orthogonal() if nrm is None else nrm - t * nrm.dot(t)
        nrm.normalize()
        bi = t.cross(nrm)
        rings.append([bm.verts.new(p + r * (math.cos(2 * math.pi * s / sides) * nrm
                                            + math.sin(2 * math.pi * s / sides) * bi))
                      for s in range(sides)])
    _close(bm, rings, True, True)


def cable_path(x, ctrl, step=0.03, smooth_passes=3):
    """Densely resampled, Laplacian-smoothed (y, z) control polyline at fixed x."""
    pts = []
    for (y0, z0), (y1, z1) in zip(ctrl, ctrl[1:]):
        n = max(1, int(math.hypot(y1 - y0, z1 - z0) / step))
        pts += [Vector((x, y0 + (y1 - y0) * i / n, z0 + (z1 - z0) * i / n))
                for i in range(n)]
    pts.append(Vector((x, *ctrl[-1])))
    for _ in range(smooth_passes):
        pts = [pts[0]] + [(pts[i - 1] + 2 * pts[i] + pts[i + 1]) / 4
                          for i in range(1, len(pts) - 1)] + [pts[-1]]
    return pts


# ---------------------------------------------------------------- the model

class _Kit:
    """Tags every part's vertices with its bone and its faces with a material.

    Parts authored in the *posed* frame (the balancer rod, which must stay
    coaxial with its barrel in the pose) are pulled back to rest through the
    bone's deform matrix, so skinning puts them exactly where they were drawn."""

    def __init__(self, bm, deform):
        self.bm, self.deform = bm, deform
        self.layer = bm.verts.layers.int.new("bone_id")

    def add(self, bone, mat, build, posed=False):
        bm = self.bm
        old_v, old_f = set(bm.verts), set(bm.faces)
        build(bm)
        new_v = [v for v in bm.verts if v not in old_v]
        for f in bm.faces:
            if f not in old_f:
                f.material_index = mat
        if posed:
            bmesh.ops.transform(bm, matrix=self.deform[bone].inverted(), verts=new_v)
        bid = FLEX_ID if bone == FLEX else BONES.index(bone)
        for v in new_v:
            v[self.layer] = bid


def _aim_z(direction):
    return direction.to_track_quat('Z', 'Y').to_matrix().to_4x4()


def _joint_motor(k, bone, z, x0, r, h, cap_r, bolt_r):
    """Servo drum on the +X face of a joint axis: housing, cap, bolt circle."""
    k.add(bone, GUNMETAL, lambda bm: cyl(bm, r, h, T((x0 + h / 2, 0, z)) @ TO_X))
    k.add(bone, STEEL, lambda bm: cyl(bm, cap_r, 0.05,
                                      T((x0 + h + 0.02, 0, z)) @ TO_X))
    for i in range(6):
        a = 2 * math.pi * i / 6
        k.add(bone, STEEL, lambda bm, a=a: hexbolt(
            bm, 0.022, 0.03, T((x0 + h - 0.005, bolt_r * math.cos(a),
                                z + bolt_r * math.sin(a))) @ TO_X))


def _side_panel(k, bone, x, z, half_y, half_z):
    """Framed side hatch (+X and -X); the inset carries the bone's weight colour."""
    for sx in (1, -1):
        k.add(bone, GUNMETAL, lambda bm, sx=sx: rbox(
            bm, (0.012, half_y, half_z), T((sx * x, 0, z)), bevel=0.008))
        k.add(bone, WEIGHTMAP, lambda bm, sx=sx: rbox(
            bm, (0.006, half_y - 0.03, half_z - 0.03),
            T((sx * (x + 0.012), 0, z)), bevel=0.004))


def build_arm(deform):
    """A six-axis-style industrial arm, drawn upright in rest pose.

    Root: bolted floor plinth, turret drum, clevis cheeks, shoulder servo and
    a finned rear drive pack. Shoulder: knuckle, tapered box-section upper
    arm, elbow clevis and servo. Elbow: knuckle and forearm ending in a wrist
    fork. Wrist: knuckle, housing, cable manifold, tool flange. Claw: a
    parallel gripper with padded jaws. A gas-spring balancer spans the
    shoulder; two cables run the arm's back from the drive pack to the wrist."""
    me = bpy.data.meshes.new("MechArm")
    bm = bmesh.new()
    try:
        k = _Kit(bm, deform)
        J1, J2, J3, J4 = (BONE_SPANS[b][1] for b in BONES[:4])

        # ---- Root: plinth, turret, cheeks, shoulder servo, rear drive pack
        k.add("Root", GUNMETAL, lambda bm: lathe(
            bm, [(0.0, 0.84), (0.07, 0.84), (0.10, 0.81), (0.13, 0.70),
                 (0.15, 0.62)], sides=56))
        for i in range(12):
            a = 2 * math.pi * (i + 0.5) / 12
            k.add("Root", STEEL, lambda bm, a=a: hexbolt(
                bm, 0.04, 0.05, T((0.76 * math.cos(a), 0.76 * math.sin(a), 0.095))))
        k.add("Root", PAINT, lambda bm: lathe(
            bm, [(0.13, 0.58), (0.17, 0.62), (0.40, 0.62), (0.45, 0.57),
                 (0.52, 0.46)], sides=56))
        k.add("Root", WEIGHTMAP, lambda bm: lathe(
            bm, [(0.26, 0.615), (0.27, 0.634), (0.32, 0.634), (0.33, 0.615)],
            sides=56))
        k.add("Root", GUNMETAL, lambda bm: lathe(
            bm, [(0.50, 0.47), (0.56, 0.44)], sides=56))
        for sx in (1, -1):
            k.add("Root", PAINT, lambda bm, sx=sx: plate(
                bm, clevis_outline(0.34, 0.36), 0.12, T((sx * 0.38, 0, J1)) @ YZX,
                bevel=0.025))
        _joint_motor(k, "Root", J1, 0.44, 0.27, 0.20, 0.19, 0.23)
        k.add("Root", GUNMETAL, lambda bm: cyl(bm, 0.22, 0.06, T((-0.47, 0, J1)) @ TO_X))
        k.add("Root", GUNMETAL, lambda bm: rbox(
            bm, (0.27, 0.21, 0.17), T((0, -0.60, 0.47)), bevel=0.035))
        for i in range(5):
            k.add("Root", GUNMETAL, lambda bm, i=i: rbox(
                bm, (0.012, 0.05, 0.13), T((-0.20 + 0.10 * i, -0.83, 0.47)),
                bevel=0.006))
        k.add("Root", GUNMETAL, lambda bm: rbox(      # cable gland on the pack
            bm, (0.23, 0.06, 0.035), T((0, -0.45, 0.665)), bevel=0.015))
        a_pt = Vector((0.0, -0.70, 0.72))              # balancer anchor
        k.add("Root", GUNMETAL, lambda bm: rbox(
            bm, (0.06, 0.07, 0.06), T(a_pt - Vector((0, 0, 0.03))), bevel=0.015))
        k.add("Root", STEEL, lambda bm: cyl(bm, 0.03, 0.16, T(a_pt) @ TO_X))

        # ---- Shoulder: knuckle, box-section upper arm, elbow clevis + servo
        k.add("Shoulder", GUNMETAL, lambda bm: cyl(bm, 0.28, 0.62, T((0, 0, J1)) @ TO_X))
        k.add("Shoulder", PAINT, lambda bm: loft(
            bm, [(1.10, 0.24, 0.22, 0.07), (1.35, 0.25, 0.26, 0.09),
                 (1.85, 0.215, 0.225, 0.08), (2.12, 0.19, 0.20, 0.07)]))
        for sx in (1, -1):
            k.add("Shoulder", PAINT, lambda bm, sx=sx: plate(
                bm, clevis_outline(0.24, 0.30), 0.10, T((sx * 0.25, 0, J2)) @ YZX,
                bevel=0.02))
        _joint_motor(k, "Shoulder", J2, 0.30, 0.21, 0.16, 0.15, 0.18)
        k.add("Shoulder", GUNMETAL, lambda bm: cyl(bm, 0.18, 0.05, T((-0.325, 0, J2)) @ TO_X))
        _side_panel(k, "Shoulder", 0.247, 1.62, 0.15, 0.30)
        b_rest = Vector((0.0, -0.36, 1.45))            # balancer lug
        k.add("Shoulder", GUNMETAL, lambda bm: rbox(
            bm, (0.06, 0.09, 0.07), T(b_rest + Vector((0, 0.02, 0))), bevel=0.015))
        k.add("Shoulder", STEEL, lambda bm: cyl(bm, 0.03, 0.16, T(b_rest) @ TO_X))

        # ---- Elbow: knuckle, forearm, wrist fork
        k.add("Elbow", GUNMETAL, lambda bm: cyl(bm, 0.22, 0.39, T((0, 0, J2)) @ TO_X))
        k.add("Elbow", PAINT, lambda bm: loft(
            bm, [(2.55, 0.17, 0.20, 0.07), (2.80, 0.185, 0.21, 0.075),
                 (3.35, 0.16, 0.175, 0.065), (3.72, 0.135, 0.15, 0.055)]))
        for sx in (1, -1):
            k.add("Elbow", PAINT, lambda bm, sx=sx: plate(
                bm, clevis_outline(0.15, 0.22), 0.06, T((sx * 0.16, 0, J3)) @ YZX,
                bevel=0.012))
        _side_panel(k, "Elbow", 0.180, 3.08, 0.13, 0.28)

        # ---- Wrist: knuckle, housing, cable manifold, tool flange
        k.add("Wrist", GUNMETAL, lambda bm: cyl(bm, 0.13, 0.25, T((0, 0, J3)) @ TO_X))
        k.add("Wrist", PAINT, lambda bm: loft(
            bm, [(3.96, 0.12, 0.125, 0.05), (4.06, 0.125, 0.13, 0.05),
                 (4.16, 0.115, 0.12, 0.045)]))
        k.add("Wrist", WEIGHTMAP, lambda bm: loft(
            bm, [(4.03, 0.132, 0.137, 0.05), (4.09, 0.132, 0.137, 0.05)]))
        k.add("Wrist", GUNMETAL, lambda bm: rbox(
            bm, (0.20, 0.05, 0.045), T((0, -0.17, 4.00)), bevel=0.012))
        k.add("Wrist", STEEL, lambda bm: lathe(bm, [(4.15, 0.15), (4.205, 0.15)]))

        # ---- Claw: tool flange and parallel gripper
        k.add("Claw", GUNMETAL, lambda bm: lathe(bm, [(4.20, 0.14), (4.27, 0.14)]))
        for i in range(6):
            a = 2 * math.pi * i / 6
            k.add("Claw", STEEL, lambda bm, a=a: hexbolt(
                bm, 0.015, 0.02, T((0.11 * math.cos(a), 0.11 * math.sin(a), 4.265))))
        # jaws open in the bend plane so both read in profile
        k.add("Claw", GUNMETAL, lambda bm: rbox(bm, (0.10, 0.21, 0.07),
                                                 T((0, 0, 4.34)), bevel=0.02))
        k.add("Claw", WEIGHTMAP, lambda bm: rbox(bm, (0.106, 0.216, 0.014),
                                                  T((0, 0, 4.34)), bevel=0.005))
        for sy in (1, -1):
            k.add("Claw", PAINT, lambda bm, sy=sy: loft(
                bm, [(4.38, 0.075, 0.04, 0.015), (4.62, 0.065, 0.034, 0.012),
                     (4.76, 0.05, 0.026, 0.01)], T((0, sy * 0.15, 0))))
            k.add("Claw", PAINT, lambda bm, sy=sy: rbox(
                bm, (0.05, 0.035, 0.03), T((0, sy * 0.125, 4.74)), bevel=0.01))
            k.add("Claw", RUBBER, lambda bm, sy=sy: rbox(
                bm, (0.05, 0.009, 0.07), T((0, sy * 0.104, 4.60)), bevel=0.004))

        # ---- balancer: barrel on Root, rod on Shoulder, coaxial in the pose
        b_posed = deform["Shoulder"] @ b_rest
        d = b_posed - a_pt
        length, d = d.length, d.normalized()
        k.add("Root", GUNMETAL, lambda bm: cyl(
            bm, 0.065, 0.56, T(a_pt + d * 0.34) @ _aim_z(d)))
        k.add("Root", STEEL, lambda bm: cyl(
            bm, 0.072, 0.04, T(a_pt + d * 0.62) @ _aim_z(d)))
        k.add("Shoulder", STEEL, lambda bm: cyl(
            bm, 0.03, length * 0.62, T(b_posed - d * (0.05 + length * 0.31)) @ _aim_z(d)),
            posed=True)
        k.add("Shoulder", GUNMETAL, lambda bm: cyl(
            bm, 0.045, 0.08, T(b_posed - d * 0.06) @ _aim_z(d)), posed=True)

        # ---- the two flex cables and their clamps (the >4-influence parts)
        ctrl = [(-0.45, 0.60), (-0.45, 0.78), (-0.43, 0.95), (-0.39, 1.12),
                (-0.36, 1.30), (-0.36, 2.35), (-0.34, 2.60), (-0.32, 2.85),
                (-0.28, 3.40), (-0.24, 3.70), (-0.21, 3.90), (-0.20, 4.00)]
        for sx in (1, -1):
            path = cable_path(sx * 0.15, ctrl)
            k.add(FLEX, WEIGHTMAP, lambda bm, path=path: tube(bm, path, 0.042))
        for bone, z, y in (("Shoulder", 1.70, -0.36), ("Shoulder", 2.08, -0.36),
                           ("Elbow", 2.85, -0.32), ("Elbow", 3.40, -0.28)):
            k.add(bone, GUNMETAL, lambda bm, z=z, y=y: rbox(
                bm, (0.19, (abs(y) - 0.15) / 2, 0.018),
                T((0, (y - 0.15) / 2 - 0.0, z)), bevel=0.006))
            for sx in (1, -1):
                k.add(bone, GUNMETAL, lambda bm, z=z, y=y, sx=sx: cyl(
                    bm, 0.058, 0.05, T((sx * 0.15, y, z)), sides=16))
        bm.to_mesh(me)
    finally:
        bm.free()  # the ownership contract, as always
    # smooth the round stock, keep machined edges crisp (no modifier: the
    # evaluated mesh must stay exactly the armature's output)
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(35.0))
    obj = bpy.data.objects.new("MechArm", me)
    bpy.context.collection.objects.link(obj)
    return obj


def assign_weights(obj):
    """Author the rich pre-limit weights from the per-vertex part tags: hard
    single-bone on rigid parts, joint hand-over plus spill on the cables."""
    me = obj.data
    groups = {b: obj.vertex_groups.new(name=b) for b in BONES}
    ids = [0] * len(me.vertices)
    me.attributes["bone_id"].data.foreach_get("value", ids)
    for idx, v in enumerate(me.vertices):
        bid = ids[idx]
        if bid == FLEX_ID:
            for b, w in zip(BONES, flex_weights(v.co.z)):
                if w > 0.0:
                    groups[b].add([idx], w, 'REPLACE')
        else:
            groups[BONES[bid]].add([idx], 1.0, 'REPLACE')
    me.attributes.remove(me.attributes["bone_id"])
    return groups


def build_rig():
    arm_data = bpy.data.armatures.new("ArmRig")
    arm = bpy.data.objects.new("ArmRig", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    prev = None
    for name in BONES:
        eb = arm_data.edit_bones.new(name)
        z0, z1 = BONE_SPANS[name]
        eb.head = (0.0, 0.0, z0)
        eb.tail = (0.0, 0.0, z1)
        if prev is not None:
            eb.parent = prev
            eb.use_connect = True
        prev = eb
    bpy.ops.object.mode_set(mode='OBJECT')
    for name, deg in POSE_DEG.items():
        pb = arm.pose.bones[name]
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler.x = math.radians(deg)
    bpy.context.view_layer.update()
    return arm


def deform_matrices(arm):
    return {n: arm.pose.bones[n].matrix @ arm.data.bones[n].matrix_local.inverted()
            for n in BONES}


def bind(obj, arm):
    mod = obj.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm
    mod.use_vertex_groups = True
    mod.use_bone_envelopes = False


def eval_positions(obj):
    """Evaluated vertex positions via the depsgraph; reference released by contract."""
    deps = bpy.context.evaluated_depsgraph_get()
    ob_eval = obj.evaluated_get(deps)
    me = ob_eval.to_mesh()
    try:
        return [tuple(v.co) for v in me.vertices]
    finally:
        ob_eval.to_mesh_clear()


def check(obj, arm, groups, pose_before, skip_limit=False):
    me = obj.data

    # pre-limit witness: the flex cables really carry five influences
    pre_max = max(len(v.groups) for v in me.vertices)
    if pre_max != 5:
        print(f"ERROR: pre-limit max influences {pre_max} != 5 — the rich "
              "authoring drifted; the witness is vacuous", file=sys.stderr)
        return 3

    # the limit, through the data API: keep top-4, drop the rest, renormalize
    changed = 0
    if not skip_limit:
        for v in me.vertices:
            gs = sorted(v.groups, key=lambda g: -g.weight)
            if len(gs) > MAX_INFLUENCES:
                changed += 1
            for g in gs[MAX_INFLUENCES:]:
                groups[BONES[g.group]].remove([v.index])
            kept = [g for g in v.groups]
            total = sum(g.weight for g in kept)
            for g in kept:
                groups[BONES[g.group]].add([v.index], g.weight / total, 'REPLACE')

    # contract 1: no vertex exceeds the engine limit
    post_max = max(len(v.groups) for v in me.vertices)
    if post_max > MAX_INFLUENCES:
        print(f"ERROR: vertex carries {post_max} groups after the limit — "
              f"engines cap at {MAX_INFLUENCES}", file=sys.stderr)
        return 4
    if changed == 0:
        print("ERROR: the limit changed nothing — no vertex exceeded the cap, "
              "the witness is vacuous", file=sys.stderr)
        return 5

    # contract 2: every vertex's weights sum to 1 (or the vertex is unskinned)
    sum_err = 0.0
    for v in me.vertices:
        if v.groups:
            sum_err = max(sum_err, abs(sum(g.weight for g in v.groups) - 1.0))
    if sum_err > SUM_TOL:
        print(f"ERROR: weight sums deviate {sum_err:.3e} from 1.0 after "
              "renormalize (dropped groups were not re-balanced)", file=sys.stderr)
        return 6

    bpy.context.view_layer.update()
    pose_after = eval_positions(obj)

    # contract 3: pruning did not damage the pose
    # zip() would truncate if the prune changed the evaluated vertex count,
    # comparing only the shared prefix and reporting a clean deviation.
    if len(pose_after) != len(pose_before) or not pose_before:
        print(f"ERROR: evaluated vertex count changed across the prune "
              f"({len(pose_before)} -> {len(pose_after)}) - the pose "
              f"comparison would only cover the shared prefix", file=sys.stderr)
        return 7
    pose_dev = max((mathutils.Vector(a) - mathutils.Vector(b)).length
                   for a, b in zip(pose_before, pose_after))
    if pose_dev > POSE_TOL:
        print(f"ERROR: limiting moved the pose by {pose_dev:.4f} "
              f"(tol {POSE_TOL}) — pruning damaged deformation", file=sys.stderr)
        return 7

    # contract 4: the modifier is still exactly LBS, with the weights read
    # back from the mesh's own deform layer (armature-bend's math, built on)
    mats = deform_matrices(arm)
    lbs_err = 0.0
    for v in me.vertices:
        predicted = sum((g.weight * (mats[BONES[g.group]] @ v.co)
                         for g in v.groups),
                        start=mathutils.Vector((0.0, 0.0, 0.0)))
        lbs_err = max(lbs_err, (mathutils.Vector(pose_after[v.index])
                                - predicted).length)
    if lbs_err > LBS_TOL:
        print(f"ERROR: evaluated mesh deviates {lbs_err:.6f} from LBS over the "
              f"limited weights (tol {LBS_TOL})", file=sys.stderr)
        return 8

    # the floor plinth is rigid on Root and must not move
    root_move = max((mathutils.Vector(pose_after[i]) - v.co).length
                    for i, v in enumerate(me.vertices)
                    if len(v.groups) == 1 and v.groups[0].weight > 0.99
                    and BONES[v.groups[0].group] == "Root")
    if root_move > 1e-5:
        print(f"ERROR: Root-weighted mount moved {root_move:.6f} (Root is unposed)",
              file=sys.stderr)
        return 9

    print(f"verts={len(me.vertices)} pre_max={pre_max} post_max={post_max} "
          f"limited_verts={changed}")
    print(f"sum_err={sum_err:.2e} (tol {SUM_TOL}) pose_dev={pose_dev:.2e} "
          f"(tol {POSE_TOL}) lbs_err={lbs_err:.2e} (tol {LBS_TOL}) "
          f"root_move={root_move:.2e}")
    return 0


def paint_weight_map(obj):
    """Render path only: paint sum_i w_i * colour_i per vertex, reading the
    weights back from the mesh's own post-limit deform layer. Rigid parts
    come out in their bone's flat colour; the cables grade across joints."""
    me = obj.data
    attr = me.color_attributes.new("BoneBlend", 'FLOAT_COLOR', 'POINT')
    cols = []
    for v in me.vertices:
        c = [0.0, 0.0, 0.0]
        for g in v.groups:
            rgb = BONE_RGB[BONES[g.group]]
            for i in range(3):
                c[i] += g.weight * rgb[i]
        cols.extend((*c, 1.0))
    attr.data.foreach_set("color", cols)


def make_materials():
    def pbr(name, base, metallic, roughness):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        b = mat.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*base, 1.0)
        b.inputs["Metallic"].default_value = metallic
        b.inputs["Roughness"].default_value = roughness
        return mat

    weight = bpy.data.materials.new("WeightMap")
    weight.use_nodes = True
    nt = weight.node_tree
    b = nt.nodes["Principled BSDF"]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "BoneBlend"
    nt.links.new(attr.outputs["Color"], b.inputs["Base Color"])
    emit = b.inputs.get("Emission Color") or b.inputs["Emission"]
    nt.links.new(attr.outputs["Color"], emit)
    b.inputs["Emission Strength"].default_value = 0.55
    b.inputs["Roughness"].default_value = 0.75
    # flat colour data goes fully matte (docs/VISUAL-STYLE.md)
    spec = b.inputs.get("Specular IOR Level")
    if spec is not None:
        spec.default_value = 0.0
    return [
        pbr("HazardOrange", (0.80, 0.25, 0.035), 0.05, 0.40),
        pbr("Gunmetal", (0.10, 0.11, 0.125), 0.80, 0.42),
        pbr("MachinedSteel", (0.56, 0.57, 0.60), 1.0, 0.24),
        pbr("GripRubber", (0.015, 0.015, 0.018), 0.0, 0.85),
        weight,
    ]


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(obj, arm, path, engine):
    scene = bpy.context.scene
    paint_weight_map(obj)
    # turn the whole rig so the reach runs left to right across the frame;
    # mesh and armature turn together, so the deformation is unchanged
    for ob in (obj, arm):
        ob.rotation_euler.z = math.radians(-90.0)
    bpy.context.view_layer.update()

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
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 8.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    # shaped warm key, faint cool fill, cool rim, warm wedge on the back wall
    # (docs/VISUAL-STYLE.md)
    light("Key", (-3.0, -5.0, 6.0), 650.0, 4.5, (1.0, 0.96, 0.9), (45, 0, -32))
    light("Fill", (6.0, -4.0, 2.5), 110.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 55))
    light("Rim", (1.5, 4.0, 5.0), 350.0, 4.0, (0.6, 0.78, 1.0), (-55, 0, 180))
    light("Wedge", (1.5, 4.5, 4.0), 480.0, 6.0, (1.0, 0.76, 0.5), (-72, 0, 190))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.36, -7.15, 2.75)
    scene.collection.objects.link(cam)
    target = bpy.data.objects.new("Aim", None)
    target.location = (1.05, 0.0, 0.98)
    scene.collection.objects.link(target)
    con = cam.constraints.new('TRACK_TO')
    con.target = target
    scene.camera = cam

    scene.render.engine = 'CYCLES' if engine == 'cycles' else eevee_engine_id()
    if engine == 'cycles':
        scene.cycles.samples = 32
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path
    # AgX would wash the hazard orange and the weight colours toward pastel
    # (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation, before
    # the beauty render so a defective composition ships no artifact.
    fcode = gallery_framing.check_framing(
        scene, cam,
        hero=[obj],
        elements=[obj],
        stage=[floor, wall],
    )
    if fcode:
        return fcode
    aqcode = gallery_asset_quality.check_asset_quality(
        scene, cam, hero=[obj], stage=[floor, wall])
    if aqcode:
        return aqcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 10
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--skip-limit", action="store_true",
                   help="skip the 4-influence prune (must fail)")
    args = p.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm = build_rig()
    obj = build_arm(deform_matrices(arm))
    for m in make_materials():
        obj.data.materials.append(m)
    groups = assign_weights(obj)
    bind(obj, arm)
    bpy.context.view_layer.update()
    pose_before = eval_positions(obj)
    code = check(obj, arm, groups, pose_before, skip_limit=args.skip_limit)
    if code:
        return code

    if args.output:
        rcode = render_still(obj, arm, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("vertex-weight-limit OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
