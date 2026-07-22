"""Mesh hygiene audit — engine-ingest topology as a runnable contract.

Witnesses the mesh-cleanliness checklist a prop pipeline relies on before
engine ingest: no ngons, no loose vertices, no non-manifold edges, no
zero-area faces, consistent outward winding, and Euler characteristic 2 for
a closed manifold solid. Every gate is derived from mesh combinatorics or
the divergence-theorem volume — never from a prior-run capture.

Companion to collision-hull-proxy (watertight / Euler on *hulls*) and
bmesh-gear (watertight parametric solid): this example audits an authored
utility-pedestal prop and stages a dirty-vs-clean dual panel so a broken
path reads in the thumbnail.

By default it runs only the correctness check (no render). Pass --output
to also render a still:

    blender --background --python mesh_hygiene_audit.py --
    blender --background --python mesh_hygiene_audit.py -- --output h.png
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Matrix, Vector

AREA_EPS = 1e-10
VOL_EPS = 1e-8


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


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


def make_material(name, rgb, rough=0.45, metallic=0.35, emit=None, estr=0.0):
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


def build_utility_pedestal():
    """Backward-compat alias — subject is now a street valve body."""
    return build_street_valve()


def build_street_valve():
    """Single closed manifold: octagonal street valve body (not a box pedestal).

    Explicit quad ring-stack with 8-sided flanges + stem so the solid stays
    quads-only, every edge borders exactly two faces, and Euler V-E+F == 2.
    Differentiated from prop-origin-transform's rectangular pedestal silhouette.
    """
    # (radius, z) rings bottom → top; each ring is a regular octagon
    n = 8
    rings = [
        (0.62, 0.00),  # base flange
        (0.62, 0.14),
        (0.40, 0.14),  # body inset
        (0.40, 0.95),
        (0.55, 0.95),  # top flange
        (0.55, 1.08),
        (0.18, 1.08),  # stem
        (0.18, 1.32),
    ]

    me = bpy.data.meshes.new("StreetValve")
    bm = bmesh.new()
    try:
        ring_verts = []
        for r, z in rings:
            ring = []
            for i in range(n):
                a = 2.0 * math.pi * i / n + math.pi / n  # flat-to-camera bias
                ring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z)))
            ring_verts.append(ring)
        for i in range(len(ring_verts) - 1):
            a, b = ring_verts[i], ring_verts[i + 1]
            for k in range(n):
                kn = (k + 1) % n
                bm.faces.new((a[k], a[kn], b[kn], b[k]))
        bot, top = ring_verts[0], ring_verts[-1]
        # fan caps as quads via center verts would add poles; use triangle fan
        # from a center → tris only on caps (still <=4). Prefer center poles.
        bot_c = bm.verts.new((0.0, 0.0, rings[0][1]))
        top_c = bm.verts.new((0.0, 0.0, rings[-1][1]))
        for k in range(n):
            kn = (k + 1) % n
            bm.faces.new((bot_c, bot[kn], bot[k]))  # outward -Z
            bm.faces.new((top_c, top[k], top[kn]))  # outward +Z

        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        tmp = bpy.data.meshes.new("_tmp_vol")
        bm.to_mesh(tmp)
        if signed_volume(tmp) < 0.0:
            for f in bm.faces:
                f.normal_flip()
        bpy.data.meshes.remove(tmp)

        bm.verts.ensure_lookup_table()
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        bmesh.ops.translate(bm, vec=(-cx, -cy, 0.0), verts=bm.verts)

        bm.to_mesh(me)
    finally:
        bm.free()

    # Brass / copper — distinct from prop-origin teal pedestal
    mat = make_material("ValveBrass", (0.55, 0.38, 0.14), rough=0.38, metallic=0.85)
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = abs(p.normal.z) < 0.85
    ob = bpy.data.objects.new("StreetValve", me)
    bpy.context.collection.objects.link(ob)
    return ob


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
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        loose = sum(1 for v in bm.verts if len(v.link_edges) == 0)
        nonman = sum(1 for e in bm.edges if len(e.link_faces) != 2)
        boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    finally:
        bm.free()

    vol = signed_volume(me)
    euler = nv - ne + nf
    return {
        "nv": nv, "ne": ne, "nf": nf,
        "ngons": ngons,
        "loose": loose,
        "nonman": nonman,
        "boundary": boundary,
        "zero_area": zero_area,
        "min_area": min_area,
        "volume": vol,
        "euler": euler,
    }


def check(me):
    """Assert the clean-prop hygiene contract. Exit codes 3–8 on failure."""
    m = audit(me)
    print(
        f"topology verts={m['nv']} edges={m['ne']} faces={m['nf']} "
        f"euler={m['euler']} volume={m['volume']:.6f} min_area={m['min_area']:.3e}"
    )

    if m["ngons"]:
        print(
            f"ERROR: {m['ngons']} ngon(s) — engine ingest wants tris/quads only",
            file=sys.stderr,
        )
        return 3
    if m["loose"]:
        print(f"ERROR: {m['loose']} loose vertex(es) — degree 0 verts", file=sys.stderr)
        return 4
    if m["nonman"] or m["boundary"]:
        print(
            f"ERROR: non-manifold topology — nonman_edges={m['nonman']} "
            f"boundary_edges={m['boundary']} (closed solid needs every edge "
            f"bordering exactly 2 faces)",
            file=sys.stderr,
        )
        return 5
    if m["zero_area"]:
        print(
            f"ERROR: {m['zero_area']} zero-area face(s) "
            f"(min_area={m['min_area']:.3e} <= {AREA_EPS})",
            file=sys.stderr,
        )
        return 6
    if m["volume"] <= VOL_EPS:
        print(
            f"ERROR: signed volume {m['volume']:.6f} <= {VOL_EPS} — "
            f"winding inverted or open shell",
            file=sys.stderr,
        )
        return 7
    if m["euler"] != 2:
        print(
            f"ERROR: Euler characteristic V-E+F={m['euler']} != 2 — "
            f"not a closed manifold sphere topology",
            file=sys.stderr,
        )
        return 8

    print(
        f"hygiene_ok ngons=0 loose=0 nonman=0 boundary=0 zero_area=0 "
        f"euler=2 volume={m['volume']:.6f} min_area={m['min_area']:.3e}"
    )
    return 0


def inject_defect(me, kind):
    """Mutate a mesh copy for falsification / dirty-panel staging."""
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        if kind == "loose":
            # Local space beside the front face so the dirty-panel bead reads
            # next to the subject (not halfway to the clean panel).
            bm.verts.new((0.0, -0.55, 0.85))
        elif kind == "boundary":
            # Prefer a large camera-facing (-Y) face so the hole reads through
            # to the lit backdrop in the dual-panel still.
            faces = sorted(bm.faces, key=lambda f: -f.calc_area())
            target = None
            for f in faces:
                n = f.normal
                if n.y < -0.55:
                    target = f
                    break
            if target is None:
                for f in faces:
                    if abs(f.normal.x) > 0.7:
                        target = f
                        break
            if target is None and faces:
                target = faces[0]
            if target is not None:
                bmesh.ops.delete(bm, geom=[target], context="FACES_ONLY")
        elif kind == "ngon":
            for e in list(bm.edges):
                if len(e.link_faces) == 2:
                    bmesh.ops.dissolve_edges(bm, edges=[e])
                    break
        elif kind == "flip":
            for f in bm.faces:
                f.normal_flip()
        elif kind == "zero_area":
            if bm.faces:
                f = bm.faces[0]
                verts = list(f.verts)
                if len(verts) >= 3:
                    target = verts[0].co.copy()
                    for v in verts[1:3]:
                        v.co = target
        else:
            raise ValueError(kind)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


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

    light("Key", (-3.5, -4.5, 5.5), 480.0, 4.5, (1.0, 0.96, 0.9), (48, 0, -35))
    light("Fill", (5.0, -3.5, 2.5), 120.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 50))
    light("Rim", (1.5, 4.5, 3.5), 280.0, 3.0, (0.6, 0.78, 1.0), (-55, 0, 170))
    light("Wedge", (2.5, 5.5, 4.0), 420.0, 6.0, (1.0, 0.72, 0.42), (-68, 0, 190))
    light("Glint", (-2.0, -4.0, 3.2), 220.0, 2.0, (1.0, 0.9, 0.75), (55, 0, -20))


def _duplicate_mesh_obj(sc, src, name, loc):
    me = src.data.copy()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    sc.collection.objects.link(ob)
    return ob


def _inject_through_hole(me):
    """Render staging: delete a front/back body-face pair so the void reads.

    Produces boundary edges (same gate class as inject_defect('boundary')).
    Does not change the check path — only the dual-panel still.
    """
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.faces.ensure_lookup_table()
        # Prefer mid-height body faces (not flanges/caps)
        body = [
            f for f in bm.faces
            if abs(f.normal.z) < 0.35 and 0.2 < f.calc_center_median().z < 0.9
        ]
        if not body:
            body = list(bm.faces)
        front = max(body, key=lambda f: -f.normal.y * f.calc_area())
        back = max(body, key=lambda f: f.normal.y * f.calc_area())
        doomed = [front] if front is back else [front, back]
        bmesh.ops.delete(bm, geom=doomed, context="FACES_ONLY")
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


def _defect_geometry(me):
    """Loose-vert coords and boundary edge pairs — same incidence as audit()."""
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        loose = [v.co.copy() for v in bm.verts if len(v.link_edges) == 0]
        boundary = [
            (e.verts[0].co.copy(), e.verts[1].co.copy())
            for e in bm.edges if len(e.link_faces) == 1
        ]
    finally:
        bm.free()
    return loose, boundary


def mark_defects_from_audit(ob):
    """Overlay markers from live mesh defects — not decorative paint.

    Loose verts → emissive beads at measured local coords.
    Boundary edges → emissive tubes along those edge endpoints.
    Body keeps the same brass as CLEAN so the difference is topological.
    """
    sc = bpy.context.scene
    loose, boundary = _defect_geometry(ob.data)
    metrics = audit(ob.data)
    print(
        f"render_defects loose={metrics['loose']} boundary_edges={metrics['boundary']} "
        f"ngons={metrics['ngons']} zero_area={metrics['zero_area']}"
    )

    brass = make_material("DirtyBrass", (0.55, 0.38, 0.14), rough=0.38, metallic=0.85)
    ob.data.materials.clear()
    ob.data.materials.append(brass)

    bead_mat = make_material(
        "LooseBead", (1.0, 0.85, 0.15), rough=0.3, metallic=0.0,
        emit=(1.0, 0.9, 0.2), estr=3.0,
    )
    for i, co in enumerate(loose):
        sme = bpy.data.meshes.new(f"LooseBead{i}")
        sbm = bmesh.new()
        try:
            bmesh.ops.create_uvsphere(sbm, u_segments=10, v_segments=8, radius=0.055)
            sbm.to_mesh(sme)
        finally:
            sbm.free()
        sme.materials.append(bead_mat)
        sob = bpy.data.objects.new(f"LooseBead{i}", sme)
        sob.location = Vector(ob.location) + co
        sc.collection.objects.link(sob)

    edge_mat = make_material(
        "BoundaryEdge", (1.0, 0.25, 0.05), rough=0.35, metallic=0.0,
        emit=(1.0, 0.35, 0.05), estr=2.8,
    )
    for i, (a, b) in enumerate(boundary):
        mid = (a + b) * 0.5
        direction = b - a
        length = direction.length
        if length < 1e-8:
            continue
        eme = bpy.data.meshes.new(f"Bnd{i}")
        ebm = bmesh.new()
        try:
            bmesh.ops.create_cone(
                ebm, cap_ends=True, segments=6,
                radius1=0.018, radius2=0.018, depth=length,
            )
            ebm.to_mesh(eme)
        finally:
            ebm.free()
        eme.materials.append(edge_mat)
        eob = bpy.data.objects.new(f"Bnd{i}", eme)
        eob.location = Vector(ob.location) + mid
        quat = direction.normalized().to_track_quat("Z", "Y")
        eob.rotation_mode = "QUATERNION"
        eob.rotation_quaternion = quat
        sc.collection.objects.link(eob)

    return metrics


def placard(sc, text, loc, size=0.18):
    cu = bpy.data.curves.new(text, "FONT")
    cu.body = text
    cu.size = size
    cu.align_x = "CENTER"
    ob = bpy.data.objects.new(text, cu)
    ob.location = loc
    sc.collection.objects.link(ob)
    mat = make_material("Label", (0.9, 0.9, 0.92), rough=0.6, metallic=0.0)
    ob.data.materials.append(mat)
    return ob


def render_still(clean_ob, path, engine):
    """Dual-panel dirty vs clean — topology defects visible in the pixels.

    DIRTY: camera-facing boundary hole + loose vert; overlays from audit data.
    CLEAN: intact manifold. Same brass on both so color alone cannot carry proof.

    Ngons / zero-area / full winding invert are check-proven but not staged
    (see README) — they do not read as geometry at thumbnail scale without faking.
    """
    sc = bpy.context.scene
    clean_ob.hide_render = True
    clean_ob.hide_viewport = True

    left = _duplicate_mesh_obj(sc, clean_ob, "Dirty", (-1.15, 0.0, 0.0))
    left.rotation_euler.z = math.radians(22.5)
    bpy.context.view_layer.update()
    _inject_through_hole(left.data)
    inject_defect(left.data, "loose")
    mark_defects_from_audit(left)

    right = _duplicate_mesh_obj(sc, clean_ob, "Clean", (1.15, 0.0, 0.0))
    right.rotation_euler.z = math.radians(-12)
    right.data.materials.clear()
    right.data.materials.append(
        make_material("CleanBrass", (0.55, 0.38, 0.14), rough=0.38, metallic=0.85)
    )
    for p in right.data.polygons:
        p.use_smooth = abs(p.normal.z) < 0.85

    placard(sc, "DIRTY", (-1.15, -1.0, 0.02), size=0.15)
    placard(sc, "CLEAN", (1.15, -1.0, 0.02), size=0.15)

    build_studio(sc)
    # Lit card behind DIRTY so the through-hole voids read against warm light
    card_me = bpy.data.meshes.new("HoleCard")
    cbm = bmesh.new()
    try:
        bmesh.ops.create_grid(cbm, x_segments=1, y_segments=1, size=1.2)
        cbm.to_mesh(card_me)
    finally:
        cbm.free()
    card_mat = make_material(
        "HoleCard", (1.0, 0.55, 0.25), rough=0.9, metallic=0.0,
        emit=(1.0, 0.55, 0.2), estr=1.8,
    )
    card_me.materials.append(card_mat)
    card = bpy.data.objects.new("HoleCard", card_me)
    card.location = (-1.15, 1.4, 0.65)
    card.rotation_euler = (math.radians(90), 0.0, 0.0)
    sc.collection.objects.link(card)
    for ob in sc.objects:
        if ob.type == "LIGHT" and ob.name == "Wedge":
            ob.data.energy = 580.0
            ob.location = (0.0, 6.5, 3.5)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.1, -5.6, 1.5)
    sc.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.62)
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
    sc.view_settings.view_transform = "Standard"
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene, build_street_valve()


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument(
        "--engine", default="eevee", choices=("eevee", "cycles"),
        help="render engine for --output",
    )
    args = p.parse_args(argv)

    print(f"binary version: {bpy.app.version} ({bpy.app.version_string})")
    sc, ob = build_scene()
    code = check(ob.data)
    if code:
        return code

    if args.output:
        if not render_still(ob, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 9
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
