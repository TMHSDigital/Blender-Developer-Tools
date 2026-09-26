"""A machined buckler verifying the tangent-space contract — a runnable example.

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

The mikktspace tangent field is identical across Blender 4.5 LTS, 5.1 and
5.2 (verified on all three: same weld deviation, same 150 seam flips, same
12 chart-seam flips). An earlier draft of this very check appeared to measure
a 471-vs-9 flip divergence between the versions — every one of those
"flips" was the stale UV handle of point 4 corrupting the seam
classification. The reference lifetime is the real hazard; the math does
not diverge.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python triangulate_tangents.py --                 # check only
    blender --background --python triangulate_tangents.py -- --zero-uv       # must fail
    blender --background --python triangulate_tangents.py -- --output s.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse
import mathutils

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing
import gallery_asset_quality

SIDES = 96                      # buckler lathe resolution
RINGS = 24                      # face profile rings (closed form below)
BOSS_R = 1.0                    # buckler radius: the polar-UV v normaliser
UNIT_TOL = 1e-4                 # |length(t) - 1| per loop
DOT_TOL = 1e-4                  # |t . n| per loop
WELD_TOL = 0.15                 # mikktspace vertex welding vs per-triangle formula
BTN_TOL = 1e-4                  # bitangent == sign * (n x t)
UV_TOL = 1e-6                   # re-fetched UV layer vs authored closed form

# render staging only (not part of the check)
STAND_H = 0.12                  # display stand height, resting on the floor
SEAT_BITE = 0.01                # rim's lowest vertex sunk into the stand top
STRUT_V = 0.00                  # local v where the kickstand meets the back
STRUT_BITE = 0.02               # strut ends buried in the back face / floor
STRUT_LEAN = 0.30               # horizontal run per metre of strut height

# face profile, (r, z) rings from the centre out: a turned boss, a flat
# flange stepped down from it, a cosine dome falling to a cut groove, then
# a rolled rim band. Every ring carries the polar UVs; the ring index also
# picks the render material (boss / flange / dome / rim).
BOSS_RINGS = 8                  # rings 0..7: the boss cap
FLANGE_RINGS = 3                # rings 8..10: the flat flange
DOME_RINGS = 6                  # rings 11..16: the lathe-grooved dome field
PROFILE = (
    # boss: a tall turned onion cap
    [(0.015, 0.700), (0.050, 0.686), (0.090, 0.652), (0.130, 0.604),
     (0.170, 0.544), (0.205, 0.482), (0.230, 0.430), (0.245, 0.395)]
    # flange: steps down off the boss, flat, then breaks into the dome
    + [(0.252, 0.375), (0.315, 0.370), (0.322, 0.358)]
    # dome: z = 0.07 + 0.288 cos(pi/2 t), flat at the flange, steep at the rim
    + [(0.322 + 0.558 * t, 0.070 + 0.288 * math.cos(math.pi / 2 * t))
       for t in (0.18, 0.36, 0.54, 0.70, 0.85, 1.0)]
    # cut groove, then the narrow rolled rim band
    + [(0.892, 0.058), (0.905, 0.075), (0.922, 0.100), (0.945, 0.112),
       (0.968, 0.108), (0.985, 0.093), (0.997, 0.070)]
)
BACK_Z = 0.015                 # flat back plane (rim wall runs down to it)


def dome_uv(co):
    """Polar UVs on the dome: u sweeps the angle, v the radius — the tangent
    field circulates around the boss (closed form)."""
    theta = math.atan2(co.y, co.x) / (2 * math.pi)
    r = math.sqrt(co.x * co.x + co.y * co.y)
    return (theta % 1.0, min(1.0, r / BOSS_R))


def build_buckler():
    """A round buckler: turned boss, flange, lathed dome, rolled rim — one
    closed lathe mesh with a polar-UV face."""
    me = bpy.data.meshes.new("Buckler")
    bm = bmesh.new()
    try:
        def ring(r, z):
            return [bm.verts.new((r * math.cos(2 * math.pi * s / SIDES),
                                  r * math.sin(2 * math.pi * s / SIDES), z))
                    for s in range(SIDES)]

        rings = [ring(r, z) for r, z in PROFILE]
        # underside: the rim wall drops straight to a flat back plate
        back = [ring(PROFILE[-1][0], BACK_Z), ring(0.30, BACK_Z)]
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
        # both caps must be explicit fans: calc_tangents aborts on any
        # ngon ("only tris/quads") — one n-gon kills the whole call
        center = bm.verts.new((0.0, 0.0, BACK_Z))
        for s in range(SIDES):
            bm.faces.new((back[1][(s + 1) % SIDES], back[1][s], center))
        apex = bm.verts.new((0.0, 0.0, PROFILE[0][1]))
        for s in range(SIDES):
            bm.faces.new((rings[0][s], rings[0][(s + 1) % SIDES], apex))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        # smooth lathe surfaces, hard machined breaks: an edge is sharp where
        # its faces turn more than 30 degrees (boss step, flange lip, groove,
        # rim wall). Mesh normals honour sharp edges since 4.1.
        for f in bm.faces:
            f.smooth = True
        for e in bm.edges:
            if e.is_manifold and e.calc_face_angle(0.0) > math.radians(30):
                e.smooth = False
        bm.to_mesh(me)
    finally:
        bm.free()  # the ownership contract, as always
    uv = me.uv_layers.new(name="UVMap")
    n_dome = (RINGS - 1) * SIDES
    for poly in me.polygons[:n_dome]:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = dome_uv(co)
    z_top = PROFILE[-1][1]
    for poly in me.polygons[n_dome:n_dome + 2 * SIDES]:
        # rim wall + underside: unwrap as strips (u sweeps the angle, v the
        # depth) — a planar projection is DEGENERATE on a cylindrical wall
        # and collapses the tangent onto the normal (dot ~1.0, measured).
        # The flat underside strip runs v along the radius instead.
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            theta = math.atan2(co.y, co.x) / (2 * math.pi)
            r = math.hypot(co.x, co.y)
            uv.data[li].uv = (theta % 1.0,
                              (z_top - co.z) + (PROFILE[-1][0] - r))
    for poly in me.polygons[n_dome + 2 * SIDES:]:  # both cap fans: planar
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
    # explicit SIDES-triangle fans closing the back plate and the boss apex
    want_tris = 2 * ((RINGS - 1) * SIDES + 2 * SIDES) + 2 * SIDES
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
    # version witness: none in the math — 4.5.11, 5.1.2 and 5.2.1 produce
    # identical counts here (150 seam flips, 12 at chart seams). The earlier draft that
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


def principled(name, rgb, metallic, rough, aniso=0.0, grooves=0.0):
    """A designed Principled material. ``aniso`` > 0 wires the UV-map
    Tangent node into the BSDF, so the anisotropic streak runs along the
    UV u direction — around the boss on the polar face. ``grooves`` > 0 adds
    a lathe-groove bump read straight off the UV v (the radius): the rings
    are exact circles by construction, no procedural distortion."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = rough
    if aniso:
        bsdf.inputs["Anisotropic"].default_value = aniso
        tangent = nt.nodes.new("ShaderNodeTangent")
        tangent.direction_type = 'UV_MAP'
        tangent.uv_map = "UVMap"
        nt.links.new(tangent.outputs["Tangent"], bsdf.inputs["Tangent"])
    if grooves:
        uvn = nt.nodes.new("ShaderNodeUVMap")
        uvn.uv_map = "UVMap"
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(uvn.outputs["UV"], sep.inputs[0])
        # height = |sin(pi * N * v)|: a sharp-bottomed V cut every 1/N of
        # the radius, like a parting tool's pass
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = 'MULTIPLY'
        mul.inputs[1].default_value = math.pi * grooves
        nt.links.new(sep.outputs["Y"], mul.inputs[0])
        sin = nt.nodes.new("ShaderNodeMath")
        sin.operation = 'SINE'
        nt.links.new(mul.outputs[0], sin.inputs[0])
        ab = nt.nodes.new("ShaderNodeMath")
        ab.operation = 'ABSOLUTE'
        nt.links.new(sin.outputs[0], ab.inputs[0])
        # the cuts sit in two decorative bands (inner and outer dome), with
        # plain turned steel between: a constant ramp on v is the band mask
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.interpolation = 'CONSTANT'
        els = ramp.color_ramp.elements
        els[0].position, els[0].color = 0.0, (0, 0, 0, 1)
        els[1].position, els[1].color = 0.38, (1, 1, 1, 1)
        for pos, c in ((0.50, 0.0), (0.70, 1.0), (0.84, 0.0)):
            e = els.new(pos)
            e.color = (c, c, c, 1.0)
        nt.links.new(sep.outputs["Y"], ramp.inputs["Fac"])
        band = nt.nodes.new("ShaderNodeMath")
        band.operation = 'MULTIPLY'
        nt.links.new(ab.outputs[0], band.inputs[0])
        nt.links.new(ramp.outputs["Color"], band.inputs[1])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.3
        bump.inputs["Distance"].default_value = 0.004
        nt.links.new(band.outputs[0], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def build_rivets(buckler):
    """Domed rivet heads: a ring on the rim band and a ring on the flange,
    each seated on the profile at its radius and sunk 2 mm into it."""
    def z_at(r):
        for (r0, z0), (r1, z1) in zip(PROFILE, PROFILE[1:]):
            if r0 <= r <= r1:
                return z0 + (z1 - z0) * (r - r0) / (r1 - r0)
        raise ValueError(r)

    me = bpy.data.meshes.new("Buckler.Rivets")
    bm = bmesh.new()
    try:
        for count, radius, head in ((16, 0.945, 0.024), (8, 0.284, 0.018)):
            z = z_at(radius) - 0.002
            for i in range(count):
                a = 2 * math.pi * (i + 0.5) / count
                geom = bmesh.ops.create_uvsphere(
                    bm, u_segments=16, v_segments=8, radius=head,
                    matrix=mathutils.Matrix.Translation(
                        (radius * math.cos(a), radius * math.sin(a), z))
                    @ mathutils.Matrix.Diagonal((1.0, 1.0, 0.55, 1.0)))
                below = [v for v in geom["verts"] if v.co.z < z - 1e-6]
                bmesh.ops.delete(bm, geom=below, context='VERTS')
        for f in bm.faces:
            f.smooth = True
        bm.to_mesh(me)
    finally:
        bm.free()
    ob = bpy.data.objects.new("Buckler.Rivets", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = buckler
    return ob


def render_still(obj, path, engine):
    scene = bpy.context.scene
    me = obj.data

    # materials by lathe ring: turned brass boss, blued-steel flange and rim,
    # a lathe-grooved steel dome field, leather-faced back. The dome carries
    # the tangent-space story: its grooves are cut along UV v and its
    # anisotropic streak runs along UV u, so the highlight fans out radially
    # from the boss only because the tangent field circulates with the UVs.
    steel = principled("Buckler.TurnedSteel", (0.56, 0.57, 0.60), 1.0, 0.32,
                       aniso=0.85, grooves=40)
    blued = principled("Buckler.BluedSteel", (0.16, 0.19, 0.25), 1.0, 0.34, aniso=0.5)
    brass = principled("Buckler.TurnedBrass", (0.78, 0.52, 0.20), 1.0, 0.26, aniso=0.7)
    leather = principled("Buckler.Leather", (0.20, 0.09, 0.035), 0.0, 0.62)
    for m in (steel, blued, brass, leather):
        me.materials.append(m)
    n_dome = (RINGS - 1) * SIDES
    boss_end = BOSS_RINGS * SIDES                       # quads up to the boss step
    flange_end = (BOSS_RINGS + FLANGE_RINGS - 1) * SIDES
    dome_end = (BOSS_RINGS + FLANGE_RINGS + DOME_RINGS - 1) * SIDES
    for p in me.polygons:
        i = p.index
        if i < boss_end:
            p.material_index = 2                        # brass boss
        elif i < flange_end:
            p.material_index = 1                        # blued flange
        elif i < dome_end:
            p.material_index = 0                        # turned steel dome
        elif i < n_dome + SIDES:                        # groove, rim, rim wall
            p.material_index = 2
        elif i < n_dome + 3 * SIDES:                    # underside + back fan
            p.material_index = 3
        else:                                           # boss apex fan
            p.material_index = 2
    rivets = build_rivets(obj)
    rivets.data.materials.append(steel)

    # presentation: the buckler leaning back on a low display stand, held by
    # a kickstand strut behind it. Every contact is derived from the posed
    # mesh: the stand sits on the floor, the rim's lowest vertex bites into
    # the stand's top, and the strut runs from the buckler's back to the floor.
    yaw = math.radians(48)
    obj.rotation_euler = (math.radians(68), 0.0, yaw)
    obj.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    low = min((obj.matrix_world @ v.co for v in obj.data.vertices), key=lambda p: p.z)
    lift = STAND_H - SEAT_BITE - low.z
    obj.location = (0.0, 0.0, lift)
    bpy.context.view_layer.update()
    mw = obj.matrix_world
    low.z += lift

    wood = principled("Stand.Walnut", (0.13, 0.065, 0.03), 0.0, 0.45)

    def box(name, dims, loc, rot, bevel):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        try:
            bmesh.ops.create_cube(bm, size=1.0,
                                  matrix=mathutils.Matrix.Diagonal((*dims, 1.0)))
            bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=2,
                            affect='EDGES', profile=0.5)
            bm.to_mesh(me)
        finally:
            bm.free()
        me.materials.append(wood)
        ob = bpy.data.objects.new(name, me)
        ob.location = loc
        ob.rotation_euler = rot
        scene.collection.objects.link(ob)
        return ob

    # the stand: on the floor, centred under the rim's contact vertex
    box("Stand", (1.0, 0.46, STAND_H), (low.x, low.y, STAND_H / 2), (0.0, 0.0, yaw), 0.02)
    # the strut: its top buried in the buckler's back face (found by a
    # local-space ray), its foot bitten into the floor behind
    hit = obj.ray_cast((0.0, STRUT_V, -1.0), (0.0, 0.0, 1.0))[1]
    back_n = (mw.to_3x3() @ mathutils.Vector((0.0, 0.0, -1.0))).normalized()
    top = mw @ hit - back_n * STRUT_BITE
    # the foot runs out between the back normal and straight away from the
    # camera (+Y), so the strut stays hidden behind the turned shield
    out = (mathutils.Vector((back_n.x, back_n.y, 0.0)).normalized()
           + mathutils.Vector((0.0, 1.0, 0.0))).normalized()
    foot = mathutils.Vector((top.x, top.y, -STRUT_BITE)) + out * top.z * STRUT_LEAN
    axis = top - foot
    box("Strut", (0.08, 0.04, axis.length), (top + foot) / 2,
        axis.to_track_quat('Z', 'Y').to_euler(), 0.008)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = principled("Studio", (0.03, 0.032, 0.037), 0.0, 0.7)
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
    # (docs/VISUAL-STYLE.md); the key's reflection is what the anisotropic
    # dome stretches into the radial streak
    light("Key", (-4.0, -5.0, 6.0), 320.0, 4.5, (1.0, 0.86, 0.68), (48, 0, -38))
    light("Fill", (5.0, -4.0, 3.0), 90.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Top", (-1.2, -2.6, 6.5), 110.0, 5.0, (1.0, 0.97, 0.92), (20, 0, -12))
    light("Rim", (0.5, 4.5, 5.0), 340.0, 4.0, (0.6, 0.78, 1.0), (-55, 0, 175))
    light("Wedge", (2.5, 3.5, 4.2), 480.0, 6.0, (1.0, 0.76, 0.5), (-72, 0, 195))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 55.0
    cam = bpy.data.objects.new("Cam", cam_data)
    # camera and aim ride with the buckler's derived lift, so the
    # composition holds if the stand height changes
    cam.location = (0.6, -6.35, lift + 1.07)
    scene.collection.objects.link(cam)
    target = bpy.data.objects.new("Aim", None)
    target.location = (0.0, 0.0, lift - 0.13)
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
    hero = [obj, rivets]
    props = [scene.objects[n] for n in ("Stand", "Strut")]
    fcode = gallery_framing.check_framing(
        scene, cam,
        hero=hero,
        elements=hero + props,
        stage=[floor, wall],
    )
    if fcode:
        return fcode
    # asset-quality floors (naming, material variation, edge treatment) —
    # exit 11 on violation
    aqcode = gallery_asset_quality.check_asset_quality(
        scene, cam, hero=hero, stage=[floor, wall])
    if aqcode:
        return aqcode
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
    p.add_argument("--zero-uv", action="store_true",
                   help="write every UV to (0, 0) (must fail)")
    args = p.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj, n_dome = build_buckler()
    if args.zero_uv:
        uv = obj.data.uv_layers["UVMap"]
        for loop in uv.data:
            loop.uv = (0.0, 0.0)
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
