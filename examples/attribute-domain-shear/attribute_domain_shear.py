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
    blender --background --python attribute_domain_shear.py -- --output a.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse, colorsys

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing

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


def assign_corner(me, pal):
    """Correct path: CORNER domain, one exact wedge color per loop."""
    attr = me.color_attributes.new(ATTR_C, type='FLOAT_COLOR', domain='CORNER')
    colors = [0.0] * (len(me.loops) * 4)
    for poly in me.polygons:
        for li in poly.loop_indices:
            colors[li * 4: li * 4 + 4] = pal[poly.index]
    attr.data.foreach_set("color", colors)
    me.color_attributes.active_color = attr
    return attr


def assign_point_naive(me, pal):
    """The AI mistake: author per-wedge colors into a POINT-domain attribute.
    Every wedge rewrites the shared hub (and its leading ring vert), so the
    last wedge wins — colors shear across every shared vertex."""
    attr = me.color_attributes.new(ATTR_P, type='FLOAT_COLOR', domain='POINT')
    hub_index = 0  # build_fan creates the hub first
    for i in range(K):
        # naive per-wedge pass: set the hub and both ring verts to palette[i]
        attr.data[hub_index].color = pal[i]
        attr.data[1 + i].color = pal[i]
        attr.data[1 + (i + 1) % K].color = pal[i]
    me.color_attributes.active_color = attr
    return attr


def check():
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
    attr_p = assign_point_naive(me_p, pal)
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


def make_attr_material(name, attr_name, matte=True):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    if matte:
        # flat color data: no specular line across the petals (VISUAL-STYLE)
        spec = bsdf.inputs.get("Specular IOR Level")
        if spec is not None:
            spec.default_value = 0.0
    bsdf.inputs["Roughness"].default_value = 0.6
    node = nt.nodes.new("ShaderNodeAttribute")
    node.attribute_type = "GEOMETRY"
    node.attribute_name = attr_name
    nt.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


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


def _pinwheel_obj(sc, name, me, loc, rot_z):
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.rotation_euler = (math.radians(12), 0.0, rot_z)
    sc.collection.objects.link(ob)
    # stem + hub cap: a garden pinwheel on a stick, not a floating disc
    stem_me = bpy.data.meshes.new(name + "Stem")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.05,
                              radius2=0.06, depth=1.35)
        bmesh.ops.translate(bm, vec=(0.0, 0.0, -0.72), verts=bm.verts)
        bm.to_mesh(stem_me)
    finally:
        bm.free()
    stem_me.materials.append(make_material("StemMetal", (0.16, 0.17, 0.18),
                                           rough=0.4, metallic=0.8))
    stem = bpy.data.objects.new(name + "Stem", stem_me)
    stem.location = loc
    stem.rotation_euler = (math.radians(12), 0.0, rot_z)
    sc.collection.objects.link(stem)
    cap_me = bpy.data.meshes.new(name + "Cap")
    bm = bmesh.new()
    try:
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.075)
        bmesh.ops.translate(bm, vec=(0.0, 0.0, HUB_Z + 0.02), verts=bm.verts)
        bm.to_mesh(cap_me)
    finally:
        bm.free()
    cap_me.materials.append(make_material("CapMetal", (0.09, 0.09, 0.095),
                                          rough=0.35, metallic=0.85))
    cap = bpy.data.objects.new(name + "Cap", cap_me)
    cap.location = loc
    cap.rotation_euler = (math.radians(12), 0.0, rot_z)
    sc.collection.objects.link(cap)
    return ob


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


def render_still(path, engine):
    """Dual pinwheel: CORNER (crisp petals to the hub) vs naive POINT (last
    write smears the shared hub + ring verts). Colors come from the same
    closed-form palette the check asserts."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    pal = palette()

    me_c = build_fan()
    assign_corner(me_c, pal)
    me_c.materials.append(make_attr_material("MatCorner", ATTR_C))
    left = _pinwheel_obj(sc, "Corner", me_c, (-1.15, 0.0, 1.35), math.radians(-8))

    me_p = build_fan()
    assign_point_naive(me_p, pal)
    me_p.materials.append(make_attr_material("MatPoint", ATTR_P))
    right = _pinwheel_obj(sc, "Point", me_p, (1.15, 0.0, 1.35), math.radians(8))

    p_corner = placard(sc, "CORNER", (-1.15, -1.05, 0.02), size=0.13)
    p_point = placard(sc, "POINT — last write wins", (1.15, -1.05, 0.02), size=0.10)

    floor, wall = build_studio(sc)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 48.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -6.4, 4.6)
    sc.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.8)
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
    # Standard, always: AgX would bend the closed-form palette the check asserts
    sc.view_settings.view_transform = "Standard"
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation.
    hero = [left, right]
    elements = hero + [p_corner, p_point]
    fcode = gallery_framing.check_framing(
        sc, cam,
        hero=hero,
        elements=elements,
        stage=[floor, wall],
    )
    if fcode:
        return fcode
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
