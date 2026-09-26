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
from mathutils import Matrix, Vector

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing
import gallery_asset_quality

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


def check(both_safe=False):
    tmp = tempfile.mkdtemp(prefix="bevelweld_")
    safe = beveled_box(DIMS, SAFE_OFFSET)
    degen = beveled_box(DIMS, SAFE_OFFSET if both_safe else DEGEN_OFFSET)

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


SEAM_AREA = 1e-6   # render overlay: faces this thin are drawn as the weld seam
CASE_YAW = 52.0    # render: cases present an end panel to the camera


def _mesh_from_bm(name, build):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        build(bm)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def _part(sc, name, me, mat, parent, loc=(0.0, 0.0, 0.0)):
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    sc.collection.objects.link(ob)
    if parent is not None:
        ob.parent = parent
    return ob


def _block(name, dims, bevel=0.012, segs=2):
    """Small hardware block with worn (beveled) edges."""
    def build(bm):
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= dims[0]
            v.co.y *= dims[1]
            v.co.z *= dims[2]
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=segs,
                        profile=0.5, affect="EDGES", clamp_overlap=True)
    return _mesh_from_bm(name, build)


def _tube_path(bm, pts, radius, sides=12, cap=True):
    """Sweep a circular section along a polyline (rotation-minimising)."""
    pts = [Vector(p) for p in pts]
    rings = []
    ref = Vector((0.0, 0.0, 1.0))
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        t = (b - a).normalized()
        if abs(t.dot(ref)) > 0.95:
            ref = Vector((1.0, 0.0, 0.0))
        u = t.cross(ref).normalized()
        w = u.cross(t).normalized()
        ref = w
        ring = []
        for k in range(sides):
            ang = 2.0 * math.pi * k / sides
            ring.append(bm.verts.new(p + radius * (math.cos(ang) * u + math.sin(ang) * w)))
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            bm.faces.new((r0[k], r0[(k + 1) % sides], r1[(k + 1) % sides], r1[k]))
    if cap:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])


def build_case(sc, prefix, offset, mats, loc, rot_z):
    """A rugged hard-shell equipment case whose shell IS the checked mesh:
    beveled_box(DIMS, offset) — the same data the check asserts on. All
    fittings sit inside the flat front/top area that survives both
    offsets, so the only difference between the two cases is the bevel."""
    shell_me = beveled_box(DIMS, offset)
    shell_me.name = f"{prefix}.Shell"
    shell = _part(sc, f"{prefix}.Shell", shell_me, mats["shell"], None, loc)
    shell.rotation_euler = (0.0, 0.0, math.radians(rot_z))
    hx, hy, hz = (d / 2 for d in DIMS)
    parts = [shell]

    # carry handle: two pivot blocks + a swept D-grip on the top ridge
    for sx in (-1, 1):
        parts.append(_part(sc, f"{prefix}.HandlePivot{'LR'[sx > 0]}",
                           _block(f"{prefix}.HandlePivot", (0.10, 0.12, 0.07), 0.015),
                           mats["steel"], shell, (sx * 0.30, 0.0, hz + 0.02)))

    def grip(bm):
        pts = []
        for i in range(25):
            t = math.pi * i / 24
            pts.append((-0.30 * math.cos(t), 0.0,
                        hz + 0.04 + 0.13 * math.sin(t) ** 0.55))
        _tube_path(bm, pts, 0.028, sides=14)
    parts.append(_part(sc, f"{prefix}.HandleGrip", _mesh_from_bm(f"{prefix}.Grip", grip),
                       mats["rubber"], shell))

    # front fittings — lid seam strip, twin draw latches across it, a
    # molded rib pair and an ID plate (asymmetric, inside the flat land)
    fy = -hy
    parts.append(_part(sc, f"{prefix}.LidSeam",
                       _block(f"{prefix}.LidSeam", (1.16, 0.02, 0.035), 0.008),
                       mats["shell_dark"], shell, (0.0, fy - 0.004, 0.17)))
    for sx in (-1, 1):
        parts.append(_part(sc, f"{prefix}.LatchBase{'LR'[sx > 0]}",
                           _block(f"{prefix}.LatchBase", (0.16, 0.04, 0.22), 0.012),
                           mats["steel"], shell, (sx * 0.40, fy - 0.01, 0.17)))
        parts.append(_part(sc, f"{prefix}.LatchLever{'LR'[sx > 0]}",
                           _block(f"{prefix}.LatchLever", (0.11, 0.035, 0.13), 0.014),
                           mats["accent"], shell, (sx * 0.40, fy - 0.045, 0.15)))
    # molded reinforcement frame around the front land
    for nm, dims, pos in (("FrameTop", (1.17, 0.03, 0.035), (0.0, 0.28)),
                          ("FrameBottom", (1.17, 0.03, 0.035), (0.0, -0.28)),
                          ("FrameL", (0.035, 0.03, 0.595), (-0.57, 0.0)),
                          ("FrameR", (0.035, 0.03, 0.595), (0.57, 0.0))):
        parts.append(_part(sc, f"{prefix}.{nm}",
                           _block(f"{prefix}.{nm}", dims, 0.01),
                           mats["shell"], shell, (pos[0], fy - 0.008, pos[1])))
    for z in (-0.10, -0.20):
        parts.append(_part(sc, f"{prefix}.Rib{int(abs(z) * 100)}",
                           _block(f"{prefix}.Rib", (0.50, 0.03, 0.04), 0.012),
                           mats["shell_dark"], shell, (-0.29, fy - 0.005, z)))
    for sx in (-1, 1):
        parts.append(_part(sc, f"{prefix}.Hasp{'LR'[sx > 0]}",
                           _block(f"{prefix}.Hasp", (0.05, 0.03, 0.09), 0.01),
                           mats["steel"], shell, (sx * 0.27, fy - 0.01, 0.17)))
    for nm, rad, depth, yoff, mat in (("PurgeValve", 0.06, 0.03, 0.010, "steel"),
                                      ("PurgeCap", 0.042, 0.05, 0.022, "rubber")):
        def valve(bm, rad=rad, depth=depth):
            bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=rad,
                                  radius2=rad, depth=depth,
                                  matrix=Matrix.Rotation(math.radians(90), 4, "X"))
            bmesh.ops.bevel(bm, geom=[e for e in bm.edges
                                      if len(e.link_faces) == 2 and
                                      e.calc_face_angle(0.0) > 1.0],
                            offset=0.006, segments=2, profile=0.5,
                            affect="EDGES", clamp_overlap=True)
        parts.append(_part(sc, f"{prefix}.{nm}", _mesh_from_bm(f"{prefix}.{nm}", valve),
                           mats[mat], shell, (0.10, fy - yoff, -0.15)))
    parts.append(_part(sc, f"{prefix}.IdPlate",
                       _block(f"{prefix}.IdPlate", (0.22, 0.02, 0.13), 0.008),
                       mats["plate"], shell, (0.40, fy - 0.004, -0.15)))

    # rubber feet on the bottom ridge line
    for sx in (-1, 1):
        parts.append(_part(sc, f"{prefix}.Foot{'LR'[sx > 0]}",
                           _block(f"{prefix}.Foot", (0.20, 0.16, 0.06), 0.02),
                           mats["rubber"], shell, (sx * 0.52, 0.0, -hz - 0.01)))
    return shell, parts


def build_weld_overlay(sc, shell, mat_seam, mat_hot):
    """Hot overlay drawn from live mesh data on the degenerate shell:
    the seam tube runs along every edge of every face thinner than
    SEAM_AREA (the collapsed top/end lands and corner bands meeting at
    mid-depth), and a glow bead sits on each zero-area face the check
    counts. Change the offset and the overlay moves or disappears."""
    me = shell.data
    thin = [p for p in me.polygons if p.area <= SEAM_AREA]
    counted = [p for p in me.polygons if p.area <= AREA_EPS]
    edges = set()
    for p in thin:
        for ek in p.edge_keys:
            edges.add(tuple(sorted(ek)))
    segs = []
    for a, b in edges:
        va, vb = me.vertices[a].co, me.vertices[b].co
        if (vb - va).length > 1e-4:
            segs.append((va.copy(), vb.copy()))
    print(f"render_defects thin_faces={len(thin)} zero_area_faces={len(counted)} "
          f"seam_segments={len(segs)}")

    def seam(bm):
        for va, vb in segs:
            _tube_path(bm, [va, vb], 0.018, sides=10)
        joints = {tuple(round(c, 5) for c in v) for s in segs for v in s}
        for j in joints:
            bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.020,
                                      matrix=Matrix.Translation(j))
    seam_ob = _part(sc, "WeldSeam", _mesh_from_bm("WeldSeam", seam), mat_seam, shell)

    def beads(bm):
        for p in counted:
            bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.038,
                                      matrix=Matrix.Translation(p.center))
    bead_ob = _part(sc, "PinchBeads", _mesh_from_bm("PinchBeads", beads), mat_hot, shell)
    return [seam_ob, bead_ob]


def render_still(path, engine):
    """Two rugged cases whose shells are the check's two meshes. Left:
    offset 0.10 — flat top land, crisp chamfer bands. Right: offset 0.20
    == min/2 — the lands vanish, the band rolls into a knife ridge at
    mid-depth, and that collapsed seam glows hot from live mesh data."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene

    def mats(tag):
        return {
            "shell": make_material(f"{tag}.Polymer", (0.02, 0.16, 0.42), rough=0.42,
                                   metallic=0.0),
            "shell_dark": make_material(f"{tag}.PolymerRib", (0.012, 0.075, 0.20),
                                        rough=0.55, metallic=0.0),
            "steel": make_material(f"{tag}.Steel", (0.62, 0.63, 0.66), rough=0.32,
                                   metallic=1.0),
            "accent": make_material(f"{tag}.LatchAnodized", (0.95, 0.52, 0.06),
                                    rough=0.35, metallic=0.6),
            "rubber": make_material(f"{tag}.Rubber", (0.025, 0.025, 0.028), rough=0.8,
                                    metallic=0.0),
            "plate": make_material(f"{tag}.IdPlate", (0.80, 0.78, 0.70), rough=0.3,
                                   metallic=0.9),
        }

    hz = DIMS[2] / 2 + 0.04    # feet lift the shell
    safe, safe_parts = build_case(sc, "CaseSafe", SAFE_OFFSET, mats("Safe"),
                                  (-0.95, 0.2, hz), CASE_YAW)
    degen, degen_parts = build_case(sc, "CaseDegen", DEGEN_OFFSET, mats("Degen"),
                                    (0.95, -0.2, hz), CASE_YAW)
    seam_mat = make_material("WeldSeam", (1.0, 0.06, 0.02), rough=0.4, metallic=0.0,
                             emit=(1.0, 0.05, 0.02), estr=2.2)
    hot_mat = make_material("PinchHot", (1.0, 0.2, 0.05), rough=0.4, metallic=0.0,
                            emit=(1.0, 0.16, 0.04), estr=3.0)
    overlay = build_weld_overlay(sc, degen, seam_mat, hot_mat)

    floor, wall = build_studio(sc)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (-0.6, -4.9, 3.1)
    sc.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.1, 0.55)
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
    # Turn the stage, not the props: every root object swings by -CASE_YAW,
    # which leaves the image unchanged but the cases axis-aligned in world
    # space (as shipped assets are, and as the asset-sheet panel expects).
    turn = Matrix.Rotation(math.radians(-CASE_YAW), 4, "Z")
    bpy.context.view_layer.update()
    for ob in list(sc.objects):
        if ob.parent is None:
            ob.matrix_world = turn @ ob.matrix_world
    bpy.context.view_layer.update()
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation.
    hero = safe_parts + degen_parts
    fcode = gallery_framing.check_framing(
        sc, cam,
        hero=hero,
        elements=hero + overlay,
        stage=[floor, wall],
    )
    if fcode:
        return fcode
    # Asset-quality floors on the designed prop (the clean case) — exit 11.
    aqcode = gallery_asset_quality.check_asset_quality(
        sc, cam, hero=safe_parts, stage=[floor, wall])
    if aqcode:
        return aqcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 9
    return 0


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
    light("Rim", (1.5, 4.5, 3.5), 200.0, 3.0, (0.6, 0.78, 1.0), (-55, 0, 170))
    light("Wedge", (2.0, 6.0, 3.6), 450.0, 6.0, (1.0, 0.70, 0.40), (-62, 0, 190))
    return floor, wall


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--both-safe", action="store_true",
                   help="bevel the degenerate box at the safe offset (must fail)")
    args = p.parse_args(argv)

    print(f"binary version: {bpy.app.version} ({bpy.app.version_string})")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    code = check(both_safe=args.both_safe)
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
