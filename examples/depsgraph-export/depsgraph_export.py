"""Depsgraph-evaluated export — a runnable example.

Witnesses the depsgraph lifetime contract AND that modifiers actually ship in
exports. Builds a game controller whose shell is a sparse quad control cage
under a SUBSURF modifier (the buttons, sticks and bumpers are plain modeled
parts parented to it), measures every mesh through
evaluated_get().to_mesh() (each paired with to_mesh_clear()), exports the
scene through wm.obj_export, and asserts:

- the shell's evaluated vertex count equals the Catmull-Clark closed form
  computed from its own cage topology (V, E, F, face corners) at the
  modifier's level — so the evaluated mesh is exactly the subdivided shell,
  not merely "bigger";
- the exported OBJ vertex count equals the summed EVALUATED counts of every
  mesh object (modifier-applied), not the summed base counts.

``--unevaluated`` exports with ``apply_modifiers=False`` and still asserts
the OBJ vertex count equals the depsgraph-evaluated meshes. That is the
falsifier (``--same-axis`` in export-preset-axis). ``--obj`` is a path
selector, not a falsifier.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python depsgraph_export.py --                 # check only
    blender --background --python depsgraph_export.py -- --unevaluated   # must fail
    blender --background --python depsgraph_export.py -- --output d.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse, tempfile
from mathutils import Matrix, Vector

# Shared Layer 1 framing + asset-quality measurement (render path only) — see
# gallery_framing.py / gallery_asset_quality.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing
import gallery_asset_quality

SUBSURF_LEVELS = 2

# ---------------------------------------------------------------------------
# Controller shell cage. A top-view quad grid (X across, Y toward the
# bumpers) with the notch between the grips cut out, extruded through three
# Z layers (bottom, seam, top). Every face is a quad; the solid is closed and
# manifold, which is what the closed form below relies on (it holds for any
# polygon mesh, but a closed quad cage keeps the count easy to audit:
# V = 2 * grid points + boundary points).
# ---------------------------------------------------------------------------
XS = (-3.2, -2.3, -1.2, 0.0, 1.2, 2.3, 3.2)
YS = (-2.4, -1.3, -0.3, 0.6, 1.3)
# kept cells per row (row 0 = grip tips, row 3 = bumper edge)
ROWS = (
    (0, 1, 4, 5),
    (0, 1, 4, 5),
    (0, 1, 2, 3, 4, 5),
    (0, 1, 2, 3, 4, 5),
)


def _shape(i, j):
    """Shaped top-view position of grid point (i, j): grips splay and taper,
    the notch between them arches up, the bumper edge rounds off."""
    x, y = XS[i], YS[j]
    ax, s = abs(x), (1.0 if x >= 0 else -1.0)
    if j == 0:      # grip tips: narrower, splayed outward
        ax = {3.2: 2.85, 2.3: 2.05, 1.2: 1.3}.get(ax, ax)
        y -= 0.10 * (ax / 3.2)
        ax += 0.25
    elif j == 1:
        ax = {3.2: 3.1, 1.2: 1.2}.get(ax, ax)
    elif j == 2 and ax < 1.0:   # arch of the notch between the grips
        y += 0.25
    elif j == 4:    # bumper edge: shoulders drop back, center stays
        y -= 0.18 * (ax / 3.2) ** 2
    return s * ax, y


def _z(x, y, layer):
    """Z of a cage point: domed top, grips hang below the deck."""
    t = max(0.0, min(1.0, (-0.3 - y) / 2.1))   # 0 on the deck, 1 at grip tips
    u = min(1.0, abs(x) / 3.2)
    top = 0.62 + 0.10 * (1.0 - u * u) - 0.22 * t
    bottom = -0.55 * t - 0.05 * (1.0 - u)
    if layer == 0:
        return bottom
    if layer == 1:
        return bottom + 0.55 * (top - bottom)
    return top


def build_shell_cage(me):
    cells = {(i, j) for j, cols in enumerate(ROWS) for i in cols}
    pts = sorted({(i + di, j + dj) for (i, j) in cells for di in (0, 1) for dj in (0, 1)})
    # boundary edges of the kept-cell region, oriented CCW (region on the left)
    bedges = []
    for (i, j) in cells:
        for (a, b, nb) in (((i, j), (i + 1, j), (i, j - 1)),
                           ((i + 1, j), (i + 1, j + 1), (i + 1, j)),
                           ((i + 1, j + 1), (i, j + 1), (i, j + 1)),
                           ((i, j + 1), (i, j), (i - 1, j))):
            if nb not in cells:
                bedges.append((a, b))
    bpts = sorted({p for e in bedges for p in e})

    bm = bmesh.new()
    try:
        layers = {}
        for layer in (0, 2):
            for p in pts:
                x, y = _shape(*p)
                layers[(p, layer)] = bm.verts.new((x, y, _z(x, y, layer)))
        for p in bpts:
            x, y = _shape(*p)
            layers[(p, 1)] = bm.verts.new((x, y, _z(x, y, 1)))
        for (i, j) in cells:
            quad = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            bm.faces.new([layers[(p, 2)] for p in quad])            # top, up
            bm.faces.new([layers[(p, 0)] for p in reversed(quad)])  # bottom, down
        for (a, b) in bedges:
            for lo, hi in ((0, 1), (1, 2)):
                f = bm.faces.new([layers[(a, lo)], layers[(b, lo)],
                                  layers[(b, hi)], layers[(a, hi)]])
                f.material_index = 1 if lo == 0 else 0
        for f in bm.faces:
            if f.normal.z < -0.5:
                f.material_index = 1   # underside is the graphite half
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()


def catmull_clark_vcount(V, E, F, S, levels):
    """Vertex count after `levels` Catmull-Clark steps, from topology alone.

    One step adds a vertex per edge and per face: V' = V + E + F. Each face
    of n corners splits into n quads, so F' = S (face corners), E' = 2E + S,
    and every later face is a quad: S' = 4F'.
    """
    for _ in range(levels):
        V, E, F, S = V + E + F, 2 * E + S, S, 4 * S
    return V


# ---------------------------------------------------------------------------
# Controls: ordinary modeled parts (no modifiers), so their evaluated count
# equals their base count and the export must carry them unchanged.
# ---------------------------------------------------------------------------
def _bevel_all(bm, offset, segments=2):
    """Round the rims only: the facet seams around a cylinder wall are
    already shallow, and beveling them collapses slivers to zero area."""
    rims = [e for e in bm.edges if e.calc_face_angle(0.0) > math.radians(50)]
    bmesh.ops.bevel(bm, geom=rims, offset=offset, segments=segments,
                    affect='EDGES', profile=0.5, clamp_overlap=True)


def part_disc(me, r, h, segs=24, bevel=0.03, dish=0.0):
    """A beveled puck standing on z=0 (button / stick cap); optional dished top."""
    bm = bmesh.new()
    try:
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs,
                              radius1=r, radius2=r, depth=h,
                              matrix=Matrix.Translation((0, 0, h / 2)))
        _bevel_all(bm, bevel)
        if dish:
            for v in bm.verts:
                if v.co.z > h - 1e-4:
                    d = math.hypot(v.co.x, v.co.y) / r
                    v.co.z -= dish * max(0.0, 1.0 - d * d)
        bm.to_mesh(me)
    finally:
        bm.free()


def part_stick(me):
    """Thumbstick: collar ring, neck, and a dished rubber cap."""
    bm = bmesh.new()
    try:
        for (r1, r2, z0, z1) in ((0.50, 0.46, 0.0, 0.06),     # collar
                                 (0.17, 0.17, 0.06, 0.26),    # neck
                                 (0.40, 0.40, 0.26, 0.40)):   # cap
            bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=28,
                                  radius1=r1, radius2=r2, depth=z1 - z0,
                                  matrix=Matrix.Translation((0, 0, (z0 + z1) / 2)))
        _bevel_all(bm, 0.025)
        for v in bm.verts:
            if v.co.z > 0.40 - 1e-4:
                d = math.hypot(v.co.x, v.co.y) / 0.40
                v.co.z -= 0.05 * max(0.0, 1.0 - d * d)
        bm.to_mesh(me)
    finally:
        bm.free()


def part_extrusion(me, outline, h, bevel):
    """Extrude a closed XY outline to height h, beveled (d-pad, pills, bumpers)."""
    bm = bmesh.new()
    try:
        vs = [bm.verts.new((x, y, 0.0)) for (x, y) in outline]
        face = bm.faces.new(vs)
        ext = bmesh.ops.extrude_face_region(bm, geom=[face])
        top = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=top, vec=(0, 0, h))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        _bevel_all(bm, bevel)
        bm.to_mesh(me)
    finally:
        bm.free()


def _stadium(length, width, segs=8):
    r = width / 2
    half = length / 2 - r
    pts = []
    for k in range(segs + 1):
        a = -math.pi / 2 + math.pi * k / segs
        pts.append((half + r * math.cos(a), r * math.sin(a)))
    for k in range(segs + 1):
        a = math.pi / 2 + math.pi * k / segs
        pts.append((-half + r * math.cos(a), r * math.sin(a)))
    return pts


def _cross(arm, w):
    a, b = arm, w / 2
    return [(b, -a), (b, -b), (a, -b), (a, b), (b, b), (b, a),
            (-b, a), (-b, b), (-a, b), (-a, -b), (-b, -b), (-b, -a)]


def principled(name, color, metallic, roughness, emission=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        key = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
        bsdf.inputs[key].default_value = color
        bsdf.inputs["Emission Strength"].default_value = emission
    return mat


def _smooth(me, angle=35.0):
    """Smooth shading with sharp breaks above `angle` (4.1+ mesh API)."""
    me.shade_smooth()
    if angle is not None:
        me.set_sharp_from_angle(angle=math.radians(angle))


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    coll = bpy.context.collection

    me = bpy.data.meshes.new("Gamepad.Shell")
    build_shell_cage(me)
    me.materials.append(principled("Gamepad.Cobalt", (0.014, 0.105, 0.54, 1.0), 0.0, 0.34))
    me.materials.append(principled("Gamepad.Graphite", (0.030, 0.032, 0.040, 1.0), 0.0, 0.55))
    _smooth(me, None)
    shell = bpy.data.objects.new("Gamepad.Shell", me)
    coll.objects.link(shell)
    ss = shell.modifiers.new("Subdivide", 'SUBSURF')
    ss.levels = SUBSURF_LEVELS
    ss.render_levels = SUBSURF_LEVELS

    # Controls sit on the shell's EVALUATED (subdivided) deck: ray-cast the
    # limit surface, not the cage, or every button floats above the plastic.
    dg = bpy.context.evaluated_depsgraph_get()

    def seat(ob, x, y, sink=0.02):
        hit, loc, nrm, _ = shell.ray_cast(Vector((x, y, 5.0)), Vector((0, 0, -1)),
                                          depsgraph=dg)
        if not hit:
            raise RuntimeError(f"{ob.name}: no shell under ({x}, {y})")
        rot = nrm.to_track_quat('Z', 'Y').to_matrix().to_4x4()
        ob.matrix_world = Matrix.Translation(loc - nrm * sink) @ rot
        ob.parent = shell   # shell sits at the identity, so no parent inverse

    rubber = principled("Gamepad.Rubber", (0.018, 0.019, 0.022, 1.0), 0.0, 0.78)
    satin = principled("Gamepad.Satin", (0.07, 0.075, 0.085, 1.0), 0.2, 0.42)
    face_cols = {"A": (0.02, 0.55, 0.12, 1.0), "B": (0.75, 0.03, 0.02, 1.0),
                 "X": (0.03, 0.22, 0.85, 1.0), "Y": (0.95, 0.62, 0.02, 1.0)}

    def part(name, builder, mat, x, y, *args, **kw):
        pme = bpy.data.meshes.new(name)
        builder(pme, *args, **kw)
        pme.materials.append(mat)
        _smooth(pme)
        ob = bpy.data.objects.new(name, pme)
        coll.objects.link(ob)
        seat(ob, x, y)
        return ob

    part("Gamepad.StickL", lambda m: part_stick(m), rubber, -1.55, -0.78)
    part("Gamepad.StickR", lambda m: part_stick(m), rubber, 1.55, -0.78)
    part("Gamepad.DPad", part_extrusion, satin, -2.15, 0.25,
         _cross(0.46, 0.30), 0.12, 0.035)
    for key, (dx, dy) in {"A": (0, -0.34), "B": (0.34, 0), "X": (-0.34, 0),
                          "Y": (0, 0.34)}.items():
        mat = principled(f"Gamepad.Button{key}", face_cols[key], 0.0, 0.30, emission=0.12)
        part(f"Gamepad.Button{key}", part_disc, mat, 2.15 + dx, 0.25 + dy,
             0.15, 0.12, 20, 0.035)
    part("Gamepad.Select", part_extrusion, satin, -0.62, 0.62, _stadium(0.36, 0.13), 0.06, 0.02)
    part("Gamepad.Start", part_extrusion, satin, 0.62, 0.62, _stadium(0.36, 0.13), 0.06, 0.02)
    home = principled("Gamepad.Home", (1.0, 0.50, 0.10, 1.0), 0.0, 0.3, emission=0.8)
    part("Gamepad.Home", part_disc, home, 0.0, 0.0, 0.16, 0.06, 28, 0.02)
    for side in (-1, 1):
        b = part(f"Gamepad.Bumper{'L' if side < 0 else 'R'}", part_extrusion, satin,
                 side * 2.2, 1.16, _stadium(1.5, 0.34), 0.15, 0.05)
        b.rotation_euler.z += math.radians(-side * 8.0)
    return shell


def mesh_objects():
    return sorted((o for o in bpy.context.scene.objects if o.type == 'MESH'),
                  key=lambda o: o.name)


def check(shell, obj_path, unevaluated=False):
    base_total = 0
    eval_total = 0
    shell_eval = None
    # depsgraph lifetime contract: evaluate, read, then release with
    # to_mesh_clear — once per object, never holding two temporaries
    dg = bpy.context.evaluated_depsgraph_get()
    for ob in mesh_objects():
        ev = ob.evaluated_get(dg)
        em = ev.to_mesh()
        n = len(em.vertices)
        ev.to_mesh_clear()  # must be paired; releases the temporary mesh
        base_total += len(ob.data.vertices)
        eval_total += n
        if ob == shell:
            shell_eval = n

    me = shell.data
    V, E, F, S = len(me.vertices), len(me.edges), len(me.polygons), len(me.loops)
    expected = catmull_clark_vcount(V, E, F, S, SUBSURF_LEVELS)

    out = obj_path or os.path.join(tempfile.gettempdir(), "depsgraph_export.obj")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    # obj_export writes the evaluated (modifier-applied) geometry by default
    bpy.ops.wm.obj_export(
        filepath=out,
        export_selected_objects=False,
        apply_modifiers=not unevaluated,
    )
    if not (os.path.exists(out) and os.path.getsize(out) > 0):
        print("ERROR: no OBJ written", file=sys.stderr)
        return 4
    exported = 0
    with open(out, encoding="utf-8") as f:
        for line in f:
            if line.startswith("v "):
                exported += 1

    print(f"shell_cage V={V} E={E} F={F} S={S} levels={SUBSURF_LEVELS} "
          f"shell_eval_vcount={shell_eval} closed_form={expected}")
    print(f"base_vcount={base_total} eval_vcount={eval_total} exported_vcount={exported}")
    if not (shell_eval > V):
        print("ERROR: evaluated mesh did not apply the modifier", file=sys.stderr)
        return 3
    if shell_eval != expected:
        print(f"ERROR: evaluated shell ({shell_eval}) != Catmull-Clark closed form "
              f"({expected})", file=sys.stderr)
        return 7
    if exported != eval_total:
        print(f"ERROR: export ({exported}) != evaluated ({eval_total}); modifier did not ship",
              file=sys.stderr)
        return 5
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def ghost(name, color, alpha):
    """Tinted see-through shell for the cage: transparent mixed with a glossy
    tint, so the sparse facets read as a volume and the wires stay dominant."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.3
    out = nt.nodes["Material Output"]
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = alpha
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(bsdf.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = 'BLENDED'
    return mat


def render_still(shell, path, engine):
    """The cage the .blend holds beside the subdivided controller the OBJ ships."""
    scene = bpy.context.scene
    coll = scene.collection

    # right: the checked scene itself — shell + controls, the export's content.
    # Tilted toward the camera on its grip tips, like a controller on a shelf.
    shell.rotation_euler = (math.radians(30), 0.0, math.radians(-10))
    shell.location = (3.45, -0.3, 0.0)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    lows = []
    for ob in mesh_objects():
        ev = ob.evaluated_get(dg)
        em = ev.to_mesh()
        mw = ob.matrix_world
        lows.append(min((mw @ v.co).z for v in em.vertices))
        ev.to_mesh_clear()
    shell.location.z = -min(lows)
    bpy.context.view_layer.update()
    product = mesh_objects()

    # left: the shell's base datablock with no modifier — the sparse control
    # cage the file stores. Warm wire on every cage edge, a bead on every
    # cage vertex (the V the closed form starts from), faint cobalt facets.
    cage_mat = principled("Cage.Wire", (1.0, 0.42, 0.06, 1.0), 0.0, 0.35, emission=0.6)
    xf = Matrix.Translation((-3.45, 0.3, 0.0)) @ \
        Matrix.Rotation(math.radians(10), 4, 'Z') @ Matrix.Rotation(math.radians(30), 4, 'X')
    cage_me = shell.data.copy()
    cage_me.name = "Cage.Shell"
    cage_me.materials.clear()
    cage_me.materials.append(ghost("Cage.Ghost", (0.02, 0.12, 0.55, 1.0), 0.30))
    for p in cage_me.polygons:
        p.material_index = 0
    cage_me.shade_flat()
    cage_shell = bpy.data.objects.new("Cage.Shell", cage_me)
    wire = bpy.data.objects.new("Cage.Wire", shell.data.copy())
    wire.data.materials.clear()
    wire.data.materials.append(cage_mat)
    w = wire.modifiers.new("wire", 'WIREFRAME')
    w.thickness = 0.045
    w.offset = 0.0
    w.use_even_offset = True
    beads_me = bpy.data.meshes.new("Cage.Beads")
    bm = bmesh.new()
    try:
        for v in shell.data.vertices:
            bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.075,
                                       matrix=Matrix.Translation(v.co))
        bm.to_mesh(beads_me)
    finally:
        bm.free()
    beads_me.materials.append(cage_mat)
    beads_me.shade_smooth()
    beads = bpy.data.objects.new("Cage.Beads", beads_me)
    cage = [cage_shell, wire, beads]
    for ob in cage:
        ob.matrix_world = xf
        coll.objects.link(ob)
    bpy.context.view_layer.update()
    low = min((xf @ v.co).z for v in shell.data.vertices) - 0.075
    for ob in cage:
        ob.location.z -= low
    bpy.context.view_layer.update()

    # Display stands: both pieces are tilted toward the camera, so each back
    # edge rests on a low satin block instead of hanging in the air. Sized
    # from the real underside — the evaluated shell for the product, the
    # cage points for the cage. Render-only; the export already ran.
    stand_mat = principled("Stand.Satin", (0.055, 0.057, 0.066, 1.0), 0.0, 0.45)

    def stand(name, mw, coords, yaw):
        back = [mw @ c for c in coords if c.y > 0.55 and c.z < 0.15]
        top = min(p.z for p in back)
        cx = sum(p.x for p in back) / len(back)
        cy = sum(p.y for p in back) / len(back)
        sme = bpy.data.meshes.new(name)
        part_extrusion(sme, [(-2.3, -0.42), (2.3, -0.42), (2.3, 0.42), (-2.3, 0.42)],
                       top, 0.05)
        sme.materials.append(stand_mat)
        _smooth(sme)
        ob = bpy.data.objects.new(name, sme)
        ob.location = (cx, cy, 0.0)
        ob.rotation_euler = (0.0, 0.0, yaw)
        coll.objects.link(ob)
        return ob

    ev = shell.evaluated_get(dg)
    em = ev.to_mesh()
    shell_pts = [v.co.copy() for v in em.vertices]
    ev.to_mesh_clear()
    stands = [
        stand("Stand.Product", shell.matrix_world, shell_pts, math.radians(-10)),
        stand("Stand.Cage", cage_shell.matrix_world,
              [v.co for v in shell.data.vertices], math.radians(10)),
    ]

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=60.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    floor_me.materials.append(principled("Studio", (0.03, 0.032, 0.037, 1.0), 0.0, 0.7))
    floor = bpy.data.objects.new("Floor", floor_me)
    coll.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 8.0, 0.0)
    wall.rotation_euler = (math.pi / 2, 0.0, 0.0)
    coll.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = \
        (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        coll.objects.link(ob)

    # warm shaped key, faint cool fill, cool rim, warm wedge on the back wall
    # (docs/VISUAL-STYLE.md)
    light("Key", (-4.0, -5.0, 6.5), 580.0, 5.0, (1.0, 0.96, 0.9), (42, 0, -38))
    light("Fill", (7.0, -6.0, 4.5), 110.0, 9.0, (0.75, 0.85, 1.0), (40, 0, 50))
    light("Rim", (1.5, 5.0, 4.5), 260.0, 4.0, (0.6, 0.78, 1.0), (-55, 0, 180))
    light("Wedge", (0.5, 6.0, 3.0), 420.0, 6.0, (1.0, 0.76, 0.5), (-72, 0, 180))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -19.0, 13.2)
    coll.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.3, 0.55)
    coll.objects.link(aim)
    con = cam.constraints.new('TRACK_TO')
    con.target = aim
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'
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
    # AgX would wash the cobalt shell and the orange cage toward pastel
    # (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation, before
    # the beauty render so a defective composition ships no artifact.
    fcode = gallery_framing.check_framing(
        scene, cam,
        hero=product + cage,
        elements=product + cage + stands,
        stage=[floor, wall],
    )
    if fcode:
        return fcode
    # Asset-quality floors on the shipped controller (exit 11).
    qcode = gallery_asset_quality.check_asset_quality(scene, cam, hero=product,
                                                      stage=[floor, wall])
    if qcode:
        return qcode
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
    p.add_argument("--obj", default=None,
                   help="optional: write the exported OBJ here (else a temp path)")
    p.add_argument("--unevaluated", action="store_true",
                   help="export with apply_modifiers=False (must fail)")
    args = p.parse_args(argv)

    shell = build()
    code = check(shell, args.obj, unevaluated=args.unevaluated)
    if code:
        return code

    if args.output:
        rcode = render_still(shell, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("depsgraph-export OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
