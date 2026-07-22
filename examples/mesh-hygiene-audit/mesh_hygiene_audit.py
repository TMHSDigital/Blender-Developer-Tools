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
    """Single closed manifold: street electrical pedestal (fabricated panels).

    Explicit quad ring-stack — flared plinth, cabinet waist, drip-cap flare —
    so the solid stays quads-only with every edge bordering exactly two faces
    and Euler V-E+F == 2. Not a beveled cube: the silhouette steps are the
    authored panels a prop pipeline would audit before ingest.
    """
    # (half_x, half_y, z) rings bottom → top
    rings = [
        (0.58, 0.48, 0.00),  # plinth base
        (0.58, 0.48, 0.18),  # plinth top
        (0.45, 0.35, 0.18),  # cabinet base (inset step)
        (0.45, 0.35, 1.30),  # cabinet top
        (0.52, 0.40, 1.30),  # drip-cap overhang
        (0.52, 0.40, 1.40),  # drip-cap top
    ]

    me = bpy.data.meshes.new("UtilityPedestal")
    bm = bmesh.new()
    try:
        ring_verts = []
        for hx, hy, z in rings:
            ring_verts.append([
                bm.verts.new((-hx, -hy, z)),
                bm.verts.new((hx, -hy, z)),
                bm.verts.new((hx, hy, z)),
                bm.verts.new((-hx, hy, z)),
            ])
        for i in range(len(ring_verts) - 1):
            a, b = ring_verts[i], ring_verts[i + 1]
            for k in range(4):
                n = (k + 1) % 4
                bm.faces.new((a[k], a[n], b[n], b[k]))
        bot = ring_verts[0]
        bm.faces.new((bot[0], bot[3], bot[2], bot[1]))
        top = ring_verts[-1]
        bm.faces.new((top[0], top[1], top[2], top[3]))

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

    mat = make_material("PedestalSteel", (0.18, 0.42, 0.38), rough=0.42, metallic=0.55)
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = False
    ob = bpy.data.objects.new("UtilityPedestal", me)
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
            # Prefer a large side face so the hole reads in the dual-panel still.
            faces = sorted(bm.faces, key=lambda f: -f.calc_area())
            target = None
            for f in faces:
                n = f.normal
                if abs(n.x) > 0.7:  # side panel
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


def mark_defects(ob):
    """Emissive hazard material + wireframe so defects read in-frame."""
    mat = make_material(
        "Hazard", (0.75, 0.18, 0.08), rough=0.5, metallic=0.25,
        emit=(1.0, 0.3, 0.05), estr=0.85,
    )
    wire_mat = make_material(
        "HazardWire", (1.0, 0.35, 0.05), rough=0.4, metallic=0.0,
        emit=(1.0, 0.4, 0.05), estr=2.0,
    )
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    ob.data.materials.append(wire_mat)
    wire = bpy.data.objects.new(ob.name + "Wire", ob.data)
    mod = wire.modifiers.new("Wire", "WIREFRAME")
    mod.thickness = 0.012
    mod.material_offset = 1
    bpy.context.scene.collection.objects.link(wire)
    wire.location = ob.location

    bm = bmesh.new()
    try:
        bm.from_mesh(ob.data)
        coords = [v.co.copy() for v in bm.verts if len(v.link_edges) == 0]
    finally:
        bm.free()
    bead_mat = make_material(
        "LooseBead", (1.0, 0.9, 0.2), rough=0.3, metallic=0.0,
        emit=(1.0, 0.85, 0.1), estr=2.5,
    )
    sc = bpy.context.scene
    for i, co in enumerate(coords):
        sme = bpy.data.meshes.new(f"Bead{i}")
        sbm = bmesh.new()
        try:
            bmesh.ops.create_uvsphere(sbm, u_segments=8, v_segments=6, radius=0.07)
            sbm.to_mesh(sme)
        finally:
            sbm.free()
        sme.materials.append(bead_mat)
        sob = bpy.data.objects.new(f"Bead{i}", sme)
        sob.location = Vector(ob.location) + co
        sc.collection.objects.link(sob)


def add_door_dressing(sc, parent_loc, suffix):
    """Non-audited door plaque + bolts — silhouette only, not in the check mesh."""
    door_m = make_material(f"Door{suffix}", (0.16, 0.20, 0.18), rough=0.4, metallic=0.65)
    bolt_m = make_material(f"Bolt{suffix}", (0.55, 0.45, 0.22), rough=0.35, metallic=0.85)
    # door plaque
    me = bpy.data.meshes.new(f"Door{suffix}")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.transform(
            bm, matrix=Matrix.Diagonal((0.55, 0.03, 0.85, 1.0)), verts=bm.verts,
        )
        bm.to_mesh(me)
    finally:
        bm.free()
    me.materials.append(door_m)
    door = bpy.data.objects.new(f"Door{suffix}", me)
    door.location = (parent_loc[0], parent_loc[1] - 0.365, parent_loc[2] + 0.75)
    sc.collection.objects.link(door)
    for x, z in ((-0.18, 0.45), (0.18, 0.45), (-0.18, 1.05), (0.18, 1.05)):
        bme = bpy.data.meshes.new(f"Bolt{suffix}_{x}_{z}")
        bbm = bmesh.new()
        try:
            bmesh.ops.create_cone(
                bbm, cap_ends=True, segments=10, radius1=0.03, radius2=0.03, depth=0.04,
            )
            bbm.to_mesh(bme)
        finally:
            bbm.free()
        bme.materials.append(bolt_m)
        bob = bpy.data.objects.new(f"Bolt{suffix}_{x}_{z}", bme)
        bob.location = (parent_loc[0] + x, parent_loc[1] - 0.39, parent_loc[2] + z)
        sc.collection.objects.link(bob)


def placard(sc, text, loc):
    cu = bpy.data.curves.new(text, "FONT")
    cu.body = text
    cu.size = 0.22
    cu.align_x = "CENTER"
    ob = bpy.data.objects.new(text, cu)
    ob.location = loc
    sc.collection.objects.link(ob)
    mat = make_material("Label", (0.9, 0.9, 0.92), rough=0.6, metallic=0.0)
    ob.data.materials.append(mat)
    return ob


def render_still(clean_ob, path, engine):
    """Dual-panel dirty (left) vs clean (right) — contract at a glance."""
    sc = bpy.context.scene
    clean_ob.hide_render = True
    clean_ob.hide_viewport = True

    left = _duplicate_mesh_obj(sc, clean_ob, "Dirty", (-1.35, 0.0, 0.0))
    inject_defect(left.data, "boundary")
    inject_defect(left.data, "loose")
    mark_defects(left)
    add_door_dressing(sc, (-1.35, 0.0, 0.0), "Dirty")

    right = _duplicate_mesh_obj(sc, clean_ob, "Clean", (1.35, 0.0, 0.0))
    right.data.materials.clear()
    right.data.materials.append(
        make_material("CleanSteel", (0.18, 0.42, 0.38), rough=0.42, metallic=0.55)
    )
    add_door_dressing(sc, (1.35, 0.0, 0.0), "Clean")

    placard(sc, "DIRTY", (-1.35, -0.85, 0.02))
    placard(sc, "CLEAN", (1.35, -0.85, 0.02))

    build_studio(sc)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 48.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.55, -5.0, 1.55)
    sc.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.70)
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
    return bpy.context.scene, build_utility_pedestal()


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
