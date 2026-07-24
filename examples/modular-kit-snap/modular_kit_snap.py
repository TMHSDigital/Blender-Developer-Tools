"""Modular kit snap — boundary vertices welded to the tile grid so segments tile seamlessly.

Witnesses the contract a tiling modular kit lives or dies by: a corridor
segment whose open-end boundary vertices sit EXACTLY on the declared tile
grid, so instances placed at tile multiples share boundary positions with
no gap and no overlap. Interior geometry is free-form (beveled detail);
only the boundary is snapped — the snap is a deliberate authoring pass,
not an accident of box modeling. An unsnapped variant built with the same
code minus the snap pass carries a measured 3 mm joint error, which is
what the check catches.

The asset is built to be reused: geometry authored in kit space with the
origin at the connection pivot (floor-center of the start edge), identity
transforms by construction, clean named datablocks, manifold everywhere
except the two intentional open ends, and all detail contained strictly
inside the tile so it can never affect tiling.

Check (all closed form or independently re-derived, nothing captured):

1. Snap: exactly 16 boundary verts (8 per open end, closed form from the
   hollow-rectangle profile), every one on its end plane x in {0, TILE}
   within 1e-6 m; every boundary edge lies on an end plane.
2. Loop coincidence: the two end rings matched by (y, z) key agree within
   1e-6 — opposing loops are coincident under the tile offset.
3. Tiling: a linked duplicate offset by (TILE, 0, 0) places its start ring
   at world positions matching the original's end ring within 1e-6 — no
   gap, no overlap at the joint.
4. Bounding box: the shell's local bbox equals the declared tile size
   exactly (0..TILE x +/-1.5 x 0..3, all float32-exact values), and the
   whole-asset bbox matches it because every detail part is contained.
5. Manifold: every edge has exactly 2 link faces except the 16 boundary
   ring edges (1 face each) — the two open ends are the only boundaries.
6. Reuse hygiene: identity object scales, names under Kit.CorridorSeg.*,
   all part origins at the pivot.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python modular_kit_snap.py --                 # check only
    blender --background --python modular_kit_snap.py -- --output k.png  # + render
    blender --background --python modular_kit_snap.py -- --falsify f.png # seam variant
"""
import bpy, bmesh, sys, os, math, argparse

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing

TILE = 4.0                # tile length along X, metres
WIDTH = 3.0               # corridor width along Y ( +/- 1.5 )
HEIGHT = 3.0              # corridor height along Z
WALL = 0.15               # shell thickness (floor / walls / ceiling)
TOL = 1e-6                # snap / coincidence / tiling tolerance (metres)
BBOX_TOL = 2e-6           # float32 rounding slack at the bbox extremes
SKEW = 3e-3               # unsnapped variant: end-ring x error (3 mm)
NUDGE = 2e-3              # unsnapped variant: two verts jogged in y (2 mm)
EXPECT_BOUNDARY_VERTS = 16   # 8 per open end (hollow-rectangle profile)
EXPECT_BOUNDARY_EDGES = 16   # 8 per open end

# Hollow-rectangle profile (y, z): outer shell corners then inner bore corners,
# ordered as one continuous ring so the extrusion's side faces come out quads.
# The ring is the cross-section of the tube wall: outer bottom-left -> outer
# bottom-right -> outer top-right -> outer top-left -> inner top-left -> ...
OUTER = [(-WIDTH / 2, 0.0), (WIDTH / 2, 0.0),
         (WIDTH / 2, HEIGHT), (-WIDTH / 2, HEIGHT)]
INNER = [(-(WIDTH / 2 - WALL), HEIGHT - WALL), (WIDTH / 2 - WALL, HEIGHT - WALL),
         (WIDTH / 2 - WALL, WALL), (-(WIDTH / 2 - WALL), WALL)]
PROFILE = OUTER + INNER   # 8 points -> 8 boundary verts per open end


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


# ---------------------------------------------------------------------------
# Asset construction (bmesh, kit space: origin = floor-center of the x=0 edge)
# ---------------------------------------------------------------------------

def build_shell(name, skew=0.0, nudge=0.0):
    """The corridor tube: hollow-rectangle profile extruded over x in [0, TILE].

    With skew=0 the end ring lands exactly on x == TILE (the snapped asset).
    skew shifts the end ring in x (unsnapped variant), nudge jogs two of its
    verts in y — the joint errors the check must catch.
    """
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        ring_a = [bm.verts.new((0.0, y, z)) for (y, z) in PROFILE]
        ring_b = []
        for i, (y, z) in enumerate(PROFILE):
            x = TILE + skew
            if nudge and i in (1, 5):      # deterministic pair, jogged in y
                y += nudge
            ring_b.append(bm.verts.new((x, y, z)))
        n = len(PROFILE)
        for i in range(n):
            a, b = i, (i + 1) % n
            bm.faces.new((ring_a[a], ring_a[b], ring_b[b], ring_b[a]))
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def _beveled_box(bm, dims, center, bevel=0.0, segments=2):
    """One watertight box; small bevels are interior detail (never boundary)."""
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x = v.co.x * dims[0] + center[0]
        v.co.y = v.co.y * dims[1] + center[1]
        v.co.z = v.co.z * dims[2] + center[2]
    if bevel > 0.0:
        bmesh.ops.bevel(
            bm, geom=list(bm.edges), offset=bevel, segments=segments,
            profile=0.5, affect="EDGES", clamp_overlap=True,
        )


def build_detail(name, dims, center, bevel=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        _beveled_box(bm, dims, center, bevel)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


# Detail layout: (suffix, dims, center, bevel). Every box sits strictly inside
# the tile — x in (0, TILE), |y| < WIDTH/2, z in (0, HEIGHT) — so detail can
# never touch a boundary plane (check 6 proves it).
def detail_layout():
    inner_y = WIDTH / 2 - WALL                    # 1.35, the bore face
    parts = [
        # start-edge frame rib: two posts + a top beam, just inside x=0
        ("Rib.Post.L", (0.24, 0.30, HEIGHT - 2 * WALL), (0.18, inner_y - 0.15, HEIGHT / 2), 0.02),
        ("Rib.Post.R", (0.24, 0.30, HEIGHT - 2 * WALL), (0.18, -(inner_y - 0.15), HEIGHT / 2), 0.02),
        ("Rib.Beam", (0.24, 2 * inner_y - 0.30, 0.34), (0.18, 0.0, HEIGHT - WALL - 0.17), 0.02),
        # walkway floor plate
        ("FloorPlate", (3.4, 1.8, 0.05), (TILE / 2, 0.0, WALL + 0.025), 0.015),
        # wall panels, two per side, recessed-look slabs on the bore face
        ("Panel.L.1", (1.15, 0.05, 1.15), (1.2, inner_y - 0.025, 1.55), 0.02),
        ("Panel.L.2", (1.15, 0.05, 1.15), (2.8, inner_y - 0.025, 1.55), 0.02),
        ("Panel.R.1", (1.15, 0.05, 1.15), (1.2, -(inner_y - 0.025), 1.55), 0.02),
        ("Panel.R.2", (1.15, 0.05, 1.15), (2.8, -(inner_y - 0.025), 1.55), 0.02),
        # orange trim rails — the lines that jog visibly when a joint steps
        ("Trim.L", (3.7, 0.06, 0.09), (TILE / 2, inner_y - 0.03, 0.78), 0.015),
        ("Trim.R", (3.7, 0.06, 0.09), (TILE / 2, -(inner_y - 0.03), 0.78), 0.015),
        # emissive light strips along the wall/ceiling join
        ("Light.L", (3.0, 0.05, 0.07), (TILE / 2, inner_y - 0.025, HEIGHT - WALL - 0.09), 0.01),
        ("Light.R", (3.0, 0.05, 0.07), (TILE / 2, -(inner_y - 0.025), HEIGHT - WALL - 0.09), 0.01),
    ]
    return parts


def build_kit_meshes(skew=0.0, nudge=0.0):
    """All kit meshes, keyed by part suffix. Skew/nudge touch the shell only."""
    meshes = {"Shell": build_shell("Kit.CorridorSeg.Shell", skew, nudge)}
    for suffix, dims, center, bevel in detail_layout():
        meshes[suffix] = build_detail(f"Kit.CorridorSeg.{suffix}", dims, center, bevel)
    return meshes


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------

def boundary_verts(me):
    """Verts of the open-end rings: x within TOL of an end plane candidate.
    Returns (on_plane, off_plane) — off_plane must be empty in the snapped
    asset and carries the measured error in the unsnapped one."""
    on, off = [], []
    for v in me.vertices:
        if abs(v.co.x) <= 0.01 or abs(v.co.x - TILE) <= 0.01 + SKEW:
            if abs(v.co.x) <= TOL or abs(v.co.x - TILE) <= TOL:
                on.append(v)
            else:
                off.append(v)
    return on, off


def ring_key(co):
    return (round(co.y, 6), round(co.z, 6))


def max_nearest_dev(keys_a, keys_b):
    """Worst displacement between two rings: for every key in A, the distance
    to its nearest key in B, maximized. Robust to a displaced vert reordering
    the ring (a sorted-zip would mispair and report a bogus cascade)."""
    if not keys_a or not keys_b or len(keys_a) != len(keys_b):
        return float("inf")
    return max(min(math.dist(a, b) for b in keys_b) for a in keys_a)


def mesh_bbox(me):
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def manifold_report(me):
    """(boundary_edges, nonmanifold_edges) via bmesh link-face counts."""
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        boundary = [e for e in bm.edges if len(e.link_faces) == 1]
        nonmanifold = [e for e in bm.edges if len(e.link_faces) not in (1, 2)]
        off_plane = [e for e in boundary
                     if not all(abs(v.co.x) <= TOL or abs(v.co.x - TILE) <= TOL
                                for v in e.verts)]
        return len(boundary), len(nonmanifold), len(off_plane)
    finally:
        bm.free()


def check():
    meshes = build_kit_meshes()
    shell = meshes["Shell"]
    fails = []

    def fail(code, msg):
        print(f"ERROR ({code}): {msg}", file=sys.stderr)
        fails.append(code)

    # --- 1. snap: 16 boundary verts, all on x in {0, TILE} -----------------
    on, off = boundary_verts(shell)
    print(f"snap boundary_verts={len(on)} off_plane={len(off)} "
          f"(closed form {EXPECT_BOUNDARY_VERTS})")
    if len(on) != EXPECT_BOUNDARY_VERTS:
        fail(3, f"boundary vert count {len(on)} != {EXPECT_BOUNDARY_VERTS} — "
                f"the profile or an end plane moved")
    if off:
        worst = max(min(abs(v.co.x), abs(v.co.x - TILE)) for v in off)
        fail(3, f"{len(off)} boundary verts off the end planes, worst "
                f"{worst:.3e} m > {TOL:.0e} — the snap pass was skipped")
    worst_on = max((min(abs(v.co.x), abs(v.co.x - TILE)) for v in on), default=0.0)
    print(f"snap max_dev={worst_on:.3e} tol={TOL:.0e}")

    # --- 2. loop coincidence: end rings agree under the tile offset --------
    ring_a = [ring_key(v.co) for v in on if abs(v.co.x) <= TOL]
    ring_b = [ring_key(v.co) for v in on if abs(v.co.x - TILE) <= TOL]
    co_dev = max_nearest_dev(ring_a, ring_b)
    print(f"loop_coincidence rings={len(ring_a)}/{len(ring_b)} max_dev={co_dev:.3e} tol={TOL:.0e}")
    if len(ring_a) != EXPECT_BOUNDARY_VERTS // 2 or len(ring_b) != EXPECT_BOUNDARY_VERTS // 2:
        fail(4, "end rings do not partition evenly — profile asymmetry")
    if co_dev > TOL:
        fail(4, f"opposing end loops differ by {co_dev:.3e} > {TOL:.0e} — "
                f"segments would not butt cleanly")

    # --- 3. tiling: linked duplicate shares boundary world positions -------
    root = bpy.data.objects.new("Kit.CorridorSeg", None)
    bpy.context.collection.objects.link(root)
    shell_ob = bpy.data.objects.new("Kit.CorridorSeg.Shell", shell)
    bpy.context.collection.objects.link(shell_ob)
    shell_ob.parent = root
    dup = shell_ob.copy()                       # linked duplicate (shares mesh)
    dup.parent = None
    dup.location = (TILE, 0.0, 0.0)
    bpy.context.collection.objects.link(dup)
    bpy.context.view_layer.update()
    end_b_yz = [ring_key(shell_ob.matrix_world @ v.co) for v in on
                if abs(v.co.x - TILE) <= TOL]
    start_a_yz = [ring_key(dup.matrix_world @ v.co) for v in on
                  if abs(v.co.x) <= TOL]
    gap = max_nearest_dev(end_b_yz, start_a_yz)
    x_gap = max((abs((dup.matrix_world @ v.co).x - TILE) for v in on
                 if abs(v.co.x) <= TOL), default=float("inf"))
    print(f"tiling joint gap/overlap yz_dev={gap:.3e} x_dev={x_gap:.3e} tol={TOL:.0e}")
    if gap > TOL or x_gap > TOL:
        fail(5, f"tiled instances do not share boundary positions "
                f"(yz {gap:.3e}, x {x_gap:.3e}) — gap or overlap at the joint")

    # --- 4. bbox == declared tile, for shell and for the whole asset -------
    lo, hi = mesh_bbox(shell)
    want_lo, want_hi = (0.0, -WIDTH / 2, 0.0), (TILE, WIDTH / 2, HEIGHT)
    bbox_dev = max(max(abs(a - b) for a, b in zip(lo, want_lo)),
                   max(abs(a - b) for a, b in zip(hi, want_hi)))
    all_lo = [min(mesh_bbox(m)[0][i] for m in meshes.values()) for i in range(3)]
    all_hi = [max(mesh_bbox(m)[1][i] for m in meshes.values()) for i in range(3)]
    asset_dev = max(max(abs(a - b) for a, b in zip(all_lo, want_lo)),
                    max(abs(a - b) for a, b in zip(all_hi, want_hi)))
    print(f"bbox shell_dev={bbox_dev:.3e} asset_dev={asset_dev:.3e} tol={BBOX_TOL:.0e}")
    if bbox_dev > BBOX_TOL:
        fail(6, f"shell bbox deviates {bbox_dev:.3e} from the declared tile — "
                f"footprint is not the contract size")
    if asset_dev > BBOX_TOL:
        fail(6, f"whole-asset bbox deviates {asset_dev:.3e} — detail escapes "
                f"the tile envelope")

    # --- 5. manifold except the two open ends -------------------------------
    n_boundary, n_nonmanifold, n_off = manifold_report(shell)
    print(f"manifold boundary_edges={n_boundary} (closed form "
          f"{EXPECT_BOUNDARY_EDGES}) nonmanifold={n_nonmanifold} off_plane_edges={n_off}")
    if n_boundary != EXPECT_BOUNDARY_EDGES:
        fail(7, f"{n_boundary} boundary edges != {EXPECT_BOUNDARY_EDGES} — "
                f"the tube is not open exactly at its two ends")
    if n_nonmanifold:
        fail(7, f"{n_nonmanifold} edges with != 2 link faces (excluding open ends)")
    if n_off:
        fail(7, f"{n_off} boundary edges off the end planes — torn rim")

    for suffix, me in meshes.items():
        if suffix == "Shell":
            continue
        db, dn, _ = manifold_report(me)
        if db or dn:
            fail(8, f"detail part {suffix} not watertight "
                    f"(boundary={db} nonmanifold={dn})")

    # --- 6. detail containment: nothing touches the boundary planes --------
    for suffix, me in meshes.items():
        if suffix == "Shell":
            continue
        d_lo, d_hi = mesh_bbox(me)
        outside = (d_lo[0] <= TOL or d_hi[0] >= TILE - TOL or
                   d_lo[1] <= -WIDTH / 2 + TOL or d_hi[1] >= WIDTH / 2 - TOL or
                   d_lo[2] <= -TOL or d_hi[2] >= HEIGHT - TOL)
        if outside:
            fail(9, f"detail part {suffix} reaches a tile boundary "
                    f"{d_lo}..{d_hi} — it would break tiling")
    print(f"detail_containment parts={len(meshes) - 1} all_inside=True")

    # --- 7. reuse hygiene: transforms, names, origins -----------------------
    parts_obs = []
    for suffix, me in meshes.items():
        ob = bpy.data.objects.new(me.name, me)
        bpy.context.collection.objects.link(ob)
        ob.parent = root
        parts_obs.append(ob)
    bpy.context.view_layer.update()
    for ob in parts_obs:
        if max(abs(s - 1.0) for s in ob.scale) > 0.0:
            fail(11, f"{ob.name} scale {tuple(ob.scale)} not applied")
        if not ob.name.startswith("Kit.CorridorSeg."):
            fail(11, f"datablock name {ob.name!r} outside the kit namespace")
        if max(abs(c) for c in ob.location) > 0.0:
            fail(11, f"{ob.name} origin off the pivot {tuple(ob.location)}")
    print(f"hygiene parts={len(parts_obs)} identity_scale=True origins_at_pivot=True")

    if fails:
        return fails[0]
    print(f"modular-kit-snap OK tile={TILE}x{WIDTH}x{HEIGHT} "
          f"boundary={len(on)}v/{n_boundary}e dev<={TOL:.0e} "
          f"joint yz={gap:.3e} bbox_dev={bbox_dev:.3e}")
    return 0


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


SEGMENT_MATS = {
    "Shell": ("Shell", (0.10, 0.11, 0.13), 0.5, 0.8, None, 0.0),
    "Rib": ("Rib", (0.05, 0.05, 0.06), 0.45, 0.85, None, 0.0),
    "FloorPlate": ("FloorPlate", (0.07, 0.08, 0.09), 0.6, 0.7, None, 0.0),
    "Panel": ("Panel", (0.19, 0.25, 0.33), 0.4, 0.6, None, 0.0),
    "Trim": ("Trim", (0.85, 0.35, 0.08), 0.35, 0.3, None, 0.0),
    "Light": ("LightStrip", (0.30, 0.25, 0.18), 0.5, 0.2, (1.0, 0.75, 0.4), 8.0),
}


def mat_for(suffix):
    key = suffix.split(".")[0]
    name, rgb, rough, metal, emit, estr = SEGMENT_MATS[key]
    return make_material(name, rgb, rough, metal, emit, estr)


def build_kit_objects(sc, x_offset, skew=0.0, nudge=0.0, y_jog=0.0, z_jog=0.0):
    """One placed segment: root empty at (x_offset, y_jog, z_jog) + all parts."""
    meshes = build_kit_meshes(skew, nudge)
    root = bpy.data.objects.new(f"Kit.CorridorSeg", None)
    root.location = (x_offset, y_jog, z_jog)
    sc.collection.objects.link(root)
    parts = []
    for suffix, me in meshes.items():
        if not me.materials:
            me.materials.append(mat_for(suffix))
        ob = bpy.data.objects.new(me.name, me)
        sc.collection.objects.link(ob)
        ob.parent = root
        parts.append(ob)
    return [root] + parts


def build_studio(sc):
    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = make_material("Studio", (0.03, 0.032, 0.037), rough=0.7, metallic=0.0)
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    sc.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    sc.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.02, 0.021, 0.025, 1.0,
    )
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

    # exterior identity rig (VISUAL-STYLE Layer 2)
    light("Key", (-3.5, -4.5, 5.5), 480.0, 4.5, (1.0, 0.96, 0.9), (48, 0, -35))
    light("Fill", (5.0, -3.5, 2.5), 120.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 50))
    light("Rim", (1.5, 4.5, 3.5), 280.0, 3.0, (0.6, 0.78, 1.0), (-55, 0, 170))
    light("Wedge", (2.5, 5.5, 4.0), 400.0, 6.0, (1.0, 0.72, 0.42), (-68, 0, 190))
    # corridor fixtures: one warm area per segment under the light strips —
    # the kit's own lighting language, designed with the asset
    for i in range(4):
        ld = bpy.data.lights.new(f"Fixture{i}", "AREA")
        ld.energy = 130.0
        ld.size = 3.2
        ld.color = (1.0, 0.8, 0.55)
        ob = bpy.data.objects.new(f"Fixture{i}", ld)
        ob.location = (TILE * i + TILE / 2, 0.0, HEIGHT - WALL - 0.12)
        ob.rotation_euler = (0.0, 0.0, 0.0)  # facing straight down (area -Z)
        sc.collection.objects.link(ob)
    return floor, wall


def build_bulkhead(sc):
    """Presentation focal: a lit door bulkhead capping the far end of the run.
    Not part of the kit — the corridor's destination for this still."""
    frame_mat = make_material("Bulkhead", (0.06, 0.06, 0.07), rough=0.4, metallic=0.85)
    door_mat = make_material("BulkheadDoor", (0.30, 0.16, 0.07), rough=0.5,
                             metallic=0.3, emit=(1.0, 0.42, 0.12), estr=0.6)
    inner_y = WIDTH / 2 - WALL
    end_x = TILE * 4
    parts = []
    for suffix, dims, center in [
        ("Post.L", (0.5, 0.35, HEIGHT), (end_x + 0.25, inner_y - 0.17, HEIGHT / 2)),
        ("Post.R", (0.5, 0.35, HEIGHT), (end_x + 0.25, -(inner_y - 0.17), HEIGHT / 2)),
        ("Head", (0.5, 2 * inner_y, WALL + 0.35), (end_x + 0.25, 0.0, HEIGHT - (WALL + 0.35) / 2)),
    ]:
        me = build_detail(f"Bulkhead.{suffix}", dims, center, 0.03)
        me.materials.append(frame_mat)
        ob = bpy.data.objects.new(f"Bulkhead.{suffix}", me)
        sc.collection.objects.link(ob)
        parts.append(ob)
    door = build_detail("Bulkhead.Door", (0.12, 1.6, 2.1), (end_x + 0.55, 0.0, 1.05))
    door.materials.append(door_mat)
    door_ob = bpy.data.objects.new("Bulkhead.Door", door)
    sc.collection.objects.link(door_ob)
    parts.append(door_ob)
    # warm spill into the corridor, toward the camera
    ld = bpy.data.lights.new("BulkheadSpill", "AREA")
    ld.energy = 140.0
    ld.size = 1.8
    ld.color = (1.0, 0.62, 0.3)
    ob = bpy.data.objects.new("BulkheadSpill", ld)
    ob.location = (end_x - 0.6, 0.0, 1.5)
    ob.rotation_euler = (math.radians(90), 0.0, math.radians(-90))  # face -X
    sc.collection.objects.link(ob)
    # cool rim from the mouth behind the camera: lifts the near right wall and
    # the ceiling edge out of dead black without touching the warm pools
    rd = bpy.data.lights.new("MouthRim", "AREA")
    rd.energy = 65.0
    rd.size = 2.0
    rd.color = (0.62, 0.76, 1.0)
    rob = bpy.data.objects.new("MouthRim", rd)
    rob.location = (-1.2, -0.9, 2.2)
    rob.rotation_euler = (math.radians(70), 0.0, math.radians(-70))
    sc.collection.objects.link(rob)
    return parts


def render_still(path, engine, falsify=False):
    """A four-segment run. Snapped: joints vanish. Falsified: each segment
    accumulates a 120 mm x gap, alternating 50 mm y jogs, and 40 mm floor
    steps, so every joint reads as a seam — the render-scale exaggeration of
    the failure the check measures at 3 mm (probe_unsnapped)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene

    all_parts = []
    for i in range(4):
        if falsify:
            obs = build_kit_objects(
                sc, TILE * i + i * 0.12,
                y_jog=(0.05 if i % 2 else 0.0),
                z_jog=(0.04 if i % 2 else 0.0))
        else:
            obs = build_kit_objects(sc, TILE * i)
        all_parts.extend(obs[1:])   # mesh parts only, not the root empties
    floor, wall = build_studio(sc)
    bulkhead = build_bulkhead(sc)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 25.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (-0.7, -0.42, 1.58)
    sc.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (10.0, 0.35, 1.25)
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
    # Layer 1 framing gate. The corridor surrounds the camera on five sides
    # and reads as extending past the frame — a documented deviation class
    # (radiating architecture), measured and reported by the helper.
    fcode = gallery_framing.check_framing(
        sc, cam,
        hero=all_parts,
        elements=all_parts + bulkhead,
        stage=[floor, wall],
        deviation="interior corridor run: the envelope surrounds the camera "
                  "and the tiling joints are the proof; edge bleed is the design",
    )
    if fcode:
        return fcode
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
                   help="optional: render the unsnapped-joint seam variant here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output/--falsify (cycles for GPU-less hosts)")
    args = p.parse_args(argv)

    print(f"binary version: {bpy.app.version} ({bpy.app.version_string})")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    code = check()
    if code:
        return code

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

    print("modular-kit-snap OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
