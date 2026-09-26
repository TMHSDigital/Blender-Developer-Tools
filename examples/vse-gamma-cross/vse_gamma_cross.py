"""The GAMMA_CROSS blend curve, asserted per frame — a runnable example.

Witnesses the fade math AI-generated sequencer code most often assumes
wrong: a GAMMA_CROSS between two strips is NOT the naive linear mix
``(1-t)*A + t*B``. It blends in a gamma-0.5 space:

    out = ((1-t)*sqrt(A) + t*sqrt(B))^2,   t = (frame - start) / duration

so the mid-cross dips below the sRGB lerp. The endpoints are chosen so the
dip is as large as a cross can make it: signal orange (1.0, 0.36, 0.0) and
azure (0.0, 0.16, 1.0) have per-channel square roots that sum to 1, so the
gamma midpoint is a neutral (0.25, 0.25, 0.25) — a dark valley — while the
lerp midpoint is a muted violet (0.5, 0.26, 0.5): 0.25 brighter on red and
blue, the per-channel maximum (a channel crossing 1 -> 0). The check renders
tiny frames across the cross and asserts every sample against the closed
form, plus that the lerp deviation at mid is material.

Also witnessed: ``t`` never reaches 1 inside the effect — the last frame of
the span blends at (duration-1)/duration; B arrives only when the effect
ends. And the version-gated creation contract from vse-cut-list holds the
whole thing up: ``strips`` (never ``.sequences``), and ``new_effect`` ends
with ``length=`` on 5.x, ``frame_end=`` on 4.5.

The blend math is identical on Blender 4.5 LTS and 5.1 (every sample matches
to the quantization step).

``--swap-inputs`` wires GC as T2 -> T1 and still asserts T1 -> T2. That is
the falsifier (``--same-axis`` in export-preset-axis).

By default it runs only the correctness check (no gallery render) — the CI
smoke check. Pass --output to also render a still: every frame of the cross
rendered by the sequencer and laid side by side as a filmstrip, the
GAMMA_CROSS strip above an authentic sequencer CROSS (the linear mix) strip,
mounted unaltered on a grading monitor:

    blender --background --python vse_gamma_cross.py --                   # check only
    blender --background --python vse_gamma_cross.py -- --swap-inputs     # must fail
    blender --background --python vse_gamma_cross.py -- --output g.png    # + render
"""
import bpy, sys, os, math, argparse, tempfile, shutil

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing

IS_5X = bpy.app.version >= (5, 0, 0)

# sqrt(A) + sqrt(B) == 1 on every channel: the gamma midpoint is the neutral
# 0.25 and the dip below the lerp is the per-channel maximum 0.25
A_RGB = (1.0, 0.36, 0.0)      # signal orange
B_RGB = (0.0, 0.16, 1.0)      # azure
SPAN = (1, 33)                # 32 frames of cross
PXW, PXH = 64, 36             # tiny per-sample renders, CI-safe like vse-cut-list
Q_TOL = 5e-3                  # 2x the 8-bit quantization step + gamma-fit residual (measured 2.71e-3)
LERP_MID_MIN = 0.05           # the gamma dip must be material at t=0.5

# sample frames 1,5,9,...,29 -> t = 0, 1/8, ..., 7/8 exactly, plus the final
# frame of the span: t = (duration-1)/duration — B never arrives inside the
# effect, and that endpoint frame is rendered and asserted like the rest
SAMPLES = [(1 + 4 * k, k / 8) for k in range(8)] + [(32, 31 / 32)]


def strips_coll(se):
    """The only accessor on both supported versions: .strips, never
    .sequences — that rename is part of what this example witnesses."""
    return se.strips


def new_effect(coll, name, typ, ch, span, **kw):
    """Each version's only accepted end kwarg (vse-cut-list's contract)."""
    if IS_5X:
        return coll.new_effect(
            name=name, type=typ, channel=ch,
            frame_start=span[0], length=span[1] - span[0], **kw,
        )
    return coll.new_effect(
        name=name, type=typ, channel=ch,
        frame_start=span[0], frame_end=span[1], **kw,
    )


def strip_span(s):
    if IS_5X:
        return s.left_handle, s.right_handle, s.duration
    return s.frame_final_start, s.frame_final_end, s.frame_final_duration


def build_cross(sc, swap_inputs=False, effect="GAMMA_CROSS"):
    """The two-strip cross: T1/T2 consumed by the GAMMA_CROSS above them
    (effect strips consume inputs only from below — vse-cut-list's wiring).
    The render path rebuilds it once with effect="CROSS" for the linear
    reference strip."""
    sc.frame_start = SPAN[0]
    sc.frame_end = SPAN[1]
    se = sc.sequence_editor or sc.sequence_editor_create()
    coll = strips_coll(se)
    t1 = new_effect(coll, "T1", "COLOR", 1, SPAN)
    t1.color = A_RGB
    t2 = new_effect(coll, "T2", "COLOR", 2, SPAN)
    t2.color = B_RGB
    src1, src2 = (t2, t1) if swap_inputs else (t1, t2)
    gc = new_effect(coll, "GC", effect, 3, SPAN, input1=src1, input2=src2)
    return gc


def closed_form(t, k):
    """The gamma-0.5 crossfade: mix in sqrt space, square back."""
    return ((1 - t) * math.sqrt(A_RGB[k]) + t * math.sqrt(B_RGB[k])) ** 2


def naive(t, k):
    return (1 - t) * A_RGB[k] + t * B_RGB[k]


def setup_render(sc, w, h):
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 1
    sc.cycles.use_denoising = False
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    # Standard keeps the strip colors exact (AgX would skew the fit)
    sc.view_settings.view_transform = 'Standard'


def sample_colors(sc, frames, tmp):
    """Render the cross at each frame and read the center pixel."""
    out = {}
    for f in frames:
        path = os.path.join(tmp, f"f{f:03d}.png")
        sc.render.filepath = path
        sc.frame_set(f)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(path)
        i = ((PXH // 2) * PXW + PXW // 2) * 4
        out[f] = tuple(img.pixels[i:i + 3])
        bpy.data.images.remove(img)
    return out


def check(sc, gc):
    start, end, duration = strip_span(gc)
    if (start, end, duration) != (SPAN[0], SPAN[1], SPAN[1] - SPAN[0]):
        print(f"ERROR: GC span {(start, end, duration)} != closed form "
              f"{(SPAN[0], SPAN[1], SPAN[1] - SPAN[0])}", file=sys.stderr)
        return 3
    if gc.input_1.name != "T1" or gc.input_2.name != "T2":
        print("ERROR: GC inputs are not T1 -> T2", file=sys.stderr)
        return 4

    # the factory default is AgX — tone-mapped samples poison the fit
    # (measured 0.146 on the red channel during authoring); Standard is
    # mandatory for any pixel witness
    setup_render(sc, PXW, PXH)
    tmp = tempfile.mkdtemp(prefix="vse_gamma_")
    try:
        frames = [f for f, _t in SAMPLES]
        got = sample_colors(sc, frames, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    q_err = 0.0
    lerp_mid = 0.0
    worst = None
    for f, t in SAMPLES:
        # t = (frame - start) / duration: never 1 inside the effect
        t_actual = (f - start) / duration
        if abs(t_actual - t) > 1e-12:
            print(f"ERROR: sample t {t_actual} != {t} — t convention drifted",
                  file=sys.stderr)
            return 5
        for k in range(3):
            e = abs(got[f][k] - closed_form(t_actual, k))
            if e > q_err:
                q_err = e
                worst = (f, k)
            if abs(t_actual - 0.5) < 1e-12:
                lerp_mid = max(lerp_mid,
                               abs(naive(t_actual, k) - closed_form(t_actual, k)))
    if q_err > Q_TOL:
        print(f"ERROR: cross sample deviates {q_err:.4f} from the gamma-0.5 "
              f"closed form at {worst} (tol {Q_TOL} — quantization-aware)",
              file=sys.stderr)
        return 6
    if lerp_mid < LERP_MID_MIN:
        print(f"ERROR: mid-cross lerp deviation only {lerp_mid:.4f} — the "
              "gamma dip is missing; the cross reads as a naive mix",
              file=sys.stderr)
        return 7

    print(f"samples={len(SAMPLES)} q_err={q_err:.2e} (tol {Q_TOL}) "
          f"lerp_mid_dev={lerp_mid:.3f} (min {LERP_MID_MIN})")
    mid = tuple(round(closed_form(0.5, k), 4) for k in range(3))
    print(f"mid(t=0.5) closed form {mid} vs lerp "
          f"{tuple(round(naive(0.5, k), 4) for k in range(3))}")
    return 0


# ------------------------------------------------------------- gallery ---

# Filmstrip geometry: every frame of the span (t = 0 .. 31/32) rendered by
# the sequencer at TILE_W x TILE_H and laid side by side, unaltered.
TILE_W, TILE_H = 24, 150
STRIP_MX, STRIP_MY, STRIP_GAP = 24, 26, 34
FRAMES = list(range(SPAN[0], SPAN[1]))              # 32 frames, t = k/32
MID_FRAME = SPAN[0] + (SPAN[1] - SPAN[0]) // 2      # frame 17, t = 1/2
MARK_RGB = (0.95, 0.80, 0.55)                       # warm t=1/2 index ticks


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def clear_strips(sc):
    """Effects first: deleting a consumed input orphans-and-deletes the
    effect ("Strip 'GC' not in scene" otherwise)."""
    coll = strips_coll(sc.sequence_editor)
    for s in reversed(list(coll)):
        coll.remove(s)


def render_filmstrip(sc, effect, tmp):
    """Render every frame of the cross with `effect` wired T1 -> T2 and
    return the frames as (TILE_H, TILE_W, 4) float arrays, read straight
    from the sequencer's PNGs."""
    import numpy as np
    clear_strips(sc)
    # resolution BEFORE the strips: on 5.2 a COLOR strip bakes the scene
    # size into its own width/height at creation, so strips built at the
    # check's 64x36 would letterbox into a thin band inside a 24x150 frame
    setup_render(sc, TILE_W, TILE_H)
    build_cross(sc, effect=effect)
    tiles = []
    for f in FRAMES:
        path = os.path.join(tmp, f"{effect}_{f:03d}.png")
        sc.render.filepath = path
        sc.frame_set(f)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(path)
        buf = np.empty(TILE_W * TILE_H * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        bpy.data.images.remove(img)
        tiles.append(buf.reshape(TILE_H, TILE_W, 4))
    return tiles


def compose_screen(gamma_tiles, linear_tiles, path):
    """Lay the two filmstrips on a black screen raster: GAMMA_CROSS on top,
    the linear CROSS directly beneath, frame for frame. The frame pixels are
    copied verbatim; the only authored pixels are the black surround and
    three small warm ticks marking the t = 1/2 column."""
    import numpy as np
    n = len(FRAMES)
    w = 2 * STRIP_MX + n * TILE_W
    h = 2 * STRIP_MY + 2 * TILE_H + STRIP_GAP
    raster = np.zeros((h, w, 4), dtype=np.float32)
    raster[..., 3] = 1.0
    # image rows run bottom-up: the linear strip sits low, gamma above it
    y_lin = STRIP_MY
    y_gam = STRIP_MY + TILE_H + STRIP_GAP
    for i, (g, l) in enumerate(zip(gamma_tiles, linear_tiles)):
        x = STRIP_MX + i * TILE_W
        raster[y_gam:y_gam + TILE_H, x:x + TILE_W] = g
        raster[y_lin:y_lin + TILE_H, x:x + TILE_W] = l
    mx = STRIP_MX + (MID_FRAME - SPAN[0]) * TILE_W + TILE_W // 2
    tick = (*MARK_RGB, 1.0)
    for y0, y1 in ((y_gam + TILE_H + 6, h - 6),            # above gamma
                   (y_lin + TILE_H + 8, y_gam - 8),         # in the gap
                   (6, y_lin - 6)):                         # below linear
        raster[y0:y1, mx - 3:mx + 3] = tick
    img = bpy.data.images.new("CrossMonitor", w, h, alpha=False)
    img.pixels.foreach_set(raster.ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    return img, w / h


def build_console(sc, screen_img, aspect):
    """A grading monitor on a machined yoke, hooded, standing on a walnut
    riser beside a three-ball control surface. The screen is one unlit quad
    showing the composed filmstrips with closest-texel sampling: the
    sequencer's pixels reach the camera exactly as it wrote them."""
    import bmesh
    import mathutils
    m = math

    def pbr(name, color, metallic, rough, spec=None):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        b = mat.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*color, 1.0)
        b.inputs["Metallic"].default_value = metallic
        b.inputs["Roughness"].default_value = rough
        if spec is not None:
            s = b.inputs.get("Specular IOR Level") or b.inputs.get("Specular")
            s.default_value = spec
        return mat

    def glow(name, rgb, strength):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*rgb, 1.0)
        em.inputs["Strength"].default_value = strength
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        return mat

    shell = pbr("MonitorShell", (0.07, 0.075, 0.085), 0.55, 0.38)
    rear = pbr("MonitorRear", (0.045, 0.047, 0.052), 0.3, 0.55)
    hood = pbr("HoodFabric", (0.018, 0.018, 0.02), 0.0, 0.92, spec=0.1)
    alu = pbr("YokeAluminium", (0.50, 0.51, 0.54), 0.6, 0.35)
    walnut = pbr("RiserWalnut", (0.19, 0.075, 0.028), 0.0, 0.55, spec=0.25)
    panel = pbr("PanelAnodized", (0.10, 0.105, 0.12), 0.7, 0.42)
    ball = pbr("TrackballResin", (0.025, 0.025, 0.03), 0.0, 0.12)
    key = pbr("KeyCap", (0.03, 0.03, 0.034), 0.0, 0.6)
    tally = glow("TallyLamp", (1.0, 0.25, 0.08), 6.0)
    keylit = glow("KeyBacklight", (0.95, 0.72, 0.42), 2.0)

    def link(name, me, loc, rot=(0.0, 0.0, 0.0)):
        ob = bpy.data.objects.new(name, me)
        ob.location = loc
        ob.rotation_euler = rot
        sc.collection.objects.link(ob)
        return ob

    def rbox(name, dims, loc, mat, bevel=0.02, rot=(0.0, 0.0, 0.0), seg=3):
        """A box with machined, rounded edges."""
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        try:
            bmesh.ops.create_cube(bm, size=1.0,
                                  matrix=mathutils.Matrix.Diagonal((*dims, 1.0)))
            if bevel > 0.0:
                bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel,
                                segments=seg, profile=0.5, affect='EDGES',
                                clamp_overlap=True)
            bm.to_mesh(me)
        finally:
            bm.free()
        me.materials.append(mat)
        return link(name, me, loc, rot)

    def cyl(name, r, depth, loc, mat, seg=48, rot=(0.0, 0.0, 0.0), r2=None):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        try:
            bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                                  radius1=r, radius2=r if r2 is None else r2,
                                  depth=depth)
            for fc in bm.faces:
                fc.smooth = abs(fc.normal.z) < 0.5
            bm.to_mesh(me)
        finally:
            bm.free()
        me.materials.append(mat)
        return link(name, me, loc, rot)

    def sphere(name, r, loc, mat):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        try:
            bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=r)
            for fc in bm.faces:
                fc.smooth = True
            bm.to_mesh(me)
        finally:
            bm.free()
        me.materials.append(mat)
        return link(name, me, loc)

    # ---- riser: a walnut slab on a recessed aluminium plinth band
    riser_top = 0.16
    rbox("Riser", (2.90, 1.50, 0.10), (0.0, -0.18, riser_top - 0.05), walnut, bevel=0.025)
    rbox("RiserBand", (2.76, 1.36, 0.07), (0.0, -0.18, 0.035), alu, bevel=0.01)

    # ---- monitor: screen quad sized from the composed raster's aspect
    scr_w = 2.30
    scr_h = scr_w / aspect
    border, chin = 0.06, 0.13
    body_w = scr_w + 2 * border
    body_h = scr_h + border + chin
    body_d = 0.12
    yoke_h = 0.34
    body_z0 = riser_top + 0.05 + yoke_h
    body_zc = body_z0 + body_h / 2
    scr_zc = body_z0 + chin + scr_h / 2
    rbox("MonitorBody", (body_w, body_d, body_h), (0.0, 0.0, body_zc), shell, bevel=0.03)
    rbox("MonitorRear", (body_w * 0.72, 0.16, body_h * 0.72),
         (0.0, body_d / 2 + 0.06, body_zc + 0.02), rear, bevel=0.06)

    sme = bpy.data.meshes.new("ScreenPanel")
    bm = bmesh.new()
    try:
        y = -body_d / 2 - 0.002
        q = [bm.verts.new(p) for p in ((-scr_w / 2, y, scr_zc - scr_h / 2),
                                       (scr_w / 2, y, scr_zc - scr_h / 2),
                                       (scr_w / 2, y, scr_zc + scr_h / 2),
                                       (-scr_w / 2, y, scr_zc + scr_h / 2))]
        uv = bm.loops.layers.uv.new("UVMap")
        fc = bm.faces.new(q)
        for li, lp in enumerate(fc.loops):
            lp[uv].uv = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))[li]
        bm.to_mesh(sme)
    finally:
        bm.free()
    smat = bpy.data.materials.new("ScreenPixels")
    smat.use_nodes = True
    nt = smat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = screen_img
    tex.interpolation = 'Closest'   # no texel blending across frame seams
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["UV"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    em.inputs["Strength"].default_value = 1.0
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    sme.materials.append(smat)
    link("ScreenPanel", sme, (0.0, 0.0, 0.0))

    # chin: tally lamp and a row of backlit function keys
    chin_z = body_z0 + chin / 2
    front = -body_d / 2
    rbox("TallyLamp", (0.06, 0.02, 0.022), (-body_w / 2 + 0.16, front - 0.004, chin_z),
         tally, bevel=0.004)
    for i in range(5):
        rbox(f"ChinKey{i}", (0.085, 0.02, 0.03),
             (body_w / 2 - 0.20 - i * 0.12, front - 0.004, chin_z), key, bevel=0.006)
    rbox("ChinKeyLit", (0.085, 0.022, 0.03),
         (body_w / 2 - 0.20, front - 0.006, chin_z), keylit, bevel=0.006)

    # hood: top and flared side flaps shading the panel
    hood_d = 0.30
    top_z = body_z0 + body_h
    rbox("HoodTop", (body_w + 0.04, hood_d, 0.018),
         (0.0, front - hood_d / 2 + 0.02, top_z + 0.004), hood, bevel=0.006,
         rot=(m.radians(-6.0), 0.0, 0.0))
    for sx in (-1.0, 1.0):
        rbox(f"HoodSide{'L' if sx < 0 else 'R'}", (0.018, hood_d, body_h - 0.02),
             (sx * (body_w / 2 + 0.01) + sx * hood_d * 0.07, front - hood_d / 2 + 0.03,
              body_zc), hood, bevel=0.006, rot=(0.0, 0.0, m.radians(-8.0 * sx)))

    # yoke: foot plate, twin uprights, cross bar into the rear housing
    rbox("YokeFoot", (0.95, 0.52, 0.05), (0.0, 0.12, riser_top + 0.025), alu, bevel=0.018)
    for sx in (-0.26, 0.26):
        rbox("YokeArm", (0.07, 0.07, yoke_h + 0.22),
             (sx, 0.17, riser_top + 0.05 + (yoke_h + 0.22) / 2 - 0.01), alu, bevel=0.015)
    rbox("YokeBar", (0.62, 0.07, 0.08), (0.0, 0.17, body_z0 + 0.20), alu, bevel=0.015)
    for sx in (-0.26, 0.26):
        cyl("YokeKnob", 0.055, 0.04, (sx + (0.055 if sx > 0 else -0.055), 0.17,
                                      body_z0 + 0.20), rear,
            rot=(0.0, m.radians(90.0), 0.0))

    # control surface: a raked anodized deck with three trackballs
    deck_rot = (m.radians(9.0), 0.0, 0.0)
    deck_c = mathutils.Vector((0.0, -0.66, riser_top + 0.055))
    rbox("ControlDeck", (1.55, 0.52, 0.09), tuple(deck_c), panel, bevel=0.02,
         rot=deck_rot)
    tilt = mathutils.Euler(deck_rot).to_matrix()
    deck_up = tilt @ mathutils.Vector((0.0, 0.0, 1.0))
    for i, bx in enumerate((-0.46, 0.0, 0.46)):
        base = deck_c + tilt @ mathutils.Vector((bx, 0.04, 0.045))
        cyl(f"TrackRing{i}", 0.15, 0.03, tuple(base + deck_up * 0.012), alu,
            rot=deck_rot)
        sphere(f"Trackball{i}", 0.115, tuple(base + deck_up * 0.045), ball)
        cyl(f"TrackCollar{i}", 0.125, 0.02, tuple(base + deck_up * 0.03), key,
            rot=deck_rot)
    for i in range(7):
        kx = -0.60 + i * 0.2
        rbox(f"DeckKey{i}", (0.12, 0.06, 0.03),
             tuple(deck_c + tilt @ mathutils.Vector((kx, -0.20, 0.05))),
             keylit if i == 3 else key, bevel=0.008, rot=deck_rot)


def build_stage(sc):
    """The house dark studio: floor, wall, world, four area lights."""
    import bmesh
    import mathutils
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
    sc.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 8.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    sc.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    if world.node_tree is None:  # 5.x worlds ship with nodes; 4.x needs this
        world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    sc.world = world

    def light(name, loc, energy, size, col, target):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        d = mathutils.Vector(target) - ob.location
        ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        sc.collection.objects.link(ob)

    # warm shaped key upper left, faint cool fill, cool rim, and the warm
    # wedge between console and wall raking a pool onto the backdrop
    light("Key", (-4.0, -5.0, 6.0), 520.0, 4.5, (1.0, 0.96, 0.9), (0.0, -0.3, 0.8))
    light("Fill", (5.5, -4.0, 2.5), 90.0, 9.0, (0.75, 0.85, 1.0), (0.0, 0.0, 1.0))
    light("Rim", (0.5, 4.0, 5.0), 300.0, 4.0, (0.6, 0.78, 1.0), (0.0, 0.2, 1.4))
    light("Wedge", (1.0, 3.2, 4.4), 460.0, 6.0, (1.0, 0.76, 0.5), (1.5, 8.0, 1.8))


def render_still(sc, path, engine):
    """Render both filmstrips from the sequencer, guard the linear reference,
    then shoot the console with those exact pixels on its screen."""
    tmp = tempfile.mkdtemp(prefix="vse_gamma_still_")
    try:
        gamma_tiles = render_filmstrip(sc, "GAMMA_CROSS", tmp)
        linear_tiles = render_filmstrip(sc, "CROSS", tmp)
        clear_strips(sc)
        # the lower strip is only a fair comparison if it IS the lerp: guard
        # the sequencer CROSS at t = 1/2 against (1-t)*A + t*B
        k_mid = MID_FRAME - SPAN[0]
        cy, cx = TILE_H // 2, TILE_W // 2
        lin_mid = linear_tiles[k_mid][cy, cx, :3]
        gam_mid = gamma_tiles[k_mid][cy, cx, :3]
        lin_err = max(abs(float(lin_mid[k]) - naive(0.5, k)) for k in range(3))
        gam_err = max(abs(float(gam_mid[k]) - closed_form(0.5, k)) for k in range(3))
        print(f"filmstrip mid: gamma {tuple(round(float(v), 3) for v in gam_mid)} "
              f"(err {gam_err:.2e}), linear {tuple(round(float(v), 3) for v in lin_mid)} "
              f"(err {lin_err:.2e})")
        # every frame must fill its tile edge to edge (a letterboxed COLOR
        # strip would paint black bars into the strip and fake a dip)
        spread = max(float((t[..., :3].max(axis=(0, 1)) - t[..., :3].min(axis=(0, 1))).max())
                     for t in gamma_tiles + linear_tiles)
        print(f"filmstrip frames uniform: max in-frame spread {spread:.2e}")
        if spread > Q_TOL:
            print(f"ERROR: a filmstrip frame is not uniform (spread {spread:.4f})",
                  file=sys.stderr)
            return 9
        if lin_err > Q_TOL or gam_err > Q_TOL:
            print(f"ERROR: filmstrip mid off its closed form (linear {lin_err:.4f}, "
                  f"gamma {gam_err:.4f}, tol {Q_TOL}) — the comparison would lie",
                  file=sys.stderr)
            return 9

        screen_img, aspect = compose_screen(
            gamma_tiles, linear_tiles, os.path.join(tmp, "monitor.png"))
        screen_img.pack()   # the raster outlives the temp dir

        build_stage(sc)
        build_console(sc, screen_img, aspect)

        cam_data = bpy.data.cameras.new("Cam")
        cam_data.lens = 50.0
        cam = bpy.data.objects.new("Cam", cam_data)
        cam.location = (1.55, -6.2, 1.55)
        sc.collection.objects.link(cam)
        aim = bpy.data.objects.new("Aim", None)
        aim.location = (0.05, -0.2, 0.86)
        sc.collection.objects.link(aim)
        con = cam.constraints.new('TRACK_TO')
        con.target = aim
        sc.camera = cam

        sc.render.engine = 'CYCLES' if engine == 'cycles' else eevee_engine_id()
        if engine == 'cycles':
            sc.cycles.samples = 64
            sc.cycles.use_denoising = True
        else:
            try:
                sc.eevee.taa_render_samples = 64
            except AttributeError:
                pass
        sc.render.resolution_x = 1280
        sc.render.resolution_y = 720
        sc.render.resolution_percentage = 100
        sc.render.image_settings.file_format = 'PNG'
        sc.render.filepath = path
        # Standard keeps the mounted sequencer pixels exact (docs/VISUAL-STYLE.md)
        sc.view_settings.view_transform = 'Standard'

        # Layer 1 framing gate on the console — exit 10 before the beauty pass
        stage = [o for o in sc.objects if o.name in ("Floor", "Wall")]
        hero = [o for o in sc.objects
                if o.type in gallery_framing._RENDER_TYPES and o not in stage]
        fcode = gallery_framing.check_framing(sc, cam, hero=hero, elements=hero,
                                              stage=stage)
        if fcode:
            return fcode
        bpy.ops.render.render(write_still=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 8
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--swap-inputs", action="store_true",
                   help="falsifier: GC T2 -> T1, still assert T1 -> T2")
    args = p.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    gc = build_cross(sc, swap_inputs=args.swap_inputs)
    code = check(sc, gc)
    if code:
        return code

    if args.output:
        code = render_still(sc, os.path.abspath(args.output), args.engine)
        if code:
            return code
        print(f"rendered still {args.output}")

    print("vse-gamma-cross OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
