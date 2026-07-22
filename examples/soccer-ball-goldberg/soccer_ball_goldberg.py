"""A soccer ball built as a Goldberg polyhedron with bmesh — a runnable example.

A truncated icosahedron (12 pentagons, 20 hexagons) derived by cutting every
edge of a bmesh icosphere at exactly 1/3, with the pentagon/hexagon faces
ordered by walking the source mesh's own link topology — nothing is
hand-listed. Distinct from bmesh-gear (which witnesses parametric extrusion
ownership): this witnesses *polyhedral topology invariants* — the closed-form
counts, Euler characteristic, uniform degree, uniform edge length, face
planarity, and a common circumsphere — plus per-face-class material binding
driven by face vertex count, never by enumeration order.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python soccer_ball_goldberg.py --                 # check only
    blender --background --python soccer_ball_goldberg.py -- --output b.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse

# truncation parameter: cutting each icosahedron edge at 1/3 makes every new
# edge the same length (a/3), which is what makes the result an Archimedean
# solid with a circumsphere at all
TRUNC_T = 1.0 / 3.0
BALL_RADIUS = 1.15          # normalized circumradius after truncation
# Tolerances: mesh coordinates are float32, and create_icosphere's own trig
# lands the Goldberg invariants at a deterministic noise floor (~9e-6 here,
# byte-identical on 4.5.11 and 5.1.2). The 3e-5 gates sit ~3x above that
# floor; a genuine contract break (wrong cut, shifted vertex, bad binding)
# produces errors of 1e-2 or larger, so the margin costs no sensitivity.
TOL_LEN = 3.0e-5            # edge-length uniformity
TOL_PLANAR = 3.0e-5         # face planarity (max vertex-to-plane distance)
TOL_RADIUS = 3.0e-5         # circumsphere uniformity
TOL_CENTER = 1.0e-6         # centroid at origin

# closed forms for a truncated icosahedron (Goldberg polyhedron GP(1,1))
EXPECT_V, EXPECT_E, EXPECT_F = 60, 90, 32
EXPECT_PENTS, EXPECT_HEXES = 12, 20
EXPECT_DEGREE = 3           # every vertex touches exactly three faces


def _fan_edges(bv):
    """Link edges of an icosphere vertex ordered circularly around it.

    BMVert.link_edges is unordered, so walk the manifold fan: each step
    crosses the link face that shares the current edge, to the face's other
    edge touching bv. A non-manifold vertex breaks the walk — which is
    itself a signal the source topology is not the icosphere we require.
    """
    first = list(bv.link_edges)[0]
    ordered = [first]
    prev_face, current = None, first
    while True:
        # first step: either link face starts the walk; after that, cross to
        # the face that is not the one we came from
        shared = ([current.link_faces[0]] if prev_face is None
                  else [f for f in current.link_faces if f is not prev_face])
        if len(shared) != 1:
            raise RuntimeError("fan walk hit a non-manifold edge")
        face = shared[0]
        cand = [e for e in face.edges if e is not current and bv in e.verts]
        if len(cand) != 1:
            raise RuntimeError("fan walk found no continuation edge")
        nxt = cand[0]
        if nxt is first:
            return ordered
        ordered.append(nxt)
        prev_face, current = face, nxt


def build_ball():
    """Truncate a bmesh icosphere at 1/3 per edge into the Goldberg ball.

    The icosphere is the topology source: cut points are computed per edge,
    pentagons are ordered by the fan walk around each source vertex, and
    hexagons by each source face's loop order. Face winding is normalized
    once at the end with recalc_face_normals on the closed solid.
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)

    src = bmesh.new()
    ball = bmesh.new()
    try:
        bmesh.ops.create_icosphere(src, subdivisions=1, radius=1.0)
        src.verts.ensure_lookup_table()
        src.edges.ensure_lookup_table()

        # two cut points per source edge, keyed so the "near" point for
        # either endpoint is retrievable without edge-orientation guessing
        cut = {}
        for e in src.edges:
            a, b = e.verts
            i, j = sorted((a.index, b.index))
            pa = a.co + (b.co - a.co) * TRUNC_T        # near a
            pb = a.co + (b.co - a.co) * (2.0 * TRUNC_T)  # near b
            cut[(i, j)] = (pa, pb) if a.index == i else (pb, pa)

        # each cut point is shared by exactly one pentagon and one hexagon,
        # so verts are created once and reused — duplicating them per face
        # would leave 180 loose vertices instead of the 60-vertex closed solid
        bvert = {}

        def near(i, j):
            """Ball vertex on edge (i,j) at the cut nearest source vertex i."""
            key = (min(i, j), max(i, j), i)
            if key not in bvert:
                pa, pb = cut[(key[0], key[1])]
                bvert[key] = ball.verts.new(pa if i < j else pb)
            return bvert[key]

        # 12 pentagons: one per source vertex, from the fan-walked link edges
        for v in src.verts:
            ring = [near(v.index, e.other_vert(v).index) for e in _fan_edges(v)]
            ball.faces.new(ring)

        # 20 hexagons: one per source triangle, in loop order
        for f in src.faces:
            i0, i1, i2 = (v.index for v in f.verts)
            ring = [
                near(i0, i1), near(i1, i0),
                near(i1, i2), near(i2, i1),
                near(i2, i0), near(i0, i2),
            ]
            ball.faces.new(ring)

        bmesh.ops.recalc_face_normals(ball, faces=ball.faces)

        # normalize scale: the solid is centered at the origin by symmetry,
        # so scale the mean circumradius to the target ball radius
        ball.verts.ensure_lookup_table()
        r_mean = sum(v.co.length for v in ball.verts) / len(ball.verts)
        bmesh.ops.scale(ball, vec=(BALL_RADIUS / r_mean,) * 3, verts=ball.verts)

        me = bpy.data.meshes.new("SoccerBall")
        ball.to_mesh(me)
    finally:
        src.free()
        ball.free()  # the ownership contract from always-free-bmesh

    obj = bpy.data.objects.new("SoccerBall", me)
    bpy.context.collection.objects.link(obj)

    # the two panel materials exist in both modes — the binding is part of
    # the contract the check reads, not a render-only decoration
    white = bpy.data.materials.new("PanelWhite")
    black = bpy.data.materials.new("PanelBlack")
    me.materials.append(white)   # slot 0: hexagons
    me.materials.append(black)   # slot 1: pentagons

    # bound by face CLASS (vertex count), never by enumeration order: a
    # builder that assigns "first 12 faces black" passes only by luck of
    # bmesh face ordering, and the check below must catch it
    for poly in me.polygons:
        poly.material_index = 1 if len(poly.vertices) == 5 else 0
    return obj


def _newell(points):
    """Independent Newell normal for a polygon ring (no Blender normal used)."""
    nx = ny = nz = 0.0
    for i, p in enumerate(points):
        q = points[(i + 1) % len(points)]
        nx += (p.y - q.y) * (p.z + q.z)
        ny += (p.z - q.z) * (p.x + q.x)
        nz += (p.x - q.x) * (p.y + q.y)
    n = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (nx / n, ny / n, nz / n)


def check(obj):
    me = obj.data

    got = (len(me.vertices), len(me.edges), len(me.polygons))
    if got != (EXPECT_V, EXPECT_E, EXPECT_F):
        print(f"ERROR: topology {got} != expected "
              f"{(EXPECT_V, EXPECT_E, EXPECT_F)}", file=sys.stderr)
        return 3
    euler = got[0] - got[1] + got[2]
    if euler != 2:
        print(f"ERROR: Euler characteristic {euler} != 2 — not a sphere topology",
              file=sys.stderr)
        return 4

    census = {}
    for p in me.polygons:
        census[len(p.vertices)] = census.get(len(p.vertices), 0) + 1
    if census != {5: EXPECT_PENTS, 6: EXPECT_HEXES}:
        print(f"ERROR: face census {census} != {{5: {EXPECT_PENTS}, 6: {EXPECT_HEXES}}}",
              file=sys.stderr)
        return 5

    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        degrees = [len(v.link_edges) for v in bm.verts]
        deg_min, deg_max = min(degrees), max(degrees)
        if deg_min != EXPECT_DEGREE or deg_max != EXPECT_DEGREE:
            print(f"ERROR: vertex degree spans {deg_min}..{deg_max}, "
                  f"expected uniform {EXPECT_DEGREE}", file=sys.stderr)
            return 6
        bad_edges = sum(1 for e in bm.edges if len(e.link_faces) != 2)
        if bad_edges:
            print(f"ERROR: {bad_edges} edge(s) do not border exactly 2 faces",
                  file=sys.stderr)
            return 7
    finally:
        bm.free()

    lengths = [(me.vertices[e.vertices[0]].co - me.vertices[e.vertices[1]].co).length
               for e in me.edges]
    l_mean = sum(lengths) / len(lengths)
    l_dev = max(abs(l - l_mean) for l in lengths)
    if l_dev > TOL_LEN:
        print(f"ERROR: edge lengths deviate {l_dev:.3e} from mean {l_mean:.6f} "
              f"(tol {TOL_LEN:.1e}) — not a uniform truncation", file=sys.stderr)
        return 8

    worst_planar = 0.0
    for p in me.polygons:
        pts = [me.vertices[i].co for i in p.vertices]
        n = _newell(pts)
        cx = sum(v.x for v in pts) / len(pts)
        cy = sum(v.y for v in pts) / len(pts)
        cz = sum(v.z for v in pts) / len(pts)
        d = max(abs((v.x - cx) * n[0] + (v.y - cy) * n[1] + (v.z - cz) * n[2])
                for v in pts)
        worst_planar = max(worst_planar, d)
    if worst_planar > TOL_PLANAR:
        print(f"ERROR: face planarity worst {worst_planar:.3e} (tol {TOL_PLANAR:.1e})",
              file=sys.stderr)
        return 9

    cx = sum(v.co.x for v in me.vertices) / EXPECT_V
    cy = sum(v.co.y for v in me.vertices) / EXPECT_V
    cz = sum(v.co.z for v in me.vertices) / EXPECT_V
    center_off = math.sqrt(cx * cx + cy * cy + cz * cz)
    if center_off > TOL_CENTER:
        print(f"ERROR: centroid off origin by {center_off:.3e} (tol {TOL_CENTER:.1e})",
              file=sys.stderr)
        return 10
    radii = [math.sqrt((v.co.x - cx) ** 2 + (v.co.y - cy) ** 2 + (v.co.z - cz) ** 2)
             for v in me.vertices]
    r_mean = sum(radii) / len(radii)
    r_dev = max(abs(r - r_mean) for r in radii)
    if r_dev > TOL_RADIUS:
        print(f"ERROR: circumradius deviates {r_dev:.3e} from {r_mean:.6f} "
              f"(tol {TOL_RADIUS:.1e}) — vertices not on one sphere", file=sys.stderr)
        return 11

    if len(me.materials) != 2:
        print(f"ERROR: expected 2 panel materials, found {len(me.materials)}",
              file=sys.stderr)
        return 12
    misbound = [p.index for p in me.polygons
                if p.material_index != (1 if len(p.vertices) == 5 else 0)]
    if misbound:
        print(f"ERROR: {len(misbound)} face(s) carry the wrong panel material for "
              f"their class (first: {misbound[0]}) — binding must follow vertex "
              f"count, not enumeration order", file=sys.stderr)
        return 13

    print(f"V={got[0]} E={got[1]} F={got[2]} euler=2 census=12x5+20x6 "
          f"degree={deg_min}..{deg_max} watertight=True")
    print(f"edge_len mean={l_mean:.6f} max_dev={l_dev:.3e} (tol {TOL_LEN:.1e}) | "
          f"planarity max={worst_planar:.3e} (tol {TOL_PLANAR:.1e})")
    print(f"circumradius mean={r_mean:.6f} max_dev={r_dev:.3e} (tol {TOL_RADIUS:.1e}) | "
          f"centroid_off={center_off:.3e} | panels bound by vertex count (12 black "
          f"pentagons, 20 white hexagons)")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def _panel_materials(obj):
    """Leather finishes for the two panel classes (render path only)."""
    white, black = obj.data.materials
    white.use_nodes = True
    wb = white.node_tree.nodes["Principled BSDF"]
    wb.inputs["Base Color"].default_value = (0.82, 0.82, 0.84, 1.0)
    wb.inputs["Roughness"].default_value = 0.52
    black.use_nodes = True
    bb = black.node_tree.nodes["Principled BSDF"]
    bb.inputs["Base Color"].default_value = (0.018, 0.02, 0.024, 1.0)
    bb.inputs["Roughness"].default_value = 0.48


def render_still(obj, path, engine):
    scene = bpy.context.scene
    me = obj.data
    _panel_materials(obj)

    # the check reads the base mesh; the still adds an UNAPPLIED Subsurf so
    # the faceted Goldberg cage reads as an inflated ball. Panel materials
    # carry through Catmull-Clark per face class, so a misbound panel would
    # still show in the image.
    for poly in me.polygons:
        poly.use_smooth = True
    sub = obj.modifiers.new("Inflate", 'SUBSURF')
    sub.subdivision_type = 'CATMULL_CLARK'
    sub.levels = 2
    sub.render_levels = 2

    # a pentagon sits on the icosphere +Z pole; tip it toward the camera and
    # spin for an asymmetric, match-worn panel layout
    obj.rotation_euler = (math.radians(58.0), math.radians(8.0), math.radians(31.0))

    # rest the ball on the floor by its EVALUATED lowest point, not the
    # cage circumradius: the subsurf surface sinks toward the face inradii,
    # so center-at-RADIUS floats the ball visibly above the floor
    obj.location = (0.0, 0.0, BALL_RADIUS)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    ev_me = ev.to_mesh()
    try:
        min_z = min((ev.matrix_world @ v.co).z for v in ev_me.vertices)
    finally:
        ev.to_mesh_clear()  # no argument: clears this object's evaluated mesh
    obj.location.z -= min_z - 0.002  # 2 mm contact: grounded, not intersecting

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

    # default-stage rig per docs/VISUAL-STYLE.md; the white leather caps the
    # key energy so the pentagons' white neighbors never clip
    light("Key", (-4.0, -5.0, 6.0), 500.0, 5.0, (1.0, 0.96, 0.9), (48, 0, -35))
    light("Fill", (5.0, -3.5, 2.5), 110.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 50))
    light("Rim", (3.0, 4.5, 5.0), 300.0, 4.0, (0.6, 0.78, 1.0), (-55, 0, 155))
    light("Wedge", (2.5, 5.5, 4.0), 380.0, 6.0, (1.0, 0.76, 0.5), (-68, 0, 190))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 55.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -7.2, 3.8)
    cam.rotation_euler = (math.radians(68), 0.0, 0.0)
    scene.collection.objects.link(cam)
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
    # AgX would wash the white leather toward grey and lift the stage
    # (docs/VISUAL-STYLE.md); Standard is the house transform
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

    obj = build_ball()
    code = check(obj)
    if code:
        return code

    if args.output:
        if not render_still(obj, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 6
        print(f"rendered still {args.output}")

    print("soccer-ball-goldberg OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
