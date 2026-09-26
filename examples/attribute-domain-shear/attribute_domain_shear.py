"""Attribute domain shear — POINT vs CORNER color attributes on shared verts.

Witnesses the domain-semantics contract of `Mesh.color_attributes` that
AI-generated code trips on after learning `color_attributes.new()` exists:
the DOMAIN chooses where colors live. A `CORNER`-domain attribute stores one
color per loop (face-corner), so the K corners of one shared vertex can each
carry their own face's color. A `POINT`-domain attribute stores one color per
vertex, so a naive per-face authoring loop — "paint every wedge its own
color" — overwrites the shared vertices once per neighbor and the LAST write
wins: intended per-face colors shear across every shared vertex. Companion
to `color-attribute-wheel` (which covers CORNER sizing == loops and
`active_color`): this example covers what the domains *mean* on a fan whose
entire point is one hub vertex shared by every wedge.

Check (all closed form, nothing captured from a prior run):

1. Storage sizes: CORNER attr data == len(loops) == 3*K; POINT == K+1 verts.
2. CORNER authoring is exact: the hub corner of wedge i reads palette[i].
3. POINT naive authoring shears by construction: the hub reads palette[K-1]
   (last write wins), EVERY wedge's hub-side loop reads that same color, and
   outer ring vert i reads palette[i] (overwritten by wedge i after wedge
   i-1 wrote it) — the measured mean deviation from intended equals the
   closed-form shear computed from the palette.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python attribute_domain_shear.py --                 # check only
    blender --background --python attribute_domain_shear.py -- --no-overwrite  # must fail
    blender --background --python attribute_domain_shear.py -- --output a.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse, colorsys

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing
import gallery_asset_quality

K = 8                 # pinwheel wedges; hub vertex is shared by all K
HUB_Z = 0.55          # raised hub: folded-paper pinwheel, not a flat disc
RING_R = 1.15
ATTR_C = "PinCorner"
ATTR_P = "PinPoint"
COLOR_EPS = 1e-6


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def palette(k=K):
    """Closed-form wedge hues: saturated HSV wheel in linear-ish floats."""
    out = []
    for i in range(k):
        r, g, b = colorsys.hsv_to_rgb(i / k, 0.82, 0.95)
        out.append((r, g, b, 1.0))
    return out


def closed_form_shear(pal):
    """Mean per-wedge |palette[i] - palette[K-1]| over RGB — the exact shear a
    last-write-wins hub produces. Derived from the palette, never measured."""
    last = pal[-1]
    return sum(
        math.sqrt(sum((pal[i][c] - last[c]) ** 2 for c in range(3)))
        for i in range(len(pal))
    ) / len(pal)


def build_fan():
    """K triangles around one raised hub vertex; outer ring alternates fold
    height so petals read as folded paper under the key light."""
    me = bpy.data.meshes.new("Pinwheel")
    bm = bmesh.new()
    try:
        hub = bm.verts.new((0.0, 0.0, HUB_Z))
        ring = []
        for i in range(K):
            a = 2.0 * math.pi * i / K
            fold = 0.14 if i % 2 else 0.0
            ring.append(bm.verts.new((RING_R * math.cos(a), RING_R * math.sin(a), fold)))
        for i in range(K):
            bm.faces.new((hub, ring[i], ring[(i + 1) % K]))
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def assign_corner(me, pal, faces_per_wedge=1):
    """Correct path: CORNER domain, one exact wedge color per loop. Faces are
    wedge-major (wedge w owns faces w*n .. w*n+n-1); the check's fan has n=1."""
    attr = me.color_attributes.new(ATTR_C, type='FLOAT_COLOR', domain='CORNER')
    colors = [0.0] * (len(me.loops) * 4)
    for poly in me.polygons:
        for li in poly.loop_indices:
            colors[li * 4: li * 4 + 4] = pal[poly.index // faces_per_wedge]
    attr.data.foreach_set("color", colors)
    me.color_attributes.active_color = attr
    return attr


def assign_point_naive(me, pal, overwrite=True, faces_per_wedge=1):
    """The AI mistake: author per-wedge colors into a POINT-domain attribute.
    A per-wedge pass paints every vertex of the wedge's faces its color, so a
    vertex shared by two wedges is rewritten by the later one: the shared hub
    and every seam vert take the LAST write, and colors shear across them.
    On the check's fan (n=1) wedge i writes hub, ring i, ring i+1 in order."""
    attr = me.color_attributes.new(ATTR_P, type='FLOAT_COLOR', domain='POINT')
    last = K if overwrite else 1
    for poly in me.polygons:
        wedge = poly.index // faces_per_wedge
        if wedge >= last:
            break
        for vi in poly.vertices:
            attr.data[vi].color = pal[wedge]
    me.color_attributes.active_color = attr
    return attr


def check(overwrite=True):
    pal = palette()
    expect_shear = closed_form_shear(pal)
    print(f"palette K={K} closed_form_shear={expect_shear:.6f}")

    # --- CORNER: exact authoring ---
    me_c = build_fan()
    attr_c = assign_corner(me_c, pal)
    if len(attr_c.data) != len(me_c.loops) or len(me_c.loops) != 3 * K:
        print(f"ERROR: CORNER attr size {len(attr_c.data)} != loops {len(me_c.loops)}",
              file=sys.stderr)
        return 3
    hub_loop_err = 0.0
    for poly in me_c.polygons:
        got = attr_c.data[poly.loop_indices[0]].color  # loop 0 of each tri is the hub
        hub_loop_err = max(hub_loop_err,
                           max(abs(got[c] - pal[poly.index][c]) for c in range(4)))
    print(f"corner_hub_max_err={hub_loop_err:.3e} (must be <= {COLOR_EPS})")
    if hub_loop_err > COLOR_EPS:
        print("ERROR: CORNER hub corners do not carry their wedge's exact color — "
              "per-face color at a shared vertex failed", file=sys.stderr)
        return 4

    # --- POINT: the shear, measured against the closed form ---
    me_p = build_fan()
    attr_p = assign_point_naive(me_p, pal, overwrite=overwrite)
    if len(attr_p.data) != len(me_p.vertices) or len(me_p.vertices) != K + 1:
        print(f"ERROR: POINT attr size {len(attr_p.data)} != verts {len(me_p.vertices)}",
              file=sys.stderr)
        return 3
    hub_got = attr_p.data[0].color
    hub_err = max(abs(hub_got[c] - pal[K - 1][c]) for c in range(4))
    if hub_err > COLOR_EPS:
        print(f"ERROR: hub reads {tuple(round(c,4) for c in hub_got)} != last-write "
              f"palette[{K-1}] — last-write-wins contract broken", file=sys.stderr)
        return 5
    # Every wedge's hub-side loop reads the same shared color: sample the POINT
    # value at the hub through each face's hub loop — one value, K faces.
    # Outer ring vert i reads pal[i] — written by wedge i after wedge i-1 —
    # EXCEPT vert 0, which the wrap-around last wedge rewrites to pal[K-1].
    ring_err = 0.0
    for i in range(K):
        want = pal[i] if i > 0 else pal[K - 1]
        got = attr_p.data[1 + i].color
        ring_err = max(ring_err, max(abs(got[c] - want[c]) for c in range(4)))
    print(f"point_ring_max_err={ring_err:.3e} hub=last_write_ok")
    if ring_err > COLOR_EPS:
        print("ERROR: outer ring verts do not read their last write — the "
              "overwrite-ordering witness failed", file=sys.stderr)
        return 6
    shear = sum(
        math.sqrt(sum((pal[i][c] - hub_got[c]) ** 2 for c in range(3)))
        for i in range(K)
    ) / K
    print(f"point_shear measured={shear:.6f} closed_form={expect_shear:.6f}")
    if abs(shear - expect_shear) > 1e-6:
        print("ERROR: measured shear does not match the palette closed form — "
              "the domain mistake is not being witnessed", file=sys.stderr)
        return 7
    if shear < 0.05:
        print("ERROR: shear is ~0 — the probe cannot distinguish naive POINT "
              "authoring from correct authoring", file=sys.stderr)
        return 7

    print(f"attribute-domain-shear OK corner_exact point_shear={shear:.6f} "
          f"(last of {K} writes wins at 1 shared hub + {K} shared ring verts)")
    return 0


def make_attr_material(name, attr_name):
    """Canopy fabric: base color read straight from the color attribute.
    Fully matte (flat color data carries no specular line, VISUAL-STYLE)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    spec = bsdf.inputs.get("Specular IOR Level")
    if spec is not None:
        spec.default_value = 0.0
    bsdf.inputs["Roughness"].default_value = 0.8
    node = nt.nodes.new("ShaderNodeAttribute")
    node.attribute_type = "GEOMETRY"
    node.attribute_name = attr_name
    nt.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def make_material(name, rgb, rough=0.45, metallic=0.35):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    return mat


# --- Render-only prop: a striped patio parasol ------------------------------
# The canopy is the check's fan grown into fabric: the same K wedges (gores)
# around ONE shared apex vertex, each gore a strip of faces whose vertices all
# sit on the two seam lines it shares with its neighbours. The same two
# authoring functions the check asserts paint it, one wedge per gore. A
# striped parasol is chosen because everyone knows its stripes must be crisp:
# CORNER keeps them; naive POINT rewrites every seam and the apex with the
# last gore's color, so the stripes smear pink and one red gore goes white.

CANOPY_R = 1.18        # rim radius
CANOPY_RISE = 0.52     # apex height above the rim
CANOPY_RINGS = 7       # vertex rings along each seam, apex excluded
VALANCE_DROP = 0.11    # hem hanging below the rim, flared slightly out
RIM_Z = 0.62           # rim height above the tilt joint (canopy-local)
JOINT_Z = 1.28         # tilt-joint height on the pole (world)
TILT = math.radians(24)

# Two-tone render palette, one entry per gore (K=8): crimson and sailcloth.
# Render-only — the check keeps its eight distinct hues, which catch
# ordering bugs a period-2 palette could not.
CRIMSON = (0.60, 0.018, 0.028, 1.0)
SAILCLOTH = (0.70, 0.64, 0.50, 1.0)
PARASOL_PAL = [CRIMSON if i % 2 == 0 else SAILCLOTH for i in range(K)]


def _profile(t):
    """Canopy seam profile, t in (0, 1]: radius and height (canopy-local)."""
    return CANOPY_R * t, RIM_Z + CANOPY_RISE * (1.0 - t ** 1.8)


def build_canopy(name):
    """Gore-major fan: gore i owns CANOPY_RINGS + 1 faces (apex triangle,
    quads down the canopy, one valance quad), every vertex on a seam.
    Returns (mesh, faces_per_gore)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        apex = bm.verts.new((0.0, 0.0, RIM_Z + CANOPY_RISE))
        seams = []
        for i in range(K):
            a = 2.0 * math.pi * i / K
            c, s = math.cos(a), math.sin(a)
            col = []
            for r in range(1, CANOPY_RINGS + 1):
                rad, z = _profile(r / CANOPY_RINGS)
                col.append(bm.verts.new((rad * c, rad * s, z)))
            col.append(bm.verts.new((1.03 * CANOPY_R * c, 1.03 * CANOPY_R * s,
                                     RIM_Z - VALANCE_DROP)))
            seams.append(col)
        for i in range(K):
            a, b = seams[i], seams[(i + 1) % K]
            bm.faces.new((apex, a[0], b[0]))
            for r in range(len(a) - 1):
                bm.faces.new((a[r], a[r + 1], b[r + 1], b[r]))
        bm.normal_update()
        bm.to_mesh(me)
    finally:
        bm.free()
    me.shade_smooth()
    # soft dome across the gores, crisp fold where the hem drops
    if hasattr(me, "set_sharp_from_angle"):
        me.set_sharp_from_angle(angle=math.radians(50))
    return me, CANOPY_RINGS + 1


def lathe(name, profile, segs=24, sharp_deg=40.0):
    """Revolve (radius, z) profile points about Z; closed where radius is 0."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        rings = []
        for rad, z in profile:
            if rad <= 1e-6:
                rings.append([bm.verts.new((0.0, 0.0, z))])
                continue
            rings.append([bm.verts.new((rad * math.cos(2 * math.pi * j / segs),
                                        rad * math.sin(2 * math.pi * j / segs), z))
                          for j in range(segs)])
        for lo, hi in zip(rings, rings[1:]):
            if len(lo) == 1 and len(hi) == 1:
                continue
            for j in range(segs):
                jn = (j + 1) % segs
                if len(lo) == 1:
                    bm.faces.new((lo[0], hi[j], hi[jn]))
                elif len(hi) == 1:
                    bm.faces.new((lo[j], lo[jn], hi[0]))
                else:
                    bm.faces.new((lo[j], lo[jn], hi[jn], hi[j]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.shade_smooth()
    if hasattr(me, "set_sharp_from_angle"):
        me.set_sharp_from_angle(angle=math.radians(sharp_deg))
    return me


def _tube(bm, pts, radius, segs=8):
    """Sweep a round tube through pts (list of Vector), capped at both ends."""
    from mathutils import Vector
    rings = []
    for k, p in enumerate(pts):
        tan = (pts[min(k + 1, len(pts) - 1)] - pts[max(k - 1, 0)]).normalized()
        ref = Vector((0.0, 0.0, 1.0)) if abs(tan.z) < 0.9 else Vector((1.0, 0.0, 0.0))
        u = tan.cross(ref).normalized()
        v = tan.cross(u).normalized()
        rings.append([bm.verts.new(p + radius * (math.cos(2 * math.pi * j / segs) * u
                                                 + math.sin(2 * math.pi * j / segs) * v))
                      for j in range(segs)])
    for lo, hi in zip(rings, rings[1:]):
        for j in range(segs):
            jn = (j + 1) % segs
            bm.faces.new((lo[j], lo[jn], hi[jn], hi[j]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


RUNNER_Z = 0.20        # sliding runner on the upper pole (canopy-local)


def build_ribs(name):
    """K ribs tucked under the seams, with the tip caps poking past the hem,
    plus K stretchers from the runner up to mid-rib."""
    from mathutils import Vector
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for i in range(K):
            a = 2.0 * math.pi * i / K
            c, s = math.cos(a), math.sin(a)
            pts = []
            for k in range(2, 15):
                t = k / 14.0
                rad, z = _profile(t)
                pts.append(Vector((rad * c, rad * s, z - 0.035)))
            # tip: a short drop past the rim so the rib end reads at the hem
            pts.append(Vector((CANOPY_R * 1.01 * c, CANOPY_R * 1.01 * s, RIM_Z - 0.06)))
            _tube(bm, pts, 0.013, segs=8)
            rad, z = _profile(0.55)
            _tube(bm, [Vector((0.035 * c, 0.035 * s, RUNNER_Z + 0.03)),
                       Vector((rad * c, rad * s, z - 0.05))], 0.009, segs=6)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.shade_smooth()
    return me


def build_parasol(sc, tag, attr_fn, attr_name, loc, spin_z, mats):
    """One patio parasol at loc. attr_fn authors the canopy color attribute
    (the CORNER or naive POINT path under test). Returns the hero parts."""
    parts = []
    root = f"Parasol{tag}"

    def link(ob_name, me, mat, location, rot):
        me.materials.append(mat)
        ob = bpy.data.objects.new(ob_name, me)
        ob.location = location
        # spin about the pole first, then tilt about world X toward the camera
        ob.rotation_mode = "ZYX"
        ob.rotation_euler = rot
        sc.collection.objects.link(ob)
        parts.append(ob)
        return ob

    upright = (0.0, 0.0, spin_z)
    x, y = loc
    # weighted cast-iron base: skirt, stepped dome, socket neck
    base = lathe(f"{root}.Base", [
        (0.0, 0.0), (0.34, 0.0), (0.355, 0.012), (0.355, 0.04), (0.335, 0.055),
        (0.25, 0.075), (0.235, 0.095), (0.14, 0.125), (0.075, 0.15),
        (0.06, 0.2), (0.068, 0.215), (0.068, 0.25), (0.05, 0.262), (0.0, 0.262)],
        segs=40, sharp_deg=35)
    link(f"{root}.Base", base, mats["iron"], (x, y, 0.0), upright)
    # lower pole, then the brass tilt knuckle it hinges at
    pole_lo = lathe(f"{root}.PoleLower", [
        (0.0, 0.22), (0.03, 0.22), (0.03, JOINT_Z - 0.05), (0.0, JOINT_Z - 0.05)],
        segs=20)
    link(f"{root}.PoleLower", pole_lo, mats["teak"], (x, y, 0.0), upright)
    knuckle = lathe(f"{root}.TiltKnuckle", [
        (0.0, -0.09), (0.036, -0.09), (0.042, -0.075), (0.042, -0.035),
        (0.05, -0.02), (0.052, 0.0), (0.05, 0.02), (0.042, 0.035), (0.042, 0.075),
        (0.036, 0.09), (0.0, 0.09)], segs=24, sharp_deg=30)
    link(f"{root}.TiltKnuckle", knuckle, mats["brass"], (x, y, JOINT_Z), upright)

    # everything above the knuckle tilts toward the camera about the joint
    tilt = (TILT, 0.0, spin_z)
    jloc = (x, y, JOINT_Z)
    pole_up = lathe(f"{root}.PoleUpper", [
        (0.0, 0.05), (0.027, 0.05), (0.027, RIM_Z + CANOPY_RISE), (0.0, RIM_Z + CANOPY_RISE)],
        segs=20)
    link(f"{root}.PoleUpper", pole_up, mats["teak"], jloc, tilt)
    runner = lathe(f"{root}.Runner", [
        (0.0, RUNNER_Z - 0.05), (0.04, RUNNER_Z - 0.05), (0.046, RUNNER_Z - 0.035),
        (0.046, RUNNER_Z + 0.035), (0.04, RUNNER_Z + 0.05), (0.0, RUNNER_Z + 0.05)],
        segs=24, sharp_deg=30)
    link(f"{root}.Runner", runner, mats["brass"], jloc, tilt)
    ribs = build_ribs(f"{root}.Ribs")
    link(f"{root}.Ribs", ribs, mats["rib"], jloc, tilt)
    top = RIM_Z + CANOPY_RISE
    finial = lathe(f"{root}.Finial", [
        (0.0, top - 0.01), (0.07, top - 0.01), (0.075, top + 0.005), (0.05, top + 0.02),
        (0.026, top + 0.045), (0.024, top + 0.07), (0.04, top + 0.085),
        (0.052, top + 0.11), (0.048, top + 0.135), (0.032, top + 0.155),
        (0.012, top + 0.17), (0.0, top + 0.175)], segs=24, sharp_deg=30)
    link(f"{root}.Finial", finial, mats["brass"], jloc, tilt)

    canopy, per_gore = build_canopy(f"{root}.Canopy")
    attr_fn(canopy, PARASOL_PAL, faces_per_wedge=per_gore)
    link(f"{root}.Canopy", canopy, make_attr_material(f"{root}.Fabric", attr_name),
         jloc, tilt)
    return parts


def floor_letters(sc, text, x, mat):
    """One bold label per parasol: extruded block letters standing on the
    floor in front of the base, readable at card size."""
    cu = bpy.data.curves.new(f"Label{text.title()}", "FONT")
    cu.body = text
    cu.size = 0.29
    cu.extrude = 0.03
    cu.bevel_depth = 0.004
    cu.offset = 0.012          # thicken the stroke: the stock font is thin
    cu.align_x = "CENTER"
    ob = bpy.data.objects.new(f"Label{text.title()}", cu)
    ob.location = (x, -1.0, 0.0)
    ob.rotation_euler = (math.radians(90), 0.0, 0.0)
    ob.data.materials.append(mat)
    sc.collection.objects.link(ob)
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
    wall.location = (0.0, 8.0, 0.0)
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

    light("Key", (-4.0, -5.0, 6.0), 520.0, 5.0, (1.0, 0.96, 0.9), (45, 0, -38))
    light("Fill", (5.0, -3.5, 2.5), 110.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 50))
    light("Rim", (1.5, 4.5, 4.0), 320.0, 3.0, (0.6, 0.78, 1.0), (-55, 0, 170))
    light("Wedge", (0.5, 5.0, 4.2), 420.0, 6.0, (1.0, 0.76, 0.5), (-68, 0, 180))
    return floor, wall


PAIR_X = 1.42


def render_still(path, engine):
    """Two striped parasols from the same authoring functions the check
    asserts, one wedge per gore: CORNER (left) keeps crisp crimson/sailcloth
    stripes; naive POINT (right) smears every seam and the apex to the last
    write, and gore 0 — crimson by intent — renders white."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    mats = {
        "teak": make_material("Teak", (0.26, 0.105, 0.04), rough=0.42, metallic=0.0),
        "brass": make_material("Brass", (0.78, 0.52, 0.2), rough=0.28, metallic=1.0),
        "iron": make_material("CastIron", (0.1, 0.1, 0.11), rough=0.38, metallic=0.75),
        "rib": make_material("RibAluminium", (0.62, 0.62, 0.64), rough=0.32, metallic=1.0),
    }
    # gore 0 spans angles 0..45 deg; spin so the red-by-intent gore faces
    # the camera on both parasols (the one the POINT loop turns white)
    spin = math.radians(-90 - 22.5)
    left = build_parasol(sc, "Corner", assign_corner, ATTR_C, (-PAIR_X, 0.0), spin, mats)
    right = build_parasol(sc, "Point", assign_point_naive, ATTR_P, (PAIR_X, 0.0), spin, mats)
    label_mat = make_material("LabelEnamel", (0.36, 0.345, 0.32), rough=0.6, metallic=0.0)
    labels = [floor_letters(sc, "CORNER", -PAIR_X, label_mat),
              floor_letters(sc, "POINT", PAIR_X, label_mat)]

    floor, wall = build_studio(sc)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -9.2, 3.75)
    sc.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 1.25)
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
    # Standard, always: AgX would bend the palette the attributes carry
    sc.view_settings.view_transform = "Standard"
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation.
    hero = left + right
    fcode = gallery_framing.check_framing(
        sc, cam,
        hero=hero,
        elements=hero + labels,
        stage=[floor, wall],
    )
    if fcode:
        return fcode
    # asset-quality floors (naming, material variation, edge treatment),
    # measured on one parasol — exit 11 on violation
    aqcode = gallery_asset_quality.check_asset_quality(
        sc, cam, hero=left, stage=[floor, wall])
    if aqcode:
        return aqcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 9
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--no-overwrite", action="store_true",
                   help="write only the first POINT wedge (must fail)")
    args = p.parse_args(argv)

    print(f"binary version: {bpy.app.version} ({bpy.app.version_string})")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    code = check(overwrite=not args.no_overwrite)
    if code:
        return code

    if args.output:
        rcode = render_still(os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("attribute-domain-shear OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
