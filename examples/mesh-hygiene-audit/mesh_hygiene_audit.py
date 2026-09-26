"""Mesh hygiene audit — engine-ingest topology as a runnable contract.

Witnesses the mesh-cleanliness checklist a prop pipeline relies on before
engine ingest, on every part of an authored upright street valve (flanged
body casting, bonnet, gland nut, threaded stem, brass handwheel, side
outlet, flange bolts):

- no ngons (tris/quads only)
- no loose vertices
- manifold edges (every edge borders exactly two faces)
- no zero-area faces
- consistent winding (every manifold edge contiguous) and outward winding
  (positive divergence-theorem signed volume)
- Euler characteristic V-E+F == 2 on the body casting, the genus-0 shell
  the other parts mount on

Every gate is derived from mesh combinatorics or the divergence-theorem
volume — never from a prior-run capture.

Companion to collision-hull-proxy (watertight / Euler on *hulls*) and
bmesh-gear (watertight parametric solid). The render stages a dirty copy of
the same valve beside the clean one; every defect marker on the dirty copy
is built from the live audit data, and the flipped / open faces glow red
through the shader's own Backfacing output, so the winding evidence is the
renderer's, not paint.

By default it runs only the correctness check (no render). Pass --output
to also render a still:

    blender --background --python mesh_hygiene_audit.py --
    blender --background --python mesh_hygiene_audit.py -- --inject ngon
    blender --background --python mesh_hygiene_audit.py -- --output h.png
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Matrix, Vector

# Shared Layer 1 helpers (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing
import gallery_asset_quality

AREA_EPS = 1e-10
VOL_EPS = 1e-8
BODY = "Valve.Body"
SEG = 32  # radial segments of the revolved castings

INJECT_KINDS = ("ngon", "loose", "boundary", "flip", "flip_patch", "zero_area", "shell")


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


# ---------------------------------------------------------------- measurement

def signed_volume(me):
    """Divergence-theorem volume; positive when face winding points outward."""
    vol = 0.0
    for p in me.polygons:
        vs = [me.vertices[i].co for i in p.vertices]
        v0 = vs[0]
        for i in range(1, len(vs) - 1):
            vol += v0.dot(vs[i].cross(vs[i + 1])) / 6.0
    return vol


def face_area(me, poly):
    vs = [me.vertices[i].co for i in poly.vertices]
    if len(vs) < 3:
        return 0.0
    v0 = vs[0]
    area = 0.0
    for i in range(1, len(vs) - 1):
        area += (vs[i] - v0).cross(vs[i + 1] - v0).length * 0.5
    return area


def audit(me):
    """Return a dict of hygiene metrics for the mesh datablock."""
    nv, ne, nf = len(me.vertices), len(me.edges), len(me.polygons)
    ngons = sum(1 for p in me.polygons if len(p.vertices) > 4)
    areas = [face_area(me, p) for p in me.polygons]
    min_area = min(areas) if areas else 0.0
    zero_area = sum(1 for a in areas if a <= AREA_EPS)

    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        loose = sum(1 for v in bm.verts if len(v.link_edges) == 0)
        nonman = sum(1 for e in bm.edges if len(e.link_faces) != 2)
        boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
        # a manifold edge whose two faces traverse it in the SAME direction
        # is a winding seam: one side is flipped relative to the other
        seams = sum(1 for e in bm.edges
                    if len(e.link_faces) == 2 and not e.is_contiguous)
    finally:
        bm.free()

    return {
        "nv": nv, "ne": ne, "nf": nf,
        "ngons": ngons, "loose": loose, "nonman": nonman,
        "boundary": boundary, "seams": seams, "zero_area": zero_area,
        "min_area": min_area, "volume": signed_volume(me),
        "euler": nv - ne + nf,
    }


def check(me, label, euler=True):
    """Assert the hygiene contract on one mesh. Exit codes 3–8 on failure."""
    m = audit(me)
    print(
        f"{label}: verts={m['nv']} edges={m['ne']} faces={m['nf']} "
        f"euler={m['euler']} volume={m['volume']:.6f} min_area={m['min_area']:.3e}"
    )
    if m["ngons"]:
        print(f"ERROR: {label}: {m['ngons']} ngon(s) — engine ingest wants "
              f"tris/quads only", file=sys.stderr)
        return 3
    if m["loose"]:
        print(f"ERROR: {label}: {m['loose']} loose vertex(es) — degree 0 verts",
              file=sys.stderr)
        return 4
    if m["nonman"] or m["boundary"]:
        print(f"ERROR: {label}: non-manifold topology — nonman_edges={m['nonman']} "
              f"boundary_edges={m['boundary']} (closed solid needs every edge "
              f"bordering exactly 2 faces)", file=sys.stderr)
        return 5
    if m["zero_area"]:
        print(f"ERROR: {label}: {m['zero_area']} zero-area face(s) "
              f"(min_area={m['min_area']:.3e} <= {AREA_EPS})", file=sys.stderr)
        return 6
    if m["seams"]:
        print(f"ERROR: {label}: {m['seams']} winding seam edge(s) — faces on "
              f"either side disagree on orientation (flipped patch)", file=sys.stderr)
        return 7
    if m["volume"] <= VOL_EPS:
        print(f"ERROR: {label}: signed volume {m['volume']:.6f} <= {VOL_EPS} — "
              f"winding inverted or open shell", file=sys.stderr)
        return 7
    if euler and m["euler"] != 2:
        print(f"ERROR: {label}: Euler characteristic V-E+F={m['euler']} != 2 — "
              f"not a single closed genus-0 shell", file=sys.stderr)
        return 8
    return 0


def check_valve(parts):
    """Every part passes gates 3–7; the body casting also passes Euler (8)."""
    for ob in parts:
        code = check(ob.data, ob.name, euler=(ob.name == BODY))
        if code:
            return code
    body = next(ob for ob in parts if ob.name == BODY)
    m = audit(body.data)
    print(
        f"hygiene_ok parts={len(parts)} ngons=0 loose=0 nonman=0 boundary=0 "
        f"seams=0 zero_area=0 body_euler={m['euler']} "
        f"body_volume={m['volume']:.6f} body_min_area={m['min_area']:.3e}"
    )
    return 0


# ------------------------------------------------------------------- modeling

def _orient_outward(bm):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    tmp = bpy.data.meshes.new("_tmp_vol")
    try:
        bm.to_mesh(tmp)
        if signed_volume(tmp) < 0.0:
            for f in bm.faces:
                f.normal_flip()
    finally:
        bpy.data.meshes.remove(tmp)


def lathe_into(bm, profile, segs, matrix=None, phase=0.0):
    """Revolve (r, z) profile about local Z into bm; fan-cap both ends.

    Quads on the sides, triangle fans on the caps: tris/quads only, every
    edge shared by exactly two faces, one closed genus-0 shell per call.
    """
    rings = []
    for r, z in profile:
        ring = []
        for i in range(segs):
            a = 2.0 * math.pi * i / segs + phase
            ring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z)))
        rings.append(ring)
    new_faces = []
    for a, b in zip(rings, rings[1:]):
        for k in range(segs):
            kn = (k + 1) % segs
            new_faces.append(bm.faces.new((a[k], a[kn], b[kn], b[k])))
    bc = bm.verts.new((0.0, 0.0, profile[0][1]))
    tc = bm.verts.new((0.0, 0.0, profile[-1][1]))
    for k in range(segs):
        kn = (k + 1) % segs
        new_faces.append(bm.faces.new((bc, rings[0][kn], rings[0][k])))
        new_faces.append(bm.faces.new((tc, rings[-1][k], rings[-1][kn])))
    verts = [v for ring in rings for v in ring] + [bc, tc]
    if matrix is not None:
        bmesh.ops.transform(bm, matrix=matrix, verts=verts)
    return new_faces


def torus_into(bm, major, minor, useg, vseg, matrix=None):
    grid = []
    for i in range(useg):
        u = 2.0 * math.pi * i / useg
        row = []
        for j in range(vseg):
            v = 2.0 * math.pi * j / vseg
            rr = major + minor * math.cos(v)
            row.append(bm.verts.new((rr * math.cos(u), rr * math.sin(u),
                                     minor * math.sin(v))))
        grid.append(row)
    for i in range(useg):
        inx = (i + 1) % useg
        for j in range(vseg):
            jn = (j + 1) % vseg
            bm.faces.new((grid[i][j], grid[inx][j], grid[inx][jn], grid[i][jn]))
    if matrix is not None:
        bmesh.ops.transform(bm, matrix=matrix,
                            verts=[v for row in grid for v in row])


def make_material(name, rgb, rough=0.45, metallic=0.0, emit=None, estr=0.0,
                  coat=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    if coat:
        sock = b.inputs.get("Coat Weight") or b.inputs.get("Clearcoat")
        if sock is not None:
            sock.default_value = coat
    if emit is not None:
        sock = b.inputs.get("Emission Color") or b.inputs["Emission"]
        sock.default_value = (*emit, 1.0)
        b.inputs["Emission Strength"].default_value = estr
    return mat


def add_backface_witness(mat, rgb=(0.85, 0.002, 0.004), strength=0.35):
    """Mix to a red emission wherever the renderer sees a face's back side.

    On a closed, outward-wound shell no back side is ever visible, so this
    changes nothing on the clean valve. On the dirty copy the renderer's own
    Backfacing output lights up flipped faces and the inside of the hole.
    """
    nt = mat.node_tree
    out = nt.nodes["Material Output"]
    bsdf = nt.nodes["Principled BSDF"]
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    # lit red plus a little glow: the inside of a hole falls dark (only the
    # opening admits light) while a flipped patch in the key reads bright
    back = nt.nodes.new("ShaderNodeBsdfPrincipled")
    back.inputs["Base Color"].default_value = (*rgb, 1.0)
    back.inputs["Roughness"].default_value = 0.5
    sock = back.inputs.get("Emission Color") or back.inputs["Emission"]
    sock.default_value = (*rgb, 1.0)
    back.inputs["Emission Strength"].default_value = strength
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(geo.outputs["Backfacing"], mix.inputs["Fac"])
    nt.links.new(bsdf.outputs["BSDF"], mix.inputs[1])
    nt.links.new(back.outputs["BSDF"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


def _finish_part(name, build, mat, smooth_angle=35.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        build(bm)
        _orient_outward(bm)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = True
    if hasattr(me, "set_sharp_from_angle"):
        me.set_sharp_from_angle(angle=math.radians(smooth_angle))
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


# Body casting profile (r, z): chamfered base flange, flared neck, globe,
# waist, chamfered bonnet flange, domed bonnet. Every step corner is broken
# by a chamfer so no ring meets its neighbour at a raw right angle.
BODY_PROFILE = [
    (0.500, 0.000), (0.520, 0.020), (0.520, 0.085), (0.500, 0.105),
    (0.400, 0.105), (0.300, 0.105), (0.280, 0.125), (0.270, 0.180),
    (0.330, 0.260), (0.395, 0.350), (0.430, 0.470), (0.420, 0.590),
    (0.360, 0.690), (0.285, 0.755), (0.270, 0.795),
    (0.370, 0.795), (0.390, 0.815), (0.390, 0.885), (0.370, 0.905),
    (0.300, 0.905), (0.240, 0.905), (0.225, 0.950), (0.200, 1.040),
    (0.160, 1.095), (0.120, 1.115),
]
BASE_TOP_Z = 0.105
BONNET_TOP_Z = 0.905


def _bolt_profile(s=1.0):
    # hex head with chamfered crown, then a short threaded stud end
    return [(0.046 * s, 0.000), (0.046 * s, 0.030 * s), (0.036 * s, 0.042 * s),
            (0.019 * s, 0.042 * s), (0.019 * s, 0.066 * s), (0.014 * s, 0.072 * s)]


def build_street_valve():
    """Assemble the valve. Returns the list of part objects (body first)."""
    paint = add_backface_witness(
        make_material("ValvePaint", (0.025, 0.14, 0.42), rough=0.42, coat=0.35))
    steel = make_material("BoltSteel", (0.62, 0.63, 0.66), rough=0.32, metallic=0.95)
    iron = make_material("GlandIron", (0.10, 0.10, 0.11), rough=0.5, metallic=0.7)
    brass = make_material("HandwheelBrass", (0.78, 0.52, 0.18), rough=0.3, metallic=1.0)

    parts = [_finish_part(BODY, lambda bm: lathe_into(bm, BODY_PROFILE, SEG,
                                                      phase=math.pi / SEG), paint)]

    def outlet(bm):
        # side outlet along +X: pipe buried in the globe, chamfered flange
        prof = [(0.150, 0.20), (0.150, 0.56), (0.235, 0.56), (0.250, 0.575),
                (0.250, 0.625), (0.235, 0.64), (0.110, 0.64)]
        rot = Matrix.Translation((0.0, 0.0, 0.47)) @ Matrix.Rotation(math.pi / 2, 4, "Y")
        lathe_into(bm, prof, 24, matrix=rot)
    parts.append(_finish_part("Valve.Outlet", outlet, paint))

    def bolts(bm):
        for ring_r, z, n in ((0.445, BASE_TOP_Z, 8), (0.330, BONNET_TOP_Z, 8)):
            for i in range(n):
                a = 2.0 * math.pi * (i + 0.5) / n
                m = Matrix.Translation((ring_r * math.cos(a), ring_r * math.sin(a), z))
                lathe_into(bm, _bolt_profile(), 6, matrix=m, phase=a)
        # outlet flange bolts, heads on the flange face pointing +X
        for i in range(6):
            a = 2.0 * math.pi * (i + 0.5) / 6
            m = (Matrix.Translation((0.64, 0.195 * math.cos(a), 0.47 + 0.195 * math.sin(a)))
                 @ Matrix.Rotation(math.pi / 2, 4, "Y") @ Matrix.Scale(0.8, 4))
            lathe_into(bm, _bolt_profile(), 6, matrix=m)
    parts.append(_finish_part("Valve.FlangeBolts", bolts, steel, smooth_angle=20.0))

    def gland(bm):
        lathe_into(bm, [(0.115, 1.090), (0.115, 1.160), (0.100, 1.180),
                        (0.060, 1.180)], 6, phase=math.pi / 6)
    parts.append(_finish_part("Valve.GlandNut", gland, iron, smooth_angle=20.0))

    def stem(bm):
        prof = [(0.034, 1.150)]
        z = 1.180
        while z < 1.360:  # threaded section: alternating crest / root rings
            prof += [(0.034, z), (0.041, z + 0.008), (0.034, z + 0.016)]
            z += 0.020
        prof += [(0.034, 1.470), (0.026, 1.480)]
        lathe_into(bm, prof, 16)
    parts.append(_finish_part("Valve.Stem", stem, steel))

    def hub(bm):
        lathe_into(bm, [(0.060, 1.380), (0.078, 1.395), (0.078, 1.435),
                        (0.060, 1.450)], 20)
    parts.append(_finish_part("Valve.HandwheelHub", hub, brass))

    def rim(bm):
        torus_into(bm, 0.330, 0.032, 48, 12,
                   matrix=Matrix.Translation((0.0, 0.0, 1.390)))
    parts.append(_finish_part("Valve.HandwheelRim", rim, brass))

    def spokes(bm):
        for i in range(5):
            a = 2.0 * math.pi * i / 5 + 0.3
            d = Vector((math.cos(a), math.sin(a), -0.10)).normalized()
            prof = [(0.020, 0.0), (0.020, 0.300), (0.016, 0.315)]
            rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
            m = Matrix.Translation((0.05 * math.cos(a), 0.05 * math.sin(a), 1.418)) @ rot
            lathe_into(bm, prof, 10, matrix=m)
    parts.append(_finish_part("Valve.HandwheelSpokes", spokes, brass))
    return parts


# --------------------------------------------------------- defect injection

def inject_defect(me, kind):
    """Mutate a mesh for falsification. Each kind breaks exactly one gate."""
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        if kind == "loose":
            bm.verts.new((0.0, -0.8, 0.6))
        elif kind == "boundary":
            bmesh.ops.delete(bm, geom=[bm.faces[0]], context="FACES_ONLY")
        elif kind == "ngon":
            quads = [f for f in bm.faces if len(f.verts) == 4]
            e = next(e for e in quads[0].edges if len(e.link_faces) == 2
                     and all(len(f.verts) == 4 for f in e.link_faces))
            bmesh.ops.dissolve_edges(bm, edges=[e])
        elif kind == "flip":
            for f in bm.faces:
                f.normal_flip()
        elif kind == "flip_patch":
            bm.faces[len(bm.faces) // 2].normal_flip()
        elif kind == "zero_area":
            verts = list(bm.faces[0].verts)
            for v in verts[1:3]:
                v.co = verts[0].co.copy()
        elif kind == "shell":
            # a leftover second closed shell buried inside: every per-edge
            # gate stays green, only V-E+F (2 per shell) can see it
            lathe_into(bm, [(0.1, 0.4), (0.1, 0.5)], 8)
            _orient_outward(bm)
        else:
            raise ValueError(kind)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


def _faces_in(bm, view_angle, half_width, zmin, zmax, pred=None):
    out = []
    for f in bm.faces:
        c = f.calc_center_median()
        if not (zmin <= c.z <= zmax) or math.hypot(c.x, c.y) < 1e-6:
            continue
        d = (math.atan2(c.y, c.x) - view_angle + math.pi) % (2 * math.pi) - math.pi
        if abs(d) <= half_width and (pred is None or pred(f)):
            out.append(f)
    return out


def stage_dirty_body(me, view_angle):
    """Render staging: author the defects an unaudited export would carry.

    view_angle is the camera azimuth in the body's local frame, so each
    defect lands on the camera-facing side. Every one of these is a gate
    failure the check path proves (see --inject); the render markers are
    then read back from audit incidence, not from this function.
    """
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        # ngon: merge a run of the planar base-flange annulus into one face
        run = _faces_in(bm, view_angle - math.radians(40), math.radians(30),
                        BASE_TOP_Z - 1e-4, BASE_TOP_Z + 1e-4,
                        pred=lambda f: f.normal.z > 0.9 and len(f.verts) == 4)
        if run:
            bmesh.ops.dissolve_faces(bm, faces=run)
        # flipped patch on the bonnet dome
        for f in _faces_in(bm, view_angle + math.radians(40), math.radians(26),
                           0.93, 1.11):
            f.normal_flip()
        # open boundary: a hole through the front of the globe
        hole = _faces_in(bm, view_angle - math.radians(4), math.radians(19),
                         0.30, 0.66)
        bmesh.ops.delete(bm, geom=hole, context="FACES_ONLY")
        # loose verts: stray points left floating off the casting
        a = view_angle + math.radians(62)
        for r, z in ((0.66, 0.60), (0.74, 0.46), (0.63, 0.34)):
            bm.verts.new((r * math.cos(a), r * math.sin(a), z))
            a += math.radians(7)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


# --------------------------------------------------------------------- render

def build_studio(sc):
    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = make_material("Studio", (0.03, 0.032, 0.037), rough=0.7)
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    sc.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 11.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    sc.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.02, 0.021, 0.025, 1.0)
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

    light("Key", (-4.0, -5.0, 6.0), 460.0, 5.0, (1.0, 0.96, 0.9), (45, 0, -38))
    light("Fill", (5.0, -3.5, 2.0), 90.0, 9.0, (0.75, 0.85, 1.0), (70, 0, 55))
    light("Rim", (0.0, 3.2, 3.6), 220.0, 3.0, (0.6, 0.78, 1.0), (-50, 0, 180))
    # the camera looks down on the pair, so the backdrop in frame is floor:
    # the wedge pools warm on the floor behind and between the two valves
    light("Wedge", (0.0, 3.8, 2.2), 130.0, 3.0, (1.0, 0.76, 0.5), (22, 0, 0))
    return floor, wall


def _marker_mat(name, rgb, strength):
    # dark base so the lit diffuse and specular do not wash the glow to pink
    return make_material(name, tuple(c * 0.1 for c in rgb), rough=0.65,
                         emit=rgb, estr=strength)


def _tube(sc, name, a, b, radius, mat):
    d = b - a
    if d.length < 1e-8:
        return None
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=radius,
                              radius2=radius, depth=d.length + radius * 1.5)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = (a + b) * 0.5
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = d.normalized().to_track_quat("Z", "Y")
    sc.collection.objects.link(ob)
    return ob


def mark_defects_from_audit(sc, ob):
    """Overlay markers read back from the dirty mesh's audit incidence.

    Boundary edges -> glowing red tubes, loose verts -> red beads, ngon
    faces -> amber material slot. Flipped faces and the inside of the hole
    need no marker: the paint's Backfacing mix lights them red on its own.
    """
    me = ob.data
    metrics = audit(me)
    print(f"render_defects loose={metrics['loose']} boundary={metrics['boundary']} "
          f"seams={metrics['seams']} ngons={metrics['ngons']}")
    mw = ob.matrix_world
    markers = []

    ngon_mat = make_material("NgonTint", (1.0, 0.55, 0.04), rough=0.45,
                             emit=(1.0, 0.5, 0.03), estr=1.0)
    me.materials.append(ngon_mat)
    slot = len(me.materials) - 1
    for p in me.polygons:
        if len(p.vertices) > 4:
            p.material_index = slot

    red = _marker_mat("DefectRed", (1.0, 0.002, 0.004), 2.5)
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        loose = [mw @ v.co for v in bm.verts if not v.link_edges]
        boundary = [(mw @ e.verts[0].co, mw @ e.verts[1].co)
                    for e in bm.edges if len(e.link_faces) == 1]
    finally:
        bm.free()
    for i, (a, b) in enumerate(boundary):
        t = _tube(sc, f"Defect.Boundary{i}", a, b, 0.014, red)
        if t:
            markers.append(t)
    for i, co in enumerate(loose):
        sme = bpy.data.meshes.new(f"Defect.Loose{i}")
        sbm = bmesh.new()
        try:
            bmesh.ops.create_uvsphere(sbm, u_segments=16, v_segments=10, radius=0.038)
            sbm.to_mesh(sme)
        finally:
            sbm.free()
        sme.materials.append(red)
        for p in sme.polygons:
            p.use_smooth = True
        s = bpy.data.objects.new(f"Defect.Loose{i}", sme)
        s.location = co
        sc.collection.objects.link(s)
        markers.append(s)
    return metrics, markers


def _place(parts, loc, rot_z):
    m = Matrix.Translation(loc) @ Matrix.Rotation(rot_z, 4, "Z")
    for ob in parts:
        ob.matrix_world = m


def render_still(parts, path, engine):
    """Dirty copy (left) beside the clean valve (right), same paint on both."""
    sc = bpy.context.scene
    floor, wall = build_studio(sc)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -5.3, 3.0)
    sc.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.64)
    sc.collection.objects.link(aim)
    tr = cam.constraints.new("TRACK_TO")
    tr.target = aim
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    sc.camera = cam

    clean_loc, dirty_loc = Vector((0.98, 0.15, 0.0)), Vector((-0.98, 0.0, 0.0))
    # outlets swing outward-back on each side so the pair reads as a mirror
    _place(parts, clean_loc, math.radians(30))
    dirty = []
    for ob in parts:
        d = bpy.data.objects.new("Dirty." + ob.name, ob.data.copy())
        d.data.materials.clear()
        for mat in ob.data.materials:
            d.data.materials.append(mat)
        sc.collection.objects.link(d)
        dirty.append(d)
    dirty_rot = math.radians(150)
    _place(dirty, dirty_loc, dirty_rot)
    bpy.context.view_layer.update()

    body = next(d for d in dirty if d.name == "Dirty." + BODY)
    to_cam = body.matrix_world.inverted() @ cam.location
    stage_dirty_body(body.data, math.atan2(to_cam.y, to_cam.x))
    metrics, markers = mark_defects_from_audit(sc, body)
    if not (metrics["boundary"] and metrics["loose"] and metrics["seams"]
            and metrics["ngons"]):
        print("ERROR: dirty staging lost a defect class", file=sys.stderr)
        return 9

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
    # Standard, not AgX: AgX pulls the paint and the red markers to pastel
    sc.view_settings.view_transform = "Standard"

    # Layer 1 framing gate (exit 10) and asset-quality floors (exit 11) run
    # before the beauty render so a defective composition ships no artifact.
    fcode = gallery_framing.check_framing(
        sc, cam, hero=parts + dirty, elements=parts + dirty + markers,
        stage=[floor, wall])
    if fcode:
        return fcode
    aqcode = gallery_asset_quality.check_asset_quality(
        sc, cam, hero=parts, stage=[floor, wall])
    if aqcode:
        return aqcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 9
    return 0


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene, build_street_valve()


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output")
    p.add_argument("--inject", choices=INJECT_KINDS, default=None,
                   help="falsifier: break one gate on a part before the check")
    p.add_argument("--inject-part", default=BODY,
                   help="part to inject into (default: the body casting)")
    p.add_argument("--inject-ngon", action="store_true",
                   help="alias for --inject ngon")
    args = p.parse_args(argv)
    if args.inject_ngon:
        args.inject = "ngon"

    print(f"binary version: {bpy.app.version} ({bpy.app.version_string})")
    sc, parts = build_scene()
    if args.inject:
        target = bpy.data.objects.get(args.inject_part)
        if target is None or target not in parts:
            print(f"ERROR: no part named {args.inject_part!r}", file=sys.stderr)
            return 2
        inject_defect(target.data, args.inject)
        print(f"injected {args.inject} into {args.inject_part}")
    code = check_valve(parts)
    if code:
        return code

    if args.output:
        rcode = render_still(parts, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("mesh-hygiene-audit OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
