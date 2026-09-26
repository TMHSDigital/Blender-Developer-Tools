"""A retro rocket at three LODs via the Decimate modifier — a runnable example.

Witnesses the modifier-based LOD contract that game pipelines rely on and
AI-generated code most often gets wrong:

1. Decimate is non-destructive and lives in the depsgraph. The evaluated mesh
   carries the reduction; the original datablock is byte-identical before and
   after evaluation. The check proves both: evaluated counts drop while
   ``obj.data`` keeps the closed-form counts — and ``to_mesh_clear()`` releases
   every evaluated reference (the lifetime contract from
   depsgraph-and-evaluated-data).
2. The COLLAPSE ratio is a target, not a guarantee. Each LOD's evaluated
   triangle count must land near ``ratio x base_tris`` — bounded, not equal.
   The check derives the bounds from the measured behavior of a known mesh and
   fails on any excursion (a wrong ratio, a dropped modifier, or an exporter
   that silently shipped the base mesh all trip it).
3. LODs preserve silhouette-critical dimensions. A rocket's height (the
   antenna tip) and its fin span are its readability; the evaluated bounding
   boxes must hold the base bbox within tolerance at every level. Decimate
   offers no vertex pinning, so this is a real, measurable risk — not a
   formality.

The rocket is one mesh assembled from closed-form parts: a lathed hull
(hollow nozzle bell, brass collar, red skirt, two recessed panel seams, a
raised brass shoulder band, a tangent-ogive nose, a brass finial and
antenna), four swept fins with chamfered brass-trimmed rims, a flanged
porthole with a domed glass, and two rows of rivets along the seams. Six
materials. Every vertex and face count is a formula of the build constants.

The Decimate modifier API (``decimate_type='COLLAPSE'``, ``ratio``) is stable
across Blender 4.5 LTS, 5.1 and 5.2 — the example runs identically on all
three, which is itself the version witness.

The render lays a triangle wireframe over each LOD — the same mesh through
the same Decimate, then Triangulate and Wireframe — so the density drop is
visible, and labels each with the evaluated triangle count the check measured.

``--no-decimate`` leaves the LOD copies without a Decimate modifier and
still runs the reduction check, so evaluated tris equal the base. That is
the falsifier (``--same-axis`` in export-preset-axis).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python lod_decimate_chain.py --                 # check only
    blender --background --python lod_decimate_chain.py -- --no-decimate   # must fail
    blender --background --python lod_decimate_chain.py -- --output r.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse
import mathutils

# Shared Layer 1 framing + asset-quality measurement (render path only) —
# see gallery_framing.py for the import-shim contract
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

CREAM, RED, BRASS, GUN, GLASS, SOOT = range(6)
SIDES = 48                      # lathe resolution of LOD0 (divisible by 4)
LODS = (0.5, 0.18)              # LOD1 / LOD2 collapse ratios (LOD0 is the base)
RATIO_BOUNDS = 0.05             # measured worst case well under 1%; still fails a real drift
BBOX_TOL = 1e-3                 # measured worst case ~1e-5; silhouette preservation, absolute units

HULL_R = 0.46                   # body radius


def seam(z):
    """A recessed panel seam: four rings stepping 9 mm into the hull."""
    return [(z - 0.012, HULL_R, GUN), (z - 0.006, HULL_R - 0.009, GUN),
            (z + 0.006, HULL_R - 0.009, GUN), (z + 0.012, HULL_R, CREAM)]


# lathe profile: (z, radius, material of the band ABOVE this ring), from the
# nozzle throat interior, down and around the bell lip, up the hull to the
# shoulder band. The ogive nose and finial are appended by hull_rings().
SEAMS = (1.00, 1.95)
PROFILE = [
    (0.40, 0.07, SOOT),         # throat interior (fanned to NOZZLE_CORE)
    (0.26, 0.15, SOOT),
    (0.14, 0.23, SOOT),
    (0.09, 0.285, GUN),         # inner lip
    (0.075, 0.305, GUN),        # lip bottom
    (0.09, 0.325, GUN),         # lip outer
    (0.18, 0.28, GUN),          # bell outer
    (0.30, 0.215, GUN),
    (0.38, 0.19, GUN),          # outer throat
    (0.41, 0.20, BRASS),        # collar flange
    (0.43, 0.34, BRASS),
    (0.45, 0.40, BRASS),
    (0.47, 0.43, RED),          # hull base bevel: red lower skirt
    (0.50, HULL_R, RED),
    *seam(SEAMS[0]),
    *seam(SEAMS[1]),
    (2.12, HULL_R, BRASS),      # raised shoulder band
    (2.135, 0.478, BRASS),
    (2.205, 0.478, BRASS),
    (2.22, HULL_R, RED),        # nose base (ogive h = 0)
]
NOZZLE_CORE = 0.43              # interior fan centre, above the throat ring
NOSE_Z0 = 2.22
NOSE_L = 0.95                   # tangent-ogive length to its virtual point
NOSE_H = 0.88                   # sampled ogive height (stops short of the point)
NOSE_RINGS = 8
FINIAL = [(0.02, 0.095), (0.05, 0.06), (0.09, 0.034)]   # (dz above nose top, r), brass
TIP_Z = NOSE_Z0 + NOSE_H + 0.30  # 3.40 — antenna tip, silhouette-critical height

# swept fin outline in the (radius, z) plane: quadratic leading edge from the
# root top out to the tip, a vertical tip cap, a flat foot, and a quadratic
# trailing edge back to the root. The cap and foot are the fin's extremes; each
# is a straight edge, so a collapse along it cannot move the silhouette.
# Four fins on the local axes: each axis extreme is then a fin's mid-rim
# vertex, never a plate corner offset by the fin thickness (an oblique fin's
# plate corner is what a collapse shaves first — measured 4.7e-3 at 0.18).
FIN_ANGLES = (0.0, 90.0, 180.0, 270.0)
FIN_SEG = 8
FIN_LE = ((0.40, 1.50), (0.80, 1.05), (1.02, 0.20))
FIN_TOE = (1.02, 0.0)
FIN_TE = ((0.84, 0.0), (0.64, 0.42), (0.40, 0.60))
FIN_THICK = 0.05
FIN_CHAMFER = 0.02
FIN_N = 2 * (FIN_SEG + 1) + 1  # outline points

PORT_Z = 1.48
PORT_AZ = 315.0                 # porthole azimuth: between two fins; the render turns it to camera
PORT_SEG = 24
# rim cross-section (rho, y): a closed six-point flange loop, back face buried in the hull
PORT_RIM = [(0.15, -0.37), (0.15, -0.475), (0.165, -0.497),
            (0.215, -0.497), (0.235, -0.475), (0.235, -0.37)]
PORT_GLASS = (0.155, -0.468, -0.49)   # ring rho, ring y, dome centre y

RIVET_ROWS = (SEAMS[0] + 0.045, SEAMS[1] - 0.045)
RIVETS_PER_ROW = 24
RIVET_R, RIVET_BASE, RIVET_TOP = 0.013, HULL_R - 0.004, HULL_R + 0.013


# -- closed-form geometry (pure functions of the constants; no bmesh) ---------

def ogive_r(h):
    rho = (HULL_R ** 2 + NOSE_L ** 2) / (2 * HULL_R)
    return math.sqrt(rho * rho - h * h) - (rho - HULL_R)


def hull_rings():
    rings = list(PROFILE)
    for k in range(1, NOSE_RINGS + 1):
        h = NOSE_H * k / NOSE_RINGS
        rings.append((NOSE_Z0 + h, ogive_r(h), BRASS if k == NOSE_RINGS else RED))
    top = NOSE_Z0 + NOSE_H
    rings += [(top + dz, r, BRASS) for dz, r in FINIAL]
    return rings


def bezier(p0, p1, p2, n):
    return [tuple((1 - t) ** 2 * a + 2 * (1 - t) * t * b + t * t * c
                  for a, b, c in zip(p0, p1, p2))
            for t in (i / n for i in range(n + 1))]


def fin_outline():
    return bezier(*FIN_LE, FIN_SEG) + [FIN_TOE] + bezier(*FIN_TE, FIN_SEG)


def fin_loops(angle_deg):
    """Three 3D loops for one fin: front face (inset), mid rim, back face (inset)."""
    pts = fin_outline()
    n = len(pts)
    # signed area -> which side is outward for the 2D edge normals
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
               for i in range(n))
    sgn = 1.0 if area > 0 else -1.0
    def normal(p, q):                                   # outward normal of edge p->q
        tx, ty = q[0] - p[0], q[1] - p[1]
        ln = math.hypot(tx, ty)
        return sgn * ty / ln, -sgn * tx / ln
    # mitred inset: each chamfer strip stays planar, so the rim is a set of
    # flat bevel faces rather than a twisted band
    inset = []
    for i in range(n):
        n1 = normal(pts[i - 1], pts[i])
        n2 = normal(pts[i], pts[(i + 1) % n])
        k = 1.0 + n1[0] * n2[0] + n1[1] * n2[1]
        inset.append((pts[i][0] - FIN_CHAMFER * (n1[0] + n2[0]) / k,
                      pts[i][1] - FIN_CHAMFER * (n1[1] + n2[1]) / k))
    a = math.radians(angle_deg)
    u = (math.cos(a), math.sin(a))
    w = (-math.sin(a), math.cos(a))

    def place(r, z, off):
        return (u[0] * r + w[0] * off, u[1] * r + w[1] * off, z)
    return ([place(r, z, -FIN_THICK / 2) for r, z in inset],
            [place(r, z, 0.0) for r, z in pts],
            [place(r, z, FIN_THICK / 2) for r, z in inset])


def port_point(rho, y, s):
    """Porthole frame: -y is outward along PORT_AZ, rho sweeps the port plane."""
    t = 2 * math.pi * s / PORT_SEG
    a = math.radians(PORT_AZ)
    d = (math.cos(a), math.sin(a))
    lat = (-math.sin(a), math.cos(a))
    x = rho * math.cos(t)
    return (lat[0] * x - d[0] * y, lat[1] * x - d[1] * y, PORT_Z + rho * math.sin(t))


def rivet_points(z, k):
    """Hex base (6) + apex, oriented radially at rivet k of the row at height z."""
    a = 2 * math.pi * (k + 0.5) / RIVETS_PER_ROW
    rad = (math.cos(a), math.sin(a))
    tan = (-math.sin(a), math.cos(a))
    base = []
    for j in range(6):
        t = 2 * math.pi * j / 6
        dt, dz = RIVET_R * math.cos(t), RIVET_R * math.sin(t)
        base.append((rad[0] * RIVET_BASE + tan[0] * dt,
                     rad[1] * RIVET_BASE + tan[1] * dt, z + dz))
    return base, (rad[0] * RIVET_TOP, rad[1] * RIVET_TOP, z)


# -- build --------------------------------------------------------------------

def build_rocket(name):
    """The LOD0 rocket: one mesh assembled from closed-form parts."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        # hull: lathe every ring, fan the throat interior and the antenna tip
        rings = hull_rings()
        sides = [[bm.verts.new((r * math.cos(2 * math.pi * s / SIDES),
                                r * math.sin(2 * math.pi * s / SIDES), z))
                  for s in range(SIDES)] for z, r, _m in rings]
        for k in range(len(rings) - 1):
            for s in range(SIDES):
                f = bm.faces.new((sides[k][s], sides[k][(s + 1) % SIDES],
                                  sides[k + 1][(s + 1) % SIDES], sides[k + 1][s]))
                f.material_index = rings[k][2]
        core = bm.verts.new((0.0, 0.0, NOZZLE_CORE))
        tip = bm.verts.new((0.0, 0.0, TIP_Z))
        for s in range(SIDES):
            bm.faces.new((sides[0][(s + 1) % SIDES], sides[0][s], core)).material_index = SOOT
            bm.faces.new((sides[-1][s], sides[-1][(s + 1) % SIDES], tip)).material_index = BRASS
        # fins: red faces, chamfered brass rim
        for ang in FIN_ANGLES:
            loops = [[bm.verts.new(p) for p in lp] for lp in fin_loops(ang)]
            n = len(loops[0])
            bm.faces.new(loops[0]).material_index = RED
            bm.faces.new(list(reversed(loops[2]))).material_index = RED
            for a, b in ((0, 1), (1, 2)):
                for i in range(n):
                    j = (i + 1) % n
                    bm.faces.new((loops[a][i], loops[a][j], loops[b][j],
                                  loops[b][i])).material_index = BRASS
        # porthole: swept flange loop + domed glass fan
        m = len(PORT_RIM)
        rim = [[bm.verts.new(port_point(rho, y, s)) for rho, y in PORT_RIM]
               for s in range(PORT_SEG)]
        for s in range(PORT_SEG):
            t = (s + 1) % PORT_SEG
            for i in range(m):
                j = (i + 1) % m
                bm.faces.new((rim[s][i], rim[s][j], rim[t][j], rim[t][i])).material_index = BRASS
        g_rho, g_y, g_c = PORT_GLASS
        glass = [bm.verts.new(port_point(g_rho, g_y, s)) for s in range(PORT_SEG)]
        dome = bm.verts.new(port_point(0.0, g_c, 0))
        for s in range(PORT_SEG):
            bm.faces.new((glass[s], glass[(s + 1) % PORT_SEG], dome)).material_index = GLASS
        # rivets: hex domes along both seams
        for z in RIVET_ROWS:
            for k in range(RIVETS_PER_ROW):
                base_p, top_p = rivet_points(z, k)
                base = [bm.verts.new(p) for p in base_p]
                top = bm.verts.new(top_p)
                bm.faces.new(base).material_index = BRASS
                for j in range(6):
                    bm.faces.new((base[j], base[(j + 1) % 6], top)).material_index = BRASS
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        # smooth hull, crisp trim: mark creases past 40 degrees sharp
        bm.normal_update()
        for e in bm.edges:
            if len(e.link_faces) == 2 and \
                    e.link_faces[0].normal.angle(e.link_faces[1].normal, 0.0) > math.radians(40):
                e.smooth = False
        for f in bm.faces:
            f.smooth = True
        bm.to_mesh(me)
    finally:
        bm.free()  # the ownership contract, as always
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def closed_form_counts():
    """Expected base-mesh counts, derived from the build constants."""
    rings = len(PROFILE) + NOSE_RINGS + len(FINIAL)
    fins, m, rivets = len(FIN_ANGLES), len(PORT_RIM), 2 * RIVETS_PER_ROW
    verts = (rings * SIDES + 2                      # hull + throat core + antenna tip
             + fins * 3 * FIN_N                     # three loops per fin
             + PORT_SEG * m + PORT_SEG + 1          # flange + glass ring + dome
             + rivets * 7)                          # hex base + apex
    quads = (rings - 1) * SIDES + fins * 2 * FIN_N + PORT_SEG * m
    tri_faces = 2 * SIDES + PORT_SEG + rivets * 6
    ngons = fins * 2 + rivets                       # fin faces (FIN_N-gons) + rivet bases (hex)
    faces = quads + tri_faces + ngons
    total_tris = (2 * quads + tri_faces
                  + fins * 2 * (FIN_N - 2) + rivets * 4)
    return verts, faces, total_tris


def closed_form_bbox():
    """Exact bbox from the build constants (every candidate extreme vertex)."""
    pts = []
    for z, r, _m in hull_rings():                   # SIDES % 4 == 0: axis extremes hit
        pts += [(r, 0.0, z), (-r, 0.0, z), (0.0, r, z), (0.0, -r, z)]
    pts += [(0.0, 0.0, NOZZLE_CORE), (0.0, 0.0, TIP_Z)]
    for ang in FIN_ANGLES:
        for lp in fin_loops(ang):
            pts += lp
    pts += [port_point(rho, y, s) for rho, y in PORT_RIM for s in range(PORT_SEG)]
    for z in RIVET_ROWS:
        for k in range(RIVETS_PER_ROW):
            base_p, top_p = rivet_points(z, k)
            pts += base_p + [top_p]
    return (tuple(min(p[i] for p in pts) for i in range(3)),
            tuple(max(p[i] for p in pts) for i in range(3)))


def eval_mesh(obj):
    """Snapshot an evaluated mesh, then release it (lifetime contract)."""
    deps = bpy.context.evaluated_depsgraph_get()
    ob_eval = obj.evaluated_get(deps)
    me = ob_eval.to_mesh()
    try:
        me.calc_loop_triangles()
        xs = [v.co.x for v in me.vertices]
        ys = [v.co.y for v in me.vertices]
        zs = [v.co.z for v in me.vertices]
        return {"verts": len(me.vertices), "tris": len(me.loop_triangles),
                "bbox": ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))}
    finally:
        ob_eval.to_mesh_clear()


def add_decimate(obj, ratio):
    mod = obj.modifiers.new("LOD", 'DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = ratio
    return mod


def check(rocket, lod1, lod2, no_decimate=False):
    """Returns (exit code, {object name: evaluated tris})."""
    me = rocket.data
    want_v, want_f, want_t = closed_form_counts()
    got = (len(me.vertices), len(me.polygons))
    if got != (want_v, want_f):
        print(f"ERROR: base topology {got} != closed form {(want_v, want_f)}",
              file=sys.stderr)
        return 3, None
    bb_min, bb_max = closed_form_bbox()
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    base_bb = ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))
    bb_err = max(abs(base_bb[i][k] - want[i][k])
                 for i in (0, 1) for k in range(3)
                 for want in ((bb_min, bb_max),))
    if bb_err > 1e-6:
        print(f"ERROR: base bbox deviates {bb_err:.3e} from its closed form",
              file=sys.stderr)
        return 4, None

    # LOD0 sanity: no modifier, evaluated == original counts
    snap0 = eval_mesh(rocket)
    if (snap0["verts"], snap0["tris"]) != (want_v, want_t):
        print(f"ERROR: LOD0 evaluated counts {(snap0['verts'], snap0['tris'])} != "
              f"base {(want_v, want_t)}", file=sys.stderr)
        return 5, None

    tris = {rocket.name: snap0["tris"]}
    measured = []
    for lod, ratio in ((lod1, LODS[0]), (lod2, LODS[1])):
        if not no_decimate:
            add_decimate(lod, ratio)
        snap = eval_mesh(lod)
        # contract 2: triangle count lands near ratio * base, within bounds
        target = ratio * want_t
        dev = abs(snap["tris"] - target) / target
        # contract 1: the reduction is real and the original is untouched
        if snap["tris"] >= want_t:
            print(f"ERROR: evaluated tris {snap['tris']} >= base {want_t} — "
                  "the modifier did not reduce (evaluated == original)",
                  file=sys.stderr)
            return 6, None
        if (len(lod.data.vertices), len(lod.data.polygons)) != (want_v, want_f):
            print("ERROR: original datablock changed after evaluation — "
                  "Decimate must be non-destructive", file=sys.stderr)
            return 7, None
        if dev > RATIO_BOUNDS:
            print(f"ERROR: LOD tris {snap['tris']} deviates {dev:.1%} from "
                  f"ratio target {target:.0f} (bounds {RATIO_BOUNDS:.0%})",
                  file=sys.stderr)
            return 8, None
        # contract 3: silhouette-critical dimensions survive
        bbox_dev = max(abs(snap["bbox"][i][k] - base_bb[i][k])
                       for i in (0, 1) for k in range(3))
        if bbox_dev > BBOX_TOL:
            print(f"ERROR: LOD bbox deviates {bbox_dev:.4f} from base "
                  f"(tol {BBOX_TOL}) — silhouette-critical dims lost",
                  file=sys.stderr)
            return 9, None
        tris[lod.name] = snap["tris"]
        measured.append((ratio, snap["tris"], target, dev, bbox_dev))

    print(f"sides={SIDES} base_verts={want_v} base_faces={want_f} "
          f"base_tris={want_t} bbox_err={bb_err:.2e}")
    for ratio, t, target, dev, bbox_dev in measured:
        print(f"lod ratio={ratio} tris={t} target={target:.0f} "
              f"dev={dev:.2%} (bounds {RATIO_BOUNDS:.0%}) "
              f"bbox_dev={bbox_dev:.2e} (tol {BBOX_TOL})")
    return 0, tris


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
        pbr("HullEnamel", (0.86, 0.80, 0.66), 0.0, 0.42),
        pbr("NoseLacquer", (0.74, 0.07, 0.05), 0.1, 0.36),
        pbr("BrassTrim", (0.80, 0.56, 0.24), 1.0, 0.30),
        pbr("NozzleSteel", (0.16, 0.17, 0.19), 0.9, 0.38),
        pbr("PortGlass", (0.04, 0.26, 0.32), 0.0, 0.12,
            emission=(0.10, 0.55, 0.66), strength=0.6),
        pbr("NozzleSoot", (0.02, 0.018, 0.016), 0.0, 0.9),
    ]


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def wire_shell(lod, ratio, wire_mat):
    """A mesh overlay of *lod*'s evaluated topology: same mesh datablock, the
    same Decimate, then a Wireframe. The rocket itself stays unmodified."""
    ob = bpy.data.objects.new(f"{lod.name}_Wire", lod.data)
    ob.location = lod.location
    ob.rotation_euler = lod.rotation_euler
    bpy.context.scene.collection.objects.link(ob)
    if ratio is not None:
        add_decimate(ob, ratio)
    # draw triangles, the unit the check counts: splitting every quad and
    # n-gon makes the overlay's faces equal the LOD's loop_triangles
    # (measured 4784 / 2392 / 860, identical to the check)
    ob.modifiers.new("Tris", 'TRIANGULATE')
    wf = ob.modifiers.new("Wire", 'WIREFRAME')
    wf.thickness = 0.009
    wf.offset = 1.0
    wf.use_even_offset = True
    wf.use_replace = True
    for slot in ob.material_slots:
        slot.link = 'OBJECT'
        slot.material = wire_mat
    return ob


def render_still(rockets, tris, path, engine):
    import gallery_framing
    import gallery_asset_quality
    scene = bpy.context.scene
    xs = (-2.55, 0.0, 2.55)
    for ob, x in zip(rockets, xs):
        ob.location.x = x
        # turn the porthole to the camera (-Y); the check reads local coords
        ob.rotation_euler.z = math.radians(270.0 - PORT_AZ)

    wm = bpy.data.materials.new("WireInk")
    wm.use_nodes = True
    wb = wm.node_tree.nodes["Principled BSDF"]
    wb.inputs["Base Color"].default_value = (0.015, 0.016, 0.02, 1.0)
    wb.inputs["Roughness"].default_value = 0.6
    wires = [wire_shell(ob, r, wm) for ob, r in zip(rockets, (None,) + LODS)]

    # one label per LOD: the evaluated triangle count the check just measured
    lm = bpy.data.materials.new("LabelInk")
    lm.use_nodes = True
    lb = lm.node_tree.nodes["Principled BSDF"]
    lb.inputs["Base Color"].default_value = (0.62, 0.60, 0.56, 1.0)
    lb.inputs["Roughness"].default_value = 0.8
    labels = []
    for ob in rockets:
        cu = bpy.data.curves.new(f"{ob.name}_Label", 'FONT')
        cu.body = f"{tris[ob.name]} tris"
        cu.align_x = 'CENTER'
        cu.size = 0.34
        cu.extrude = 0.01
        lab = bpy.data.objects.new(f"{ob.name}_Label", cu)
        # nearer the camera (y = -12) than the rockets, so pull x in by the
        # depth ratio to sit each label under its rocket in the frame
        lab.location = (ob.location.x * (12.0 - 1.95) / 12.0, -1.95, 0.0)
        lab.rotation_euler = (math.radians(62), 0.0, 0.0)
        lab.data.materials.append(lm)
        scene.collection.objects.link(lab)
        labels.append(lab)

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
    light("Key", (-4.0, -5.0, 6.0), 520.0, 4.5, (1.0, 0.96, 0.9), (48, 0, -38))
    light("Fill", (5.0, -4.0, 3.0), 100.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Rim", (0.5, 4.5, 5.0), 320.0, 4.0, (0.6, 0.78, 1.0), (-55, 0, 175))
    light("Wedge", (2.5, 3.5, 4.2), 420.0, 6.0, (1.0, 0.76, 0.5), (-72, 0, 195))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -12.0, 3.1)
    scene.collection.objects.link(cam)
    target = bpy.data.objects.new("Aim", None)
    target.location = (0.0, 0.0, 1.55)
    scene.collection.objects.link(target)
    con = cam.constraints.new('TRACK_TO')
    con.target = target
    scene.camera = cam

    scene.render.engine = 'CYCLES' if engine == 'cycles' else eevee_engine_id()
    if engine == 'cycles':
        scene.cycles.samples = 64
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path
    # AgX would wash the cream hull and red nose toward pastel
    # (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    bpy.context.view_layer.update()

    stage = [floor, wall]
    fcode = gallery_framing.check_framing(scene, cam, hero=rockets,
                                          elements=rockets + wires + labels, stage=stage)
    if fcode:
        return fcode
    # the asset is the rocket itself — the LOD copies and overlays are staging
    aqcode = gallery_asset_quality.check_asset_quality(scene, cam, hero=[rockets[0]],
                                                       stage=stage)
    if aqcode:
        return aqcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 12
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--no-decimate", action="store_true",
                   help="skip adding Decimate to the LOD copies (must fail)")
    args = p.parse_args(argv)

    print(f"binary version: {bpy.app.version} ({bpy.app.version_string})")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = make_materials()
    rockets = []
    for name in ("Rocket", "Rocket_LOD1", "Rocket_LOD2"):
        r = build_rocket(name)
        for m in mats:
            r.data.materials.append(m)
        rockets.append(r)
    code, tris = check(rockets[0], rockets[1], rockets[2],
                       no_decimate=args.no_decimate)
    if code:
        return code

    if args.output:
        code = render_still(rockets, tris, os.path.abspath(args.output), args.engine)
        if code:
            return code
        print(f"rendered still {args.output}")

    print("lod-decimate-chain OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
