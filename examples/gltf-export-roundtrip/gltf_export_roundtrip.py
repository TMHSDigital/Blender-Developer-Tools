"""A sci-fi supply crate round-tripped through glTF export/import — a runnable example.

Witnesses the contracts of the game-asset interchange path that AI-generated
code most often gets silently wrong:

1. The +Y-up convention. glTF is +Y-up, Blender is +Z-up, and
   ``export_yup=True`` (the default) bakes the conversion into the vertex
   data itself — (x, y, z) -> (x, z, -y) on disk — with no node rotation.
   The check parses the exported .gltf JSON and asserts the POSITION accessor
   bounds equal the axis-converted evaluated bounding box, and that the node
   carries neither rotation nor scale. Exporting with ``export_yup=False``
   writes raw Z-up data that every engine will display lying on its back.
2. Modifiers ship evaluated geometry. ``export_apply=True`` applies the
   crate's bevel modifier: the re-imported mesh matches the
   depsgraph-evaluated mesh, not the base cage. With ``export_apply=False``
   the file silently contains the low-poly cage.
3. The round-trip is faithful. Positions, loop normals, UVs, and material
   bindings of the re-imported mesh match the evaluated mesh within float
   tolerances. UVs are V-flipped on disk (glTF texture origin is top-left)
   and flipped back on import — the check proves both flips, reading the
   .bin buffer directly.

Version witness (probed during authoring on Blender 4.5.11 LTS and 5.1.2):
the operator signatures are byte-identical — 109 exporter properties, 20
importer properties, same defaults — and the exported JSON differs only in
``asset.generator`` ("Khronos glTF Blender I/O v4.5.51" vs "v5.1.20"). The
example therefore runs identical kwargs on both versions and guards forward
drift explicitly: every kwarg it passes must still exist in the operator's
RNA (a rename fails the check loudly instead of drifting silently).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python gltf_export_roundtrip.py --                 # check only
    blender --background --python gltf_export_roundtrip.py -- --output c.png  # + render
"""
import bpy, bmesh, sys, os, math, json, struct, shutil, tempfile, argparse
import mathutils

# ---------------------------------------------------------------------------
# Crate specification. Every part is an axis-aligned box, so every base-cage
# vertex is a closed form: center +/- size/2. The parts interpenetrate on
# purpose — kit-bashed shells are how real game props are assembled — and the
# bevel modifier rounds each shell independently.
# ---------------------------------------------------------------------------
PAINT, TRIM, GLOW = 0, 1, 2
BEVEL_WIDTH = 0.03
BEVEL_SEGMENTS = 2

# (name, center, size, material) — 35 shells. Geometry rules that keep the
# exporter's seam-splitting exact: no two shells share a face plane (exact
# float coincidences weld loops on export), interpenetration is fine, and the
# bevel width stays under half of every box dimension.
PARTS = [
    ("body",        (0.0, 0.0, 0.73),       (2.00, 1.40, 1.10), PAINT),
    ("lid",         (0.0, 0.0, 1.42),       (2.14, 1.54, 0.26), PAINT),
    ("lid_plate",   (0.0, 0.0, 1.57),       (0.90, 0.50, 0.08), TRIM),
    ("panel_front", (0.0, -0.725, 0.75),    (1.50, 0.08, 0.70), PAINT),
    ("panel_back",  (0.0, 0.725, 0.75),     (1.50, 0.08, 0.70), PAINT),
    ("panel_left",  (-1.025, 0.0, 0.75),    (0.08, 1.00, 0.70), PAINT),
    ("panel_right", (1.025, 0.0, 0.75),     (0.08, 1.00, 0.70), PAINT),
    ("strip",       (0.0, -0.78, 1.05),     (1.60, 0.10, 0.12), GLOW),
]
PARTS += [("foot", (sx * 0.85, sy * 0.55, 0.09), (0.30, 0.30, 0.24), TRIM)
          for sx in (-1, 1) for sy in (-1, 1)]
PARTS += [("cornerA", (sx * 1.045, sy * 0.63, 0.73), (0.08, 0.24, 1.16), TRIM)
          for sx in (-1, 1) for sy in (-1, 1)]
PARTS += [("cornerB", (sx * 0.92, sy * 0.70, 0.73), (0.24, 0.08, 1.16), TRIM)
          for sx in (-1, 1) for sy in (-1, 1)]
PARTS += [("handle_post", (sx * 1.06, sy * 0.25, 1.00), (0.10, 0.08, 0.30), TRIM)
          for sx in (-1, 1) for sy in (-1, 1)]
PARTS += [("handle_bar", (sx * 1.06, 0.0, 1.13), (0.10, 0.60, 0.08), TRIM)
          for sx in (-1, 1)]
PARTS += [("latch", (sx * 0.55, -0.74, 1.38), (0.10, 0.08, 0.14), TRIM)
          for sx in (-1, 1)]
# rivets frame the front panel's visible band below the glow strip
PARTS += [("rivet", (sx * 0.66, -0.78, sz), (0.08, 0.08, 0.08), TRIM)
          for sx in (-1, 1) for sz in (0.47, 0.90)]
# three status pips on the lid plate share the strip's emissive language
PARTS += [("pip", (sx * 0.18, 0.0, 1.60), (0.08, 0.08, 0.08), GLOW)
          for sx in (-1, 0, 1)]

UV_SCALE = 0.4          # box-map scale; authored UVs are a closed form of position
EXPORT_KWARGS = dict(
    export_format='GLTF_SEPARATE',   # parseable .gltf JSON + .bin buffer
    export_apply=True,               # contract 2: ship the evaluated (beveled) mesh
    export_yup=True,                 # contract 1: bake the +Y-up conversion
    export_texcoords=True,
    export_normals=True,
    export_materials='EXPORT',
    export_animations=False,
    export_image_format='NONE',      # geometry contract only; no textures to pack
)

POS_TOL = 2e-5          # float32 on disk vs float32 in Blender, plus axis math
NRM_TOL = 2e-4
UV_TOL = 3e-5
UNIT_TOL = 1e-3         # |length(n) - 1| for re-imported loop normals
KEY_DIGITS = 4          # position-key grid for attribute lookups


def box_corners(center, size):
    cx, cy, cz = center
    hx, hy, hz = (s / 2 for s in size)
    return [(cx + sx * hx, cy + sy * hy, cz + sz * hz)
            for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]


def boxmap_uv(co, normal):
    """Closed-form UV for a loop: project onto the face's dominant axis plane."""
    ax = max(range(3), key=lambda i: abs(normal[i]))
    if ax == 2:
        return (0.5 + UV_SCALE * co.x, 0.5 + UV_SCALE * co.y)
    if ax == 0:
        return (0.5 + UV_SCALE * co.z, 0.5 + UV_SCALE * co.y)
    return (0.5 + UV_SCALE * co.x, 0.5 + UV_SCALE * co.z)


def build_crate():
    """The supply crate: 35 beveled box shells, 3 material slots, box-mapped UVs."""
    me = bpy.data.meshes.new("SupplyCrate")
    bm = bmesh.new()
    try:
        for _name, center, size, mat in PARTS:
            n0 = len(bm.faces)
            m = (mathutils.Matrix.Translation(center)
                 @ mathutils.Matrix.Diagonal((*size, 1.0)))
            bmesh.ops.create_cube(bm, size=1.0, matrix=m)
            for f in bm.faces[n0:]:
                f.material_index = mat
        bm.to_mesh(me)
    finally:
        bm.free()  # the ownership contract, as always
    for poly in me.polygons:
        poly.use_smooth = False  # crisp low-poly facets; normals are unambiguous
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            loop = me.loops[li]
            uv.data[li].uv = boxmap_uv(me.vertices[loop.vertex_index].co, poly.normal)
    obj = bpy.data.objects.new("SupplyCrate", me)
    bpy.context.collection.objects.link(obj)
    mod = obj.modifiers.new("EdgeRounding", 'BEVEL')
    mod.width = BEVEL_WIDTH
    mod.segments = BEVEL_SEGMENTS
    return obj


def make_materials():
    """Authored PBR set: olive drab paint, gunmetal trim, teal status glow."""
    def pbr(name, base, metallic, roughness, emission=None, strength=0.0):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        b = mat.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*base, 1.0)
        b.inputs["Metallic"].default_value = metallic
        b.inputs["Roughness"].default_value = roughness
        if emission is not None:
            sock = b.inputs.get("Emission Color") or b.inputs["Emission"]
            sock.default_value = (*emission, 1.0)
            b.inputs["Emission Strength"].default_value = strength
        return mat
    return [
        pbr("Paint", (0.16, 0.18, 0.12), 0.15, 0.50),
        pbr("Trim", (0.12, 0.13, 0.15), 0.90, 0.35),
        pbr("Glow", (0.02, 0.20, 0.25), 0.0, 0.40,
            emission=(0.10, 0.75, 0.85), strength=3.0),
    ]


# ---------------------------------------------------------------------------
# Evaluated-mesh capture: the independent reference the file must carry.
# ---------------------------------------------------------------------------
def capture_evaluated(obj):
    """Snapshot the depsgraph-evaluated mesh, then release it (lifetime contract)."""
    deps = bpy.context.evaluated_depsgraph_get()
    ob_eval = obj.evaluated_get(deps)
    me = ob_eval.to_mesh()
    try:
        # loop normals auto-compute on read; Mesh.calc_normals() was removed in
        # 5.0 (deprecated 4.x) — calling it is itself a cross-version hazard
        me.calc_loop_triangles()
        uv = me.uv_layers.active.data
        return {
            "verts": [tuple(v.co) for v in me.vertices],
            "loops": [tuple(me.vertices[l.vertex_index].co) for l in me.loops],
            "normals": [tuple(l.normal) for l in me.loops],
            "uvs": [tuple(uv[i].uv) for i in range(len(me.loops))],
            "tris": [(t.material_index, tuple(t.center))
                     for t in me.loop_triangles],
        }
    finally:
        ob_eval.to_mesh_clear()  # the reference dies here, by contract


def key_of(p, digits=KEY_DIGITS):
    return tuple(round(c, digits) for c in p)


def set_map(positions, values):
    """position key -> set of attribute values (split loops share positions)."""
    m = {}
    for p, v in zip(positions, values):
        m.setdefault(key_of(p), set()).add(tuple(round(c, 6) for c in v))
    return m


def candidates(m, p):
    """Union of the set at p's key and its 26 neighbor keys.

    Values that differ by less than the key grid can straddle a rounding
    boundary; probing the neighboring cells makes the lookup straddle-safe.
    """
    step = 10 ** -KEY_DIGITS
    k0 = key_of(p)
    out = set()
    for dx in (-step, 0.0, step):
        for dy in (-step, 0.0, step):
            for dz in (-step, 0.0, step):
                out |= m.get((k0[0] + dx, k0[1] + dy, k0[2] + dz), set())
    return out


# ---------------------------------------------------------------------------
# glTF JSON + buffer reading (GLTF_SEPARATE layout).
# ---------------------------------------------------------------------------
def read_gltf(path):
    g = json.load(open(path))
    blob = open(os.path.join(os.path.dirname(path),
                             g["buffers"][0]["uri"]), "rb").read()

    def accessor_floats(idx, ncomp):
        acc = g["accessors"][idx]
        bv = g["bufferViews"][acc["bufferView"]]
        off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = bv.get("byteStride", 4 * ncomp)
        return [struct.unpack_from(f"<{ncomp}f", blob, off + stride * i)
                for i in range(acc["count"])]

    return g, accessor_floats


# ---------------------------------------------------------------------------
# The check. Distinct exit codes per contract; measured maxima printed on success.
# ---------------------------------------------------------------------------
def check(crate):
    # contract 0 (version guard): every kwarg we rely on still exists.
    exp_props = {p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties}
    imp_props = {p.identifier for p in bpy.ops.import_scene.gltf.get_rna_type().properties}
    missing = [k for k in EXPORT_KWARGS if k not in exp_props]
    if missing or "filepath" not in exp_props or "filepath" not in imp_props:
        print(f"ERROR: exporter/importer RNA drifted, missing kwargs {missing} — "
              "the API contract this example pins has changed", file=sys.stderr)
        return 3

    me = crate.data
    # base cage is exactly the authored closed form: 35 boxes x 8 corners
    expect = sorted(key_of(c) for _n, ce, s, _m in PARTS for c in box_corners(ce, s))
    got = sorted(key_of(v.co) for v in me.vertices)
    if got != expect:
        print(f"ERROR: base cage drifted from its closed form "
              f"({len(got)} verts vs {len(expect)} expected)", file=sys.stderr)
        return 4

    # authored UVs are the box-map closed form of position + face normal
    uv0 = me.uv_layers["UVMap"].data
    uv_err = max((uv0[li].uv - mathutils.Vector(boxmap_uv(
        me.vertices[me.loops[li].vertex_index].co, p.normal))).length
        for p in me.polygons for li in p.loop_indices)
    if uv_err > 1e-6:
        print(f"ERROR: authored UV drift {uv_err:.3e} from box-map closed form",
              file=sys.stderr)
        return 5

    snap = capture_evaluated(crate)
    if not (len(snap["verts"]) > len(me.vertices) and len(snap["loops"]) > len(me.loops)):
        print("ERROR: bevel modifier produced no evaluated geometry", file=sys.stderr)
        return 6
    # the export/import cycle below wipes the file — read_factory_settings
    # frees this Mesh; capture the count now (touching a freed RNA raises
    # ReferenceError, the classic dangling-reference hazard)
    base_verts = len(me.vertices)

    tmp = tempfile.mkdtemp(prefix="gltf_roundtrip_")
    try:
        path = os.path.join(tmp, "crate.gltf").replace("\\", "/")
        bpy.ops.export_scene.gltf(filepath=path, **EXPORT_KWARGS)

        # contract 1 (on disk): +Y-up is baked into vertex data, no node transform
        g, acc_floats = read_gltf(path)
        prims = g["meshes"][0]["primitives"]
        node = g["nodes"][0]
        if len(g["nodes"]) != 1 or len(g["meshes"]) != 1:
            print("ERROR: expected exactly one node and one mesh on disk", file=sys.stderr)
            return 7
        if "Khronos" not in g["asset"].get("generator", ""):
            print("ERROR: unexpected exporter generator string", file=sys.stderr)
            return 7
        if node.get("rotation") is not None or node.get("scale") is not None:
            print(f"ERROR: yup conversion leaked into the node transform: {node}",
                  file=sys.stderr)
            return 7
        if len(prims) != 3 or {p.get("material") for p in prims} != {0, 1, 2}:
            print(f"ERROR: expected 3 primitives bound to materials 0..2, got "
                  f"{[p.get('material') for p in prims]}", file=sys.stderr)
            return 8
        # contract 2 (on disk): the file carries the evaluated mesh, not the
        # base cage — flat shading + UV seams split exactly one vertex per
        # evaluated loop, so the on-disk POSITION count is the loop count
        disk_verts = sum(g["accessors"][p["attributes"]["POSITION"]]["count"]
                         for p in prims)
        if disk_verts != len(snap["loops"]):
            print(f"ERROR: on-disk POSITION count {disk_verts} != evaluated loop "
                  f"count {len(snap['loops'])} — the file's vertex split drifted "
                  "from the evaluated mesh (export_apply / export_normals contract)",
                  file=sys.stderr)
            return 10

        xs = [v[0] for v in snap["verts"]]
        ys = [v[1] for v in snap["verts"]]
        zs = [v[2] for v in snap["verts"]]
        # Blender (x, y, z) -> glTF (x, z, -y): the +Y-up conversion, in closed form
        want_min = (min(xs), min(zs), -max(ys))
        want_max = (max(xs), max(zs), -min(ys))
        got_min = [1e30] * 3
        got_max = [-1e30] * 3
        for p in prims:
            a = g["accessors"][p["attributes"]["POSITION"]]
            got_min = [min(got_min[i], a["min"][i]) for i in range(3)]
            got_max = [max(got_max[i], a["max"][i]) for i in range(3)]
        bbox_err = max(abs(got_min[i] - want_min[i]) for i in range(3))
        bbox_err = max(bbox_err, max(abs(got_max[i] - want_max[i]) for i in range(3)))
        if bbox_err > POS_TOL:
            print(f"ERROR: on-disk POSITION bounds deviate {bbox_err:.3e} from the "
                  "axis-converted evaluated bbox — the +Y-up convention drifted",
                  file=sys.stderr)
            return 9

        # contract 3a (on disk): TEXCOORD_0 is V-flipped vs Blender UV space
        prim0 = prims[0]["attributes"]
        disk_pos = acc_floats(prim0["POSITION"], 3)
        disk_uv = acc_floats(prim0["TEXCOORD_0"], 2)
        uv_set = set_map(snap["loops"], snap["uvs"])
        flip_err = 0.0
        for pd, (u, v) in zip(disk_pos[:32], disk_uv[:32]):
            pb = (pd[0], -pd[2], pd[1])  # glTF (x, z, -y) -> Blender (x, y, z)
            best = min((max(abs(u - e[0]), abs((1.0 - v) - e[1]))
                        for e in candidates(uv_set, pb)), default=1e30)
            flip_err = max(flip_err, best)
        if flip_err > UV_TOL:
            print(f"ERROR: on-disk UVs deviate {flip_err:.3e} from the V-flipped "
                  "authored layout (glTF texture origin is top-left)", file=sys.stderr)
            return 11

        # wipe the file, then re-import: names must survive exactly
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    if len(meshes) != 1:
        print(f"ERROR: re-import produced {len(meshes)} mesh objects, expected 1",
              file=sys.stderr)
        return 12
    ri = meshes[0]
    ident_err = max(abs(ri.matrix_world[i][j] - (1.0 if i == j else 0.0))
                    for i in range(4) for j in range(4))
    if ident_err > 1e-6:
        print(f"ERROR: re-imported object carries a transform (err {ident_err:.3e})",
              file=sys.stderr)
        return 13
    names = sorted(m.name for m in ri.data.materials)
    if names != ["Glow", "Paint", "Trim"]:
        print(f"ERROR: material names drifted on re-import: {names}", file=sys.stderr)
        return 14
    if len(ri.data.vertices) != len(snap["loops"]):
        print(f"ERROR: re-import has {len(ri.data.vertices)} verts, expected "
              f"{len(snap['loops'])} (one per evaluated loop: flat normals + "
              "UV seams split every loop)", file=sys.stderr)
        return 15

    # contract 3b: positions round-trip (sorted point sets; the importer
    # re-applies the inverse axis conversion)
    want = sorted(snap["loops"])
    got = sorted(tuple(v.co) for v in ri.data.vertices)
    pos_err = max(max(abs(a[k] - b[k]) for k in range(3))
                  for a, b in zip(got, want))
    if pos_err > POS_TOL:
        print(f"ERROR: round-trip position drift {pos_err:.3e} (tol {POS_TOL})",
              file=sys.stderr)
        return 16

    # contract 3c: loop normals round-trip (unit length, member of the
    # evaluated normal set at the same position)
    normal_set = set_map(snap["loops"], snap["normals"])
    rme = ri.data
    unit_err = max(abs(l.normal.length - 1.0) for l in rme.loops)
    nrm_err = 0.0
    for l in rme.loops:
        p = tuple(rme.vertices[l.vertex_index].co)
        best = min((max(abs(l.normal[k] - e[k]) for k in range(3))
                    for e in candidates(normal_set, p)), default=1e30)
        nrm_err = max(nrm_err, best)
    if unit_err > UNIT_TOL or nrm_err > NRM_TOL:
        print(f"ERROR: round-trip normal drift {nrm_err:.3e} (tol {NRM_TOL}), "
              f"unit err {unit_err:.3e}", file=sys.stderr)
        return 17

    # contract 3d: UVs round-trip (the double V-flip returns the authored values)
    ruv = rme.uv_layers.active.data
    rt_uv_err = 0.0
    for l in rme.loops:
        p = tuple(rme.vertices[l.vertex_index].co)
        best = min((max(abs(ruv[l.index].uv[k] - e[k]) for k in range(2))
                    for e in candidates(uv_set, p)), default=1e30)
        rt_uv_err = max(rt_uv_err, best)
    if rt_uv_err > UV_TOL:
        print(f"ERROR: round-trip UV drift {rt_uv_err:.3e} (tol {UV_TOL})",
              file=sys.stderr)
        return 18

    # contract 3e: per-triangle material bindings round-trip (positions of the
    # triangle centers carry the binding; straddle-safe neighbor lookup)
    if len(rme.polygons) != len(snap["tris"]):
        print(f"ERROR: re-import has {len(rme.polygons)} triangles, expected "
              f"{len(snap['tris'])}", file=sys.stderr)
        return 19
    tri_map = {}
    for mat, ctr in snap["tris"]:
        tri_map.setdefault(key_of(ctr), []).append((mat, ctr))
    bind_err = 0.0
    for p in rme.polygons:
        best = 1e30
        for dx in (-1e-4, 0.0, 1e-4):
            for dy in (-1e-4, 0.0, 1e-4):
                for dz in (-1e-4, 0.0, 1e-4):
                    k = (round(p.center.x + dx, KEY_DIGITS),
                         round(p.center.y + dy, KEY_DIGITS),
                         round(p.center.z + dz, KEY_DIGITS))
                    for mat, ctr in tri_map.get(k, []):
                        if mat == p.material_index:
                            best = min(best, max(abs(p.center[i] - ctr[i])
                                                 for i in range(3)))
        bind_err = max(bind_err, best)
    if bind_err > 4e-5:
        print(f"ERROR: per-triangle material bindings drifted on round-trip "
              f"(center err {bind_err:.3e})", file=sys.stderr)
        return 20

    print(f"verts={base_verts} eval_verts={len(snap['verts'])} "
          f"eval_loops={len(snap['loops'])} disk_verts={disk_verts} tris={len(snap['tris'])}")
    print(f"uv_closed_form_err={uv_err:.2e} bbox_err={bbox_err:.2e} "
          f"flip_err={flip_err:.2e} ident_err={ident_err:.2e} "
          f"bind_err={bind_err:.2e}")
    print(f"roundtrip pos_err={pos_err:.2e} (tol {POS_TOL}) "
          f"nrm_err={nrm_err:.2e} (tol {NRM_TOL}) "
          f"uv_err={rt_uv_err:.2e} (tol {UV_TOL}) unit_err={unit_err:.2e}")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(authored, roundtrip, path, engine):
    scene = bpy.context.scene

    # the authored twin keeps its materials; the re-imported twin renders with
    # whatever the file carried back — the same look through the format itself
    authored.location.x = -1.35
    roundtrip.location.x = 1.35

    pm = bpy.data.materials.new("PlaqueMetal")
    pm.use_nodes = True
    pb = pm.node_tree.nodes["Principled BSDF"]
    # diffuse light-grey, not metal: the AUTHORED/ROUND-TRIP labels are the
    # render's argument and must survive thumbnail scale on the dark floor
    pb.inputs["Base Color"].default_value = (0.42, 0.44, 0.48, 1.0)
    pb.inputs["Metallic"].default_value = 0.2
    pb.inputs["Roughness"].default_value = 0.6

    def plaque(text, x):
        cu = bpy.data.curves.new("Plaque", 'FONT')
        cu.body = text
        cu.align_x = 'CENTER'
        cu.size = 0.30
        cu.extrude = 0.008
        ob = bpy.data.objects.new("Plaque", cu)
        ob.location = (x, -1.55, 0.01)
        ob.data.materials.append(pm)
        scene.collection.objects.link(ob)

    plaque("AUTHORED", -1.35)
    plaque("ROUND-TRIP", 1.35)

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

    # shaped warm key, faint cool fill, cool rim, warm wedge on the back wall
    # (docs/VISUAL-STYLE.md)
    light("Key", (-4.0, -5.0, 6.0), 560.0, 4.5, (1.0, 0.96, 0.9), (48, 0, -38))
    light("Fill", (5.0, -4.0, 3.0), 100.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Rim", (0.5, 4.5, 5.0), 360.0, 4.0, (0.6, 0.78, 1.0), (-55, 0, 175))
    light("Wedge", (2.5, 3.5, 4.2), 460.0, 5.5, (1.0, 0.76, 0.5), (-72, 0, 195))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 53.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -8.6, 2.7)
    scene.collection.objects.link(cam)
    target = bpy.data.objects.new("Aim", None)
    target.location = (0.0, 0.0, 0.75)
    scene.collection.objects.link(target)
    con = cam.constraints.new('TRACK_TO')
    con.target = target
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
    # AgX would wash the olive drab and teal glow toward pastel
    # (docs/VISUAL-STYLE.md)
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

    bpy.ops.wm.read_factory_settings(use_empty=True)
    crate = build_crate()
    for m in make_materials():
        crate.data.materials.append(m)
    code = check(crate)
    if code:
        return code

    if args.output:
        # the re-imported crate is still in the file (check wiped and
        # re-imported); build an authored twin beside it
        roundtrip = [o for o in bpy.data.objects if o.type == 'MESH'][0]
        authored = build_crate()
        for m in make_materials():
            authored.data.materials.append(m)
        if not render_still(authored, roundtrip, os.path.abspath(args.output),
                            args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 21
        print(f"rendered still {args.output}")

    print("gltf-export-roundtrip OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
