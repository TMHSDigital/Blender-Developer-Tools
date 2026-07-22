"""A jerry can prop shaded three ways — a runnable example.

Witnesses the shading contract a game prop's silhouette depends on (engines
generally, FiveM/GTA-style prop workflows specifically): which edges read
hard and which read smooth is mesh DATA, and since Blender 4.1 it is carried
by face smooth flags plus a `sharp_edge` attribute — `use_auto_smooth` is
gone. AI-generated Blender code still emits the pre-4.1 API
(`mesh.use_auto_smooth = True`, `bpy.ops.object.shade_auto_smooth()`), so
this example asserts what the supported versions actually expose:

  legacy API    — use_auto_smooth, use_custom_normals, calc_normals are
                  AttributeError on BOTH 4.5 LTS and 5.1
  by-angle data — `mesh.set_sharp_from_angle(angle)` + face smooth flags:
                  the sharp set lands EXACTLY where an independently
                  recomputed dihedral angle crosses the threshold
  normal welds  — through depsgraph evaluation, loops across a smooth edge
                  share one normal (welded) and loops across a sharp edge
                  carry their face normals (split by the dihedral)
  custom normals— per-loop normals set with `normals_split_custom_set`
                  survive depsgraph evaluation within the int16 storage
                  quantization (~7.5e-05 measured, tol 2e-4), unit length
  divergence    — the legacy `shade_auto_smooth` OPERATOR needs the bundled
                  Smooth-by-Angle node-group asset: headless on 4.5 LTS it
                  returns {'CANCELLED'} ("Asset loading is unfinished") and
                  the mesh is UNTOUCHED — silent flat shading for any script
                  that ignores the return set; on 5.1 it FINISHES and adds
                  the NODES modifier. The portable path is the data API.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still (the same can shaded flat /
smooth-everywhere / by-angle, so a broken path reads as faceting or smear):

    blender --background --python custom_normals_shade.py --                 # check only
    blender --background --python custom_normals_shade.py -- --output c.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector

ANGLE_DEG = 30.0          # shade-by-angle threshold
ANGLE = math.radians(ANGLE_DEG)
TOL_NORMAL = 2e-4         # custom-normal readback: int16 storage quantizes to ~7.5e-05
TOL_UNIT = 1e-6           # unit-length tolerance for evaluated normals (measured 4.5e-08)
TOL_SMOOTH = 1e-3         # loop-normal equality across a welded (smooth) edge
TOL_SHARP = 5e-3          # radians: split-normal angle vs dihedral across a sharp edge

# ---------------------------------------------------------------------------
# Prop construction. A 20-unit jerry can: rounded-slab shell, pressed X ribs
# floating on both faces, spout neck + cap, three-post carry handle. All
# dimensions invented for this prop; ribs are floater prisms, the game-prop
# norm — every checked mesh is itself closed and manifold.
# ---------------------------------------------------------------------------

SHELL_W, SHELL_H, SHELL_D, SHELL_R = 1.4, 1.8, 0.62, 0.28


def signed_volume(me):
    """Divergence-theorem volume; positive when face winding points outward."""
    vol = 0.0
    for p in me.polygons:
        vs = [me.vertices[i].co for i in p.vertices]
        v0 = vs[0]
        for i in range(1, len(vs) - 1):
            vol += v0.dot(vs[i].cross(vs[i + 1])) / 6.0
    return vol


def finish_mesh(name, bm):
    me = bpy.data.meshes.new(name)
    try:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    if signed_volume(me) < 0.0:  # pin outward winding by the closed form
        for p in me.polygons:
            p.flip()
    return obj


def rounded_rect_profile(w, h, r, segs):
    """(x, z) loop of a rounded rectangle, z from 0 to h, CCW seen from -Y."""
    pts = []
    for cx, cz, a0 in ((w / 2 - r, r, -90), (w / 2 - r, h - r, 0),
                       (-(w / 2 - r), h - r, 90), (-(w / 2 - r), r, 180)):
        for i in range(segs):
            a = math.radians(a0 + 90.0 * i / segs)
            pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    return pts


def build_shell():
    """Loft the rounded-rect profile along Y; caps are the end ngons."""
    prof = rounded_rect_profile(SHELL_W, SHELL_H, SHELL_R, 6)
    n = len(prof)
    y0, y1 = -SHELL_D / 2, SHELL_D / 2
    bm = bmesh.new()
    front = [bm.verts.new((x, y0, z)) for x, z in prof]
    back = [bm.verts.new((x, y1, z)) for x, z in prof]
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((front[i], back[i], back[j], front[j]))
    bm.faces.new(front)
    bm.faces.new(back)
    return finish_mesh("Shell", bm)


def build_rib(name, p0, p1, face_y, outward):
    """Trapezoid-section pressed rib from p0 to p1 (x, z), raised off the
    face plane by `outward` (-1 front, +1 back)."""
    wb, wt, hgt = 0.09, 0.06, 0.045
    d = Vector((p1[0] - p0[0], 0.0, p1[1] - p0[1])).normalized()
    side = Vector((-d.z, 0.0, d.x))
    up = Vector((0.0, outward, 0.0))
    bm = bmesh.new()
    ends = []
    for px, pz in (p0, p1):
        c = Vector((px, face_y, pz))
        ends.append([bm.verts.new(c - side * wb), bm.verts.new(c + side * wb),
                     bm.verts.new(c + side * wt + up * hgt),
                     bm.verts.new(c - side * wt + up * hgt)])
    a, b = ends
    bm.faces.new((a[0], a[1], a[2], a[3]))
    bm.faces.new((b[1], b[0], b[3], b[2]))
    bm.faces.new((a[1], b[1], b[2], a[2]))
    bm.faces.new((a[3], b[3], b[0], a[0]))
    bm.faces.new((a[0], b[0], b[1], a[1]))
    bm.faces.new((a[2], b[2], b[3], a[3]))
    return finish_mesh(name, bm)


def lathe(name, profile, segments):
    """Spin an (r, z) profile around Z; r == 0 ends become poles."""
    bm = bmesh.new()
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
        rings.append([bm.verts.new((r * math.cos(a), r * math.sin(a), z))
                      for r, z in profile])
    for i in range(segments):
        j = (i + 1) % segments
        for k in range(len(profile) - 1):
            bm.faces.new((rings[i][k], rings[j][k], rings[j][k + 1], rings[i][k + 1]))
        if bot is not None:
            bm.faces.new((rings[j][0], rings[i][0], bot))
        if top is not None:
            bm.faces.new((rings[i][-1], rings[j][-1], top))
    return finish_mesh(name, bm)


def build_jerry_can():
    """All parts at world placement; returns {"shell", "rib", "neck", "parts"}."""
    shell = build_shell()
    parts = [shell]

    ribs = []
    inset = [(0.46, 0.22), (0.46, 1.58)]
    specs = [((inset[0], ( -inset[0][0], inset[1][1])), "RibDiagA"),
             (((-inset[0][0], inset[0][1]), inset[1]), "RibDiagB"),
             (((0.0, 0.18), (0.0, 1.62)), "RibVert")]
    for fy, out, tag in ((-SHELL_D / 2, -1.0, "F"), (SHELL_D / 2, 1.0, "B")):
        for (p0, p1), rn in specs:
            ribs.append(build_rib(f"{rn}{tag}", p0, p1, fy, out))
    parts.extend(ribs)

    neck = lathe("Neck", [(0.0, 0.0), (0.21, 0.0), (0.21, 0.05), (0.175, 0.07),
                          (0.165, 0.10), (0.165, 0.16), (0.185, 0.17),
                          (0.185, 0.20), (0.165, 0.21), (0.165, 0.24), (0.0, 0.24)], 16)
    neck.location = (0.42, -0.12, 1.75)
    neck.rotation_euler = (math.radians(-8.0), 0.0, 0.0)
    cap = lathe("Cap", [(0.0, 0.0), (0.205, 0.0), (0.205, 0.04), (0.19, 0.05),
                        (0.19, 0.11), (0.14, 0.14), (0.0, 0.145)], 16)
    cap.location = (0.42, -0.0866, 1.9877)
    cap.rotation_euler = (math.radians(-8.0), 0.0, 0.0)
    parts.extend((neck, cap))

    for i, x in enumerate((-0.28, 0.0, 0.28)):
        post = lathe(f"Post{i}", [(0.0, 0.0), (0.055, 0.0), (0.055, 0.17), (0.0, 0.17)], 16)
        post.location = (x, 0.08, 1.79)
        parts.append(post)
    grip = lathe("Grip", [(0.0, 0.0), (0.06, 0.0), (0.06, 0.68), (0.0, 0.68)], 16)
    grip.rotation_euler = (0.0, math.radians(90.0), 0.0)
    grip.location = (-0.34, 0.08, 1.96)
    parts.append(grip)

    return {"shell": shell, "rib": ribs[0], "neck": neck, "parts": parts}


# ---------------------------------------------------------------------------
# The contract checks.
# ---------------------------------------------------------------------------

def manifold_dihedrals(me):
    """Independent recompute: {vertex-pair key: (degrees, v1, v2)} for edges
    with exactly two link faces, plus the count of non-manifold edges."""
    bm = bmesh.new()
    out = {}
    nonmanifold = 0
    try:
        bm.from_mesh(me)
        for e in bm.edges:
            if len(e.link_faces) != 2:
                nonmanifold += 1
                continue
            deg = math.degrees(e.link_faces[0].normal.angle(e.link_faces[1].normal))
            v1, v2 = e.verts[0].index, e.verts[1].index
            out[frozenset((v1, v2))] = (deg, v1, v2)
    finally:
        bm.free()
    return out, nonmanifold


def sharp_edge_keys(me):
    attr = me.attributes.get("sharp_edge")
    if attr is None:
        return set()
    return {frozenset((me.edges[i].vertices[0], me.edges[i].vertices[1]))
            for i, d in enumerate(attr.data) if d.value}


def check_api_surface(me):
    """The legacy shading API is gone on every supported version."""
    for gone in ("use_auto_smooth", "use_custom_normals", "calc_normals"):
        if hasattr(me, gone):
            print(f"ERROR: mesh still exposes {gone} on {bpy.app.version_string} — "
                  f"the pre-4.1 shading API must stay removed", file=sys.stderr)
            return 3
    for needed in ("normals_split_custom_set", "normals_split_custom_set_from_vertices",
                   "set_sharp_from_angle", "corner_normals", "has_custom_normals"):
        if not hasattr(me, needed):
            print(f"ERROR: mesh lacks {needed} on {bpy.app.version_string}",
                  file=sys.stderr)
            return 3
    print(f"api-surface: use_auto_smooth/use_custom_normals/calc_normals absent, "
          f"modern path present ({bpy.app.version_string})")
    return 0


def check_by_angle(objs):
    """set_sharp_from_angle must mark exactly the edges whose independently
    recomputed dihedral crosses the threshold — on every checked mesh."""
    total_sharp = total_manifold = 0
    for obj in objs:
        me = obj.data
        for p in me.polygons:
            p.use_smooth = True
        me.set_sharp_from_angle(angle=ANGLE)
        dih, nonmanifold = manifold_dihedrals(me)
        if nonmanifold:
            print(f"ERROR: {obj.name}: {nonmanifold} non-manifold edge(s) — the "
                  f"dihedral test is undefined there", file=sys.stderr)
            return 4
        expect = {k for k, (deg, _, _) in dih.items() if deg > ANGLE_DEG}
        got = sharp_edge_keys(me)
        if got != expect:
            only_got = len(got - expect)
            only_exp = len(expect - got)
            print(f"ERROR: {obj.name}: sharp set mismatch vs independent dihedral "
                  f"test ({only_got} extra, {only_exp} missing of {len(expect)} "
                  f"expected)", file=sys.stderr)
            return 5
        total_sharp += len(got)
        total_manifold += len(dih)
        print(f"by-angle {obj.name}: edges={len(dih)} sharp={len(got)} "
              f"matches independent dihedral recompute (>{ANGLE_DEG:.0f}deg)")
    print(f"by-angle: {len(objs)} meshes, {total_manifold} manifold edges, "
          f"{total_sharp} sharp, exact set match")
    return 0


def check_normal_welds(obj):
    """Through depsgraph evaluation: loops across a smooth edge share one
    normal; loops across a sharp edge carry their face normals (split by the
    dihedral). The rendered shading, verified — not the attribute's say-so."""
    me = obj.data
    dih, _ = manifold_dihedrals(me)
    sharp = sharp_edge_keys(me)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg).to_mesh()
    try:
        # per manifold edge, per endpoint vertex, per polygon: the loop normal
        loop_normal = [tuple(l.normal) for l in ev.loops]
        poly_of_loop = [0] * len(ev.loops)
        for p in ev.polygons:
            for li in range(p.loop_start, p.loop_start + p.loop_total):
                poly_of_loop[li] = p.index
        by_edge = {}
        for li, l in enumerate(ev.loops):
            pi, vi = poly_of_loop[li], l.vertex_index
            for vj in ev.polygons[pi].vertices:
                if vj == vi:
                    continue
                k = frozenset((vi, vj))
                if k in dih:
                    by_edge.setdefault(k, {}).setdefault(vi, {})[pi] = loop_normal[li]
        max_smooth = 0.0
        max_sharp = 0.0
        unit_worst = 0.0
        for k, (deg, v1, v2) in dih.items():
            for v in (v1, v2):
                sides = by_edge.get(k, {}).get(v, {})
                if len(sides) != 2:
                    print(f"ERROR: edge {tuple(sorted(k))} endpoint v{v}: expected "
                          f"loop normals on both sides, got {len(sides)}", file=sys.stderr)
                    return 6
                n1, n2 = (Vector(s) for s in sides.values())
                unit_worst = max(unit_worst, abs(n1.length - 1.0), abs(n2.length - 1.0))
                if k in sharp:
                    err = abs(n1.angle(n2) - math.radians(deg))
                    max_sharp = max(max_sharp, err)
                else:
                    max_smooth = max(max_smooth, (n1 - n2).length)
        if unit_worst > TOL_UNIT:
            print(f"ERROR: evaluated normal off unit length by {unit_worst:.3e} "
                  f"(tol {TOL_UNIT})", file=sys.stderr)
            return 6
        if max_smooth > TOL_SMOOTH:
            print(f"ERROR: smooth edge not welded: loop normals differ by "
                  f"{max_smooth:.3e} (tol {TOL_SMOOTH})", file=sys.stderr)
            return 6
        if max_sharp > TOL_SHARP:
            print(f"ERROR: sharp edge split {max_sharp:.6f} rad off its dihedral "
                  f"(tol {TOL_SHARP})", file=sys.stderr)
            return 6
        print(f"normal-welds {obj.name}: smooth max deviation {max_smooth:.3e} "
              f"(tol {TOL_SMOOTH}), sharp max angle err {max_sharp:.3e} rad "
              f"(tol {TOL_SHARP}), unit err {unit_worst:.3e}")
    finally:
        obj.evaluated_get(dg).to_mesh_clear()
    return 0


def check_custom_normals_roundtrip(obj):
    """Per-loop custom normals survive depsgraph evaluation. Tolerance is the
    int16 storage quantization, measured 7.5e-05 on both versions."""
    me = obj.data
    n = len(me.loops)
    custom = []
    for i in range(n):
        a = 2.0 * math.pi * i / n
        custom.append(Vector((0.5 * math.cos(a), 0.5 * math.sin(a), 0.85)).normalized())
    me.normals_split_custom_set(custom)
    if not me.has_custom_normals:
        print("ERROR: has_custom_normals False after normals_split_custom_set — "
              "no use_custom_normals flag exists to flip anymore", file=sys.stderr)
        return 7
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg).to_mesh()
    try:
        err = max((Vector(tuple(l.normal)) - custom[i]).length
                  for i, l in enumerate(ev.loops))
        unit = max(abs(Vector(tuple(l.normal)).length - 1.0) for l in ev.loops)
    finally:
        obj.evaluated_get(dg).to_mesh_clear()
    if err > TOL_NORMAL or unit > TOL_UNIT:
        print(f"ERROR: custom normals lost in evaluation: max_err {err:.3e} "
              f"(tol {TOL_NORMAL}), unit err {unit:.3e}", file=sys.stderr)
        return 7
    print(f"custom-normals: {n} loops survive depsgraph evaluation, "
          f"max_err {err:.3e} (tol {TOL_NORMAL}), unit err {unit:.3e}")
    return 0


def check_legacy_operator():
    """The shade_auto_smooth OPERATOR is a version-split trap: it builds the
    Smooth-by-Angle node-group modifier from a bundled asset. Headless on
    4.5 LTS the asset load never finishes and the op CANCELS — silently, no
    exception — leaving flat shading. On 5.1 it FINISHES with the modifier."""
    me = bpy.data.meshes.new("LegacyProbe")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new("LegacyProbe", me)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    try:
        result = bpy.ops.object.shade_auto_smooth(angle=ANGLE)
    except Exception as e:
        print(f"ERROR: shade_auto_smooth raised {type(e).__name__}: {e}",
              file=sys.stderr)
        return 8
    mods = [(m.name, m.type) for m in obj.modifiers]
    smooth = sum(1 for p in me.polygons if p.use_smooth)
    bpy.data.objects.remove(obj)
    bpy.data.meshes.remove(me)
    if bpy.app.version >= (5, 0, 0):
        ok = result == {'FINISHED'} and any(t == 'NODES' for _, t in mods) and smooth > 0
        detail = f"expect FINISHED + Smooth-by-Angle NODES modifier, got {result} mods={mods} smooth={smooth}"
    else:
        ok = result == {'CANCELLED'} and not mods and smooth == 0
        detail = f"expect CANCELLED headless (asset load never finishes) + untouched mesh, got {result} mods={mods} smooth={smooth}"
    if not ok:
        print(f"ERROR: legacy-operator divergence drifted: {detail}", file=sys.stderr)
        return 8
    print(f"legacy-op ({bpy.app.version_string}): {detail} — as asserted")
    return 0


# ---------------------------------------------------------------------------
# Render: the same can three ways — flat (faceting), smooth-everywhere (the
# smeared AI bug), by-angle (the contract). Failure modes flank the truth.
# ---------------------------------------------------------------------------

def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def make_material(name, color, metallic, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def variant_meshes(parts, mode):
    """Fresh mesh copies with one shading treatment applied."""
    out = []
    for o in parts:
        me = o.data.copy()
        me.name = f"{o.name}_{mode}"
        for p in me.polygons:
            p.use_smooth = mode != "flat"
        if mode == "byangle":
            me.set_sharp_from_angle(angle=ANGLE)
        dup = bpy.data.objects.new(f"{o.name}_{mode}", me)
        dup.location = o.location
        dup.rotation_euler = o.rotation_euler
        bpy.context.collection.objects.link(dup)
        out.append(dup)
    return out


def render_still(can, path, engine):
    scene = bpy.context.scene
    # semi-gloss painted steel: rough enough to read as paint, glossy enough
    # that a highlight exposes every normal discontinuity — matte would hide
    # the very shading differences this render exists to show
    steel = make_material("OliveDrab", (0.31, 0.35, 0.15), 0.8, 0.26)
    accent = make_material("FuelMarker", (0.55, 0.06, 0.03), 0.3, 0.30)

    # the checked base can IS the by-angle variant; the two failure modes are
    # mesh copies with their own shading, no materials yet
    variants = []
    for mode, x in (("flat", -1.5), ("smooth", 0.0), ("byangle", 1.5)):
        objs = variant_meshes(can["parts"], mode)
        for o in objs:
            o.location.x += x
            o.rotation_euler.z += math.radians(-10.0)  # uniform yaw, fronts to camera
            o.data.materials.append(steel)
            if o.name.startswith("Cap"):
                o.data.materials.append(accent)
                for p in o.data.polygons:  # cap rim ring in the marker red
                    if p.center.z < 0.045:
                        p.material_index = 1
        variants.append(objs)
    # hide the checked originals: the byangle variant re-shows the same data
    for o in can["parts"]:
        o.hide_render = True

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
    light("Key", (-4.0, -5.0, 6.0), 520.0, 4.5, (1.0, 0.96, 0.9), (50, 0, -38))
    light("Fill", (5.5, -3.5, 2.5), 120.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 55))
    light("Rim", (1.5, 4.5, 4.0), 340.0, 3.0, (0.6, 0.78, 1.0), (-58, 0, 170))
    light("Wedge", (2.5, 5.5, 4.0), 400.0, 6.0, (1.0, 0.76, 0.5), (-68, 0, 190))
    # the shading audit light: a tall strip whose reflection runs down each
    # can face — it stair-steps on flat shading, warps at the rim on
    # smooth-everything, and stays straight with crisp edges on by-angle
    ld = bpy.data.lights.new("Strip", 'AREA')
    ld.energy = 460.0
    ld.shape = 'RECTANGLE'
    ld.size = 1.0
    ld.size_y = 8.0
    ld.color = (0.9, 0.95, 1.0)
    strip = bpy.data.objects.new("Strip", ld)
    strip.location = (-3.5, -4.5, 3.2)
    strip.rotation_euler = (math.radians(60), 0.0, math.radians(-30))
    scene.collection.objects.link(strip)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.9, -7.2, 2.6)
    scene.collection.objects.link(cam)
    target = bpy.data.objects.new("Aim", None)
    target.location = (0.0, 0.0, 1.05)
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
    # AgX would flatten the olive drab toward mud (docs/VISUAL-STYLE.md)
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
    can = build_jerry_can()

    for step in (lambda: check_api_surface(can["shell"].data),
                 lambda: check_by_angle([can["shell"], can["rib"], can["neck"]]),
                 lambda: check_normal_welds(can["shell"]),
                 lambda: check_custom_normals_roundtrip(can["shell"]),
                 check_legacy_operator):
        code = step()
        if code:
            return code

    if args.output:
        if not render_still(can, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 9
        print(f"rendered still {args.output}")

    print("custom-normals-shade OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
