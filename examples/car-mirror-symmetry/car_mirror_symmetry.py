"""A generic hatchback built as one half and completed by the Mirror modifier
— a runnable example.

Witnesses the Mirror + depsgraph contract from depsgraph-and-evaluated-data:
the original datablock keeps only the authored half, while the depsgraph
carries the mirrored whole. Closed forms: evaluated vertex count is exactly
2n - c (c = welded centerline verts), every evaluated vertex has an exact
partner at negated X, the merge threshold actually welds (no doubled
centerline), the evaluated shell is watertight with Euler characteristic 2,
and the wheels mirror about their object origins sitting ON the symmetry
plane. Failure is dramatically visible: a car with one side missing.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python car_mirror_symmetry.py --                 # check only
    blender --background --python car_mirror_symmetry.py -- --output c.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse

# --- closed-form construction parameters -----------------------------------
# 14 loft stations along Y (front at -Y), each a 9-point half-ring from the
# bottom centerline out and up to the roof centerline. Fields:
# (y, w_side, z_floor, z_sill, z_side, w_glass, z_glass_base, w_roof, z_roof)
STATIONS = [
    (-1.95, 0.74, 0.34, 0.36, 0.52, 0.05, 0.62, 0.04, 0.64),  # nose tip
    (-1.80, 0.83, 0.30, 0.32, 0.55, 0.08, 0.70, 0.07, 0.73),  # front bumper
    (-1.65, 0.86, 0.28, 0.28, 0.54, 0.10, 0.72, 0.09, 0.74),
    (-1.30, 0.87, 0.28, 0.62, 0.66, 0.11, 0.74, 0.10, 0.76),  # front arch peak
    (-0.95, 0.86, 0.28, 0.28, 0.54, 0.12, 0.78, 0.11, 0.80),
    (-0.60, 0.85, 0.28, 0.28, 0.55, 0.38, 0.90, 0.34, 0.95),  # hood -> cowl
    (-0.30, 0.84, 0.28, 0.28, 0.56, 0.54, 1.02, 0.50, 1.30),  # windshield
    ( 0.20, 0.83, 0.28, 0.28, 0.57, 0.60, 1.05, 0.56, 1.45),  # roof front
    ( 0.70, 0.83, 0.28, 0.28, 0.57, 0.60, 1.05, 0.55, 1.44),  # roof rear
    ( 0.95, 0.84, 0.28, 0.28, 0.56, 0.58, 1.04, 0.52, 1.38),
    ( 1.30, 0.85, 0.28, 0.62, 0.68, 0.50, 1.00, 0.44, 1.24),  # rear arch peak
    ( 1.65, 0.84, 0.28, 0.28, 0.55, 0.34, 0.95, 0.28, 1.10),  # hatch
    ( 1.90, 0.80, 0.30, 0.32, 0.53, 0.12, 0.86, 0.11, 0.92),  # tail
    ( 2.00, 0.72, 0.34, 0.36, 0.50, 0.05, 0.78, 0.04, 0.78),  # rear bumper
]
RING = 9                       # points per half-ring, p0 and p8 on the centerline
WHEEL_SEG = 16
WHEEL_RINGS = [                # (x, radius) profile: bead, tread, sidewall, rim, cap
    (0.63, 0.30), (0.67, 0.33), (0.83, 0.33), (0.87, 0.30), (0.89, 0.19), (0.90, 0.15),
]
WHEEL_Y = (-1.3, 1.3)          # front / rear axle positions
WHEEL_Z = 0.33                 # axle height == tire radius: wheels rest on z=0

N_BODY = len(STATIONS) * RING                    # 126
F_BODY = (len(STATIONS) - 1) * (RING - 1) + 2    # 104 quads + 2 caps
E_BODY = (len(STATIONS) * (RING - 1)             # ring edges
          + (len(STATIONS) - 1) * RING           # longitudinal edges
          + 2)                                   # cap closing edges
CENTERLINE = len(STATIONS) * 2                   # p0 + p8 per station: 28
N_WHEEL = len(WHEEL_RINGS) * WHEEL_SEG           # 96
F_WHEEL = (len(WHEEL_RINGS) - 1) * WHEEL_SEG + 1 # strips + hubcap ngon

MERGE_THRESHOLD = 1.0e-3
TOL_SYMM = 2.0e-5    # evaluated partner deviation (float32 storage; mirror copies exact)
TOL_BBOX = 1.0e-5    # |min.x + max.x| on the evaluated body
TOL_PLANE = 1.0e-6   # |x| this small counts as on the symmetry plane


def half_ring(st):
    """One 9-point half cross-section, bottom centerline -> roof centerline."""
    y, w, zf, zsill, zside, wg, zgb, wr, zroof = st
    return [
        (0.0, y, zf),                 # p0 bottom centerline
        (0.55 * w, y, zf - 0.02),     # p1 underbody
        (0.95 * w, y, zsill),         # p2 sill (rises over wheel arches)
        (w, y, zside),                # p3 lower door (widest)
        (0.99 * w, y, zside + 0.10),  # p4 shoulder
        (wg, y, zgb),                 # p5 greenhouse base
        (wr, y, zroof),               # p6 roof edge
        (0.55 * wr, y, zroof + 0.015),# p7 roof crown
        (0.0, y, zroof),              # p8 top centerline
    ]


def _newell(pts):
    nx = ny = nz = 0.0
    for i, p in enumerate(pts):
        q = pts[(i + 1) % len(pts)]
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    n = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (nx / n, ny / n, nz / n)


def build_car():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # -- half body loft ------------------------------------------------------
    rings = [half_ring(st) for st in STATIONS]
    me = bpy.data.meshes.new("CarBodyHalf")
    bm = bmesh.new()
    try:
        bv = [[bm.verts.new(co) for co in ring] for ring in rings]
        faces = []
        for i in range(len(STATIONS) - 1):
            for k in range(RING - 1):
                faces.append(bm.faces.new(
                    (bv[i][k], bv[i][k + 1], bv[i + 1][k + 1], bv[i + 1][k])))
        caps = [bm.faces.new(bv[0]), bm.faces.new(bv[-1])]
        # winding: the probe side quad must face +X; flip everything if the
        # loft convention came out inward (mirror does not fix winding)
        probe = [v.co for v in (bv[8][3], bv[8][4], bv[9][4], bv[9][3])]
        if _newell(probe)[0] < 0:
            for f in faces + caps:
                f.normal_flip()
        # caps must point away from the body (front -Y, rear +Y)
        if _newell([v.co for v in bv[0]])[1] > 0:
            caps[0].normal_flip()
        if _newell([v.co for v in bv[-1]])[1] < 0:
            caps[1].normal_flip()
        bm.to_mesh(me)
    finally:
        bm.free()  # the ownership contract from always-free-bmesh

    body = bpy.data.objects.new("CarBody", me)
    bpy.context.collection.objects.link(body)
    mirror = body.modifiers.new("MirrorHalf", 'MIRROR')
    mirror.use_axis[0] = True
    mirror.use_clip = True            # centerline verts cannot leave x=0
    mirror.use_mirror_merge = True    # weld the two halves shut
    mirror.merge_threshold = MERGE_THRESHOLD

    # -- wheels: own Mirror each, object origins ON the symmetry plane -------
    wheels = []
    for y in WHEEL_Y:
        wme = bpy.data.meshes.new("WheelHalf")
        bm = bmesh.new()
        try:
            wr = []
            for x, r in WHEEL_RINGS:
                wr.append([bm.verts.new(
                    (x, r * math.cos(2.0 * math.pi * s / WHEEL_SEG),
                     r * math.sin(2.0 * math.pi * s / WHEEL_SEG)))
                    for s in range(WHEEL_SEG)])
            for j in range(len(WHEEL_RINGS) - 1):
                for s in range(WHEEL_SEG):
                    bm.faces.new((wr[j][s], wr[j][(s + 1) % WHEEL_SEG],
                                  wr[j + 1][(s + 1) % WHEEL_SEG], wr[j + 1][s]))
            bm.faces.new(wr[-1])  # hubcap ngon
            bm.to_mesh(wme)
        finally:
            bm.free()
        wheel = bpy.data.objects.new("WheelFront" if y < 0 else "WheelRear", wme)
        wheel.location = (0.0, y, WHEEL_Z)  # origin on the plane: mirror mirrors DATA
        bpy.context.collection.objects.link(wheel)
        wm = wheel.modifiers.new("MirrorHalf", 'MIRROR')
        wm.use_axis[0] = True
        wm.use_mirror_merge = True
        wm.merge_threshold = MERGE_THRESHOLD
        wheels.append(wheel)

    # materials exist in both modes (slot layout is part of the scene contract)
    for name in ("Paint", "Glass", "Trim", "Tire", "Hubcap", "Headlamp", "Taillamp"):
        bpy.data.materials.new(name)
    for mat_name in ("Paint", "Glass", "Trim"):
        body.data.materials.append(bpy.data.materials[mat_name])
    for w in wheels:
        for mat_name in ("Tire", "Hubcap"):
            w.data.materials.append(bpy.data.materials[mat_name])

    # -- lamps: small mirrored boxes, same origin-on-plane idiom as wheels ---
    def lamp(name, x0, x1, y0, y1, z0, z1):
        lme = bpy.data.meshes.new(name + "Half")
        bm = bmesh.new()
        try:
            bmesh.ops.create_cube(bm, size=1.0)
            bmesh.ops.scale(bm, vec=(x1 - x0, y1 - y0, z1 - z0), verts=bm.verts)
            bmesh.ops.translate(bm, vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2),
                                verts=bm.verts)
            bm.to_mesh(lme)
        finally:
            bm.free()
        ob = bpy.data.objects.new(name, lme)
        bpy.context.collection.objects.link(ob)  # origin at world origin: on the plane
        lm = ob.modifiers.new("MirrorHalf", 'MIRROR')
        lm.use_axis[0] = True
        lm.use_mirror_merge = True
        lm.merge_threshold = MERGE_THRESHOLD
        ob.data.materials.append(bpy.data.materials[name])
        return ob

    headlamp = lamp("Headlamp", 0.38, 0.78, -1.97, -1.88, 0.40, 0.50)
    taillamp = lamp("Taillamp", 0.30, 0.70, 1.97, 2.01, 0.50, 0.62)

    _assign_body_materials(body)
    _assign_wheel_materials(wheels)
    return {"body": body,
            "mirrored": [(w, N_WHEEL, F_WHEEL) for w in wheels]
                        + [(headlamp, 8, 6), (taillamp, 8, 6)]}


def _assign_body_materials(body):
    """Deterministic panel classes by construction position (not hand-picked):
    side windows are ring segment 5 at cabin stations; the windshield and
    rear window are the full slopes (segments 5..7) at the steepest roof-rise
    and roof-drop station pairs; pillars/roof sides stay paint, underbody/
    sill/caps/bumpers are trim, everything else paint."""
    PAINT, GLASS, TRIM = 0, 1, 2
    n_st = len(STATIONS)
    dz = [STATIONS[i + 1][8] - STATIONS[i][8] for i in range(n_st - 1)]
    shield_pair = max(range(n_st - 1), key=lambda i: dz[i])      # windshield slope
    cabin = [i for i in range(n_st - 1)
             if STATIONS[i][5] >= 0.30 and STATIONS[i + 1][5] >= 0.30]
    rear_pair = min(cabin, key=lambda i: dz[i])                  # rear-window slope
    for poly in body.data.polygons:
        i, k = divmod(poly.index, RING - 1)
        if i >= n_st - 1:            # cap ngons (front/rear)
            poly.material_index = TRIM
            continue
        both_cabin = STATIONS[i][5] >= 0.30 and STATIONS[i + 1][5] >= 0.30
        if both_cabin and (k == 5 or (i in (shield_pair, rear_pair) and 5 <= k <= 7)):
            poly.material_index = GLASS
        elif k <= 1 or (i in (0, n_st - 2) and k <= 2):
            poly.material_index = TRIM       # underbody/sill + bumper bands
        else:
            poly.material_index = PAINT


def _assign_wheel_materials(wheels):
    for w in wheels:
        for poly in w.data.polygons:
            j = poly.index // WHEEL_SEG
            poly.material_index = 1 if j >= len(WHEEL_RINGS) - 2 else 0


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


def check(objs):
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

    # 4. mirrored parts (wheels, lamps): each mirrored about an object origin
    # that sits ON the plane — the data is offset, the object is not
    part_lines = []
    for w, n_half, f_half in objs["mirrored"]:
        if abs(w.location.x) > TOL_PLANE:
            print(f"ERROR: {w.name} origin x={w.location.x} — mirror mirrors "
                  f"about the object origin; it must sit on the plane",
                  file=sys.stderr)
            return 12
        if len(w.data.vertices) != n_half or len(w.data.polygons) != f_half:
            print(f"ERROR: {w.name} datablock "
                  f"{(len(w.data.vertices), len(w.data.polygons))} != "
                  f"{(n_half, f_half)}", file=sys.stderr)
            return 13
        wv, _, wf = _eval_mesh(w, dg)
        if len(wv) != 2 * n_half or wf != 2 * f_half:
            print(f"ERROR: {w.name} evaluated {(len(wv), wf)} != "
                  f"{(2 * n_half, 2 * f_half)}", file=sys.stderr)
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
        part_lines.append(f"{w.name} sym_dev={wdev:.3e}")

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
    p.inputs["Base Color"].default_value = (0.48, 0.015, 0.022, 1.0)
    p.inputs["Metallic"].default_value = 0.5
    p.inputs["Roughness"].default_value = 0.32
    g = principled("Glass")
    # dielectric, not metal: metallic glass mirrors the key light across the
    # whole windshield and it renders as a hot salmon slab
    g.inputs["Base Color"].default_value = (0.02, 0.026, 0.036, 1.0)
    g.inputs["Metallic"].default_value = 0.0
    g.inputs["Roughness"].default_value = 0.3
    t = principled("Trim")
    t.inputs["Base Color"].default_value = (0.02, 0.021, 0.026, 1.0)
    t.inputs["Roughness"].default_value = 0.6
    tire = principled("Tire")
    tire.inputs["Base Color"].default_value = (0.012, 0.013, 0.016, 1.0)
    tire.inputs["Roughness"].default_value = 0.85
    hub = principled("Hubcap")
    hub.inputs["Base Color"].default_value = (0.62, 0.64, 0.68, 1.0)
    hub.inputs["Metallic"].default_value = 1.0
    hub.inputs["Roughness"].default_value = 0.28
    head = principled("Headlamp")
    head.inputs["Base Color"].default_value = (0.85, 0.9, 0.95, 1.0)
    head.inputs["Emission Color"].default_value = (0.9, 0.95, 1.0, 1.0)
    head.inputs["Emission Strength"].default_value = 1.2
    tail = principled("Taillamp")
    tail.inputs["Base Color"].default_value = (0.3, 0.008, 0.01, 1.0)
    tail.inputs["Emission Color"].default_value = (0.8, 0.02, 0.02, 1.0)
    tail.inputs["Emission Strength"].default_value = 0.9


def render_still(objs, path, engine):
    scene = bpy.context.scene
    _finish_materials()
    body = objs["body"]
    for poly in body.data.polygons:
        poly.use_smooth = False  # crisp loft panels

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
    # metallic paint needs a faint ambient or the flanks die to black
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.024, 0.026, 0.032, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    # default-stage rig per docs/VISUAL-STYLE.md
    light("Key", (-4.0, -5.0, 6.0), 550.0, 5.0, (1.0, 0.96, 0.9), (48, 0, -35))
    light("Fill", (5.0, -3.5, 2.5), 120.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 50))
    light("Rim", (3.0, 4.5, 5.0), 320.0, 4.0, (0.6, 0.78, 1.0), (-55, 0, 155))
    light("Wedge", (2.5, 5.5, 4.0), 400.0, 6.0, (1.0, 0.76, 0.5), (-68, 0, 190))

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.55)
    scene.collection.objects.link(aim)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 52.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (4.4, -5.3, 2.1)
    scene.collection.objects.link(cam)
    track = cam.constraints.new('TRACK_TO')  # data API, not bpy.ops (damped-track-aim)
    track.target = aim
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'
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
    # AgX would flatten the candy paint toward chalk (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    args = p.parse_args(argv)

    objs = build_car()
    code = check(objs)
    if code:
        return code

    if args.output:
        if not render_still(objs, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 6
        print(f"rendered still {args.output}")

    print("car-mirror-symmetry OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
