"""The GAMMA_CROSS blend curve, asserted per frame — a runnable example.

Witnesses the fade math AI-generated sequencer code most often assumes
wrong: a GAMMA_CROSS between two strips is NOT the naive linear mix
``(1-t)*A + t*B``. It blends in a gamma-0.5 space:

    out = ((1-t)*sqrt(A) + t*sqrt(B))^2,   t = (frame - start) / duration

so the mid-cross dips below the sRGB lerp — from crimson (0.85, 0.10, 0.22)
and teal (0.06, 0.75, 0.80) the midpoint is (0.341, 0.349, 0.463), a full
0.114 darker on the red channel than the lerp (0.455, 0.425, 0.510). The
check renders tiny frames across the cross and asserts every sample against
the closed form, plus that the lerp deviation at mid is material.

Also witnessed: ``t`` never reaches 1 inside the effect — the last frame of
the span blends at (duration-1)/duration; B arrives only when the effect
ends. And the version-gated creation contract from vse-cut-list holds the
whole thing up: ``strips`` (never ``.sequences``), and ``new_effect`` ends
with ``length=`` on 5.x, ``frame_end=`` on 4.5.

The blend math is identical on Blender 4.5 LTS and 5.1 (every sample matches
to the quantization step).

By default it runs only the correctness check (no gallery render) — the CI
smoke check. Pass --output to also render a still:

    blender --background --python vse_gamma_cross.py --                 # check only
    blender --background --python vse_gamma_cross.py -- --output g.png  # + render
"""
import bpy, sys, os, math, argparse, tempfile, shutil

IS_5X = bpy.app.version >= (5, 0, 0)

A_RGB = (0.85, 0.10, 0.22)    # crimson
B_RGB = (0.06, 0.75, 0.80)    # teal
SPAN = (1, 33)                # 32 frames of cross
PXW, PXH = 64, 36             # tiny per-sample renders, CI-safe like vse-cut-list
Q_TOL = 5e-3                  # 2x the 8-bit quantization step + gamma-fit residual (measured 2.93e-3)
LERP_MID_MIN = 0.05           # the gamma dip must be material at t=0.5

# sample frames 1,5,9,...,29 -> t = 0, 1/8, ..., 7/8 exactly
SAMPLES = [(1 + 4 * k, k / 8) for k in range(8)]


def strips_coll(se):
    """The version-safe accessor: .strips everywhere, never .sequences."""
    return se.strips if hasattr(se, "strips") else se.sequences


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


def build_cross(sc):
    """The two-strip cross: T1/T2 consumed by the GAMMA_CROSS above them
    (effect strips consume inputs only from below — vse-cut-list's wiring)."""
    sc.frame_start = SPAN[0]
    sc.frame_end = SPAN[1]
    se = sc.sequence_editor or sc.sequence_editor_create()
    coll = strips_coll(se)
    t1 = new_effect(coll, "T1", "COLOR", 1, SPAN)
    t1.color = A_RGB
    t2 = new_effect(coll, "T2", "COLOR", 2, SPAN)
    t2.color = B_RGB
    gc = new_effect(coll, "GC", "GAMMA_CROSS", 3, SPAN, input1=t1, input2=t2)
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

def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def build_bench(sc, got):
    """The mixing bench: the 8 authentic cross samples as emissive panels,
    plus the naive lerp midpoint framed in hazard orange for contrast."""
    import bmesh
    import math as m

    def panel(name, rgb, x, z, hot=False):
        mat = bpy.data.materials.new(f"Swatch{name}")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*rgb, 1.0)
        em.inputs["Strength"].default_value = 1.0
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        try:
            bmesh.ops.create_cube(bm, size=1.0,
                                  matrix=__import__("mathutils").Matrix.Diagonal(
                                      (0.56, 0.10, 0.66, 1.0)))
            bm.to_mesh(me)
        finally:
            bm.free()
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        ob.location = (x, 0.0, z)
        sc.collection.objects.link(ob)
        if hot:
            frame_mat = bpy.data.materials.new("HotFrame")
            frame_mat.use_nodes = True
            fb = frame_mat.node_tree.nodes["Principled BSDF"]
            fb.inputs["Base Color"].default_value = (0.80, 0.28, 0.06, 1.0)
            fb.inputs["Roughness"].default_value = 0.5
            fm = bpy.data.meshes.new("Frame")
            bm = bmesh.new()
            try:
                bmesh.ops.create_cube(bm, size=1.0,
                                      matrix=__import__("mathutils").Matrix.Diagonal(
                                          (0.62, 0.06, 0.72, 1.0)))
                bm.to_mesh(fm)
            finally:
                bm.free()
            fm.materials.append(frame_mat)
            fob = bpy.data.objects.new("Frame", fm)
            fob.location = (x, 0.07, z)
            sc.collection.objects.link(fob)

    # two rows: the authentic fade across the top, the naive mid below it,
    # framed — the gamma dip is the visible contrast
    xs = [(-2.17 + 0.62 * i) for i in range(8)]
    for (f, _t), x in zip(SAMPLES, xs):
        panel(f"t{_t}", got[f], x, z=1.85)
    lerp_rgb = tuple(naive(0.5, k) for k in range(3))
    panel("lerp_mid", lerp_rgb, 0.45, z=0.90, hot=True)

    # captions
    cu_mat = bpy.data.materials.new("CaptionGrey")
    cu_mat.use_nodes = True
    cb = cu_mat.node_tree.nodes["Principled BSDF"]
    cb.inputs["Base Color"].default_value = (0.42, 0.44, 0.48, 1.0)
    cb.inputs["Metallic"].default_value = 0.2
    cb.inputs["Roughness"].default_value = 0.6
    sock = cb.inputs.get("Emission Color") or cb.inputs["Emission"]
    sock.default_value = (0.35, 0.37, 0.42, 1.0)
    cb.inputs["Emission Strength"].default_value = 0.6

    def caption(text, x, z):
        cu = bpy.data.curves.new("Caption", 'FONT')
        cu.body = text
        cu.align_x = 'CENTER'
        cu.size = 0.14
        cu.extrude = 0.004
        ob = bpy.data.objects.new("Caption", cu)
        ob.location = (x, -0.09, z)
        ob.rotation_euler = (m.radians(90), 0.0, 0.0)
        ob.data.materials.append(cu_mat)
        sc.collection.objects.link(ob)

    caption("GAMMA_CROSS", 0.0, 2.45)
    caption("t=0", -2.50, 1.40)
    caption("t=1/2", 0.02, 1.40)
    caption("t=7/8", 2.54, 1.40)
    # on the floor in front of the console, facing up like the arc plaques
    cu = bpy.data.curves.new("Caption", 'FONT')
    cu.body = "NAIVE LERP t=1/2"
    cu.align_x = 'CENTER'
    cu.size = 0.14
    cu.extrude = 0.004
    ob = bpy.data.objects.new("Caption", cu)
    ob.location = (0.45, -0.75, 0.01)
    ob.data.materials.append(cu_mat)
    sc.collection.objects.link(ob)


def render_still(sc, got, path, engine):
    scene = sc
    build_bench(scene, got)

    import mathutils, bmesh
    console_me = bpy.data.meshes.new("Console")
    bm2 = bmesh.new()
    try:
        bmesh.ops.create_cube(bm2, size=1.0,
                              matrix=mathutils.Matrix.Diagonal((5.6, 0.9, 0.5, 1.0)))
        bm2.to_mesh(console_me)
    finally:
        bm2.free()
    cmat = bpy.data.materials.new("ConsoleMetal")
    cmat.use_nodes = True
    cc = cmat.node_tree.nodes["Principled BSDF"]
    cc.inputs["Base Color"].default_value = (0.07, 0.08, 0.09, 1.0)
    cc.inputs["Metallic"].default_value = 0.7
    cc.inputs["Roughness"].default_value = 0.5
    console_me.materials.append(cmat)
    console = bpy.data.objects.new("Console", console_me)
    console.location = (0.0, 0.15, 0.25)
    scene.collection.objects.link(console)

    floor_me = bpy.data.meshes.new("Floor")
    import bmesh
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
    light("Key", (-4.0, -5.0, 6.0), 500.0, 4.5, (1.0, 0.96, 0.9), (48, 0, -38))
    light("Fill", (5.0, -4.0, 3.0), 90.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Rim", (0.5, 4.5, 5.0), 300.0, 4.0, (0.6, 0.78, 1.0), (-55, 0, 175))
    light("Wedge", (2.5, 3.5, 4.2), 460.0, 6.0, (1.0, 0.76, 0.5), (-72, 0, 195))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.3, -9.2, 2.5)
    scene.collection.objects.link(cam)
    target = bpy.data.objects.new("Aim", None)
    target.location = (0.15, 0.0, 1.35)
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
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path
    # Standard keeps the swatch colors true (docs/VISUAL-STYLE.md)
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
    sc = bpy.context.scene
    gc = build_cross(sc)
    code = check(sc, gc)
    if code:
        return code

    if args.output:
        # re-sample the authentic cross colors for the bench panels
        setup_render(sc, PXW, PXH)
        tmp = tempfile.mkdtemp(prefix="vse_gamma_still_")
        try:
            got = sample_colors(sc, [f for f, _t in SAMPLES], tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        # the bench is a 3D scene: clear the timeline or the sequencer
        # composites the last cross frame over everything (a full-teal
        # still). Effects first: deleting inputs orphans-and-deletes the
        # effect ("Strip 'GC' not in scene" otherwise)
        coll = strips_coll(sc.sequence_editor)
        for s in reversed(list(coll)):
            coll.remove(s)
        if not render_still(sc, got, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 8
        print(f"rendered still {args.output}")

    print("vse-gamma-cross OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
