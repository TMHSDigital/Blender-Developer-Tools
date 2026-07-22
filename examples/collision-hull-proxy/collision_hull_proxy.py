"""A fire hydrant prop plus its convex collision proxies — a runnable example.

Witnesses the collision contract every game prop pipeline (engines generally,
FiveM/GTA-style prop workflows specifically) depends on: a prop's collision is
a COMPOUND of convex pieces, each piece a watertight, outward-wound hull that
fully encloses its render geometry and stays inside the engine's per-piece
face budget. Each piece is built with `bmesh.ops.convex_hull` from a coarse
collision cage — never from the dense render mesh, whose hull would blow the
budget — and the check derives every property from closed forms:

  containment  — every render-mesh vertex on the inner side of every face
                 plane of its piece's hull (max excursion printed, tol 2e-4)
  convexity    — the same plane test restricted to the hull's own vertices
  watertight   — every hull edge borders exactly two faces
  winding      — positive signed volume (divergence theorem)
  manifold     — Euler characteristic V - E + F == 2 (a convex hull is a
                 topological sphere)
  budget       — every piece <= 255 faces (the common per-piece convex limit
                 engines impose on collision meshes)

The cage is a coarser lathe whose profile rings are inflated by sec(pi / n)
so its n-gon rings circumscribe the render rings exactly — that is why
containment holds with a measured margin of ~0 instead of by luck. Concave
details (grooves) never touch the hull; proud details cost hull faces. That
trade-off IS the collision-authoring lesson.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python collision_hull_proxy.py --                 # check only
    blender --background --python collision_hull_proxy.py -- --output h.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector

SEGMENTS = 48          # lathe resolution of the render mesh
CAGE_SEG_BODY = 8      # collision cage resolutions — the hull face budget
CAGE_SEG_CAP = 8       #   is spent through these, not through SEGMENTS
CAGE_SEG_NUT = 5
HULL_BUDGET = 255      # engine per-piece convex face limit
TOL = 2e-4             # plane-test tolerance: cage circumscribes render exactly

# ---------------------------------------------------------------------------
# Prop construction. The hydrant is lathed around Z; caps are lathed around Z
# too and tipped onto their sides by the object rotation. All dimensions are
# invented for this prop — no real-world design is referenced.
# ---------------------------------------------------------------------------

# (radius, height) render profile of body + bonnet, bottom pole to top pole.
# Ribs are GROOVES: concave details are free under a convex hull, proud ones
# would have to be paid for in cage rows.
BODY_PROFILE = [
    (0.00, 0.000),
    (0.60, 0.000),   # base flange edge
    (0.60, 0.045),
    (0.575, 0.055),  # flange groove (concave)
    (0.575, 0.070),
    (0.60, 0.080),
    (0.60, 0.095),   # flange top edge
    (0.48, 0.115),   # taper (convex curve, lies inside the cage chord)
    (0.40, 0.155),
    (0.37, 0.205),   # neck
    (0.35, 0.320),   # barrel
    (0.346, 0.545),
    (0.334, 0.555),  # barrel groove (concave)
    (0.334, 0.575),
    (0.346, 0.590),
    (0.345, 0.880),  # barrel top
    (0.348, 0.930),
    (0.336, 0.950),  # upper groove (concave)
    (0.336, 1.000),
    (0.348, 1.030),
    (0.36, 1.090),   # shoulder under bonnet
    (0.35, 1.150),   # bonnet dome (concave curve — cage keeps every row)
    (0.30, 1.220),
    (0.21, 1.280),
    (0.10, 1.315),
    (0.00, 1.325),
]

# Cage silhouette: every convex corner of the render profile, nothing else.
# sec(pi/8) inflation makes each 8-gon cage ring circumscribe its render ring.
CAGE_BODY_PROFILE = [
    (0.00, 0.000),
    (0.60, 0.000),
    (0.60, 0.095),
    (0.37, 0.205),
    (0.345, 0.880),
    (0.36, 1.090),
    (0.35, 1.150),
    (0.30, 1.220),
    (0.21, 1.280),
    (0.10, 1.315),
    (0.00, 1.325),
]

NUT_PROFILE = [(0.09, 1.325), (0.072, 1.40), (0.0, 1.40)]

# Side caps at z=0.76, pumper (bigger) at z=0.66. A cap's outlet direction
# equals its azimuth (degrees from +X); the camera sits near azimuth 292, so
# the pumper faces it and the side caps read on the flanks.
SIDE_CAPS = [(0.66, 315.0), (0.76, 45.0), (0.76, 165.0)]
PUMPER = 0  # index of the large front outlet in SIDE_CAPS


def cap_profiles(r_cap, reach):
    """Render and cage (r, z) profiles for one outlet cap. The rim flare is
    1.10x the barrel radius so the dense rim rows lie inside the cage chord."""
    render = [
        (0.0, 0.0),
        (r_cap, 0.0),
        (r_cap, reach - 0.05),
        (r_cap * 1.10, reach - 0.03),   # rim
        (r_cap * 1.10, reach),
        (r_cap * 0.72, reach + 0.045),  # cap dome
        (0.0, reach + 0.06),
    ]
    cage = [
        (0.0, 0.0),
        (r_cap, 0.0),
        (r_cap * 1.10, reach - 0.03),
        (r_cap * 1.10, reach),
        (r_cap * 0.72, reach + 0.045),
        (0.0, reach + 0.06),
    ]
    return render, cage


def signed_volume(me):
    """Divergence-theorem volume; positive when face winding points outward."""
    vol = 0.0
    for p in me.polygons:
        vs = [me.vertices[i].co for i in p.vertices]
        v0 = vs[0]
        for i in range(1, len(vs) - 1):
            vol += v0.dot(vs[i].cross(vs[i + 1])) / 6.0
    return vol


def lathe_object(name, profile, segments, inflate=1.0):
    """Spin an (r, z) profile around Z. r == 0 ends become pole vertices, so
    the mesh closes with fans instead of degenerate rings. `inflate` scales
    radii only — the collision cage uses sec(pi / segments) so its polygon
    rings circumscribe the render rings exactly."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bot = top = None
        if profile[0][0] == 0.0:
            bot = bm.verts.new((0.0, 0.0, profile[0][1]))
            profile = profile[1:]
        if profile[-1][0] == 0.0:
            top = bm.verts.new((0.0, 0.0, profile[-1][1]))
            profile = profile[:-1]
        rings = []
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            ca, sa = math.cos(a), math.sin(a)
            rings.append([bm.verts.new((r * inflate * ca, r * inflate * sa, z))
                          for r, z in profile])
        for i in range(segments):
            j = (i + 1) % segments
            for k in range(len(profile) - 1):
                bm.faces.new((rings[i][k], rings[j][k], rings[j][k + 1], rings[i][k + 1]))
            if bot is not None:
                bm.faces.new((rings[j][0], rings[i][0], bot))
            if top is not None:
                bm.faces.new((rings[i][-1], rings[j][-1], top))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        # recalc picks a consistent winding but not a direction; outward is
        # pinned below by the same signed-volume form the check uses.
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    if signed_volume(me) < 0.0:
        for p in me.polygons:
            p.flip()
    return obj


def make_material(name, color, metallic, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def build_hydrant():
    """Builds the prop and its collision cages. Returns a list of collision
    groups: {"name", "render": [objects], "cage": [objects]} — one convex
    hull piece per group, the compound-collision structure engines ingest."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    red = make_material("EnamelRed", (0.48, 0.035, 0.022), 0.15, 0.30)
    yellow = make_material("EnamelYellow", (0.82, 0.53, 0.05), 0.15, 0.32)
    iron = make_material("CastIron", (0.05, 0.052, 0.06), 0.9, 0.48)

    inflate_body = 1.0 / math.cos(math.pi / CAGE_SEG_BODY)
    inflate_cap = 1.0 / math.cos(math.pi / CAGE_SEG_CAP)
    inflate_nut = 1.0 / math.cos(math.pi / CAGE_SEG_NUT)

    # --- body group: body + bonnet + operating nut ---
    body = lathe_object("Body", BODY_PROFILE, SEGMENTS)
    body.data.materials.append(red)
    body.data.materials.append(yellow)
    for p in body.data.polygons:  # the bonnet dome is the yellow profile tail
        if p.center.z > 1.09:
            p.material_index = 1
    nut = lathe_object("Nut", NUT_PROFILE, 5)
    nut.data.materials.append(iron)
    body_cage = lathe_object("BodyCage", CAGE_BODY_PROFILE, CAGE_SEG_BODY, inflate_body)
    nut_cage = lathe_object("NutCage", NUT_PROFILE, CAGE_SEG_NUT, inflate_nut)
    groups = [{"name": "body", "render": [body, nut], "cage": [body_cage, nut_cage]}]

    # --- one group per outlet cap ---
    for idx, (z, azim) in enumerate(SIDE_CAPS):
        big = idx == PUMPER
        r_cap = 0.19 if big else 0.145
        reach = 0.62 if big else 0.56
        prof_r, prof_c = cap_profiles(r_cap, reach)
        cap = lathe_object("PumperCap" if big else f"SideCap{idx}", prof_r, 24)
        cap.data.materials.append(red)
        lug_prof = [(0.075, reach + 0.05), (0.07, reach + 0.11), (0.0, reach + 0.11)]
        lug = lathe_object(f"Lug{idx}", lug_prof, 6)
        lug.data.materials.append(iron)
        cap_cage = lathe_object(f"CapCage{idx}", prof_c, CAGE_SEG_CAP, inflate_cap)
        lug_cage = lathe_object(f"LugCage{idx}", lug_prof, CAGE_SEG_CAP, inflate_cap)
        rot = (math.radians(90), 0.0, math.radians(azim + 90.0))
        for o in (cap, lug, cap_cage, lug_cage):
            o.rotation_euler = rot
            o.location = (0.0, 0.0, z)
        groups.append({"name": "pumper" if big else f"side{idx}",
                       "render": [cap, lug], "cage": [cap_cage, lug_cage]})
    return groups


# ---------------------------------------------------------------------------
# Hull construction and the contract checks.
# ---------------------------------------------------------------------------

def collect_points(objects):
    """World-space vertex cloud, read via foreach_get."""
    bpy.context.view_layer.update()  # matrix_world lags RNA writes until evaluated
    pts = []
    for o in objects:
        me = o.data
        buf = [0.0] * (len(me.vertices) * 3)
        me.vertices.foreach_get("co", buf)
        mw = o.matrix_world
        for i in range(0, len(buf), 3):
            pts.append(mw @ Vector((buf[i], buf[i + 1], buf[i + 2])))
    return pts


def build_hull(name, points):
    """Convex hull of a point cloud via bmesh.ops.convex_hull."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        verts = [bm.verts.new(p) for p in points]
        bmesh.ops.convex_hull(bm, input=verts)
        # the op leaves interior input verts behind; drop any vert not
        # referenced by a face so V - E + F is meaningful
        used = {v for f in bm.faces for v in f.verts}
        for v in list(bm.verts):
            if v not in used:
                bm.verts.remove(v)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def max_plane_excursion(me, points):
    """Largest signed distance of any point to the OUTER side of any face
    plane. <= 0 means every point is inside or on the hull."""
    worst = -math.inf
    where = None
    for p in me.polygons:
        n = p.normal
        c = p.center
        for q in points:
            d = (q - c).dot(n)
            if d > worst:
                worst = d
                where = (p.index, tuple(round(v, 4) for v in q))
    return worst, where


def check(pieces):
    """pieces: [(group_name, hull_obj, render_points)]. Returns exit code."""
    total_faces = 0
    for name, hull, points in pieces:
        me = hull.data
        nv, ne, nf = len(me.vertices), len(me.edges), len(me.polygons)
        total_faces += nf

        bm = bmesh.new()  # watertight: every edge borders exactly two faces
        try:
            bm.from_mesh(me)
            bad_edges = sum(1 for e in bm.edges if len(e.link_faces) != 2)
        finally:
            bm.free()
        if bad_edges:
            print(f"ERROR: piece {name}: {bad_edges} hull edge(s) do not border "
                  f"exactly two faces — proxy is not watertight", file=sys.stderr)
            return 4

        vol = signed_volume(me)  # winding: positive signed volume
        if vol <= 0.0:
            print(f"ERROR: piece {name}: signed volume {vol:.6f} <= 0 — hull "
                  f"winding is inverted", file=sys.stderr)
            return 5

        contain_err, where = max_plane_excursion(me, points)
        if contain_err > TOL:
            print(f"ERROR: piece {name}: render vertex escapes its hull by "
                  f"{contain_err:.6f} (tol {TOL}) at face {where[0]}, point "
                  f"{where[1]} — proxy does not enclose the render mesh",
                  file=sys.stderr)
            return 3

        hull_pts = [v.co.copy() for v in me.vertices]
        hull_err, _ = max_plane_excursion(me, hull_pts)
        if hull_err > TOL:
            print(f"ERROR: piece {name}: hull vertex off its own face plane by "
                  f"{hull_err:.6f} — proxy is not convex", file=sys.stderr)
            return 6

        euler = nv - ne + nf  # a convex hull is a topological sphere
        if euler != 2:
            print(f"ERROR: piece {name}: Euler characteristic {euler} != 2 — "
                  f"hull is not a closed manifold sphere", file=sys.stderr)
            return 7

        if nf > HULL_BUDGET:
            print(f"ERROR: piece {name}: {nf} faces, over the {HULL_BUDGET}-face "
                  f"per-piece collision budget", file=sys.stderr)
            return 8

        print(f"piece {name}: verts={nv} edges={ne} faces={nf} watertight=True "
              f"euler=2 volume={vol:.6f} containment={contain_err:.3e} "
              f"convexity={hull_err:.3e} budget={nf}<={HULL_BUDGET}")

    print(f"compound: pieces={len(pieces)} total_faces={total_faces} "
          f"(per-piece budget {HULL_BUDGET}; engine ingests the compound)")
    return 0


# ---------------------------------------------------------------------------
# Render: dark-studio staging per docs/VISUAL-STYLE.md. The hull pieces draw
# as faceted translucent shells with a thin wire overlay; if a piece failed
# to enclose its geometry, painted metal would poke through the shell.
# ---------------------------------------------------------------------------

def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(groups, pieces, path, engine):
    scene = bpy.context.scene
    for g in groups:
        for o in g["render"]:
            for p in o.data.polygons:
                p.use_smooth = True
    for g in groups:  # cages exist only to build hulls; never rendered
        for o in g["cage"]:
            o.hide_render = True

    # translucent shell: Transparent mixed over Principled works identically
    # in EEVEE and Cycles without touching blend-method RNA (renamed in 4.2)
    shell = bpy.data.materials.new("HullShell")
    shell.use_nodes = True
    nt = shell.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = 0.14          # 86% transparent: output =
                                                # (1-Fac)*Transparent + Fac*Principled
    transp = nt.nodes.new("ShaderNodeBsdfTransparent")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.16, 0.55, 0.75, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.12
    nt.links.new(transp.outputs[0], mix.inputs[1])
    nt.links.new(bsdf.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])

    wire_mat = make_material("HullWire", (0.35, 0.85, 1.0), 0.0, 0.4)
    wbsdf = wire_mat.node_tree.nodes["Principled BSDF"]
    wbsdf.inputs["Emission Color"].default_value = (0.2, 0.65, 0.85, 1.0)
    wbsdf.inputs["Emission Strength"].default_value = 0.6

    for name, hull, _ in pieces:
        hull.data.materials.append(shell)
        for p in hull.data.polygons:
            p.use_smooth = False                # facets must read as facets
        hull.data.materials.append(wire_mat)
        wire = bpy.data.objects.new(f"{name}Wire", hull.data)
        mod = wire.modifiers.new("Wire", 'WIREFRAME')
        mod.thickness = 0.010
        mod.material_offset = 1
        scene.collection.objects.link(wire)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = make_material("Studio", (0.03, 0.032, 0.037), 0.0, 0.7)
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 11.0, 0.0)
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

    # key/fill/rim/wedge per docs/VISUAL-STYLE.md
    light("Key", (-3.5, -4.5, 5.5), 500.0, 4.5, (1.0, 0.96, 0.9), (48, 0, -35))
    light("Fill", (5.0, -3.5, 2.5), 110.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 50))
    light("Rim", (1.5, 4.5, 3.5), 300.0, 3.0, (0.6, 0.78, 1.0), (-55, 0, 170))
    light("Wedge", (2.5, 5.5, 4.0), 380.0, 6.0, (1.0, 0.76, 0.5), (-68, 0, 190))
    # small warm glint off the camera-left shoulder: lifts the pumper cap face
    light("Glint", (-1.5, -4.0, 3.5), 260.0, 2.0, (1.0, 0.9, 0.75), (55, 0, -15))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 52.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (2.05, -4.5, 1.85)
    scene.collection.objects.link(cam)
    target = bpy.data.objects.new("Aim", None)
    target.location = (0.0, 0.0, 0.72)
    scene.collection.objects.link(target)
    con = cam.constraints.new('TRACK_TO')
    con.target = target
    scene.camera = cam

    scene.render.engine = 'CYCLES' if engine == 'cycles' else eevee_engine_id()
    if engine == 'cycles':
        scene.cycles.samples = 48
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path
    # AgX would flatten the enamel toward pastel (docs/VISUAL-STYLE.md)
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

    groups = build_hydrant()
    pieces = []
    for g in groups:
        hull = build_hull(f"{g['name']}Hull", collect_points(g["cage"]))
        pieces.append((g["name"], hull, collect_points(g["render"])))
    code = check(pieces)
    if code:
        return code

    if args.output:
        if not render_still(groups, pieces, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 9
        print(f"rendered still {args.output}")

    print("collision-hull-proxy OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
