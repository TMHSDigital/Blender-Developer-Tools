"""Socket attach points — named empties parented into an asset as spawn mounts.

Witnesses the contract a spawn system depends on when it bolts modules onto a
prop at runtime: an attachment placed at socket S with an identity local
transform must land exactly where the artist authored the socket, oriented the
way the naming convention promises. Everything in that sentence is a matrix
identity, and every one of them can silently drift — a skipped
``matrix_parent_inverse``, a basis built with the cross product the wrong way
round, a transform applied on the parent after the sockets were placed.

The asset is a survey drone chassis with seven sockets: four canted rotor
mounts, a belly camera mount, a dorsal mast mount, and a rear battery mount.
Sockets are authored in WORLD space (where an artist actually places them) and
then parented to the chassis root, which is itself posed at a non-trivial world
transform — so the parent-inverse is load-bearing rather than incidentally
identity.

Socket convention, encoded in the name prefix ``SKT_``:

    +Z  the outward mount normal — the direction the module grows away from
        the hull, matching the mount pad's own face normal
    +Y  the module's up reference: chassis +Z orthogonalised against +Z_socket,
        falling back to chassis +X when the normal is parallel to chassis up
    +X  Y x Z, so the basis is right-handed (det == +1)

Check (all closed form or independently re-derived, nothing captured):

1. Socket matrices (exit 3): every evaluated ``matrix_world`` equals the
   authored world transform within 1e-6, and every basis is orthonormal
   right-handed (det == +1, Gram error ~0).
2. Orientation vs geometry (exit 4): each socket's world +Z equals the Newell
   normal of its mount pad's mount face, computed from mesh vertex coordinates
   by a construction path (quaternion swing from +Z) independent of the socket
   basis (explicit Gram-Schmidt); the origin sits on that face's centroid; the
   up axis follows the documented fallback rule.
3. Seating (exit 5): each module, parented to its socket with an identity local
   transform, puts its mount origin exactly on the socket origin and its own
   mount axis exactly on the socket +Z (dot == 1 within 1e-6).
4. Reuse hygiene (exit 6): identity object scales, ``Drone.Survey.*`` /
   ``SKT_*`` names, no default datablock names, chassis resting on z == 0.
5. Rigid invariance (exit 7): re-posing the chassis root to an arbitrary
   transform moves every socket to ``root.matrix_world @ authored_local``
   within 1e-6, and every module follows its socket.
6. Transform apply (exit 8): applying loc/rot/scale on the chassis root leaves
   every socket's world matrix unchanged within 1e-6 — but, because the root is
   an Empty with no data to bake into, Blender pushes the transform DOWN into
   the children: every ``matrix_parent_inverse`` is cleared to identity and
   every child picks up the root's scale locally. Both halves are asserted, so
   the hazard cannot silently change under us.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python socket_attach_points.py --                  # check
    blender --background --python socket_attach_points.py -- --output d.png   # + render
    blender --background --python socket_attach_points.py -- --falsify f.png  # no-MPI variant
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector, Matrix

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing
import gallery_asset_quality

TOL = 1e-6            # matrix / position tolerance (metres, unitless for axes)
                      # float32 noise on a 4x4 world matrix measures ~3.6e-07 here
ORTHO_TOL = 1e-6      # orthonormality + handedness tolerance
PARALLEL = 0.999      # |n . chassis_up| above this takes the +X up-axis fallback

CHASSIS_UP = Vector((0.0, 0.0, 1.0))       # chassis local up
CHASSIS_FWD = Vector((1.0, 0.0, 0.0))      # chassis local forward

# Chassis geometry, metres. Origin is the skid contact plane centre: z == 0 is
# where the drone rests, +X is forward. An 0.86 m span survey quadcopter.
HULL_Z = 0.152            # fuselage centreline height above the skid plane
DECK_Z = 0.214            # top of the fuselage
BELLY_Z = 0.090           # bottom of the fuselage
ARM_YAW = math.radians(41.0)
ARM_LEN = 0.430           # hub centre -> rotor pad centre, horizontal
ARM_RISE = 0.053          # rotor pads sit this far above the centreline
ROTOR_CANT = math.radians(8.0)   # rotor pads cant outward: NOT axis aligned
PAD_T = 0.014             # mount pad plate thickness

# Chassis root pose in the scene: translated, yawed and banked, so the sockets'
# parent-inverse is load-bearing rather than incidentally identity.
ROOT_LOC = (0.240, -0.130, 0.470)
ROOT_ROT = (math.radians(-7.0), math.radians(5.0), math.radians(24.0))

# Re-pose used by check 5 (rigid invariance) — a second arbitrary transform.
REPOSE_LOC = (-1.150, 0.820, 0.315)
REPOSE_ROT = (math.radians(13.0), math.radians(-21.0), math.radians(-64.0))

# Transform-apply pose used by check 6: a uniform scale, so applying it is a
# real change to the object transform rather than a no-op.
APPLY_SCALE = 1.35


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


# ---------------------------------------------------------------------------
# Socket specification (authored, chassis-local)
# ---------------------------------------------------------------------------

def rotor_dirs():
    """Horizontal outward directions of the four arms, front-left first."""
    out = []
    for tag, sx, sy in (("FL", 1, 1), ("FR", 1, -1), ("RL", -1, 1), ("RR", -1, -1)):
        yaw = sy * (ARM_YAW if sx > 0 else math.pi - ARM_YAW)
        out.append((tag, Vector((math.cos(yaw), math.sin(yaw), 0.0))))
    return out


def socket_spec():
    """[(socket_name, pad_name, centre, normal, pad_radius)], chassis-local.

    The normal is the declared mount direction. The pad MESH is built from it
    by a quaternion swing from +Z; the socket BASIS is built from it by
    explicit Gram-Schmidt. Check 2 compares the two independent derivations.
    """
    spec = []
    for tag, d in rotor_dirs():
        # canted outward: the rotor discs tilt away from the hull, so no rotor
        # socket is axis aligned and a "just use +Z" spawn breaks visibly
        n = (CHASSIS_UP * math.cos(ROTOR_CANT) + d * math.sin(ROTOR_CANT)).normalized()
        centre = d * ARM_LEN + Vector((0.0, 0.0, HULL_Z + ARM_RISE))
        spec.append((f"SKT_Rotor.{tag}", f"Pad.Rotor.{tag}", centre, n, 0.047))
    # belly camera mount: normal is -Z, exactly antiparallel to chassis up ->
    # exercises the +X up-axis fallback
    spec.append(("SKT_Camera", "Pad.Camera",
                 Vector((0.062, 0.0, BELLY_Z)), Vector((0.0, 0.0, -1.0)), 0.040))
    # dorsal mast mount: normal is +Z, parallel to chassis up -> fallback again
    spec.append(("SKT_Mast", "Pad.Mast",
                 Vector((-0.130, 0.0, DECK_Z)), Vector((0.0, 0.0, 1.0)), 0.034))
    # rear battery mount: rearward and tilted down, a fully general normal
    spec.append(("SKT_Battery", "Pad.Battery",
                 Vector((-0.286, 0.0, 0.146)),
                 Vector((-1.0, 0.0, -0.26)).normalized(), 0.042))
    return spec


def socket_basis(normal):
    """The documented convention, by explicit Gram-Schmidt. Returns a 3x3."""
    z = Vector(normal).normalized()
    ref = CHASSIS_FWD if abs(z.dot(CHASSIS_UP)) > PARALLEL else CHASSIS_UP
    y = (ref - z * ref.dot(z)).normalized()
    x = y.cross(z)                       # x cross y == z, so this is right-handed
    return Matrix((x, y, z)).transposed()


def authored_local(centre, normal):
    """The socket's authored chassis-local 4x4."""
    m = socket_basis(normal).to_4x4()
    m.translation = Vector(centre)
    return m


# ---------------------------------------------------------------------------
# Mesh construction
#
# Parts are assembled from primitive groups, each tagged with a material slot
# name. Slot indices are written onto the bmesh faces before to_mesh, so
# accents (lens glass, nav lights, pad rings) are per-face assignments inside
# one object rather than extra objects — the same technique
# custom-normals-shade and lod-decimate-chain use for their accents.
# ---------------------------------------------------------------------------

class Part:
    """A bmesh under construction with named material slots."""

    def __init__(self):
        self.bm = bmesh.new()
        self.slots = []            # slot name per material index, in order

    def slot(self, name):
        if name not in self.slots:
            self.slots.append(name)
        return self.slots.index(name)

    def group(self, slot_name, fn):
        """Run fn(bm), then tag everything it created with slot_name."""
        before = set(self.bm.faces)
        fn(self.bm)
        idx = self.slot(slot_name)
        for f in self.bm.faces:
            if f not in before:
                f.material_index = idx
        return self

    def finish(self, name):
        me = bpy.data.meshes.new(name)
        try:
            # HAZARD: bm.normal_update() recomputes normals from the EXISTING
            # winding — it does not fix a face built the wrong way round. The
            # lofted fuselage below winds its side quads inward, which renders
            # as a flat unshaded white panel rather than an obvious hole.
            # recalc_face_normals makes each shell outward-consistent; it runs
            # per connected shell, so the intersecting sub-solids in one Part
            # are each fixed independently.
            bmesh.ops.recalc_face_normals(self.bm, faces=list(self.bm.faces))
            self.bm.normal_update()
            self.bm.to_mesh(me)
        finally:
            self.bm.free()
        me["slots"] = self.slots      # material slot order, read by the renderer
        return me


def _box(bm, dims, centre, bevel=0.0, segments=2, rot=None):
    before = set(bm.verts)
    bmesh.ops.create_cube(bm, size=1.0)
    made = [v for v in bm.verts if v not in before]
    for v in made:
        c = Vector((v.co.x * dims[0], v.co.y * dims[1], v.co.z * dims[2]))
        if rot is not None:
            c = rot @ c
        v.co = c + Vector(centre)
    if bevel > 0.0:
        edges = [e for e in bm.edges if all(v in made for v in e.verts)]
        bmesh.ops.bevel(bm, geom=edges, offset=bevel, segments=segments,
                        profile=0.5, affect="EDGES", clamp_overlap=True)


def _prism(bm, sides, radius, half_h, centre, stretch=1.0, bevel=0.0, rot=None,
           taper=1.0):
    """An n-gon prism along local Z, optionally tapered toward +Z."""
    before = set(bm.verts)
    ring = []
    for i in range(sides):
        a = 2.0 * math.pi * i / sides + math.pi / sides
        ring.append((math.cos(a) * radius * stretch, math.sin(a) * radius))
    top = [bm.verts.new((x * taper, y * taper, half_h)) for x, y in ring]
    bot = [bm.verts.new((x, y, -half_h)) for x, y in ring]
    bm.faces.new(top)
    bm.faces.new(list(reversed(bot)))
    for i in range(sides):
        j = (i + 1) % sides
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    made = [v for v in bm.verts if v not in before]
    for v in made:
        c = Vector(v.co)
        if rot is not None:
            c = rot @ c
        v.co = c + Vector(centre)
    if bevel > 0.0:
        edges = [e for e in bm.edges if all(v in made for v in e.verts)]
        bmesh.ops.bevel(bm, geom=edges, offset=bevel, segments=2,
                        profile=0.7, affect="EDGES", clamp_overlap=True)


def _rounded_ring(half_w, half_h, z_c, corner):
    """Rounded-rectangle cross-section in (y, z), CCW seen from +X."""
    hw, hh, k = half_w, half_h, corner
    return [(-hw, z_c - hh + k), (-hw, z_c + hh - k), (-hw + k, z_c + hh),
            (hw - k, z_c + hh), (hw, z_c + hh - k), (hw, z_c - hh + k),
            (hw - k, z_c - hh), (-hw + k, z_c - hh)]


def _loft(bm, stations, bevel=0.0):
    """Loft rounded-rect cross-sections along X. stations: (x, hw, zc, hh, k)."""
    before = set(bm.verts)
    rings = []
    for x, hw, zc, hh, k in stations:
        rings.append([bm.verts.new((x, y, z)) for y, z in
                      _rounded_ring(hw, hh, zc, k)])
    n = len(rings[0])
    for a, b in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(list(reversed(rings[0])))       # rear cap
    bm.faces.new(rings[-1])                      # nose cap
    if bevel > 0.0:
        made = [v for v in bm.verts if v not in before]
        edges = [e for e in bm.edges if all(v in made for v in e.verts)]
        bmesh.ops.bevel(bm, geom=edges, offset=bevel, segments=2,
                        profile=0.6, affect="EDGES", clamp_overlap=True)


def _blade(bm, length, root_chord, tip_chord, thick, twist_deg, yaw, z0):
    """A tapered, twisted rotor blade: four stations lofted tip-ward.

    A rotor blade is an aerofoil, not a plank — chord tapers, the section
    twists toward the tip, and the trailing edge is thinner than the leading
    edge. Modelled here because a plank reads as programmer art at any
    lighting.
    """
    yawm = Matrix.Rotation(yaw, 3, "Z")
    fr = [0.0, 0.38, 0.76, 1.0]
    rings = []
    for f in fr:
        chord = root_chord + (tip_chord - root_chord) * f
        t = thick * (1.0 - 0.55 * f)
        tw = math.radians(twist_deg * (1.0 - f))
        r = length * (0.14 + 0.86 * f)
        sec = []
        # 6-point aerofoil-ish section in (chordwise, thickness)
        for cx, cz in ((-0.5, 0.0), (-0.18, 0.62), (0.22, 0.48),
                       (0.5, 0.0), (0.22, -0.30), (-0.18, -0.42)):
            p = Vector((cx * chord, 0.0, cz * t))
            p = Matrix.Rotation(tw, 3, "Y") @ p
            sec.append(yawm @ Vector((p.x + 0.0, r, p.z)) + Vector((0, 0, z0)))
        rings.append([bm.verts.new(tuple(v)) for v in sec])
    n = len(rings[0])
    for a, b in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


MOUNT_FACE_SIDES = 12    # the mount face is a 12-gon; polygon index 0 by build order


def build_pad(name, centre, normal, radius, thick=PAD_T):
    """A mount pad plate whose MOUNT FACE IS POLYGON 0.

    Construction path: a flat ring in the XY plane swung onto ``normal`` by
    ``Vector((0,0,1)).rotation_difference(normal)``. This never calls
    ``socket_basis``, so check 2's Newell-vs-socket comparison is a comparison
    of two independent derivations of the same declared normal, not a tautology.

    The pad is authored FIRST in the part so its mount face is polygon 0; the
    collar detail below it is added afterwards and never disturbs that index.
    """
    n = Vector(normal).normalized()
    swing = Vector((0.0, 0.0, 1.0)).rotation_difference(n)
    part = Part()

    def plate(bm):
        top, bot = [], []
        for i in range(MOUNT_FACE_SIDES):
            a = 2.0 * math.pi * i / MOUNT_FACE_SIDES
            p = Vector((math.cos(a) * radius, math.sin(a) * radius, 0.0))
            top.append(bm.verts.new(swing @ p + Vector(centre)))
            bot.append(bm.verts.new(swing @ (p * 0.86 - Vector((0, 0, thick)))
                                    + Vector(centre)))
        bm.faces.new(top)                        # polygon 0 == the mount face
        bm.faces.new(list(reversed(bot)))
        for i in range(MOUNT_FACE_SIDES):
            j = (i + 1) % MOUNT_FACE_SIDES
            bm.faces.new((bot[i], bot[j], top[j], top[i]))

    part.group("SocketPad", plate)

    def collar(bm):
        # four fixing bosses around the pad: where a mount plate actually bolts
        for i in range(4):
            a = math.pi / 4 + i * math.pi / 2
            p = Vector((math.cos(a), math.sin(a), 0.0)) * radius * 0.70
            _prism(bm, 6, radius * 0.16, thick * 0.62,
                   tuple(swing @ (p - Vector((0, 0, thick * 0.40)))
                         + Vector(centre)),
                   rot=swing.to_matrix())

    part.group("Fixing", collar)
    return part.finish(name)


def newell_normal(me, poly_index=0):
    """Area-weighted normal of one polygon straight from vertex coordinates.

    Newell's method: independent of ``Mesh.polygons[i].normal`` (which Blender
    computes for us) and independent of the pad's construction quaternion.
    """
    poly = me.polygons[poly_index]
    co = [Vector(me.vertices[i].co) for i in poly.vertices]
    n = Vector((0.0, 0.0, 0.0))
    for i, a in enumerate(co):
        b = co[(i + 1) % len(co)]
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    return n.normalized()


def polygon_centroid(me, poly_index=0):
    poly = me.polygons[poly_index]
    c = Vector((0.0, 0.0, 0.0))
    for i in poly.vertices:
        c += Vector(me.vertices[i].co)
    return c / len(poly.vertices)


# Fuselage cross-sections: (x, half_width, centre_z, half_height, corner).
HULL_STATIONS = [
    (-0.280, 0.062, 0.152, 0.036, 0.018),
    (-0.215, 0.122, 0.152, 0.058, 0.026),
    (-0.060, 0.150, 0.152, 0.062, 0.030),
    (0.090, 0.144, 0.151, 0.059, 0.030),
    (0.205, 0.108, 0.147, 0.046, 0.024),
    (0.286, 0.052, 0.142, 0.026, 0.013),
]


def build_chassis_meshes():
    """Every chassis part, keyed by suffix. Chassis-local space."""
    meshes = {}

    # --- fuselage: lofted body + deck plate + canopy face + intake louvres ---
    hull = Part()
    hull.group("Carbon", lambda bm: _loft(bm, HULL_STATIONS, bevel=0.006))
    hull.group("Deck", lambda bm: _box(bm, (0.250, 0.176, 0.012),
                                       (-0.050, 0.0, DECK_Z + 0.002), bevel=0.004))
    # forward canopy: the sensor face, angled down toward the nose
    hull.group("Canopy", lambda bm: _box(
        bm, (0.118, 0.150, 0.010), (0.176, 0.0, 0.186), bevel=0.004,
        rot=Matrix.Rotation(math.radians(24.0), 3, "Y")))
    def louvres(bm):
        for i in range(4):
            _box(bm, (0.020, 0.104, 0.007), (-0.140 + i * 0.030, 0.0, DECK_Z + 0.010),
                 bevel=0.002, rot=Matrix.Rotation(math.radians(-18.0), 3, "Y"))
    hull.group("Vent", louvres)
    def flank(bm):
        # proud of the skin, not flush with it: at y == +/-0.150 the strip was
        # coplanar with the fuselage side and z-fought into a speckled band
        for sy in (1.0, -1.0):
            _box(bm, (0.196, 0.016, 0.030), (0.010, sy * 0.156, 0.150), bevel=0.005)
    hull.group("Trim", flank)
    meshes["Hull"] = hull.finish("Drone.Survey.Hull")

    # --- arms: tapered booms with a hull-side fairing and a motor can --------
    for tag, d in rotor_dirs():
        yaw = math.atan2(d.y, d.x)
        rot = (Matrix.Rotation(yaw, 3, "Z")
               @ Matrix.Rotation(math.radians(-4.0), 3, "Y"))
        arm = Part()
        mid = d * (ARM_LEN * 0.56) + Vector((0.0, 0.0, HULL_Z + ARM_RISE * 0.42))
        arm.group("Boom", lambda bm, r=rot, m=mid: _box(
            bm, (ARM_LEN * 0.80, 0.042, 0.030), tuple(m), bevel=0.010, rot=r))
        # the fairing is deliberately NOT coplanar with the boom's flat sides:
        # at r=0.046/half=0.052 two facets landed on the boom faces and
        # z-fought into a speckled patch at render scale
        root = d * 0.142 + Vector((0.0, 0.0, HULL_Z + 0.004))
        arm.group("Fairing", lambda bm, r=rot, m=root: _prism(
            bm, 10, 0.053, 0.044, tuple(m), bevel=0.010, taper=0.52,
            rot=r @ Matrix.Rotation(math.radians(90.0), 3, "Y")))
        hub = d * ARM_LEN + Vector((0.0, 0.0, HULL_Z + ARM_RISE - 0.032))
        arm.group("Motor", lambda bm, h=hub: _prism(
            bm, 12, 0.036, 0.028, tuple(h), bevel=0.005))
        def fins(bm, h=hub):
            for i in range(8):
                a = i * math.pi / 4
                p = Vector((math.cos(a), math.sin(a), 0.0)) * 0.036
                _box(bm, (0.008, 0.010, 0.040), tuple(Vector(h) + p),
                     bevel=0.0015, rot=Matrix.Rotation(a, 3, "Z"))
        arm.group("MotorFin", fins)
        # navigation light: front arms green-white, rear arms red
        nav = "NavFwd" if tag.startswith("F") else "NavAft"
        arm.group(nav, lambda bm, dd=d: _prism(
            bm, 8, 0.011, 0.006,
            tuple(dd * (ARM_LEN + 0.030) + Vector((0.0, 0.0, HULL_Z + ARM_RISE - 0.038))),
            bevel=0.002))
        meshes[f"Arm.{tag}"] = arm.finish(f"Drone.Survey.Arm.{tag}")

    # --- landing gear: two skid rails on splayed struts ----------------------
    for side, sy in (("L", 1.0), ("R", -1.0)):
        y = sy * 0.158
        gear = Part()
        # bevel offset must stay well under half the octagon's edge length
        # (2 * r * sin(22.5 deg) = 9.9 mm here): at offset == min_dim/2 the
        # band collapses to zero-area faces, the failure degenerate-bevel-weld
        # witnesses. 5 mm produced 3 zero-area faces per rail; 2.2 mm is clean.
        gear.group("Skid", lambda bm, yy=y: _prism(
            bm, 8, 0.013, 0.185, (0.0, yy, 0.013), bevel=0.0022,
            rot=Matrix.Rotation(math.radians(90.0), 3, "Y")))
        def feet(bm, yy=y):
            for xx in (0.150, -0.150):
                _prism(bm, 8, 0.017, 0.008, (xx, yy, 0.008), bevel=0.003)
        gear.group("Foot", feet)
        def struts(bm, yy=y):
            for xx in (0.112, -0.116):
                _box(bm, (0.026, 0.024, 0.082), (xx, yy * 0.78, 0.055),
                     bevel=0.006,
                     rot=Matrix.Rotation(math.radians(12.0) * (1 if yy > 0 else -1),
                                         3, "X"))
            # shoulder block where the strut meets the fuselage: without it the
            # rails read as detached rods floating under the airframe (draft 3)
            for xx in (0.112, -0.116):
                _box(bm, (0.044, 0.038, 0.022), (xx, yy * 0.62, 0.096), bevel=0.006)
        gear.group("Strut", struts)
        meshes[f"Gear.{side}"] = gear.finish(f"Drone.Survey.Gear.{side}")

    # --- mount pads, one per socket ------------------------------------------
    for skt_name, pad_name, centre, normal, radius in socket_spec():
        meshes[pad_name] = build_pad(f"Drone.Survey.{pad_name}", centre, normal,
                                     radius)
    return meshes


# Module (attachment) geometry, authored in MOUNT SPACE: origin at the mount
# point, +Z growing away from the mount surface, +Y the module's up. Parented
# to a socket with an identity local transform, a module seats by construction.
def build_module_meshes():
    out = {}

    rotor = Part()
    rotor.group("Hub", lambda bm: _prism(bm, 12, 0.028, 0.016, (0, 0, 0.016),
                                         bevel=0.005, taper=0.82))
    rotor.group("Spinner", lambda bm: _prism(bm, 10, 0.015, 0.014, (0, 0, 0.043),
                                             bevel=0.006, taper=0.35))
    def blades(bm):
        for k in range(2):
            _blade(bm, length=0.200, root_chord=0.058, tip_chord=0.032,
                   thick=0.0115, twist_deg=15.0,
                   yaw=math.pi * k + math.radians(5.0), z0=0.029)
    rotor.group("Blade", blades)
    out["Mod.Rotor"] = rotor.finish("Drone.Survey.Mod.Rotor")

    cam = Part()
    cam.group("PodYoke", lambda bm: _prism(bm, 8, 0.032, 0.018, (0, 0, 0.018),
                                           bevel=0.006, taper=0.78))
    cam.group("PodBall", lambda bm: _prism(bm, 14, 0.041, 0.034, (0, 0, 0.070),
                                           bevel=0.016))
    # lens barrel points forward: in the belly socket's frame +X is chassis aft,
    # so the barrel runs along -X. Glass is its own slot, the only emitter.
    cam.group("LensRing", lambda bm: _prism(
        bm, 14, 0.023, 0.024, (-0.038, 0.0, 0.072), bevel=0.005, taper=0.88,
        rot=Matrix.Rotation(math.radians(-90.0), 3, "Y")))
    cam.group("LensGlass", lambda bm: _prism(
        bm, 14, 0.016, 0.004, (-0.062, 0.0, 0.072), bevel=0.0008,
        rot=Matrix.Rotation(math.radians(-90.0), 3, "Y")))
    out["Mod.CamPod"] = cam.finish("Drone.Survey.Mod.CamPod")

    mast = Part()
    mast.group("MastBase", lambda bm: _prism(bm, 8, 0.024, 0.013, (0, 0, 0.013),
                                             bevel=0.005, taper=0.72))
    mast.group("MastTube", lambda bm: _prism(bm, 8, 0.0095, 0.088, (0, 0, 0.114),
                                             bevel=0.002, taper=0.80))
    def dish(bm):
        _prism(bm, 16, 0.036, 0.004, (0, 0, 0.176), bevel=0.0015, taper=0.72)
        _prism(bm, 8, 0.006, 0.016, (0, 0, 0.196), bevel=0.001, taper=0.4)
    mast.group("Dish", dish)
    mast.group("SensorHead", lambda bm: _box(bm, (0.070, 0.026, 0.040),
                                             (0, 0, 0.226), bevel=0.008))
    mast.group("Beacon", lambda bm: _prism(bm, 8, 0.008, 0.007, (0, 0, 0.252),
                                           bevel=0.002, taper=0.5))
    out["Mod.Mast"] = mast.finish("Drone.Survey.Mod.Mast")

    batt = Part()
    batt.group("Cell", lambda bm: _box(bm, (0.104, 0.124, 0.058), (0, 0, 0.058),
                                       bevel=0.010))
    def ribs(bm):
        for i in range(3):
            _box(bm, (0.014, 0.128, 0.048), (0.0, 0.0, 0.030 + i * 0.022),
                 bevel=0.003)
    batt.group("Rib", ribs)
    batt.group("Latch", lambda bm: _box(bm, (0.018, 0.086, 0.024), (0, 0, 0.098),
                                        bevel=0.005))
    def gauge(bm):
        for i in range(3):
            _box(bm, (0.006, 0.014, 0.004), (0.038, -0.030 + i * 0.030, 0.088),
                 bevel=0.001)
    batt.group("Gauge", gauge)
    out["Mod.Battery"] = batt.finish("Drone.Survey.Mod.Battery")
    return out


# Which module seats on which socket, and the module's own mount axis in its
# authored mount space (+Z by convention — asserted, not assumed).
MODULE_FOR_SOCKET = {
    "SKT_Rotor.FL": "Mod.Rotor", "SKT_Rotor.FR": "Mod.Rotor",
    "SKT_Rotor.RL": "Mod.Rotor", "SKT_Rotor.RR": "Mod.Rotor",
    "SKT_Camera": "Mod.CamPod",
    "SKT_Mast": "Mod.Mast",
    "SKT_Battery": "Mod.Battery",
}
MODULE_MOUNT_AXIS = Vector((0.0, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def assemble(sc, root_loc=ROOT_LOC, root_rot=ROOT_ROT, skip_mpi=False,
             chassis_meshes=None, module_meshes=None):
    """Build the posed drone. Returns (root, parts, sockets, modules).

    Sockets are authored in WORLD space (where an artist places them) and then
    parented to the posed root. Keeping their world transform requires
    ``matrix_parent_inverse = root.matrix_world.inverted()``; skip_mpi=True
    omits it, which is the falsification probe.
    """
    chassis_meshes = chassis_meshes or build_chassis_meshes()
    module_meshes = module_meshes or build_module_meshes()

    root = bpy.data.objects.new("Drone.Survey", None)
    root.empty_display_type = "PLAIN_AXES"
    root.location = root_loc
    root.rotation_euler = root_rot
    sc.collection.objects.link(root)
    bpy.context.view_layer.update()

    parts = []
    for suffix, me in chassis_meshes.items():
        ob = bpy.data.objects.new(me.name, me)
        sc.collection.objects.link(ob)
        ob.parent = root
        parts.append(ob)

    sockets, modules = {}, {}
    for skt_name, pad_name, centre, normal, radius in socket_spec():
        local = authored_local(centre, normal)
        skt = bpy.data.objects.new(skt_name, None)
        skt.empty_display_type = "ARROWS"
        skt.empty_display_size = 0.09
        sc.collection.objects.link(skt)
        # authored in world space first — this is the step that makes the
        # parent-inverse load-bearing
        skt.matrix_world = root.matrix_world @ local
        bpy.context.view_layer.update()
        skt.parent = root
        if not skip_mpi:
            skt.matrix_parent_inverse = root.matrix_world.inverted()
        bpy.context.view_layer.update()
        sockets[skt_name] = skt

        mod_key = MODULE_FOR_SOCKET[skt_name]
        mod = bpy.data.objects.new(f"Drone.Survey.{mod_key}@{skt_name}",
                                   module_meshes[mod_key])
        sc.collection.objects.link(mod)
        mod.parent = skt
        # the spawn contract: identity local transform, identity parent-inverse
        mod.matrix_parent_inverse = Matrix.Identity(4)
        mod.matrix_basis = Matrix.Identity(4)
        modules[skt_name] = mod
    bpy.context.view_layer.update()
    return root, parts, sockets, modules


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------

def mat_dev(a, b):
    return max(abs(x - y) for ra, rb in zip(a, b) for x, y in zip(ra, rb))


def evaluated_matrix(ob):
    """World matrix straight off the depsgraph, not the cached object."""
    dg = bpy.context.evaluated_depsgraph_get()
    return Matrix(ob.evaluated_get(dg).matrix_world)


def ortho_error(m3):
    """Max deviation of M^T M from the identity — 0 for an orthonormal basis."""
    g = m3.transposed() @ m3
    return max(abs(g[i][j] - (1.0 if i == j else 0.0))
               for i in range(3) for j in range(3))


def check():
    sc = bpy.context.scene
    fails = []

    def fail(code, msg):
        print(f"ERROR ({code}): {msg}", file=sys.stderr)
        fails.append(code)

    chassis = build_chassis_meshes()
    root, parts, sockets, modules = assemble(sc, chassis_meshes=chassis)
    spec = socket_spec()
    pad_by_socket = {s[0]: s[1] for s in spec}
    local_by_socket = {s[0]: authored_local(s[2], s[3]) for s in spec}
    normal_by_socket = {s[0]: Vector(s[3]).normalized() for s in spec}

    # --- 1. socket matrices == authored world transform ---------------------
    worst_m, worst_o, worst_det = 0.0, 0.0, 0.0
    for name, skt in sockets.items():
        want = root.matrix_world @ local_by_socket[name]
        d = mat_dev(evaluated_matrix(skt), want)
        m3 = evaluated_matrix(skt).to_3x3()
        oe = ortho_error(m3)
        dd = abs(m3.determinant() - 1.0)
        worst_m, worst_o = max(worst_m, d), max(worst_o, oe)
        worst_det = max(worst_det, dd)
        if d > TOL:
            fail(3, f"{name} world matrix deviates {d:.3e} > {TOL:.0e} from the "
                    f"authored transform — parent-inverse or basis is wrong")
        if oe > ORTHO_TOL:
            fail(3, f"{name} basis is not orthonormal (Gram error {oe:.3e}) — "
                    f"modules would spawn sheared or scaled")
        if dd > ORTHO_TOL:
            fail(3, f"{name} basis determinant {m3.determinant():.6f} != +1 — "
                    f"left-handed socket, modules mirror on spawn")
    print(f"socket_matrices n={len(sockets)} max_dev={worst_m:.3e} "
          f"ortho_err={worst_o:.3e} det_err={worst_det:.3e} tol={TOL:.0e}")

    # --- 2. orientation vs pad geometry (independent derivations) -----------
    rot3 = root.matrix_world.to_3x3()
    worst_n, worst_c, worst_up = 0.0, 0.0, 0.0
    for name, skt in sockets.items():
        pad_me = chassis[pad_by_socket[name]]
        n_world = (rot3 @ newell_normal(pad_me, 0)).normalized()
        z_world = evaluated_matrix(skt).to_3x3().col[2].normalized()
        ndev = (n_world - z_world).length
        c_world = root.matrix_world @ polygon_centroid(pad_me, 0)
        cdev = (c_world - evaluated_matrix(skt).translation).length
        # documented up-axis rule, re-derived here rather than reused
        n_l = normal_by_socket[name]
        ref = CHASSIS_FWD if abs(n_l.dot(CHASSIS_UP)) > PARALLEL else CHASSIS_UP
        y_want = (rot3 @ (ref - n_l * ref.dot(n_l)).normalized()).normalized()
        updev = (y_want - evaluated_matrix(skt).to_3x3().col[1].normalized()).length
        worst_n, worst_c = max(worst_n, ndev), max(worst_c, cdev)
        worst_up = max(worst_up, updev)
        if ndev > TOL:
            fail(4, f"{name} +Z deviates {ndev:.3e} from its pad's Newell normal "
                    f"— the socket does not face the way its pad does")
        if cdev > TOL:
            fail(4, f"{name} origin is {cdev:.3e} m off its pad's mount-face "
                    f"centroid — the module would float or sink")
        if updev > TOL:
            fail(4, f"{name} +Y deviates {updev:.3e} from the documented up rule "
                    f"— modules spawn rolled about their mount axis")
    print(f"pad_orientation sockets={len(sockets)} normal_dev={worst_n:.3e} "
          f"centroid_dev={worst_c:.3e} up_dev={worst_up:.3e} tol={TOL:.0e}")

    # --- 3. module seating --------------------------------------------------
    worst_seat, worst_axis = 0.0, 0.0
    for name, mod in modules.items():
        skt_m = evaluated_matrix(sockets[name])
        mod_m = evaluated_matrix(mod)
        seat = (mod_m.translation - skt_m.translation).length
        axis_dot = (mod_m.to_3x3() @ MODULE_MOUNT_AXIS).normalized().dot(
            skt_m.to_3x3().col[2].normalized())
        worst_seat = max(worst_seat, seat)
        worst_axis = max(worst_axis, abs(axis_dot - 1.0))
        if seat > TOL:
            fail(5, f"module on {name} sits {seat:.3e} m off the socket origin")
        if abs(axis_dot - 1.0) > TOL:
            fail(5, f"module on {name} mount axis dot {axis_dot:.9f} != 1 — "
                    f"seated crooked")
        if mat_dev(mod.matrix_basis, Matrix.Identity(4)) > 0.0:
            fail(5, f"module on {name} carries a non-identity local transform — "
                    f"it is not seated by the socket, it is nudged into place")
    print(f"module_seating n={len(modules)} max_offset={worst_seat:.3e} "
          f"max_axis_err={worst_axis:.3e} tol={TOL:.0e}")

    # --- 4. reuse hygiene (before the destructive apply below) --------------
    default_names = {"Cube", "Sphere", "Torus", "Suzanne", "Plane", "Circle",
                     "Cylinder", "Cone", "Grid", "Icosphere", "Empty"}
    for ob in parts:
        if max(abs(s - 1.0) for s in ob.scale) > 0.0:
            fail(6, f"{ob.name} scale {tuple(ob.scale)} not applied")
        if not ob.name.startswith("Drone.Survey."):
            fail(6, f"chassis part {ob.name!r} outside the asset namespace")
        if ob.data.name.split(".")[0] in default_names:
            fail(6, f"{ob.name} carries a default datablock name {ob.data.name!r}")
    for name in sockets:
        if not name.startswith("SKT_"):
            fail(6, f"socket {name!r} does not carry the SKT_ prefix a spawn "
                    f"system scans for")
    lo = min(min(v.co.z for v in me.vertices) for me in chassis.values())
    if abs(lo) > 1e-4:
        fail(6, f"chassis rests at z={lo:.5f}, not on the skid contact plane")
    print(f"hygiene parts={len(parts)} sockets={len(sockets)} "
          f"modules={len(modules)} skid_plane_z={lo:.2e}")

    # --- 5. rigid invariance: re-pose the root, sockets follow exactly -------
    root.location = REPOSE_LOC
    root.rotation_euler = REPOSE_ROT
    bpy.context.view_layer.update()
    worst_r, worst_rm = 0.0, 0.0
    for name, skt in sockets.items():
        want = root.matrix_world @ local_by_socket[name]
        d = mat_dev(evaluated_matrix(skt), want)
        worst_r = max(worst_r, d)
        if d > TOL:
            fail(7, f"{name} does not track the re-posed root (dev {d:.3e})")
        md = (evaluated_matrix(modules[name]).translation
              - evaluated_matrix(skt).translation).length
        worst_rm = max(worst_rm, md)
        if md > TOL:
            fail(7, f"module on {name} lost its socket under the re-pose "
                    f"(dev {md:.3e})")
    print(f"rigid_invariance repose_dev={worst_r:.3e} module_dev={worst_rm:.3e} "
          f"tol={TOL:.0e}")

    # --- 6. transform apply on the root (destructive — runs last) -----------
    root.scale = (APPLY_SCALE,) * 3
    bpy.context.view_layer.update()
    before = {n: Matrix(evaluated_matrix(s)) for n, s in sockets.items()}
    mpi_before = {n: Matrix(s.matrix_parent_inverse) for n, s in sockets.items()}
    part_scale_before = max(max(abs(s - 1.0) for s in ob.scale) for ob in parts)
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    root.select_set(True)
    bpy.context.view_layer.objects.active = root
    # HAZARD: only the root may be selected. A child left selected has the
    # parent transform applied twice — measured at 2.335 m of socket drift on
    # this asset (probe double_apply).
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.view_layer.update()
    worst_a, cleared = 0.0, 0
    for name, skt in sockets.items():
        d = mat_dev(evaluated_matrix(skt), before[name])
        worst_a = max(worst_a, d)
        if d > TOL:
            fail(8, f"{name} moved {d:.3e} when the root transform was applied "
                    f"— the asset cannot be frozen without breaking its sockets")
        if (mat_dev(skt.matrix_parent_inverse, Matrix.Identity(4)) == 0.0
                and mat_dev(mpi_before[name], Matrix.Identity(4)) > 0.0):
            cleared += 1
    # HAZARD, asserted rather than described: the root is an Empty, so there is
    # no object data to bake the transform into. Blender pushes it DOWN into
    # every child instead — parent-inverses reset to identity and the children
    # pick up the root's scale in their own local matrices. World matrices are
    # preserved to float32; local transforms are not what they were. A spawn
    # system that reads socket.matrix_local, or an exporter that trusts
    # "transforms are applied", reads different numbers after an artist freezes
    # the rig.
    part_scale_after = max(max(abs(s - 1.0) for s in ob.scale) for ob in parts)
    print(f"transform_apply scale={APPLY_SCALE} world_dev={worst_a:.3e} "
          f"mpi_cleared={cleared}/{len(sockets)} "
          f"child_scale_before={part_scale_before:.3e} "
          f"child_scale_after={part_scale_after:.3e} tol={TOL:.0e}")
    if cleared != len(sockets):
        fail(8, f"only {cleared}/{len(sockets)} parent-inverses were cleared by "
                f"the apply — the documented hazard changed behaviour, so the "
                f"README's warning about reading local transforms is now wrong")
    if part_scale_after < APPLY_SCALE - 1.0 - 1e-3:
        fail(8, f"child scale pushdown {part_scale_after:.3e} does not match the "
                f"applied {APPLY_SCALE} — the documented Empty-root hazard "
                f"changed behaviour")
    worst_as = max((evaluated_matrix(modules[n]).translation
                    - evaluated_matrix(sockets[n]).translation).length
                   for n in sockets)
    if worst_as > TOL:
        fail(8, f"modules drifted {worst_as:.3e} m off their sockets after the "
                f"apply")
    print(f"transform_apply module_seating_dev={worst_as:.3e}")

    if fails:
        return fails[0]
    print(f"socket-attach-points OK sockets={len(sockets)} modules={len(modules)} "
          f"parts={len(parts)} matrix_dev={worst_m:.3e} normal_dev={worst_n:.3e} "
          f"seat_dev={worst_seat:.3e} apply_dev={worst_a:.3e} "
          f"repose_dev={worst_r:.3e}")
    return 0


def probe_no_mpi():
    """Falsification probe: parent the sockets without the parent-inverse."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    root, parts, sockets, modules = assemble(sc, skip_mpi=True)
    worst = 0.0
    for name, pad, centre, normal, radius in socket_spec():
        want = root.matrix_world @ authored_local(centre, normal)
        worst = max(worst, (evaluated_matrix(sockets[name]).translation
                            - want.translation).length)
    print(f"probe_no_mpi worst_socket_jump={worst:.6f} m")
    return worst


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def make_material(name, rgb, rough=0.45, metallic=0.6, emit=None, estr=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    if emit is not None:
        sock = b.inputs.get("Emission Color") or b.inputs["Emission"]
        sock.default_value = (*emit, 1.0)
        b.inputs["Emission Strength"].default_value = estr
    return mat


# One entry per material slot name used by the Part builders above:
# (base rgb, roughness, metallic, emission rgb or None, emission strength).
SLOT_MATS = {
    "Carbon":     ((0.044, 0.049, 0.060), 0.62, 0.22, None, 0.0),
    "Deck":       ((0.058, 0.067, 0.080), 0.52, 0.55, None, 0.0),
    "Canopy":     ((0.020, 0.048, 0.062), 0.14, 0.30, None, 0.0),
    "Vent":       ((0.066, 0.074, 0.086), 0.58, 0.70, None, 0.0),
    "Trim":       ((0.046, 0.052, 0.062), 0.72, 0.30, None, 0.0),
    "Boom":       ((0.040, 0.045, 0.055), 0.40, 0.60, None, 0.0),
    "Fairing":    ((0.050, 0.056, 0.068), 0.64, 0.45, None, 0.0),
    "Motor":      ((0.150, 0.158, 0.172), 0.26, 0.92, None, 0.0),
    "MotorFin":   ((0.108, 0.114, 0.126), 0.30, 0.90, None, 0.0),
    "NavFwd":     ((0.060, 0.140, 0.090), 0.30, 0.10, (0.30, 1.00, 0.55), 2.6),
    "NavAft":     ((0.150, 0.048, 0.040), 0.30, 0.10, (1.00, 0.22, 0.16), 2.6),
    "Skid":       ((0.092, 0.098, 0.110), 0.46, 0.78, None, 0.0),
    "Foot":       ((0.030, 0.030, 0.033), 0.78, 0.05, None, 0.0),
    "Strut":      ((0.070, 0.075, 0.086), 0.44, 0.72, None, 0.0),
    # the signature: every mount pad is the same machined orange, so the
    # sockets read as sockets at a glance
    "SocketPad":  ((0.640, 0.250, 0.045), 0.34, 0.40, None, 0.0),
    "Fixing":     ((0.170, 0.176, 0.188), 0.24, 0.95, None, 0.0),
    "Hub":        ((0.120, 0.126, 0.138), 0.28, 0.90, None, 0.0),
    "Spinner":    ((0.520, 0.200, 0.038), 0.26, 0.55, None, 0.0),
    "Blade":      ((0.072, 0.076, 0.086), 0.26, 0.40, None, 0.0),
    "PodYoke":    ((0.096, 0.102, 0.114), 0.34, 0.85, None, 0.0),
    "PodBall":    ((0.038, 0.052, 0.062), 0.22, 0.45, None, 0.0),
    "LensRing":   ((0.070, 0.074, 0.082), 0.20, 0.90, None, 0.0),
    "LensGlass":  ((0.010, 0.026, 0.038), 0.05, 0.30, (0.06, 0.26, 0.40), 0.30),
    "MastBase":   ((0.096, 0.102, 0.114), 0.34, 0.85, None, 0.0),
    "MastTube":   ((0.130, 0.136, 0.148), 0.28, 0.92, None, 0.0),
    "Dish":       ((0.150, 0.156, 0.166), 0.32, 0.88, None, 0.0),
    "SensorHead": ((0.044, 0.050, 0.060), 0.30, 0.55, None, 0.0),
    "Beacon":     ((0.170, 0.090, 0.030), 0.30, 0.10, (1.00, 0.52, 0.16), 3.0),
    "Cell":       ((0.150, 0.108, 0.042), 0.54, 0.28, None, 0.0),
    "Rib":        ((0.088, 0.064, 0.028), 0.60, 0.25, None, 0.0),
    "Latch":      ((0.130, 0.136, 0.148), 0.28, 0.90, None, 0.0),
    "Gauge":      ((0.060, 0.140, 0.090), 0.30, 0.10, (0.34, 1.00, 0.50), 2.2),
}

_mat_cache = {}


def mat_for_slot(slot):
    if slot not in _mat_cache:
        rgb, rough, metal, emit, estr = SLOT_MATS[slot]
        _mat_cache[slot] = make_material(slot, rgb, rough, metal, emit, estr)
    return _mat_cache[slot]


def bind_materials(ob):
    """Append this mesh's material slots in the order the Part builder used."""
    me = ob.data
    if me.materials:
        return
    for slot in me.get("slots", []):
        me.materials.append(mat_for_slot(slot))


def build_studio(sc):
    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = make_material("Studio", (0.030, 0.032, 0.037), rough=0.7, metallic=0.0)
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    sc.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    # far enough back that the wedge draws a contained pool rather than
    # flooding the whole backdrop (drafts 2-3 blew the wall out to mid grey)
    wall.location = (0.0, 5.8, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    sc.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.020, 0.021, 0.025, 1.0)
    sc.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        sc.collection.objects.link(ob)
        return ob

    # VISUAL-STYLE Layer 2 rig, energies scaled to a 0.86 m subject
    light("Key", (-1.30, -0.80, 2.30), 150.0, 1.4, (1.0, 0.96, 0.9), (26, 0, -58))
    light("Fill", (1.70, -1.00, 0.90), 14.0, 2.6, (0.75, 0.85, 1.0), (66, 0, 54))
    light("Rim", (-0.35, 1.60, 1.40), 55.0, 1.2, (0.6, 0.78, 1.0), (-50, 0, 196))
    # Wedge sits between subject and wall, aimed at the wall, not the drone.
    # Draft 3 put it high and hot: the pool blew to white and was clipped by
    # the top-right corner. Low, larger and softer keeps the pool contained
    # behind the subject where it lifts the silhouette.
    light("Wedge", (0.10, 3.30, 0.34), 70.0, 3.0, (1.0, 0.76, 0.5), (-88, 0, 182))
    return floor, wall


def render_still(path, engine, falsify=False):
    """The drone on the stage with every module seated at its socket.

    Falsified: the sockets are parented without ``matrix_parent_inverse``, so
    every socket collapses toward the world origin and drags its module with
    it — rotors, camera and battery hang in space off the airframe.
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _mat_cache.clear()
    sc = bpy.context.scene

    root, parts, sockets, modules = assemble(sc, skip_mpi=falsify)
    hero = parts + list(modules.values())
    for ob in hero:
        bind_materials(ob)
    floor, wall = build_studio(sc)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    # three-quarter from above: the deck, the canted rotor pads and the belly
    # pod all read from here; a level side-on view (draft 2) flattened the
    # airframe into a silhouette
    cam.location = (1.28, -1.42, 1.44)
    sc.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.10, -0.05, 0.60)
    sc.collection.objects.link(aim)
    tr = cam.constraints.new("TRACK_TO")
    tr.target = aim
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    sc.camera = cam

    sc.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        sc.cycles.device = "CPU"
        sc.cycles.samples = 64
        sc.cycles.use_denoising = True
    else:
        try:
            sc.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    sc.render.resolution_x = 1280
    sc.render.resolution_y = 720
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    # Standard, always — AgX would lift the stage toward grey (VISUAL-STYLE)
    sc.view_settings.view_transform = "Standard"
    bpy.context.view_layer.update()

    # The gallery still is gated; the --falsify diagnostic is not. Its whole
    # point is that the modules fly off the airframe, so measuring it against
    # the Layer 1 band would only ever report the breakage as a framing
    # violation. The numbers are still printed under an explicit reason.
    fcode = gallery_framing.check_framing(
        sc, cam, hero=hero, elements=hero, stage=[floor, wall],
        deviation=("falsification diagnostic: the sockets are deliberately "
                   "unparented, so modules leave the frame — this render is "
                   "evidence, not a gallery hero") if falsify else None)
    if fcode:
        return fcode
    aqcode = gallery_asset_quality.check_asset_quality(sc, cam, hero=hero,
                                                       stage=[floor, wall])
    if aqcode:
        return aqcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 9
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--falsify", default=None,
                   help="optional: render the no-parent-inverse variant here")
    p.add_argument("--probe", action="store_true",
                   help="optional: print the measured no-parent-inverse jump")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    args = p.parse_args(argv)

    print(f"binary version: {bpy.app.version} ({bpy.app.version_string})")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    code = check()
    if code:
        return code
    if args.probe:
        probe_no_mpi()
    if args.output:
        rcode = render_still(os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    if args.falsify:
        rcode = render_still(os.path.abspath(args.falsify), args.engine, falsify=True)
        if rcode:
            return rcode
        print(f"rendered falsified variant {args.falsify}")

    print("socket-attach-points OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
