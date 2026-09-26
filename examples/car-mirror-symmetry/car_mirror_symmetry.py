"""A stylized hatchback built as one half and completed by the Mirror modifier
— a runnable example.

Witnesses the Mirror + depsgraph contract from depsgraph-and-evaluated-data:
the original datablock keeps only the authored half, while the depsgraph
carries the mirrored whole. Closed forms: evaluated vertex count is exactly
2n - c (c = welded centerline verts), every evaluated vertex has an exact
partner at negated X, the merge threshold actually welds (no doubled
centerline), the evaluated shell is watertight with Euler characteristic 2,
and every separate part (wheels, lamps, grille, mirrors, handles) mirrors about
an object origin sitting ON the symmetry plane. Failure is dramatically
visible: a car with one side missing.

``--no-mirror`` turns off the Mirror X axis on every mirrored object and
still runs the evaluated-count check, so the half-car fails ``2n − c``.
That is the falsifier (``--same-axis`` in export-preset-axis).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python car_mirror_symmetry.py --                 # check only
    blender --background --python car_mirror_symmetry.py -- --no-mirror     # must fail
    blender --background --python car_mirror_symmetry.py -- --output c.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector
from mathutils.bvhtree import BVHTree

# --- closed-form construction parameters -----------------------------------
# The half body is a loft: one 13-point half-ring per station along Y (front
# at -Y), from the bottom centerline (p0) out and up to the roof centerline
# (p12). Station Ys are placed, not sampled: every panel edge the design
# needs (arch openings, cowl, B-pillar, roof end, hatch base) is a station.
RING = 13
AXLES = (-1.22, 1.22)          # front / rear axle Y
TIRE_R = 0.33                  # axle height == tire radius: wheels rest on z=0
ARCH_R = 0.40                  # wheel-arch opening radius about the axle
Y_NOSE, Y_TAIL = -1.95, 1.90
Y_COWL, Y_ROOF0 = -0.60, 0.02  # windshield base / top
Y_ROOF1, Y_HATCH = 1.30, 1.78  # roof end / hatch-glass base
Y_BPILLAR = (0.18, 0.30)
Y_CPILLAR = 1.05


def _stations():
    ys = {Y_NOSE, -1.93, -1.89, -1.83, -1.71,               # rounded nose
          -0.70, Y_COWL, -0.44, -0.28, -0.13, Y_ROOF0,       # windshield
          Y_BPILLAR[0], Y_BPILLAR[1], 0.50, 0.70, Y_CPILLAR,
          Y_ROOF1, 1.74, Y_HATCH, 1.83, 1.87, Y_TAIL}        # hatch + tail
    for a in AXLES:                                          # arch openings
        ys.add(round(a - ARCH_R - 0.03, 4))
        ys.add(round(a + ARCH_R + 0.03, 4))
        for s in range(13):
            ys.add(round(a - ARCH_R * math.cos(math.pi * s / 12), 4))
    return sorted(ys)


STATION_Y = _stations()
N_ST = len(STATION_Y)                            # 52
N_BODY = N_ST * RING                             # 676
F_BODY = (N_ST - 1) * (RING - 1) + 2             # 612 quads + 2 caps
E_BODY = (N_ST * (RING - 1)                      # ring edges
          + (N_ST - 1) * RING                    # longitudinal edges
          + 2)                                   # cap closing edges
CENTERLINE = N_ST * 2                            # p0 + p12 per station: 104

WHEEL_SEG = 30                 # 5 spokes x 6 segments
WHEEL_RINGS = [                # (x, radius): tire bead -> tread -> rim -> hub cap
    (0.600, 0.200), (0.605, 0.285), (0.625, 0.322), (0.660, 0.330),
    (0.840, 0.330), (0.865, 0.322), (0.882, 0.290), (0.886, 0.238),
    (0.880, 0.224), (0.868, 0.206), (0.868, 0.086), (0.874, 0.064),
    (0.882, 0.040),
]
DISH_RINGS = (9, 10)           # rings whose gap verts recess to form spokes
DISH_GAP_X = 0.820
N_WHEEL = len(WHEEL_RINGS) * WHEEL_SEG           # 390
F_WHEEL = (len(WHEEL_RINGS) - 1) * WHEEL_SEG + 1 # strips + hubcap ngon

POD_P = 16                     # profile points per pod ring (lamps, grille, mirror)

MERGE_THRESHOLD = 1.0e-3
TOL_SYMM = 2.0e-5    # evaluated partner deviation (float32 storage; mirror copies exact)
TOL_BBOX = 1.0e-5    # |min.x + max.x| on the evaluated body
TOL_PLANE = 1.0e-6   # |x| this small counts as on the symmetry plane

MATERIALS = ("Paint", "Glass", "Trim", "Chrome", "Tire", "Rim",
             "Headlamp", "Taillamp")


# --- profile functions (all closed-form in y) ------------------------------
def _clamp(t):
    return 0.0 if t < 0.0 else 1.0 if t > 1.0 else t


def _ramp(y, y0, y1):
    return _clamp((y - y0) / (y1 - y0))


def _interp(y, pts):
    if y <= pts[0][0]:
        return pts[0][1]
    for (y0, v0), (y1, v1) in zip(pts, pts[1:]):
        if y <= y1:
            t = (y - y0) / (y1 - y0)
            t = t * t * (3.0 - 2.0 * t)          # smoothstep between keys
            return v0 + (v1 - v0) * t
    return pts[-1][1]


def _round(t):
    """Quarter-circle rounding: 0 at the very end, 1 once the body is full."""
    t = _clamp(t)
    return math.sqrt(max(0.0, 1.0 - (1.0 - t) ** 2))


def cabin(y):
    """0 on hood / rear deck, 1 under the roof, linear through the glass."""
    return min(_ramp(y, Y_COWL, Y_ROOF0), 1.0 - _ramp(y, Y_ROOF1, Y_HATCH))


def half_ring(y):
    """One 13-point half cross-section at y, bottom centerline -> roof centerline."""
    rn = min(_round((y - Y_NOSE) / 0.24), _round((Y_TAIL - y) / 0.16))
    f = 0.70 + 0.30 * rn                     # plan-view corner rounding
    br = 0.06 * (1.0 - rn)                   # bottom tucks up at the ends
    td = 0.035 * (1.0 - rn)                  # top rolls down at the ends
    flare = max(math.exp(-((y - a) / 0.42) ** 2) for a in AXLES)
    w = (0.84 + 0.04 * flare) * f            # half width, flared over wheels
    zbelt = _interp(y, [(-1.95, 0.74), (-1.60, 0.80), (-1.22, 0.84),
                        (-0.60, 0.915), (0.50, 0.945), (1.30, 0.955),
                        (1.90, 0.935)]) - td
    ztop = (_interp(y, [(-1.95, 0.80), (-1.60, 0.86), (-1.00, 0.91),
                        (-0.60, 0.965)]) if y < 0.5 else
            _interp(y, [(1.30, 1.02), (1.78, 1.01), (1.90, 0.975)])) - td
    zroof = _interp(y, [(-0.60, 1.32), (0.02, 1.34), (0.60, 1.36),
                        (1.30, 1.33)])
    crease = zbelt - 0.15
    zfloor = 0.20 + br

    d = min((abs(y - a) for a in AXLES))
    if d <= ARCH_R + 1e-9:                   # inside a wheel-arch opening
        za = TIRE_R + math.sqrt(max(0.0, ARCH_R ** 2 - d * d))
        lower = [(0.50, za), (0.93 * w, za), (0.99 * w, za), (w, za + 0.06),
                 (1.01 * w, max(crease, za + 0.10))]   # cladding flares out
    else:
        lower = [(0.50, zfloor), (0.95 * w, 0.24 + br), (0.975 * w, 0.28 + br),
                 (0.975 * w, 0.36 + 0.5 * br), (1.01 * w, crease)]  # p5: character line

    c = cabin(y)
    wr = 0.70 * w
    cab = [(0.93 * w, zbelt + 0.03), (wr + 0.05, zroof - 0.09),
           (wr, zroof - 0.035), (0.80 * wr, zroof), (0.42 * wr, zroof + 0.018),
           (0.0, zroof + 0.022)]
    hood = []
    for fx in (0.91, 0.80, 0.66, 0.50, 0.27, 0.0):
        hood.append((fx * w, ztop - (ztop - zbelt) * (fx / 0.965) ** 2))
    upper = [(h[0] + (k[0] - h[0]) * c, h[1] + (k[1] - h[1]) * c)
             for h, k in zip(hood, cab)]

    pts = [(0.0, zfloor)] + lower + [(0.965 * w, zbelt)] + upper
    return [(x, y, z) for x, z in pts]


def _newell(pts):
    nx = ny = nz = 0.0
    for i, p in enumerate(pts):
        q = pts[(i + 1) % len(pts)]
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    n = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (nx / n, ny / n, nz / n)


def _link_mirrored(name, me):
    """Object at the world origin (ON the plane) + Mirror X with merge."""
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    m = ob.modifiers.new("MirrorHalf", 'MIRROR')
    m.use_axis[0] = True
    m.use_mirror_merge = True
    m.merge_threshold = MERGE_THRESHOLD
    return ob


def pod(name, center, normal, half_w, half_h, rings, band_mats, cap_mat,
        up=(0.0, 0.0, 1.0), expo=4.0, split=False):
    """Superellipse pod: len(rings) rings, capped at both ends.
    rings = [(scale, depth along normal)], back to front.

    Offset pod (split=False): POD_P points per closed ring, entirely off the
    plane. Closed form n = R * POD_P, f = (R - 1) * POD_P + 2, welds 0.
    Split pod (split=True, center ON the plane, normal in the plane): only
    the +X half profile, POD_P/2 + 1 points from bottom to top with both
    ends exactly at x = 0 — the Mirror weld completes it into one part.
    Closed form n = R * (POD_P/2 + 1), f = (R - 1) * POD_P/2 + 2, welds 2R.
    Either way the object origin stays on the plane.
    Returns (object, n_half, f_half, welded)."""
    n = Vector(normal).normalized()
    u = Vector(up).cross(n).normalized()
    v = n.cross(u).normalized()
    ctr = Vector(center)
    npts = POD_P // 2 + 1 if split else POD_P
    nfac = POD_P // 2 if split else POD_P
    me = bpy.data.meshes.new(name + "Half")
    bm = bmesh.new()
    try:
        rv = []
        for scale, depth in rings:
            ring = []
            for s in range(npts):
                a = (math.pi * (s / (npts - 1) - 0.5) if split
                     else 2.0 * math.pi * s / POD_P)
                ca, sa = math.cos(a), math.sin(a)
                if split and s in (0, npts - 1):
                    ca = 0.0                     # exactly on the plane
                px = math.copysign(abs(ca) ** (2.0 / expo), ca) * half_w * scale
                py = math.copysign(abs(sa) ** (2.0 / expo), sa) * half_h * scale
                ring.append(bm.verts.new(ctr + u * px + v * py + n * depth))
            rv.append(ring)
        bands = []
        for b in range(len(rings) - 1):
            for s in range(nfac):
                f = bm.faces.new((rv[b][s], rv[b][(s + 1) % npts],
                                  rv[b + 1][(s + 1) % npts], rv[b + 1][s]))
                f.material_index = band_mats[b]
                bands.append(f)
        back = bm.faces.new(rv[0])
        back.material_index = band_mats[0]
        front = bm.faces.new(rv[-1])
        front.material_index = cap_mat
        if not split:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)  # closed: outward
        else:  # open along the plane: orient explicitly
            side = bands[nfac // 2]          # outboard wall of the first band
            if side.normal.dot(u) < 0:
                for f in bands:
                    f.normal_flip()
            if front.normal.dot(n) < 0:
                front.normal_flip()
            if back.normal.dot(n) > 0:
                back.normal_flip()
        bm.to_mesh(me)
    finally:
        bm.free()
    for m in MATERIALS:
        me.materials.append(bpy.data.materials[m])
    ob = _link_mirrored(name, me)
    R = len(rings)
    return ob, R * npts, (R - 1) * nfac + 2, (2 * R if split else 0)


def build_car():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for m in MATERIALS:  # exist in both modes (slot layout is part of the scene)
        bpy.data.materials.new(m)

    # -- half body loft ------------------------------------------------------
    rings = [half_ring(y) for y in STATION_Y]
    me = bpy.data.meshes.new("CarBodyHalf")
    bm = bmesh.new()
    try:
        bv = [[bm.verts.new(co) for co in ring] for ring in rings]
        faces = []
        for i in range(N_ST - 1):
            for k in range(RING - 1):
                faces.append(bm.faces.new(
                    (bv[i][k], bv[i][k + 1], bv[i + 1][k + 1], bv[i + 1][k])))
        caps = [bm.faces.new(bv[0]), bm.faces.new(bv[-1])]
        # winding: a door quad must face +X; flip everything if the loft
        # convention came out inward (mirror does not fix winding)
        mid = N_ST // 2
        probe = [v.co for v in (bv[mid][4], bv[mid][5], bv[mid + 1][5], bv[mid + 1][4])]
        if _newell(probe)[0] < 0:
            for f in faces + caps:
                f.normal_flip()
        # caps must point away from the body (front -Y, rear +Y)
        if _newell([v.co for v in bv[0]])[1] > 0:
            caps[0].normal_flip()
        if _newell([v.co for v in bv[-1]])[1] < 0:
            caps[1].normal_flip()
        bm.to_mesh(me)
        bm.faces.ensure_lookup_table()
        bvh = BVHTree.FromBMesh(bm)  # seats the separate parts on the skin
    finally:
        bm.free()  # the ownership contract from always-free-bmesh

    body = bpy.data.objects.new("CarBody", me)
    bpy.context.collection.objects.link(body)
    mirror = body.modifiers.new("MirrorHalf", 'MIRROR')
    mirror.use_axis[0] = True
    mirror.use_clip = True            # centerline verts cannot leave x=0
    mirror.use_mirror_merge = True    # weld the two halves shut
    mirror.merge_threshold = MERGE_THRESHOLD
    for m in MATERIALS:
        me.materials.append(bpy.data.materials[m])
    _assign_body_materials(body)

    def skin_y(x, z, front=True):
        """Y of the body surface at (x, z), probed along the long axis."""
        o = Vector((x, -5.0 if front else 5.0, z))
        hit = bvh.ray_cast(o, Vector((0.0, 1.0 if front else -1.0, 0.0)))
        return hit[0].y

    def skin_x(y, z):
        """X of the +X flank at (y, z), probed inward from outside."""
        return bvh.ray_cast(Vector((5.0, y, z)), Vector((-1.0, 0.0, 0.0)))[0].x

    # -- wheels: own Mirror each, object origins ON the symmetry plane -------
    mirrored = []
    for y in AXLES:
        wme = bpy.data.meshes.new("WheelHalf")
        bm = bmesh.new()
        try:
            wr = []
            for j, (x, r) in enumerate(WHEEL_RINGS):
                ring = []
                for s in range(WHEEL_SEG):
                    gap = j in DISH_RINGS and s % 6 in (3, 4, 5)
                    a = 2.0 * math.pi * s / WHEEL_SEG
                    ring.append(bm.verts.new((DISH_GAP_X if gap else x,
                                              r * math.cos(a), r * math.sin(a))))
                wr.append(ring)
            strips = []
            for j in range(len(WHEEL_RINGS) - 1):
                for s in range(WHEEL_SEG):
                    f = bm.faces.new((wr[j][s], wr[j][(s + 1) % WHEEL_SEG],
                                      wr[j + 1][(s + 1) % WHEEL_SEG], wr[j + 1][s]))
                    strips.append(f)
                    if j <= 6:
                        f.material_index = MATERIALS.index("Tire")
                    elif 8 <= j <= 10 and s % 6 in (3, 4):
                        f.material_index = MATERIALS.index("Trim")   # spoke gaps
                    else:
                        f.material_index = MATERIALS.index("Rim")
            hub = bm.faces.new(wr[-1])
            hub.material_index = MATERIALS.index("Rim")
            # tread faces point away from the axle; hub cap faces +X
            t = strips[3 * WHEEL_SEG]
            c = t.calc_center_median()
            if t.normal.dot(Vector((0.0, c.y, c.z))) < 0:
                for f in strips:
                    f.normal_flip()
            if hub.normal.x < 0:
                hub.normal_flip()
            bm.to_mesh(wme)
        finally:
            bm.free()
        for m in MATERIALS:
            wme.materials.append(bpy.data.materials[m])
        wheel = _link_mirrored("WheelFront" if y < 0 else "WheelRear", wme)
        wheel.location = (0.0, y, TIRE_R)  # origin on the plane: mirror mirrors DATA
        mirrored.append((wheel, N_WHEEL, F_WHEEL, 0))

    M = MATERIALS.index
    # -- lamps, grille, door mirror: pods seated on the skin, origins on plane
    hx, hz = 0.42, 0.645
    mirrored.append(pod(
        "Headlamp", (hx, skin_y(hx, hz), hz), (0.28, -1.0, 0.06), 0.165, 0.054,
        [(1.0, -0.06), (1.0, 0.016), (0.86, 0.022), (0.50, 0.030)],
        [M("Trim"), M("Chrome"), M("Chrome")], M("Headlamp"), expo=3.2))
    gz = 0.44
    mirrored.append(pod(   # split pod: authored half, welded whole on the plane
        "Grille", (0.0, skin_y(0.15, gz), gz), (0.0, -1.0, 0.0), 0.31, 0.085,
        [(1.0, -0.05), (1.0, 0.022), (0.90, 0.022), (0.90, 0.006)],
        [M("Trim"), M("Chrome"), M("Trim")], M("Trim"), expo=5.0, split=True))
    tx, tz = 0.50, 0.84
    mirrored.append(pod(
        "Taillamp", (tx, skin_y(tx, tz, front=False), tz), (0.30, 1.0, 0.0),
        0.15, 0.055,
        [(1.0, -0.05), (1.0, 0.012), (0.90, 0.018)],
        [M("Trim"), M("Chrome")], M("Taillamp")))
    my = -0.46
    mz = half_ring(my)[6][2] + 0.075
    mirrored.append(pod(
        "DoorMirror", (0.76, my, mz), (1.0, 0.0, 0.0), 0.040, 0.026,
        [(1.0, 0.0), (1.0, 0.09), (1.9, 0.11), (2.1, 0.20), (1.6, 0.235)],
        [M("Trim"), M("Trim"), M("Paint"), M("Paint")], M("Paint"),
        expo=2.6))
    for name, hy in (("DoorHandleFront", 0.02), ("DoorHandleRear", 0.66)):
        hz = half_ring(hy)[5][2] + 0.035    # just under the character line
        mirrored.append(pod(
            name, (skin_x(hy, hz), hy, hz), (1.0, 0.0, 0.0), 0.075, 0.016,
            [(1.0, -0.02), (1.0, 0.010), (0.8, 0.016)],
            [M("Trim"), M("Chrome")], M("Chrome"), up=(0.0, 0.0, 1.0)))

    return {"body": body, "mirrored": mirrored}


def _assign_body_materials(body):
    """Deterministic panel classes by construction position (not hand-picked):
    underbody, rocker and wheel-arch cladding are trim; the ring segment
    between sill and glass top is the side glass under the roof (a trim
    B-pillar interrupts it, paint C-pillar ends it); the drip rail above it
    is trim and becomes the A-pillar through the windshield; the roof bands
    are glass exactly where the cabin factor ramps (windshield, hatch)."""
    PAINT, GLASS, TRIM = (MATERIALS.index(m) for m in ("Paint", "Glass", "Trim"))
    for poly in body.data.polygons:
        i, k = divmod(poly.index, RING - 1)
        if i >= N_ST - 1:            # cap ngons (front/rear fascia)
            poly.material_index = PAINT
            continue
        y0, y1 = STATION_Y[i], STATION_Y[i + 1]
        ym = 0.5 * (y0 + y1)
        cab = cabin(ym) > 1e-6
        if k <= 3:
            poly.material_index = TRIM       # underbody, rocker, arch cladding
        elif k == 7 and cab and ym < Y_CPILLAR:
            in_b = Y_BPILLAR[0] <= ym <= Y_BPILLAR[1]
            poly.material_index = TRIM if in_b else GLASS
        elif k == 8 and cab and ym < Y_CPILLAR:
            poly.material_index = TRIM       # drip rail / A-pillar
        elif k >= 9 and (Y_COWL <= y0 and y1 <= Y_ROOF0
                         or Y_ROOF1 <= y0 and y1 <= Y_HATCH):
            poly.material_index = GLASS      # windshield / hatch glass
        else:
            poly.material_index = PAINT


def _eval_mesh(obj, dg):
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        verts = [(ev.matrix_world @ v.co) for v in me.vertices]
        edges = len(me.edges)
        faces = len(me.polygons)
        yield_v = (verts, edges, faces)
    finally:
        ev.to_mesh_clear()  # no argument: clears this object's evaluated mesh
    return yield_v


def _symmetry_dev(verts, tol_plane):
    """Max deviation between every vertex and its negated-X partner.

    Buckets by rounded (y, z, |x|): on-plane verts must be alone in their
    bucket; off-plane buckets must pair exactly one +X with one -X, and the
    pair's coordinate deltas are the measured error."""
    buckets = {}
    for v in verts:
        key = (round(v.y, 5), round(v.z, 5), round(abs(v.x), 5))
        buckets.setdefault(key, []).append(v)
    dev = 0.0
    lone = 0
    for key, members in buckets.items():
        if key[2] <= tol_plane:
            if len(members) != 1:
                lone += 1
            continue
        pos = [m for m in members if m.x > 0]
        neg = [m for m in members if m.x < 0]
        if len(pos) != 1 or len(neg) != 1:
            lone += 1
            continue
        p, n = pos[0], neg[0]
        dev = max(dev, abs(p.x + n.x), abs(p.y - n.y), abs(p.z - n.z))
    return dev, lone


def check(objs, no_mirror=False):
    if no_mirror:
        for ob in [objs["body"]] + [w for w, *_ in objs["mirrored"]]:
            for mod in ob.modifiers:
                if mod.type == 'MIRROR':
                    mod.use_axis[0] = False

    body = objs["body"]
    me = body.data

    # 1. the original datablock holds ONLY the authored half
    got = (len(me.vertices), len(me.edges), len(me.polygons))
    if got != (N_BODY, E_BODY, F_BODY):
        print(f"ERROR: body datablock {got} != half-model closed form "
              f"{(N_BODY, E_BODY, F_BODY)} — the mirror must live in the "
              f"modifier stack, not in applied data", file=sys.stderr)
        return 3
    c = sum(1 for v in me.vertices if abs(v.co.x) <= TOL_PLANE)
    if c != CENTERLINE:
        print(f"ERROR: {c} authored centerline verts != {CENTERLINE}",
              file=sys.stderr)
        return 4

    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    verts, e_eval, f_eval = _eval_mesh(body, dg)

    # 2. evaluated counts: exactly 2n - c, and watertight Euler 2
    want_v = 2 * N_BODY - CENTERLINE
    if len(verts) != want_v:
        print(f"ERROR: evaluated body has {len(verts)} verts != 2n-c = {want_v} "
              f"— merge is not welding the centerline (doubled seam)", file=sys.stderr)
        return 5
    on_plane = sum(1 for v in verts if abs(v.x) <= TOL_PLANE)
    if on_plane != CENTERLINE:
        print(f"ERROR: {on_plane} evaluated on-plane verts != {CENTERLINE} "
              f"(merge threshold must weld, not duplicate)", file=sys.stderr)
        return 6
    euler = len(verts) - e_eval + f_eval
    if euler != 2:
        print(f"ERROR: evaluated Euler {euler} != 2 — mirrored shell is not a "
              f"closed solid", file=sys.stderr)
        return 7
    bm = bmesh.new()
    try:
        ev = body.evaluated_get(dg)
        ev_me = ev.to_mesh()
        try:
            bm.from_mesh(ev_me)
        finally:
            ev.to_mesh_clear()
        bad = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    finally:
        bm.free()
    if bad:
        print(f"ERROR: {bad} non-manifold edge(s) in the evaluated shell",
              file=sys.stderr)
        return 8

    # 3. every evaluated vertex has an exact negated-X partner
    dev, lone = _symmetry_dev(verts, TOL_PLANE)
    if lone:
        print(f"ERROR: {lone} evaluated vert(s) lack a mirrored partner",
              file=sys.stderr)
        return 9
    if dev > TOL_SYMM:
        print(f"ERROR: mirror partner deviation {dev:.3e} > tol {TOL_SYMM:.1e}",
              file=sys.stderr)
        return 10
    xmin = min(v.x for v in verts)
    xmax = max(v.x for v in verts)
    bbox_asym = abs(xmin + xmax)
    if bbox_asym > TOL_BBOX:
        print(f"ERROR: evaluated bbox asymmetric by {bbox_asym:.3e} "
              f"(tol {TOL_BBOX:.1e})", file=sys.stderr)
        return 11

    # 4. mirrored parts (wheels, lamps, grille, mirrors, handles): each mirrored
    # about an object origin that sits ON the plane — the data is offset,
    # the object is not. Offset parts double exactly (2n); the split grille
    # is authored as a half with `weld` verts on the plane and must weld
    # like the body (2n - weld), or it renders as two grilles.
    part_lines = []
    for w, n_half, f_half, weld in objs["mirrored"]:
        if abs(w.location.x) > TOL_PLANE:
            print(f"ERROR: {w.name} origin x={w.location.x} — mirror mirrors "
                  f"about the object origin; it must sit on the plane",
                  file=sys.stderr)
            return 12
        w_plane = sum(1 for v in w.data.vertices
                      if abs((w.matrix_world @ v.co).x) <= TOL_PLANE)
        if (len(w.data.vertices), len(w.data.polygons), w_plane) != (n_half, f_half, weld):
            print(f"ERROR: {w.name} datablock verts/faces/on-plane "
                  f"{(len(w.data.vertices), len(w.data.polygons), w_plane)} != "
                  f"{(n_half, f_half, weld)}", file=sys.stderr)
            return 13
        wv, _, wf = _eval_mesh(w, dg)
        wv_plane = sum(1 for v in wv if abs(v.x) <= TOL_PLANE)
        if len(wv) != 2 * n_half - weld or wf != 2 * f_half or wv_plane != weld:
            print(f"ERROR: {w.name} evaluated verts/faces/on-plane "
                  f"{(len(wv), wf, wv_plane)} != "
                  f"{(2 * n_half - weld, 2 * f_half, weld)}", file=sys.stderr)
            return 14
        wdev, wlone = _symmetry_dev(wv, TOL_PLANE)
        if wlone or wdev > TOL_SYMM:
            print(f"ERROR: {w.name} partner check: {wlone} lone, dev {wdev:.3e}",
                  file=sys.stderr)
            return 15
        if min(v.x for v in wv) >= 0.0:
            print(f"ERROR: {w.name} evaluated mesh stayed on one side — "
                  f"mirror produced no mirrored half", file=sys.stderr)
            return 16
        part_lines.append(f"{w.name} {n_half}/{f_half}->{len(wv)}/{wf}"
                          + (f" welded={weld}" if weld else "")
                          + f" sym_dev={wdev:.3e}")

    print(f"body half={got[0]}/{got[1]}/{got[2]} centerline={c} | "
          f"eval={len(verts)}/{e_eval}/{f_eval} euler=2 manifold=True | "
          f"sym_dev={dev:.3e} (tol {TOL_SYMM:.1e}) bbox_asym={bbox_asym:.3e}")
    print("mirrored parts | " + " | ".join(part_lines)
          + " | origins on plane, evaluated spans both sides")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def _finish_materials():
    def principled(name):
        m = bpy.data.materials[name]
        m.use_nodes = True
        return m.node_tree.nodes["Principled BSDF"]
    p = principled("Paint")
    p.inputs["Base Color"].default_value = (0.50, 0.016, 0.02, 1.0)
    p.inputs["Metallic"].default_value = 0.0
    p.inputs["Roughness"].default_value = 0.38
    p.inputs["Coat Weight"].default_value = 1.0   # clear coat: crisp light streaks
    p.inputs["Coat Roughness"].default_value = 0.06
    g = principled("Glass")
    # opaque dark dielectric, glossy (metallic glass mirrors the key across
    # the whole windshield as a hot slab). On a near-black stage there is
    # little to reflect, so a facing-ratio ramp lifts the glass toward steel
    # blue at grazing angles: tinted glass that reads as glass, not as paint.
    nt = bpy.data.materials["Glass"].node_tree
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.010, 0.014, 0.020, 1.0)
    ramp.color_ramp.elements[1].position = 0.9
    ramp.color_ramp.elements[1].color = (0.11, 0.15, 0.21, 1.0)
    nt.links.new(lw.outputs["Facing"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], g.inputs["Base Color"])
    g.inputs["Metallic"].default_value = 0.0
    g.inputs["Roughness"].default_value = 0.05
    g.inputs["Coat Weight"].default_value = 1.0
    g.inputs["Coat Roughness"].default_value = 0.02
    t = principled("Trim")
    t.inputs["Base Color"].default_value = (0.022, 0.023, 0.027, 1.0)
    t.inputs["Roughness"].default_value = 0.55
    ch = principled("Chrome")
    ch.inputs["Base Color"].default_value = (0.78, 0.79, 0.82, 1.0)
    ch.inputs["Metallic"].default_value = 1.0
    ch.inputs["Roughness"].default_value = 0.2
    tire = principled("Tire")
    tire.inputs["Base Color"].default_value = (0.016, 0.016, 0.018, 1.0)
    tire.inputs["Roughness"].default_value = 0.82
    rim = principled("Rim")
    rim.inputs["Base Color"].default_value = (0.62, 0.64, 0.68, 1.0)
    rim.inputs["Metallic"].default_value = 1.0
    rim.inputs["Roughness"].default_value = 0.3
    head = principled("Headlamp")
    head.inputs["Base Color"].default_value = (0.8, 0.84, 0.9, 1.0)
    head.inputs["Roughness"].default_value = 0.1
    head.inputs["Emission Color"].default_value = (0.95, 0.97, 1.0, 1.0)
    head.inputs["Emission Strength"].default_value = 0.6
    tail = principled("Taillamp")
    tail.inputs["Base Color"].default_value = (0.35, 0.01, 0.012, 1.0)
    tail.inputs["Roughness"].default_value = 0.12
    tail.inputs["Emission Color"].default_value = (1.0, 0.04, 0.03, 1.0)
    tail.inputs["Emission Strength"].default_value = 1.2


def _shade_smooth(ob, angle_deg=35.0):
    """Smooth shading with sharp edges by dihedral angle and material border.

    Set on the authored half; the Mirror modifier carries the flags across.
    Boundary edges ON the plane have no partner face in the half, so their
    angle is the one to the mirror image of their face: acos(1 - 2 nx^2).
    (The weld itself is not a pixel witness: the hood and roof are nearly
    flat across the plane, so an unwelded seam renders within 12/255 of the
    welded one. The 2n - c count is what catches it.)"""
    thr = math.radians(angle_deg)
    bm = bmesh.new()
    try:
        bm.from_mesh(ob.data)
        for f in bm.faces:
            f.smooth = True
        for e in bm.edges:
            lf = e.link_faces
            if len(lf) == 2:
                sharp = (e.calc_face_angle(0.0) > thr
                         or lf[0].material_index != lf[1].material_index)
            elif len(lf) == 1 and all(abs(v.co.x) <= TOL_PLANE for v in e.verts):
                nx = lf[0].normal.x
                sharp = math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * nx * nx))) > thr
            else:
                sharp = True
            e.smooth = not sharp
        bm.to_mesh(ob.data)
    finally:
        bm.free()


def render_still(objs, path, engine):
    # Shared Layer 1 gates (render path only) — see gallery_framing.py
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
    sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
    import gallery_framing
    import gallery_asset_quality

    scene = bpy.context.scene
    _finish_materials()
    body = objs["body"]
    parts = [body] + [w for w, *_ in objs["mirrored"]]
    _shade_smooth(body)
    for ob in parts[1:]:
        _shade_smooth(ob, 40.0)

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
    wall.location = (0.0, 9.0, 0.0)
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

    # default-stage rig per docs/VISUAL-STYLE.md
    light("Key", (-4.0, -5.0, 6.0), 520.0, 5.0, (1.0, 0.96, 0.9), (48, 0, -35))
    light("Fill", (5.0, -3.5, 2.5), 110.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 50))
    light("Rim", (3.0, 4.5, 5.0), 320.0, 4.0, (0.6, 0.78, 1.0), (-55, 0, 155))
    light("Wedge", (2.5, 5.5, 4.0), 420.0, 6.0, (1.0, 0.76, 0.5), (-68, 0, 190))

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, -0.3, 0.62)
    scene.collection.objects.link(aim)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 54.0
    cam = bpy.data.objects.new("Cam", cam_data)
    # On the key's side (-X), high enough to look down the hood centerline so
    # both halves — both headlamps, both A-pillars, both wheels — read.
    cam.location = (-4.3, -5.6, 2.7)
    scene.collection.objects.link(cam)
    track = cam.constraints.new('TRACK_TO')  # data API, not bpy.ops (damped-track-aim)
    track.target = aim
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'
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
    # AgX would flatten the candy paint toward chalk (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    bpy.context.view_layer.update()

    if gallery_framing.check_framing(scene, cam, hero=parts, elements=parts,
                                     stage=[floor, wall]):
        return 17   # the helper's 10, remapped: 10 is the partner-deviation check
    if gallery_asset_quality.check_asset_quality(scene, cam, hero=parts,
                                                 stage=[floor, wall]):
        return 18   # the helper's 11, remapped: 11 is the bbox check
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 6
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--no-mirror", action="store_true",
                   help="turn off Mirror X (must fail)")
    args = p.parse_args(argv)

    objs = build_car()
    code = check(objs, no_mirror=args.no_mirror)
    if code:
        return code

    if args.output:
        code = render_still(objs, os.path.abspath(args.output), args.engine)
        if code:
            return code
        print(f"rendered still {args.output}")

    print("car-mirror-symmetry OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
