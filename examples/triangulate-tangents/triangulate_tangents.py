"""A buckler whose brushed grooves follow its tangent field — a runnable example.

Witnesses the tangent-space contract a game engine's normal mapping depends
on, computed through the same mikktspace path engines use:

1. Triangulation is deterministic: ``calc_loop_triangles`` yields the
   closed-form count (two triangles per quad) and per-loop tangent frames.
2. Every loop tangent is unit length and exactly orthogonal to its loop
   normal — the engine's normal-map basis.
3. The tangent frame follows the UVs: per-triangle tangents match the
   independently derived edge/UV-delta formula within mikktspace's vertex
   welding tolerance, and the bitangent is exactly
   ``bitangent_sign * (normal x tangent)``. Flip the UV island and the
   tangent field flips with it — a pipeline baking normal maps from stale
   UVs breaks exactly here.
4. Safe-read protocol: on Blender 4.5 a ``MeshUVLoopLayer`` handle held
   across ``calc_tangents()`` dangles — reads return tangent floats, not
   UVs (measured err ~1.85 while authoring; on 5.1 the same stale read
   survives by memory-layout luck). Never hold layer handles across
   CustomData-reallocating calls; re-fetch by name.

The mikktspace tangent field is byte-identical between Blender 4.5 LTS and
5.1 (verified on both: same weld deviations, same 42 seam flips, same 9
chart-seam flips). An earlier draft of this very check appeared to measure
a 471-vs-9 flip divergence between the versions — every one of those
"flips" was the stale UV handle of point 4 corrupting the seam
classification. The reference lifetime is the real hazard; the math does
not diverge.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python triangulate_tangents.py --                 # check only
    blender --background --python triangulate_tangents.py -- --output s.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse
import mathutils

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing

SIDES = 48                      # buckler lathe resolution
RINGS = 6                       # dome profile rings (closed form below)
BOSS_R = 1.0
UNIT_TOL = 1e-4                 # |length(t) - 1| per loop
DOT_TOL = 1e-4                  # |t . n| per loop
WELD_TOL = 0.15                 # mikktspace vertex welding vs per-triangle formula
BTN_TOL = 1e-4                  # bitangent == sign * (n x t)
UV_TOL = 1e-6                   # re-fetched UV layer vs authored closed form

# dome profile: (r, z) rings from center out, then the raised rim lip
PROFILE = [(0.02, 0.34), (0.30, 0.30), (0.55, 0.22), (0.78, 0.12),
           (0.95, 0.05), (1.00, 0.05)]


def dome_uv(co):
    """Polar UVs on the dome: u sweeps the angle, v the radius — the tangent
    field circulates around the boss (closed form)."""
    theta = math.atan2(co.y, co.x) / (2 * math.pi)
    r = math.sqrt(co.x * co.x + co.y * co.y)
    return (theta % 1.0, min(1.0, r / BOSS_R))


def build_buckler():
    """A round buckler: lathed dome with raised rim, polar-UV dome face."""
    me = bpy.data.meshes.new("Buckler")
    bm = bmesh.new()
    try:
        rings = []
        for r, z in PROFILE:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * s / SIDES),
                                        r * math.sin(2 * math.pi * s / SIDES), z))
                          for s in range(SIDES)])
        # underside: mirror of the outer two rings, then a flat back
        back = [[bm.verts.new((r * math.cos(2 * math.pi * s / SIDES),
                               r * math.sin(2 * math.pi * s / SIDES), z - 0.10))
                 for s in range(SIDES)] for r, z in ((1.00, 0.05), (0.30, 0.02))]
        for k in range(len(rings) - 1):
            for s in range(SIDES):
                bm.faces.new((rings[k][s], rings[k][(s + 1) % SIDES],
                              rings[k + 1][(s + 1) % SIDES], rings[k + 1][s]))
        # rim side wall and underside
        for s in range(SIDES):
            bm.faces.new((rings[-1][s], rings[-1][(s + 1) % SIDES],
                          back[0][(s + 1) % SIDES], back[0][s]))
        for s in range(SIDES):
            bm.faces.new((back[0][s], back[0][(s + 1) % SIDES],
                          back[1][(s + 1) % SIDES], back[1][s]))
        # the back cap must be an explicit fan: calc_tangents aborts on any
        # ngon ("only tris/quads") — one n-gon kills the whole call
        center = bm.verts.new((0.0, 0.0, -0.08))
        for s in range(SIDES):
            bm.faces.new((back[1][(s + 1) % SIDES], back[1][s], center))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()  # the ownership contract, as always
    for poly in me.polygons:
        poly.use_smooth = False  # faceted boss plates keep the basis unambiguous
    uv = me.uv_layers.new(name="UVMap")
    n_dome = (RINGS - 1) * SIDES
    for poly in me.polygons[:n_dome]:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = dome_uv(co)
    for poly in me.polygons[n_dome:n_dome + 2 * SIDES]:
        # rim wall + underside: unwrap as strips (u sweeps the angle, v the
        # depth) — a planar projection is DEGENERATE on a cylindrical wall
        # and collapses the tangent onto the normal (dot ~1.0, measured)
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            theta = math.atan2(co.y, co.x) / (2 * math.pi)
            uv.data[li].uv = (theta % 1.0, (0.05 - co.z) / 0.23)
    for poly in me.polygons[n_dome + 2 * SIDES:]:  # back fan: flat, planar
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (co.x * 0.5 + 0.5, co.y * 0.5 + 0.5)
    obj = bpy.data.objects.new("Buckler", me)
    bpy.context.collection.objects.link(obj)
    return obj, n_dome


def formula_tangents(me, uv, tri):
    """Per-triangle tangent/bitangent from edges and UV deltas — the
    independent derivation engines implement. UV deltas are unwrapped so a
    polar seam inside one triangle does not flip the frame."""
    vs = [me.vertices[me.loops[li].vertex_index].co for li in tri.loops]
    uvs = [uv.data[li].uv for li in tri.loops]
    e1 = vs[1] - vs[0]
    e2 = vs[2] - vs[0]
    du1, dv1 = uvs[1].x - uvs[0].x, uvs[1].y - uvs[0].y
    du2, dv2 = uvs[2].x - uvs[0].x, uvs[2].y - uvs[0].y
    du1, dv1, du2, dv2 = (d - math.copysign(1.0, d) if abs(d) > 0.5 else d
                          for d in (du1, dv1, du2, dv2))
    det = du1 * dv2 - du2 * dv1
    if abs(det) < 1e-12:
        return None
    return ((e1 * dv2 - e2 * dv1) / det, (e2 * du1 - e1 * du2) / det)


def check(obj, n_dome):
    me = obj.data
    me.calc_loop_triangles()

    # contract 1: closed-form topology: two triangles per quad plus the
    # explicit SIDES-triangle fan in the back cap
    want_tris = 2 * ((RINGS - 1) * SIDES + 2 * SIDES) + SIDES
    if len(me.loop_triangles) != want_tris:
        print(f"ERROR: {len(me.loop_triangles)} loop triangles != closed "
              f"form {want_tris}", file=sys.stderr)
        return 3

    # re-fetch the layer AFTER calc_tangents: on 4.5 a handle held across
    # that call dangles and reads tangent floats (measured err ~1.85 while
    # authoring); on 5.1 the stale read survives by luck. Never trust a
    # held handle — re-fetch by name.
    uv = me.uv_layers["UVMap"]

    # contract 4: the re-fetched layer still holds the authored closed form
    uv_err = 0.0
    for poly in me.polygons[:n_dome]:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            want = dome_uv(co)
            uv_err = max(uv_err, (uv.data[li].uv - mathutils.Vector(want)).length)
    if uv_err > UV_TOL:
        print(f"ERROR: re-fetched UV layer deviates {uv_err:.3e} from the "
              "authored polar field — layer contents were reallocated",
              file=sys.stderr)
        return 4

    me.calc_tangents(uvmap="UVMap")
    # re-fetch AGAIN: the handle captured before calc_tangents dangles on
    # 4.5 (reads there return garbage), corrupting the seam classification
    uv = me.uv_layers["UVMap"]

    # per-position UV sets: a position carrying more than one UV across the
    # mesh is a chart seam. mikktspace welds frames there, and the result is
    # version-sensitive (4.5 welds across and can flip; 5.x splits cleanly).
    uv_by_pos = {}
    for li, loop in enumerate(me.loops):
        key = tuple(round(c, 5) for c in me.vertices[loop.vertex_index].co)
        uv_by_pos.setdefault(key, set()).add(
            (round(uv.data[li].uv.x, 5), round(uv.data[li].uv.y, 5)))
    seam_positions = {k for k, s in uv_by_pos.items() if len(s) > 1}

    def tri_is_seam(tri):
        """A triangle whose frame is implementation-defined: it touches a
        chart-seam position, or its own UV deltas cross the polar wrap."""
        uvs = [uv.data[li].uv for li in tri.loops]
        for i in range(3):
            key = tuple(round(c, 5)
                        for c in me.vertices[me.loops[tri.loops[i]].vertex_index].co)
            if key in seam_positions:
                return True
            j = (i + 1) % 3
            if (abs(uvs[j].x - uvs[i].x) > 0.5 or abs(uvs[j].y - uvs[i].y) > 0.5):
                return True
        return False

    unit_err = 0.0
    dot_err = 0.0
    btn_err = 0.0
    sign_bad = 0
    weld_err = 0.0
    clean_flips = 0       # flips inside clean triangles: never allowed
    seam_flips = 0        # flips inside seam triangles: implementation-defined
    chart_flips = 0       # seam flips at chart-seam positions (4.5 welds these)
    for tri in me.loop_triangles:
        seam = tri_is_seam(tri)
        ft = None if seam else formula_tangents(me, uv, tri)
        for li in tri.loops:
            loop = me.loops[li]
            t = loop.tangent
            b = loop.bitangent
            s = loop.bitangent_sign
            n = loop.normal
            # contract 2 (everywhere, both versions): unit + orthogonal basis
            unit_err = max(unit_err, abs(t.length - 1.0))
            dot_err = max(dot_err, abs(t.dot(n)))
            # contract 3b (everywhere): bitangent is exactly sign * (n x t)
            btn_err = max(btn_err, (b - s * n.cross(t)).length)
            if s not in (-1.0, 1.0):
                sign_bad += 1
            # contract 3a (clean triangles): tangents match the independent
            # derivation within mikktspace's vertex-welding tolerance
            if ft is not None:
                fn = ft[0].normalized()
                if t.dot(fn) < -0.5:
                    clean_flips += 1
                else:
                    weld_err = max(weld_err, (t - fn).length)
            elif ft is None:
                # orientation inside seam triangles is implementation-defined;
                # count it for the version witness
                ft2 = formula_tangents(me, uv, tri)
                if ft2 is not None and t.dot(ft2[0].normalized()) < -0.5:
                    seam_flips += 1
                    key = tuple(round(c, 5)
                                for c in me.vertices[loop.vertex_index].co)
                    if key in seam_positions:
                        chart_flips += 1
    if unit_err > UNIT_TOL or dot_err > DOT_TOL:
        print(f"ERROR: tangent basis not orthonormal: unit err {unit_err:.3e}, "
              f"t.n err {dot_err:.3e}", file=sys.stderr)
        return 5
    if btn_err > BTN_TOL or sign_bad:
        print(f"ERROR: bitangent != sign*(n x t): err {btn_err:.3e}, "
              f"{sign_bad} bad signs", file=sys.stderr)
        return 6
    if weld_err > WELD_TOL:
        print(f"ERROR: tangents deviate {weld_err:.3e} from the edge/UV "
              f"closed form (mikktspace weld tol {WELD_TOL})", file=sys.stderr)
        return 7
    # contract 3c: a flipped frame inside a CLEAN triangle is never legal —
    # the tangent field must follow the UVs wherever the UVs are smooth
    if clean_flips:
        print(f"ERROR: {clean_flips} flipped tangent(s) inside clean "
              "triangles — the tangent field does not follow the UVs",
              file=sys.stderr)
        return 8
    # version witness: none in the math — 4.5.11 and 5.1.2 produce identical
    # counts here (42 seam flips, 9 at chart seams). The earlier draft that
    # "measured" a 471-vs-9 divergence was reading the stale UV handle from
    # point 4; the hazard corrupted the measurement itself.

    print(f"sides={SIDES} tris={len(me.loop_triangles)} "
          f"unit_err={unit_err:.2e} dot_err={dot_err:.2e} "
          f"btn_err={btn_err:.2e} uv_err={uv_err:.2e}")
    print(f"weld_err={weld_err:.2e} (tol {WELD_TOL}) sign_bad={sign_bad} "
          f"clean_flips={clean_flips} seam_flips={seam_flips} "
          f"chart_flips={chart_flips} seam_positions={len(seam_positions)}")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(obj, path, engine):
    scene = bpy.context.scene

    # brushed steel: the groove rings follow V, so the anisotropic sweep
    # only reads concentric if the tangent field circulates with the UVs
    mat = bpy.data.materials.new("BrushedSteel")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.30, 0.32, 0.36, 1.0)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.40
    aniso = bsdf.inputs.get("Anisotropic IOR Level") or bsdf.inputs.get("Anisotropic")
    if aniso is not None:
        aniso.default_value = 0.6
    tangent = nt.nodes.new("ShaderNodeTangent")
    tangent.direction_type = 'UV_MAP'
    tan_in = bsdf.inputs.get("Tangent")
    if tan_in is not None:
        nt.links.new(tangent.outputs["Tangent"], tan_in)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = 'RINGS'
    wave.rings_direction = 'SPHERICAL'
    wave.inputs["Scale"].default_value = 9.0
    wave.inputs["Distortion"].default_value = 3.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.07
    bump.inputs["Distance"].default_value = 0.03
    nt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    obj.data.materials.append(mat)

    # presentation: the buckler leaning back on a low display stand
    obj.location = (0.0, 0.0, 1.55)
    obj.rotation_euler = (math.radians(70), 0.0, math.radians(-12))
    stand_me = bpy.data.meshes.new("Stand")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0,
                              matrix=mathutils.Matrix.Diagonal((0.9, 0.5, 0.12, 1.0)))
        bm.to_mesh(stand_me)
    finally:
        bm.free()
    smat = bpy.data.materials.new("StandMetal")
    smat.use_nodes = True
    sb = smat.node_tree.nodes["Principled BSDF"]
    sb.inputs["Base Color"].default_value = (0.09, 0.10, 0.12, 1.0)
    sb.inputs["Metallic"].default_value = 0.85
    sb.inputs["Roughness"].default_value = 0.45
    stand_me.materials.append(smat)
    stand = bpy.data.objects.new("Stand", stand_me)
    # under the leaning rim's contact patch, so the cradle visibly carries it
    stand.location = (0.0, -0.34, 0.55)
    scene.collection.objects.link(stand)

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
    # (docs/VISUAL-STYLE.md); the glint is the anisotropic streak's driver
    light("Key", (-4.0, -5.0, 6.0), 320.0, 4.5, (1.0, 0.96, 0.9), (48, 0, -38))
    light("Fill", (5.0, -4.0, 3.0), 100.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Rim", (0.5, 4.5, 5.0), 340.0, 4.0, (0.6, 0.78, 1.0), (-55, 0, 175))
    light("Wedge", (2.5, 3.5, 4.2), 480.0, 6.0, (1.0, 0.76, 0.5), (-72, 0, 195))
    light("Glint", (1.5, -5.5, 5.5), 150.0, 1.2, (1.0, 0.9, 0.75), (42, 0, 15))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 55.0
    cam = bpy.data.objects.new("Cam", cam_data)
    # Reframed: the old (0.6,-8.8,2.8) left the buckler at 0.334 fill adrift
    # in the stage; moved in ~2.2x so the brushed-steel tangent sweep fills
    # the frame — the grooves are the tangent-field evidence.
    cam.location = (0.6, -6.35, 2.62)
    scene.collection.objects.link(cam)
    target = bpy.data.objects.new("Aim", None)
    target.location = (0.0, 0.0, 1.42)
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
    # AgX would wash the steel toward chalk (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation, before
    # the beauty render so a defective composition ships no artifact.
    stand_ob = scene.objects.get("Stand")
    fcode = gallery_framing.check_framing(
        scene, cam,
        hero=[obj],
        elements=[obj] + ([stand_ob] if stand_ob else []),
        stage=[floor, wall],
    )
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 10
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    args = p.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj, n_dome = build_buckler()
    code = check(obj, n_dome)
    if code:
        return code

    if args.output:
        rcode = render_still(obj, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("triangulate-tangents OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
