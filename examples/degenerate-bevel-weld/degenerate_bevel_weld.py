"""Degenerate bevel weld — the half-dimension collapse that ships to disk.

Witnesses the bevel-threshold hazard a prop pipeline hits when a width is
authored against one box and later used on a thinner one: `bmesh.ops.bevel`
(or the Bevel modifier) with offset >= half the smallest box dimension
collapses the bevel band into zero-area faces, and those degenerate
triangles cross the export boundary — re-parsed from the GLB itself, they
are sitting in the shipped file, where an engine-side merge-by-distance
welds their loops. Found authoring `gltf-export-roundtrip` (its count check
caught a 36-vertex weld on a thin crate part); this example isolates the
threshold with closed forms at every stage.

Check (all closed form or independently re-derived, nothing captured):

1. Threshold: offset 0.10 (< 0.20 = min_dim/2) yields ZERO zero-area faces;
   offset 0.20 (== min_dim/2) yields exactly 12 == 4 min-axis edges x
   3 segments, with min_area collapsing > 1e5x (5.8e-04 vs ~1.8e-09).
2. Collapse witness: coincident-position verts == 16 == 4 edges x
   (segments+1), re-derived by 6-decimal position grouping.
3. Export crossing: a stdlib re-parse of the exported GLB recomputes every
   triangle area from raw POSITION+indices — 32 degenerate triangles ship
   (the 12 collapsed faces triangulated, MEASURED regression constant like
   curve-bevel-arc's EXPECT_VERTS; re-measure recipe in check()), versus
   zero for the safe mesh, and the exporter ships every loop
   (positions == loop count) — nothing warns you.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python degenerate_bevel_weld.py --                 # check only
    blender --background --python degenerate_bevel_weld.py -- --output b.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse, json, struct, tempfile

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing

DIMS = (1.6, 0.4, 1.0)          # min dim 0.4 -> half = 0.2, the threshold
SAFE_OFFSET = 0.10
DEGEN_OFFSET = 0.20             # exactly half the min dimension
SEGMENTS = 3
AREA_EPS = 1e-8
MIN_EDGES_MIN_AXIS = 4          # edges parallel to the min (Y) axis on a box
EXPECT_DEGEN_FACES = 12         # 4 min-axis edges x SEGMENTS (closed form)
EXPECT_COINCIDENT = 16          # 4 edges x (SEGMENTS + 1) (closed form)
EXPECT_GLB_DEGEN_TRIS = 32      # MEASURED regression constant (see check step 3)
EXPECT_LOOPS = 384              # 96 verts, 4 loops/face x 96... measured: loops


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def beveled_box(dims, offset, segments=SEGMENTS, clamp=True):
    """Box scaled to dims with every edge beveled — bmesh path, deterministic."""
    me = bpy.data.meshes.new("Crate")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= dims[0]
            v.co.y *= dims[1]
            v.co.z *= dims[2]
        bmesh.ops.bevel(
            bm,
            geom=list(bm.edges),
            offset=offset,
            segments=segments,
            profile=0.5,
            affect="EDGES",
            clamp_overlap=clamp,
        )
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def zero_area_count(me, eps=AREA_EPS):
    return sum(1 for p in me.polygons if p.area <= eps)


def min_area(me):
    return min(p.area for p in me.polygons)


def coincident_verts(me, ndp=6):
    """Extra verts sharing a position at ndp-decimal rounding — the loops a
    downstream merge-by-distance will weld."""
    seen = set()
    extra = 0
    for v in me.vertices:
        key = tuple(round(c, ndp) for c in v.co)
        if key in seen:
            extra += 1
        seen.add(key)
    return extra


def glb_degenerate_tris(path, eps=AREA_EPS):
    """Stdlib GLB re-parse: recompute every triangle area from the raw
    POSITION + indices buffers. Independent of Blender's mesh API."""
    with open(path, "rb") as f:
        data = f.read()
    jlen = struct.unpack_from("<I", data, 12)[0]
    js = json.loads(data[20: 20 + jlen])
    bin_ofs = 20 + jlen + 8
    prim = js["meshes"][0]["primitives"][0]
    pos_acc = js["accessors"][prim["attributes"]["POSITION"]]
    pos_bv = js["bufferViews"][pos_acc["bufferView"]]
    pos = struct.unpack_from(
        f"<{pos_acc['count'] * 3}f", data, bin_ofs + pos_bv.get("byteOffset", 0)
    )
    idx_acc = js["accessors"][prim["indices"]]
    idx_bv = js["bufferViews"][idx_acc["bufferView"]]
    fmt = {5123: "H", 5125: "I"}[idx_acc["componentType"]]
    idx = struct.unpack_from(
        f"<{idx_acc['count']}{fmt}", data, bin_ofs + idx_bv.get("byteOffset", 0)
    )
    degen = 0
    min_a = None
    for t in range(0, len(idx), 3):
        a = pos[idx[t] * 3: idx[t] * 3 + 3]
        b = pos[idx[t + 1] * 3: idx[t + 1] * 3 + 3]
        c = pos[idx[t + 2] * 3: idx[t + 2] * 3 + 3]
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        n = (
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        )
        area = 0.5 * math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
        if min_a is None or area < min_a:
            min_a = area
        if area <= eps:
            degen += 1
    return degen, min_a, pos_acc["count"]


def export_glb(ob, path):
    # per-object file: the parse reads meshes[0], so export only this object
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=path, export_format="GLB", export_apply=False, use_selection=True
    )
    return path


def check():
    tmp = tempfile.mkdtemp(prefix="bevelweld_")
    safe = beveled_box(DIMS, SAFE_OFFSET)
    degen = beveled_box(DIMS, DEGEN_OFFSET)

    # --- 1. threshold: zero-area faces flip on at offset == half min dim ---
    safe_za = zero_area_count(safe)
    degen_za = zero_area_count(degen)
    safe_min = min_area(safe)
    degen_min = min_area(degen)
    print(f"threshold safe_za={safe_za} degen_za={degen_za} "
          f"(closed form {MIN_EDGES_MIN_AXIS} edges x {SEGMENTS} segs = "
          f"{EXPECT_DEGEN_FACES})")
    if safe_za != 0:
        print(f"ERROR: safe bevel produced {safe_za} zero-area faces — the "
              f"threshold moved below offset {SAFE_OFFSET}", file=sys.stderr)
        return 3
    if degen_za != EXPECT_DEGEN_FACES:
        print(f"ERROR: degenerate bevel produced {degen_za} zero-area faces, "
              f"closed form {EXPECT_DEGEN_FACES} — re-derive via "
              f"zero_area_count() if bevel internals change", file=sys.stderr)
        return 4
    ratio = safe_min / max(degen_min, 1e-30)
    print(f"min_area safe={safe_min:.3e} degen={degen_min:.3e} ratio={ratio:.3e}")
    if ratio < 1e5:
        print("ERROR: min_area collapse under 1e5x — the band did not pinch",
              file=sys.stderr)
        return 5

    # --- 2. collapse witness: coincident-position verts ---
    safe_co = coincident_verts(safe)
    degen_co = coincident_verts(degen)
    print(f"coincident safe={safe_co} degen={degen_co} "
          f"(closed form {MIN_EDGES_MIN_AXIS} x ({SEGMENTS}+1) = {EXPECT_COINCIDENT})")
    if safe_co != 0 or degen_co != EXPECT_COINCIDENT:
        print("ERROR: coincident-position count off the closed form",
              file=sys.stderr)
        return 6

    # --- 3. export crossing: degenerate tris ship in the GLB ---
    safe_ob = bpy.data.objects.new("Safe", safe)
    bpy.context.collection.objects.link(safe_ob)
    degen_ob = bpy.data.objects.new("Degen", degen)
    bpy.context.collection.objects.link(degen_ob)
    safe_path = export_glb(safe_ob, os.path.join(tmp, "safe.glb"))
    degen_path = export_glb(degen_ob, os.path.join(tmp, "degen.glb"))
    s_tri, s_min, s_pos = glb_degenerate_tris(safe_path)
    d_tri, d_min, d_pos = glb_degenerate_tris(degen_path)
    nloops = len(degen.loops)
    print(f"glb safe_tris_degen={s_tri} degen_tris_degen={d_tri} "
          f"(expected {EXPECT_GLB_DEGEN_TRIS}) positions={d_pos} loops={nloops}")
    if s_tri != 0:
        print("ERROR: safe GLB carries degenerate triangles", file=sys.stderr)
        return 7
    if d_tri != EXPECT_GLB_DEGEN_TRIS:
        # MEASURED regression constant (like curve-bevel-arc EXPECT_VERTS):
        # the 12 collapsed faces triangulate; if a future Blender changes
        # triangulation, re-measure with glb_degenerate_tris() and update.
        print(f"ERROR: GLB carries {d_tri} degenerate triangles, expected "
              f"{EXPECT_GLB_DEGEN_TRIS} — re-measure if triangulation changed",
              file=sys.stderr)
        return 8
    if d_pos != nloops:
        print(f"ERROR: exported positions {d_pos} != loops {nloops} — the "
              f"exporter welded unexpectedly for this shape", file=sys.stderr)
        return 8

    print(f"degenerate-bevel-weld OK threshold@{DIMS[1]/2} collapse "
          f"{degen_za}f/{degen_co}v ships {d_tri} degenerate tris in the GLB")
    return 0


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


def _degen_face_centers(me, eps=AREA_EPS):
    return [p.center.copy() for p in me.polygons if p.area <= eps]


def render_still(path, engine):
    """Dual tray: clean bevel vs collapsed band, with the zero-area faces
    marked from live mesh data — the seam markers ARE the check's numbers."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene

    tray_mat = make_material("Tray", (0.10, 0.34, 0.34), rough=0.38, metallic=0.75)
    seam_mat = make_material("SeamMark", (0.95, 0.25, 0.1), rough=0.4,
                             metallic=0.1, emit=(1.0, 0.3, 0.1), estr=1.2)

    safe_me = beveled_box(DIMS, SAFE_OFFSET)
    safe_me.materials.append(tray_mat)
    safe_ob = bpy.data.objects.new("SafeTray", safe_me)
    safe_ob.location = (-1.15, 0.0, 0.55)
    sc.collection.objects.link(safe_ob)

    degen_me = beveled_box(DIMS, DEGEN_OFFSET)
    degen_me.materials.append(tray_mat)
    degen_ob = bpy.data.objects.new("DegenTray", degen_me)
    degen_ob.location = (1.15, 0.0, 0.55)
    sc.collection.objects.link(degen_ob)

    # seam markers at every zero-area face centroid — overlay from live data
    centers = _degen_face_centers(degen_me)
    print(f"render_defects zero_area_faces={len(centers)}")
    for i, co in enumerate(centers):
        sme = bpy.data.meshes.new(f"Seam{i}")
        sbm = bmesh.new()
        try:
            bmesh.ops.create_uvsphere(sbm, u_segments=8, v_segments=6, radius=0.022)
            sbm.to_mesh(sme)
        finally:
            sbm.free()
        sme.materials.append(seam_mat)
        sob = bpy.data.objects.new(f"Seam{i}", sme)
        sob.location = degen_ob.location + co
        sc.collection.objects.link(sob)

    p_safe = placard(sc, "BEVEL 0.10", (-1.15, -1.1, 0.02), size=0.13)
    p_degen = placard(sc, "BEVEL 0.20 = min/2", (1.15, -1.1, 0.02), size=0.11)

    floor, wall = build_studio(sc)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -6.6, 2.9)
    sc.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.6)
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
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation.
    hero = [safe_ob, degen_ob]
    seams = [o for o in sc.objects if o.name.startswith("Seam")]
    fcode = gallery_framing.check_framing(
        sc, cam,
        hero=hero,
        elements=hero + [p_safe, p_degen] + seams,
        stage=[floor, wall],
    )
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 9
    return 0


def placard(sc, text, loc, size=0.18):
    cu = bpy.data.curves.new(text, "FONT")
    cu.body = text
    cu.size = size
    cu.align_x = "CENTER"
    ob = bpy.data.objects.new(text, cu)
    ob.location = loc
    sc.collection.objects.link(ob)
    ob.data.materials.append(make_material("Label", (0.9, 0.9, 0.92),
                                           rough=0.6, metallic=0.0))
    return ob


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
    light("Wedge", (2.5, 5.5, 4.0), 400.0, 6.0, (1.0, 0.72, 0.42), (-68, 0, 190))
    return floor, wall


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
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

    print("degenerate-bevel-weld OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
