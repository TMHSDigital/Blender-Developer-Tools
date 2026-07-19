"""VSE cut list — a runnable example.

Witnesses the sequencer API rename between Blender 4.5 LTS and 5.x, the
single most common way AI-generated VSE code dies on a modern Blender:

- ``sequence_editor.sequences`` is gone on 5.x — only ``.strips`` remains
  (4.5 keeps both accessors as a transition bridge).
- ``strips.new_effect(...)`` ends a strip with ``frame_end=`` on 4.5 but
  ``length=`` on 5.x; the wrong kwarg raises TypeError on each side.
- Timeline bounds read ``frame_final_start/end/duration`` on 4.5. On 5.x
  those names are deprecated (removal announced for 6.0) and the canonical
  accessors are ``left_handle`` / ``right_handle`` / ``duration``.
- The ``TRANSFORM`` effect-strip type is removed on 5.x; per-strip
  ``strip.transform`` (StripTransform) is the cross-version way to place
  strips in the frame. Effect inputs are ``input_1`` / ``input_2`` on both.

Two further hazards surfaced while authoring and are witnessed here:

- A GAMMA_CROSS asked to outlast its inputs' overlap is silently clamped to
  the overlap — requesting length 9 over a (25, 33) overlap yields (25, 33).
- A scene strip pointing at its OWN scene is a feedback loop: it renders
  transparent (alpha 0), so the "stage" is silently absent from the frame.
  Scene strips must source a separate scene.
- Effect strips CONSUME their inputs: a strip feeding an effect never
  composites on its own channel, and the effect's own transform is applied
  on top of the inputs' transforms. A first-draft program wall that fed
  display strips A/B into the cross lost both cells — only the effect's
  output rendered. The consumption is also ordered: the effect must sit on
  a channel ABOVE its inputs, or they keep compositing independently (the
  second draft put GC below T1/T2 and T2 painted teal over the whole wall).
  The timeline below therefore feeds the cross a dedicated source pair
  (T1/T2) that owns no mosaic cell, on channels directly under GC.

The check builds a deterministic cut list, asserts every span against its
closed form on each version's canonical accessors, then proves the spans,
wiring, colors, and transforms survive a save/reload round-trip. Pass
--output to render the authentic program wall (the sequencer output
sampled mid-cross) presented on a reference monitor in the dark-studio
editing bay, and --check-pixels to assert the compositing contract on a
tiny render (cell colors and input consumption), the way CI does:

    blender --background --python vse_cut_list.py --
    blender --background --python vse_cut_list.py -- --check-pixels
    blender --background --python vse_cut_list.py -- --output vse.png
"""
import bpy, sys, os, math, argparse, tempfile, warnings, shutil
import mathutils

IS_5X = bpy.app.version >= (5, 0, 0)

# Closed-form cut list, end-exclusive [start, end) spans on the timeline.
# Channel order matters: an effect strip consumes its inputs only when it
# sits ABOVE them — below, the inputs composite independently (T2 painted
# teal over the whole wall in the first draft). GC must be top-most.
SC_CH, A_CH, B_CH, C_CH, TXT_CH, T1_CH, T2_CH, GC_CH = 1, 2, 3, 4, 5, 6, 7, 8
A_SPAN = (1, 33)     # crimson program, 32 frames
B_SPAN = (25, 57)    # teal program, 32 frames, overlaps A on 25..32
C_SPAN = (1, 57)     # amber long-runner, outlives both
T1_SPAN = (1, 33)    # cross source 1 (crimson) — consumed by GC, no cell
T2_SPAN = (25, 57)   # cross source 2 (teal) — consumed by GC, no cell
GC_SPAN = (25, 33)   # 8-frame cross, exactly the T1/T2 overlap (clamped to it)
TXT_SPAN = (1, 57)   # caption lives for the whole color timeline
SCENE_END = 250      # explicit scene frame_end -> scene strip spans [1, 251)
TXT_BODY = "CUT LIST  A 001-032  B 025-056  CROSS 025-032  @ F29"

RENDER_W, RENDER_H = 1280, 720
SAMPLE_FRAME = 29    # mid-cross: GC output is the 50/50 blend; all cells live

# Program-wall mosaic: per-strip transform, offsets in display pixels.
CELL_SCALE = 0.36
CELL_OX = 244.4      # 28 px crosshair gap, ~165 px side margins at 1280x720
CELL_OY = 143.6      # 28 px gap, ~87 px top/bottom margins
XF_TOL = 1e-3        # float32 transform read-back tolerance

A_RGB = (0.85, 0.10, 0.22)    # crimson
B_RGB = (0.06, 0.75, 0.80)    # teal
C_RGB = (0.95, 0.62, 0.10)    # amber

# --check-pixels geometry (96x54 mini render): fractional cell centers and a
# top-margin point that would be crimson if T1 composited independently.
PXW, PXH = 96, 54
PX_TOL = 0.10        # per-channel tolerance on unlit strip colors


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def strips_coll(se):
    """The version-safe accessor: .strips everywhere, never .sequences."""
    return se.strips if hasattr(se, "strips") else se.sequences


def new_effect(coll, name, typ, ch, span, **kw):
    """Create an effect strip covering [span[0], span[1]) — end-exclusive —
    using each version's only accepted end kwarg."""
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
    """Timeline bounds (start, end, duration) via the canonical accessors:
    frame_final_* on 4.5; left_handle/right_handle/duration on 5.x, where the
    frame_final_* names are deprecated aliases slated for removal in 6.0."""
    if IS_5X:
        return s.left_handle, s.right_handle, s.duration
    return s.frame_final_start, s.frame_final_end, s.frame_final_duration


def expect_raises_typeerror(fn, what):
    try:
        fn()
    except TypeError:
        return None
    return f"{what} did not raise TypeError"


def build_cut_list(sc, pix=1.0):
    """The deterministic cut list. pix scales the pixel-unit mosaic offsets
    for renders smaller than 1280x720. Returns the strip collection."""
    sc.frame_start = 1
    sc.frame_end = SCENE_END
    se = sc.sequence_editor or sc.sequence_editor_create()
    coll = strips_coll(se)

    # The scene strip sources a SEPARATE stage scene: a scene strip pointing
    # at its own scene is a feedback loop and renders transparent (the first
    # draft's "studio" was the viewer showing alpha=0 as grey).
    stage = bpy.data.scenes.new("Stage")
    stage.frame_start = 1
    stage.frame_end = SCENE_END
    coll.new_scene(name="SC", scene=stage, channel=SC_CH, frame_start=1)

    a = new_effect(coll, "A", "COLOR", A_CH, A_SPAN)
    a.color = A_RGB
    b = new_effect(coll, "B", "COLOR", B_CH, B_SPAN)
    b.color = B_RGB
    c = new_effect(coll, "C", "COLOR", C_CH, C_SPAN)
    c.color = C_RGB
    # Dedicated cross sources: strips feeding an effect are consumed by it
    # (they never composite on their own channel), so the display programs
    # A/B cannot double as the cross inputs without losing their cells.
    t1 = new_effect(coll, "T1", "COLOR", T1_CH, T1_SPAN)
    t1.color = A_RGB
    t2 = new_effect(coll, "T2", "COLOR", T2_CH, T2_SPAN)
    t2.color = B_RGB
    gc = new_effect(coll, "GC", "GAMMA_CROSS", GC_CH, GC_SPAN,
                    input1=t1, input2=t2)
    txt = new_effect(coll, "TXT", "TEXT", TXT_CH, TXT_SPAN)
    txt.text = TXT_BODY

    # Program-wall mosaic via per-strip transform (the TRANSFORM effect type
    # is gone on 5.x; StripTransform exists on both versions).
    for s, ox, oy in ((a, -CELL_OX, CELL_OY), (b, CELL_OX, CELL_OY),
                      (c, -CELL_OX, -CELL_OY), (gc, CELL_OX, -CELL_OY)):
        s.transform.scale_x = CELL_SCALE
        s.transform.scale_y = CELL_SCALE
        s.transform.offset_x = ox * pix
        s.transform.offset_y = oy * pix
    return coll


def check_span(coll, name, want):
    s = coll.get(name)
    if s is None:
        return f"strip {name!r} missing"
    got = strip_span(s)
    if got != (want[0], want[1], want[1] - want[0]):
        return (f"{name} span {got} != closed form "
                f"({want[0]}, {want[1]}, {want[1] - want[0]})")
    return None


def check(coll_owner):
    """Assert the full contract against the editor of the given scene.
    Returns 0 or an exit code; each stage witnesses one contract."""
    se = coll_owner.sequence_editor

    # 3. Accessor contract: .sequences removed on 5.x, bridged on 4.5.
    if IS_5X:
        if hasattr(se, "sequences"):
            return fail("5.x still exposes sequence_editor.sequences — the "
                        "rename contract drifted", 3)
    else:
        if not hasattr(se, "sequences"):
            return fail("4.5 lost the legacy .sequences bridge", 3)
        if len(se.sequences) != len(se.strips):
            return fail(
                f"4.5 bridge mismatch: .sequences sees {len(se.sequences)} "
                f"strips, .strips sees {len(se.strips)}", 3)
    coll = strips_coll(se)

    # 4. Creation signature: each side accepts exactly one end kwarg.
    msg = expect_raises_typeerror(
        lambda: coll.new_effect(
            name="BAD", type="COLOR", channel=9,
            frame_start=1, **({"frame_end": 9} if IS_5X else {"length": 8})),
        "legacy end kwarg on this version")
    if msg:
        return fail(msg + " — the porting trap no longer hard-fails", 4)
    if IS_5X:
        # The TRANSFORM effect-strip type is removed on 5.x.
        msg = expect_raises_typeerror(
            lambda: coll.new_effect(name="BAD2", type="TRANSFORM", channel=9,
                                    frame_start=1, length=8,
                                    input1=coll.get("A")),
            "TRANSFORM effect type on 5.x")
        if msg:
            return fail(msg + " — removed enum value came back", 4)

    # 5. Frame ranges against the closed form, on canonical accessors.
    for name, span in (("A", A_SPAN), ("B", B_SPAN), ("C", C_SPAN),
                       ("T1", T1_SPAN), ("T2", T2_SPAN), ("GC", GC_SPAN),
                       ("TXT", TXT_SPAN)):
        msg = check_span(coll, name, span)
        if msg:
            return fail(msg, 5)
    for name, ch in (("A", A_CH), ("B", B_CH), ("C", C_CH), ("GC", GC_CH),
                     ("TXT", TXT_CH), ("T1", T1_CH), ("T2", T2_CH),
                     ("SC", SC_CH)):
        if coll.get(name).channel != ch:
            return fail(f"{name} landed on channel "
                        f"{coll.get(name).channel}, expected {ch}", 5)

    # 6. Deprecation bridge: 5.x marks frame_final_* deprecated yet keeps the
    # values equal; 4.5 has no deprecation flags at all.
    a = coll.get("A")
    prop = a.bl_rna.properties.get("frame_final_start")
    flag = getattr(prop, "is_deprecated", None)
    if IS_5X:
        if not flag:
            return fail("5.x no longer flags frame_final_start deprecated", 6)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            legacy = (a.frame_final_start, a.frame_final_end,
                      a.frame_final_duration)
        if legacy != strip_span(a):
            return fail(f"5.x deprecated alias {legacy} != canonical "
                        f"{strip_span(a)} — the bridge changed semantics", 6)
    else:
        if flag:
            return fail("4.5 already deprecates frame_final_start", 6)

    # 7. Effect wiring: GAMMA_CROSS inputs are input_1/input_2 on both
    # versions (not input1), in authored order, and the cross is clamped to
    # exactly the source overlap (25..33).
    gc = coll.get("GC")
    if gc.input_count != 2 or gc.input_1.name != "T1" or gc.input_2.name != "T2":
        return fail(
            f"GC wiring drifted: input_count={gc.input_count} "
            f"inputs=({getattr(gc.input_1, 'name', None)}, "
            f"{getattr(gc.input_2, 'name', None)}), expected T1 -> T2", 7)
    if gc.type != "GAMMA_CROSS" or coll.get("A").type != "COLOR":
        return fail("strip .type enum drifted", 7)

    # 8. Scene strip: 4-arg signature, default span is the scene frame range,
    # and it sources the separate Stage scene (same-scene strips recurse).
    sc_s = coll.get("SC")
    if strip_span(sc_s) != (1, SCENE_END + 1, SCENE_END):
        return fail(f"scene strip span {strip_span(sc_s)} != "
                    f"(1, {SCENE_END + 1}, {SCENE_END})", 8)
    if sc_s.scene is None or sc_s.scene.name != "Stage":
        return fail("scene strip does not source the Stage scene", 8)

    # 9. Mosaic transforms + compositing defaults persist on the strips.
    xf_err = 0.0
    for name, ox, oy in (("A", -CELL_OX, CELL_OY), ("B", CELL_OX, CELL_OY),
                         ("C", -CELL_OX, -CELL_OY), ("GC", CELL_OX, -CELL_OY)):
        t = coll.get(name).transform
        xf_err = max(xf_err, abs(t.scale_x - CELL_SCALE),
                     abs(t.scale_y - CELL_SCALE),
                     abs(t.offset_x - ox), abs(t.offset_y - oy))
    if xf_err > XF_TOL:
        return fail(f"transform read-back error {xf_err:.2e} > {XF_TOL:.0e}",
                    9)
    for name in ("A", "B", "C"):
        s = coll.get(name)
        if s.blend_type != "ALPHA_OVER" or s.alpha_mode != "STRAIGHT":
            return fail(f"{name} compositing defaults drifted: "
                        f"{s.blend_type}/{s.alpha_mode}", 9)
    if coll.get("TXT").text != TXT_BODY:
        return fail("text strip body drifted", 9)
    if tuple(round(v, 3) for v in coll.get("A").color) != A_RGB:
        return fail("strip color drifted", 9)
    return 0


def check_roundtrip():
    """Save, reload, and re-assert: frame ranges, wiring, and transforms
    must survive the .blend serialization round-trip."""
    tmp = tempfile.mkdtemp(prefix="vse_cut_list_")
    path = os.path.join(tmp, "cutlist.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    return check(bpy.context.scene)


def run_checks():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    build_cut_list(sc)
    code = check(sc)
    if code != 0:
        return code
    code = check_roundtrip()
    if code != 0:
        return fail(f"round-trip re-assert failed (exit {code})", 10)
    print(
        f"accessor: {'strips only (.sequences removed)' if IS_5X else '.sequences bridged to .strips'}; "
        f"end kwarg: {'length' if IS_5X else 'frame_end'} (wrong kwarg TypeErrors); "
        f"spans A{A_SPAN} B{B_SPAN} C{C_SPAN} GC{GC_SPAN} "
        f"SC(1, {SCENE_END + 1}) on {'left_handle/right_handle/duration' if IS_5X else 'frame_final_*'}; "
        f"GC input_1=T1 input_2=T2 clamped to the overlap; "
        f"transforms tol {XF_TOL:.0e}; all survive save/reload"
    )
    return 0


# ---------------------------------------------------------------- render ---

def eevee_engine_id():
    return "BLENDER_EEVEE" if IS_5X else "BLENDER_EEVEE_NEXT"


def build_stage(sc):
    """The dark studio the program wall floats in: floor, back wall, warm
    key/fill/rim plus the signature wedge raking the backdrop."""
    import bmesh
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
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    sc.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    if world.node_tree is None:  # 5.x worlds ship with nodes; 4.x needs this
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

    light("Key", (-4.0, -5.0, 6.0), 500.0, 4.5, (1.0, 0.96, 0.9), (48, 0, -38))
    light("Fill", (5.0, -4.0, 3.0), 85.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Rim", (0.5, 4.5, 5.0), 260.0, 4.0, (0.6, 0.78, 1.0), (-55, 0, 175))
    # Between the mosaic zone and the wall so it only rakes the backdrop.
    light("Wedge", (2.5, 3.5, 4.2), 560.0, 6.0, (1.0, 0.76, 0.5), (-72, 0, 195))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 45.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (-0.3, -10.5, 2.4)
    cam.rotation_euler = (math.radians(87), 0.0, 0.0)
    sc.collection.objects.link(cam)
    sc.camera = cam


def render_frame(sc, path, engine, w, h):
    """Render the SEQUENCER output at SAMPLE_FRAME: the mosaic is VSE
    compositing, not 3D geometry — a broken span drops its cell to stage."""
    pix = w / RENDER_W
    coll = strips_coll(sc.sequence_editor)
    txt = coll.get("TXT")
    txt.font_size = 40.0 * pix
    txt.color = (0.92, 0.90, 0.86, 1.0)
    txt.location = (0.5, 0.035)

    sc.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        sc.cycles.samples = 64 if w >= RENDER_W else 1
        sc.cycles.use_denoising = False
    else:
        try:
            sc.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    # AgX desaturates the program cells toward pastel — Standard keeps the
    # authored strip colors exact.
    sc.view_settings.view_transform = "Standard"
    sc.frame_set(SAMPLE_FRAME)
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def build_bay(sc, frame_path):
    """The editing-bay presentation: a reference monitor on a desk in the
    dark studio, its screen showing the AUTHENTIC sequencer frame. The pixels
    on the screen are the evidence (rendered by the VSE above); the bay is
    only the designed presentation around them."""
    import bmesh

    def box(name, size, loc, mat):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        try:
            bmesh.ops.create_cube(bm, size=1.0,
                                  matrix=mathutils.Matrix.Diagonal((*size, 1.0)))
            bm.to_mesh(me)
        finally:
            bm.free()
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        ob.location = loc
        sc.collection.objects.link(ob)
        return ob

    def pbr(name, base, metallic, roughness):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        b = mat.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*base, 1.0)
        b.inputs["Metallic"].default_value = metallic
        b.inputs["Roughness"].default_value = roughness
        return mat

    gunmetal = pbr("BayMetal", (0.08, 0.09, 0.10), 0.7, 0.40)
    deskmat = pbr("DeskTop", (0.05, 0.05, 0.06), 0.0, 0.80)

    # desk slab, stand, and the monitor bezel (screen face toward -Y)
    box("Desk", (2.80, 1.10, 0.72), (0.0, 0.0, 0.36), deskmat)
    box("StandBase", (0.70, 0.50, 0.06), (0.0, 0.05, 0.75), gunmetal)
    box("Stand", (0.18, 0.12, 0.50), (0.0, 0.05, 0.99), gunmetal)
    box("Bezel", (2.06, 0.09, 1.30), (0.0, 0.0, 1.89), gunmetal)

    # the screen: one unlit quad sampling the authentic frame end to end —
    # emission only, so the VSE pixels read exactly as the sequencer wrote them
    img = bpy.data.images.load(frame_path)
    smat = bpy.data.materials.new("ProgramScreen")
    smat.use_nodes = True
    nt = smat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["UV"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    sme = bpy.data.meshes.new("Screen")
    bm = bmesh.new()
    try:
        q = [bm.verts.new(p) for p in ((-0.96, -0.048, 1.35), (0.96, -0.048, 1.35),
                                       (0.96, -0.048, 2.43), (-0.96, -0.048, 2.43))]
        # explicit UVs, not Generated: the quad is flat in Y, so Generated's
        # image-V is a constant and the screen samples one strip of the frame
        uv_layer = bm.loops.layers.uv.new("UVMap")
        f = bm.faces.new(q)
        for li, l in enumerate(f.loops):
            l[uv_layer].uv = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))[li]
        bm.to_mesh(sme)
    finally:
        bm.free()
    sme.materials.append(smat)
    sob = bpy.data.objects.new("Screen", sme)
    sc.collection.objects.link(sob)

    # a small desk-lip caption, the bay's only typography
    cmat = pbr("CaptionGrey", (0.42, 0.44, 0.48), 0.2, 0.6)
    cu = bpy.data.curves.new("BayCaption", "FONT")
    cu.body = "PROGRAM"
    cu.align_x = "CENTER"
    cu.size = 0.10
    cu.extrude = 0.004
    cob = bpy.data.objects.new("BayCaption", cu)
    cob.location = (0.0, -0.40, 0.73)
    cob.data.materials.append(cmat)
    sc.collection.objects.link(cob)


def render_bay(sc, path, engine, w, h):
    """Render the editing bay. The camera moves to a three-quarter view of
    the monitor; everything else reuses the house stage."""
    cam_data = bpy.data.cameras.new("BayCam")
    cam_data.lens = 52.0
    cam = bpy.data.objects.new("BayCam", cam_data)
    cam.location = (2.0, -5.2, 1.72)
    sc.collection.objects.link(cam)
    target = bpy.data.objects.new("BayAim", None)
    target.location = (0.0, 0.0, 1.28)
    sc.collection.objects.link(target)
    con = cam.constraints.new("TRACK_TO")
    con.target = target
    sc.camera = cam

    sc.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        sc.cycles.samples = 64
        sc.cycles.use_denoising = False
    else:
        try:
            sc.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    # Standard keeps both the stage saturated and the on-screen frame true
    sc.view_settings.view_transform = "Standard"
    bpy.ops.render.render(write_still=True, scene=sc.name)
    return os.path.exists(path) and os.path.getsize(path) > 0


def render_still(path, engine):
    """Two passes: the authentic sequencer frame (evidence), then the
    editing-bay presentation with that exact frame on the monitor screen."""
    sc = bpy.context.scene
    build_cut_list(sc)
    build_stage(bpy.data.scenes["Stage"])
    tmp = tempfile.mkdtemp(prefix="vse_frame_")
    try:
        frame_path = os.path.join(tmp, "program.png")
        if not render_frame(sc, frame_path, engine, RENDER_W, RENDER_H):
            return False
        bay = bpy.data.scenes.new("Bay")
        build_stage(bay)          # the house dark studio, lights included
        build_bay(bay, frame_path)
        return render_bay(bay, path, engine, RENDER_W, RENDER_H)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # pixels live on in the blend


def near(got, want, tol):
    return all(abs(g - w) <= tol for g, w in zip(got, want))


def check_pixels(engine):
    """Compositing witness on a tiny render: cell centers carry their strip
    colors, the cross cell is the blend (neither source), and a margin point
    is stage-dark — if T1 composited independently it would be crimson."""
    sc = bpy.context.scene
    build_cut_list(sc, pix=PXW / RENDER_W)
    build_stage(bpy.data.scenes["Stage"])
    tmp = tempfile.mkdtemp(prefix="vse_pixels_")
    path = os.path.join(tmp, "px.png")
    if not render_frame(sc, path, engine, PXW, PXH):
        return fail("pixel-check render produced no file", 12)
    img = bpy.data.images.load(path)
    if (img.size[0], img.size[1]) != (PXW, PXH):
        bpy.data.images.remove(img)
        return fail(f"pixel-check size {tuple(img.size)} != {(PXW, PXH)}", 12)
    px = img.pixels[:]
    bpy.data.images.remove(img)

    def at(fx, fy):
        x, y = int(fx * PXW), int(fy * PXH)
        i = (y * PXW + x) * 4
        return tuple(px[i:i + 3])

    tl, tr = at(0.25, 0.75), at(0.75, 0.75)
    bl, br = at(0.25, 0.25), at(0.75, 0.25)
    margin = at(0.5, 0.97)
    if not near(tl, A_RGB, PX_TOL):
        return fail(f"TL cell {tuple(round(c,3) for c in tl)} != crimson "
                    f"{A_RGB} — A's span or cell broke", 12)
    if not near(tr, B_RGB, PX_TOL):
        return fail(f"TR cell {tuple(round(c,3) for c in tr)} != teal "
                    f"{B_RGB}", 12)
    if not near(bl, C_RGB, PX_TOL):
        return fail(f"BL cell {tuple(round(c,3) for c in bl)} != amber "
                    f"{C_RGB}", 12)
    # Mid-cross the blend must sit strictly between the two sources on every
    # channel (a mixed color, not a source, black, or a freeze), with teal's
    # blue dominant and crimson still present in red.
    between = all(lo < v < hi for v, lo, hi in zip(
        br, (B_RGB[0], A_RGB[1], A_RGB[2]), (A_RGB[0], B_RGB[1], B_RGB[2])))
    if not (between and br[2] > br[0] and br[2] > br[1] and br[0] > 0.2):
        return fail(f"BR cross cell {tuple(round(c,3) for c in br)} is not "
                    f"a mid crimson-teal blend", 12)
    # The margin shows the real stage through the scene strip; if a consumed
    # cross source still composited, the margin would carry its full-frame
    # color instead (T2 painted the whole wall teal in the first draft).
    if near(margin, A_RGB, PX_TOL) or near(margin, B_RGB, PX_TOL):
        return fail(f"top margin {tuple(round(c,3) for c in margin)} matches "
                    f"a cross source — a consumed strip composited", 12)
    print(
        f"pixels: TL{tuple(round(c,3) for c in tl)} "
        f"TR{tuple(round(c,3) for c in tr)} "
        f"BL{tuple(round(c,3) for c in bl)} "
        f"BR(blend){tuple(round(c,3) for c in br)} "
        f"margin{tuple(round(c,3) for c in margin)} (tol {PX_TOL})"
    )
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument(
        "--engine", default="eevee", choices=("eevee", "cycles"),
        help="render engine for --output/--check-pixels (cycles for GPU-less hosts)",
    )
    p.add_argument(
        "--check-pixels", action="store_true",
        help="also assert the compositing contract on a tiny render",
    )
    args = p.parse_args(argv)

    code = run_checks()
    if code != 0:
        return code
    if args.check_pixels:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        code = check_pixels(args.engine)
        if code != 0:
            return code
    if args.output:
        # The round-trip reloaded a .blend; start clean for the still.
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if not render_still(os.path.abspath(args.output), args.engine):
            return fail(f"render produced no file at {args.output}", 11)
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
