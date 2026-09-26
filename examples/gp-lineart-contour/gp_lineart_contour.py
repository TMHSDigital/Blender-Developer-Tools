"""Grease Pencil Line Art contours — a runnable example.

Witnesses the Line Art modifier contract AI-generated NPR code most often
gets wrong across the 4.5 LTS → 5.1 window:

1. Contours come from ``modifiers.new(..., 'LINEART')`` on a GPv3 object,
   not from freestyle or hand-drawn strokes.
2. ``source_type='OBJECT'`` + ``source_object`` is load-bearing — clearing
   the source yields zero evaluated strokes.
3. ``use_contour`` must be on for silhouette edges; with every edge-type
   flag off the evaluator emits nothing.
4. Stroke width: 4.5 exposes both ``thickness`` (legacy px) and ``radius``;
   5.1 removes ``thickness`` (AttributeError) and keeps ``radius`` only.
5. GPv3 datablock address matches grease-pencil-rosette: ``grease_pencils_v3``
   on 4.5, ``grease_pencils`` on 5.x.

The subject is a lighthouse on a rocky islet with its keeper's cottage —
one mesh object, toon-shaded, so the Line Art ink is what turns it into an
inked illustration. The check evaluates the modifier through the depsgraph
(no bake required) from the same camera the still renders from and asserts
stroke/point lower bounds against the known failure modes above.

``--no-contour`` clears ``use_contour`` after the modifier is built and
still asserts it is True. That is the falsifier (``--same-axis`` in
export-preset-axis). The GPv3 address shim and the thickness/radius trap
are untouched.

By default it runs the correctness check only. Pass --output to render:

    blender --background --python gp_lineart_contour.py --
    blender --background --python gp_lineart_contour.py -- --no-contour
    blender --background --python gp_lineart_contour.py -- --output l.png
"""
import bpy, bmesh, sys, os, math, argparse, random

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing
from mathutils import Matrix, Vector

# Gates on the evaluated drawing. Measured 255 strokes / 1393 points on 4.5.11,
# 5.1.2 and 5.2.1. Each gate sits above the count left when any ONE of the four
# edge types is dropped (contour 234 s, crease 171 s / 1099 p, material 1305 p,
# intersection 179 s / 921 p), so every edge type is load-bearing on the count.
STROKE_MIN = 240
POINT_MIN = 1320
RADIUS = 0.021        # ink half-width in world units (portable width path)
THICKNESS_45 = 22       # 4.5-only legacy px width, set before radius

# Lighthouse proportions (world units; the islet stands on the floor at z=0)
TOWER_N = 32            # tower ring segments (fine enough: no facet creases)
TOWER_Z0 = 0.34         # tower foot, on top of the plinth
TOWER_H = 2.05
TOWER_R0 = 0.40         # radius at the foot
TOWER_R1 = 0.27         # radius at the gallery
TOWER_BANDS = 5         # red / white / red / white / red

# Material slots on the single source mesh
RED, WHITE, IRON, GLOW, ROCK, STONE, SLATE, SEA = range(8)
SEA_Z = 0.07            # top of the diorama sea disc

INK = (0.015, 0.014, 0.02, 1.0)


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def gp_data_new(name):
    """Version-gated GPv3 datablock creation (same bridge as grease-pencil-rosette)."""
    if bpy.app.version >= (5, 0, 0):
        return bpy.data.grease_pencils.new(name)
    return bpy.data.grease_pencils_v3.new(name)


def check_gp_version_gate():
    if bpy.app.version >= (5, 0, 0):
        if not hasattr(bpy.data, "grease_pencils"):
            print("ERROR: grease_pencils missing on 5.x", file=sys.stderr)
            return 2
        if hasattr(bpy.data, "grease_pencils_v3"):
            print("ERROR: grease_pencils_v3 should be gone on 5.x", file=sys.stderr)
            return 2
        print("5.x contract: grease_pencils is GPv3; _v3 alias gone")
    else:
        if not hasattr(bpy.data, "grease_pencils_v3"):
            print("ERROR: grease_pencils_v3 missing on 4.5", file=sys.stderr)
            return 2
        legacy = bpy.data.grease_pencils.new("LegacyProbe")
        lframe = legacy.layers.new("L").frames.new(1)
        if hasattr(lframe, "drawing") or not hasattr(lframe, "strokes"):
            print("ERROR: 4.5 grease_pencils is not legacy GPencil", file=sys.stderr)
            return 2
        bpy.data.grease_pencils.remove(legacy)
        print("4.5 contract: grease_pencils is legacy; GPv3 lives at _v3")
    return 0


# --- the source mesh: one object, many named parts via material slots --------

def toon_material(name, color):
    """Flat cel shading: Diffuse -> Shader to RGB -> constant ramp, times the
    base colour, emitted. Three tones (shadow / mid / lit) so the key light
    still shapes the form while the Line Art ink carries the drawing."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    diff.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    to_rgb = nt.nodes.new("ShaderNodeShaderToRGB")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    els = ramp.color_ramp.elements
    els[0].position = 0.0
    els[0].color = (0.30, 0.30, 0.34, 1.0)     # shadow tone, slightly cool
    els[1].position = 0.10
    els[1].color = (0.62, 0.62, 0.64, 1.0)     # mid tone
    lit = els.new(0.34)
    lit.color = (1.0, 1.0, 1.0, 1.0)           # lit tone
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    mul.inputs[6].default_value = color         # A
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Strength"].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(diff.outputs[0], to_rgb.inputs[0])
    nt.links.new(to_rgb.outputs["Color"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], mul.inputs[7])  # B
    nt.links.new(mul.outputs[2], emit.inputs["Color"])
    nt.links.new(emit.outputs[0], out.inputs["Surface"])
    return mat


def glow_material(name, color, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = color
    emit.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(emit.outputs[0], out.inputs["Surface"])
    return mat


def _tag(bm, verts, mat):
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mat


def _cyl(bm, mat, r1, r2, z0, z1, segs, x=0.0, y=0.0, rot=0.0):
    res = bmesh.ops.create_cone(
        bm, cap_ends=True, segments=segs, radius1=r1, radius2=r2,
        depth=z1 - z0,
        matrix=Matrix.Translation((x, y, (z0 + z1) / 2)) @ Matrix.Rotation(rot, 4, "Z"),
    )
    _tag(bm, res["verts"], mat)
    return res["verts"]


def _box(bm, mat, center, size, rot_z=0.0):
    m = (Matrix.Translation(center) @ Matrix.Rotation(rot_z, 4, "Z")
         @ Matrix.Diagonal((size[0], size[1], size[2], 1.0)))
    res = bmesh.ops.create_cube(bm, size=1.0, matrix=m)
    _tag(bm, res["verts"], mat)
    return res["verts"]


def tower_radius(z):
    t = (z - TOWER_Z0) / TOWER_H
    return TOWER_R0 + (TOWER_R1 - TOWER_R0) * t


def _tower(bm):
    """Tapered, banded tower: shared rings, so the only line between bands is
    the material border Line Art reads from the slots."""
    rings = []
    for i in range(TOWER_BANDS + 1):
        z = TOWER_Z0 + TOWER_H * i / TOWER_BANDS
        r = tower_radius(z)
        rings.append([bm.verts.new((r * math.cos(2 * math.pi * k / TOWER_N),
                                    r * math.sin(2 * math.pi * k / TOWER_N), z))
                      for k in range(TOWER_N)])
    for i in range(TOWER_BANDS):
        lo, hi = rings[i], rings[i + 1]
        for k in range(TOWER_N):
            f = bm.faces.new((lo[k], lo[(k + 1) % TOWER_N],
                              hi[(k + 1) % TOWER_N], hi[k]))
            f.material_index = RED if i % 2 == 0 else WHITE
    bm.faces.new(list(reversed(rings[0]))).material_index = WHITE
    bm.faces.new(rings[-1]).material_index = IRON


def _on_tower(az, z, depth):
    """Placement matrix for a fixture set into the tower wall at azimuth az."""
    r = tower_radius(z) - depth * 0.35
    return Vector((r * math.cos(az), r * math.sin(az), z)), az


def _lantern(bm, z_top):
    """Gallery deck, railing, lantern room with mullions, roof and vent ball."""
    deck_z1 = z_top + 0.07
    _cyl(bm, IRON, 0.46, 0.46, z_top, deck_z1, 32)
    # railing: posts + top rail
    rail_r, post_h = 0.43, 0.19
    for k in range(18):
        a = 2 * math.pi * k / 18
        _cyl(bm, IRON, 0.011, 0.011, deck_z1, deck_z1 + post_h, 6,
             rail_r * math.cos(a), rail_r * math.sin(a))
    _cyl(bm, IRON, rail_r + 0.018, rail_r + 0.018, deck_z1 + post_h - 0.02,
         deck_z1 + post_h + 0.005, 32)
    # lantern base, glass, mullions
    base_z1 = deck_z1 + 0.09
    _cyl(bm, RED, 0.26, 0.25, deck_z1, base_z1, 8, rot=math.pi / 8)
    glass_z1 = base_z1 + 0.36
    _cyl(bm, GLOW, 0.215, 0.215, base_z1, glass_z1, 8, rot=math.pi / 8)
    for k in range(8):
        a = 2 * math.pi * k / 8
        r = 0.215 / math.cos(math.pi / 8) * 0.99
        _box(bm, IRON, (r * math.cos(a), r * math.sin(a), (base_z1 + glass_z1) / 2),
             (0.03, 0.03, glass_z1 - base_z1), a)
    # roof: eaves ring, cone, vent ball
    _cyl(bm, IRON, 0.29, 0.29, glass_z1, glass_z1 + 0.035, 8, rot=math.pi / 8)
    roof_z1 = glass_z1 + 0.035 + 0.27
    _cyl(bm, RED, 0.30, 0.02, glass_z1 + 0.035, roof_z1, 8, rot=math.pi / 8)
    res = bmesh.ops.create_uvsphere(
        bm, u_segments=12, v_segments=8, radius=0.055,
        matrix=Matrix.Translation((0.0, 0.0, roof_z1 + 0.03)))
    _tag(bm, res["verts"], IRON)
    _cyl(bm, IRON, 0.008, 0.008, roof_z1 + 0.07, roof_z1 + 0.2, 6)


def _rock(bm, rng, center, scale, rot):
    res = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    for v in res["verts"]:
        v.co *= 1.0 + rng.uniform(-0.16, 0.16)
    m = (Matrix.Translation(center) @ Matrix.Rotation(rot, 4, "Z")
         @ Matrix.Diagonal((scale[0], scale[1], scale[2], 1.0)))
    bmesh.ops.transform(bm, matrix=m, verts=res["verts"])
    _tag(bm, res["verts"], ROCK)


def _wave(bm, cx, cy, r, a0, span, steps=12, width=0.11, lift=0.025):
    """A stylised wave crest: a thin curved bar lying on the sea, tapering
    to points at both ends — the comic shorthand for a wave."""
    rings = []
    for i in range(steps + 1):
        s = i / steps
        a = a0 + span * s
        w = width * max(0.08, math.sin(math.pi * s))
        d = Vector((math.cos(a), math.sin(a), 0.0))
        c = Vector((cx, cy, SEA_Z)) + d * r
        rings.append([bm.verts.new(c - d * w / 2 + Vector((0, 0, -0.01))),
                      bm.verts.new(c + d * w / 2 + Vector((0, 0, -0.01))),
                      bm.verts.new(c + d * w / 2 + Vector((0, 0, lift))),
                      bm.verts.new(c - d * w / 2 + Vector((0, 0, lift)))])
    for i in range(steps):
        a, b = rings[i], rings[i + 1]
        for k in range(4):
            bm.faces.new((a[k], a[(k + 1) % 4], b[(k + 1) % 4], b[k])).material_index = WHITE
    bm.faces.new(list(reversed(rings[0]))).material_index = WHITE
    bm.faces.new(rings[-1]).material_index = WHITE


def _islet(bm):
    rng = random.Random(1907)
    rocks = [
        ((0.05, 0.05, 0.02), (1.05, 0.95, 0.30), 0.2),
        ((-0.95, 0.30, 0.0), (0.95, 0.70, 0.26), 0.9),
        ((0.78, -0.20, 0.0), (0.55, 0.48, 0.30), 0.5),
        ((0.55, 0.55, 0.0), (0.50, 0.45, 0.36), 1.3),
        ((-0.40, -0.72, 0.0), (0.42, 0.35, 0.24), 2.1),
        ((1.18, 0.30, 0.0), (0.30, 0.26, 0.22), 0.4),
        ((-1.55, 0.05, 0.0), (0.34, 0.30, 0.20), 2.6),
        ((0.20, -0.95, 0.0), (0.22, 0.20, 0.14), 1.7),
    ]
    for c, s, r in rocks:
        _rock(bm, rng, c, s, r)
    # diorama sea: a shallow disc the rocks break through, so Line Art's
    # intersection edges ink the waterline around every rock
    _cyl(bm, SEA, 2.05, 2.0, 0.0, SEA_Z, 48)
    for cx, cy, r, a0, span in ((-1.30, -0.70, 0.30, 205, 115),
                                (-0.45, -1.30, 0.34, 225, 110),
                                (0.55, -1.30, 0.28, 250, 110),
                                (1.50, -0.55, 0.26, 280, 100),
                                (1.35, 0.85, 0.24, 300, 100),
                                (-1.45, 1.00, 0.24, 180, 110)):
        _wave(bm, cx, cy, r, math.radians(a0), math.radians(span))
    # stepped stone plinth the tower stands on
    _cyl(bm, STONE, 0.60, 0.58, 0.10, 0.24, 12, rot=math.pi / 12)
    _cyl(bm, STONE, 0.50, 0.46, 0.24, TOWER_Z0 + 0.02, 12, rot=math.pi / 12)


def _cottage(bm):
    """Keeper's cottage behind-left of the tower: walls, pitched roof with
    overhang, chimney, door and two windows."""
    cx, cy, rot = -1.15, 0.30, math.radians(-14)
    w, d, h = 0.95, 0.62, 0.46
    z0 = 0.16
    R = Matrix.Rotation(rot, 4, "Z")
    base = Matrix.Translation((cx, cy, 0.0)) @ R

    def local(p):
        return base @ Vector(p)

    _box(bm, WHITE, local((0, 0, z0 + h / 2)), (w, d, h), rot)
    # pitched roof prism with overhang
    ow, od, rh = w / 2 + 0.07, d / 2 + 0.08, 0.30
    zr = z0 + h
    pts = [(-ow, -od, zr - 0.02), (ow, -od, zr - 0.02), (ow, 0, zr + rh),
           (-ow, 0, zr + rh), (-ow, od, zr - 0.02), (ow, od, zr - 0.02)]
    v = [bm.verts.new(local(p)) for p in pts]
    faces = [(v[0], v[1], v[2], v[3]), (v[3], v[2], v[5], v[4]),
             (v[0], v[3], v[4]), (v[1], v[5], v[2]), (v[0], v[4], v[5], v[1])]
    for f in faces:
        bm.faces.new(f).material_index = SLATE
    # chimney
    _box(bm, STONE, local((0.24, 0.12, zr + 0.26)), (0.11, 0.11, 0.36), rot)
    _box(bm, IRON, local((0.24, 0.12, zr + 0.45)), (0.14, 0.14, 0.04), rot)
    # door + windows on the camera-facing wall (local -y)
    _box(bm, SLATE, local((0.20, -d / 2, z0 + 0.15)), (0.15, 0.04, 0.30), rot)
    for x in (-0.25, -0.02):
        _box(bm, GLOW, local((x, -d / 2, z0 + 0.25)), (0.12, 0.035, 0.12), rot)


def _rowboat(bm):
    """A clinker-style rowboat hauled up on the rocks: an open hull lofted
    through U-shaped sections, a thwart and a painted gunwale strip."""
    L, W, D = 1.0, 0.21, 0.14
    n_sec, n_prof = 9, 9
    yaw = 0.35
    # heeled toward the camera so the open hull and thwart read
    place = (Matrix.Translation((1.22, -0.58, 0.10)) @ Matrix.Rotation(yaw, 4, "Z")
             @ Matrix.Rotation(math.radians(14), 4, "X"))
    secs = []
    for i in range(n_sec):
        t = -1.0 + 2.0 * i / (n_sec - 1)
        half_w = W * max(0.04, (1.0 - t * t) ** 0.6)
        sheer = D * (1.0 + 0.35 * t * t)          # bow and stern rise
        depth = D * (1.0 - 0.55 * t * t)
        ring = []
        for j in range(n_prof):
            a = math.pi * j / (n_prof - 1)
            y = -half_w * math.cos(a)
            z = sheer - (sheer - (D - depth)) * math.sin(a)
            ring.append(bm.verts.new(place @ Vector((t * L / 2, y, z))))
        secs.append(ring)
    for i in range(n_sec - 1):
        for j in range(n_prof - 1):
            f = bm.faces.new((secs[i][j], secs[i + 1][j],
                              secs[i + 1][j + 1], secs[i][j + 1]))
            f.material_index = RED if j in (0, n_prof - 2) else SLATE
    # thwart (seat) across the middle
    c = place @ Vector((0.0, 0.0, D * 0.78))
    _box(bm, STONE, c, (0.08, 2 * W * 0.95, 0.025), yaw)


def build_lighthouse(sc):
    me = bpy.data.meshes.new("Lighthouse")
    bm = bmesh.new()
    try:
        _islet(bm)
        _tower(bm)
        # door and two windows set into the tower on the camera side
        for az, z, size, mat in ((-1.02, TOWER_Z0 + 0.17, (0.08, 0.17, 0.32), SLATE),
                                 (-0.80, TOWER_Z0 + 0.95, (0.06, 0.11, 0.17), GLOW),
                                 (-1.25, TOWER_Z0 + 1.62, (0.06, 0.10, 0.15), GLOW)):
            c, rot = _on_tower(az, z, size[0])
            _box(bm, mat, c, size, rot)
        _lantern(bm, TOWER_Z0 + TOWER_H)
        _cottage(bm)
        _rowboat(bm)
        bm.normal_update()
        bm.to_mesh(me)
    finally:
        bm.free()
    for p in me.polygons:
        p.use_smooth = False
    for name, col in (("Lighthouse.Red", (0.72, 0.07, 0.05, 1.0)),
                      ("Lighthouse.White", (0.93, 0.90, 0.82, 1.0)),
                      ("Lighthouse.Iron", (0.10, 0.12, 0.15, 1.0)),
                      (None, None),
                      ("Lighthouse.Rock", (0.10, 0.15, 0.24, 1.0)),
                      ("Lighthouse.Stone", (0.62, 0.55, 0.44, 1.0)),
                      ("Lighthouse.Slate", (0.05, 0.30, 0.34, 1.0)),
                      ("Lighthouse.Sea", (0.02, 0.14, 0.32, 1.0))):
        if name is None:
            me.materials.append(glow_material("Lighthouse.Lamp", (1.0, 0.62, 0.14, 1.0), 1.0))
        else:
            me.materials.append(toon_material(name, col))
    ob = bpy.data.objects.new("Lighthouse", me)
    sc.collection.objects.link(ob)
    return ob


# --- the Line Art object ------------------------------------------------------

def configure_lineart(mod, source, gp_mat):
    mod.source_type = "OBJECT"
    mod.source_object = source
    mod.use_contour = True
    mod.use_crease = True
    if hasattr(mod, "use_material"):
        mod.use_material = True          # ink between the red and white bands
    if hasattr(mod, "use_intersection"):
        mod.use_intersection = True      # ink where fixtures meet the tower
    mod.crease_threshold = math.radians(130)
    mod.target_layer = "Ink"
    mod.target_material = gp_mat
    # Width: radius is portable; thickness is 4.5-only
    if hasattr(mod, "thickness"):
        mod.thickness = THICKNESS_45
    mod.radius = RADIUS


def build_lineart(sc, source):
    gp = gp_data_new("LineArtGP")
    ob = bpy.data.objects.new("LineArt", gp)
    sc.collection.objects.link(ob)

    layer = gp.layers.new("Ink")
    layer.frames.new(1)

    mat = bpy.data.materials.new("Ink")
    bpy.data.materials.create_gpencil_data(mat)
    gp_set = mat.grease_pencil
    if hasattr(gp_set, "color"):
        gp_set.color = INK
    gp.materials.append(mat)

    mod = ob.modifiers.new("LineArt", "LINEART")
    configure_lineart(mod, source, mat)

    # Ink is flat black: keep scene lights off the GP layer
    if hasattr(layer, "use_lights"):
        layer.use_lights = False
    return ob, mod, gp


def setup_camera(sc):
    """One camera for the check and the still: Line Art is view-dependent, so
    the counts the check gates are the strokes the still draws."""
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (5.78, -10.25, 3.5)
    sc.collection.objects.link(cam)
    sc.camera = cam
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (-0.12, 0.0, 1.52)
    sc.collection.objects.link(aim)
    tr = cam.constraints.new("TRACK_TO")
    tr.target = aim
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    return cam


def eval_stroke_counts(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    eob = ob.evaluated_get(dg)
    layer = eob.data.layers[0]
    frame = layer.frames[0]
    drawing = frame.drawing
    strokes = list(drawing.strokes)
    n_strokes = len(strokes)
    n_points = sum(len(s.points) for s in strokes)
    return n_strokes, n_points


def check_thickness_trap(mod):
    if bpy.app.version >= (5, 0, 0):
        if hasattr(mod, "thickness"):
            print("ERROR: thickness still present on 5.x LINEART", file=sys.stderr)
            return 3
        try:
            _ = mod.thickness
            print("ERROR: thickness read did not raise on 5.x", file=sys.stderr)
            return 3
        except AttributeError:
            pass
        if not hasattr(mod, "radius"):
            print("ERROR: radius missing on 5.x LINEART", file=sys.stderr)
            return 3
        print(f"5.x contract: LINEART.radius={mod.radius} thickness=AttributeError")
    else:
        if not hasattr(mod, "thickness"):
            print("ERROR: thickness missing on 4.5 LINEART", file=sys.stderr)
            return 3
        if not hasattr(mod, "radius"):
            print("ERROR: radius missing on 4.5 LINEART", file=sys.stderr)
            return 3
        print(
            f"4.5 contract: LINEART.thickness={mod.thickness} radius={mod.radius}"
        )
    return 0


def check(sc, source, la_ob, mod):
    code = check_gp_version_gate()
    if code:
        return code
    code = check_thickness_trap(mod)
    if code:
        return code

    if mod.type != "LINEART":
        print(f"ERROR: modifier type {mod.type!r} != 'LINEART'", file=sys.stderr)
        return 4
    if mod.source_type != "OBJECT":
        print(f"ERROR: source_type {mod.source_type!r} != 'OBJECT'", file=sys.stderr)
        return 4
    if mod.source_object != source:
        print("ERROR: source_object round-trip failed", file=sys.stderr)
        return 4
    if not mod.use_contour:
        print("ERROR: use_contour should be True", file=sys.stderr)
        return 4

    # Happy path: contours present
    n_s, n_p = eval_stroke_counts(la_ob)
    if n_s < STROKE_MIN or n_p < POINT_MIN:
        print(
            f"ERROR: evaluated Line Art too thin: strokes={n_s} points={n_p} "
            f"(need >= {STROKE_MIN} strokes, >= {POINT_MIN} points)",
            file=sys.stderr,
        )
        return 5
    print(f"contour_ok strokes={n_s} points={n_p} (gates>={STROKE_MIN},>={POINT_MIN})")

    # Failure mode A: clear source_object → zero strokes
    saved = mod.source_object
    mod.source_object = None
    z_s, z_p = eval_stroke_counts(la_ob)
    mod.source_object = saved
    if z_s != 0 or z_p != 0:
        print(
            f"ERROR: cleared source_object still produced strokes={z_s} points={z_p}",
            file=sys.stderr,
        )
        return 6
    print("nosource_ok strokes=0 points=0")

    # Failure mode B: rebuild modifier with every edge type off → zero strokes
    gp_mat = la_ob.data.materials[0]
    while la_ob.modifiers:
        la_ob.modifiers.remove(la_ob.modifiers[0])
    mod_off = la_ob.modifiers.new("LineArtOff", "LINEART")
    configure_lineart(mod_off, source, gp_mat)
    for flag in ("use_contour", "use_crease", "use_loose", "use_intersection",
                 "use_material", "use_edge_mark"):
        if hasattr(mod_off, flag):
            setattr(mod_off, flag, False)
    z_s, z_p = eval_stroke_counts(la_ob)
    if z_s != 0 or z_p != 0:
        print(
            f"ERROR: every edge type off still produced strokes={z_s} points={z_p}",
            file=sys.stderr,
        )
        return 7
    print("noflags_ok strokes=0 points=0")

    # Restore the working Line Art modifier for the optional still
    while la_ob.modifiers:
        la_ob.modifiers.remove(la_ob.modifiers[0])
    mod_on = la_ob.modifiers.new("LineArt", "LINEART")
    configure_lineart(mod_on, source, gp_mat)
    n_s2, n_p2 = eval_stroke_counts(la_ob)
    if (n_s2, n_p2) != (n_s, n_p):
        print(
            f"ERROR: contours did not recover after restore: "
            f"strokes={n_s2} points={n_p2} (first pass {n_s}/{n_p})",
            file=sys.stderr,
        )
        return 7
    print(
        f"restored_ok strokes={n_s2} points={n_p2} radius={mod_on.radius:.4f}"
    )
    return 0


# --- render staging (not part of the check) -----------------------------------

def build_studio(sc):
    """Default stage floor, wall and world; lighting re-weighted for toon
    shading (see the README's Stage deviation line)."""
    def plane(name, size, loc, rot):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        try:
            bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size)
            bm.to_mesh(me)
        finally:
            bm.free()
        mat = bpy.data.materials.new(name + "M")
        mat.use_nodes = True
        b = mat.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.03, 0.032, 0.037, 1.0)
        b.inputs["Roughness"].default_value = 0.7
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        ob.location = loc
        ob.rotation_euler = rot
        sc.collection.objects.link(ob)
        return ob

    plane("Floor", 30.0, (0, 0, 0), (0, 0, 0))
    plane("Wall", 30.0, (0, 8, 0), (math.radians(90), 0, 0))

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

    light("Key", (-4, -5, 6), 520.0, 5.0, (1.0, 0.96, 0.9), (48, 0, -35))
    light("Fill", (5, -3.5, 2.5), 90.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 50))
    light("Wedge", (1.8, 4.6, 4.2), 420.0, 6.0, (1.0, 0.76, 0.5), (-62, 0, 190))


def render_still(sc, path, engine):
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
    # Standard, not AgX: the toon tones are emitted colours and must land
    # on screen as authored, not desaturated toward pastel
    sc.view_settings.view_transform = "Standard"
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation, before
    # the beauty render so a defective composition ships no artifact. The
    # hero is the source mesh plus the GP ink object it evaluates into.
    stage = [o for o in sc.objects if o.name in {"Floor", "Wall"}]
    hero = [sc.objects["Lighthouse"], sc.objects["LineArt"]]
    fcode = gallery_framing.check_framing(
        sc, sc.camera, hero=hero, elements=hero, stage=stage,
    )
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 8
    return 0


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    build_studio(sc)
    source = build_lighthouse(sc)
    setup_camera(sc)
    la_ob, mod, gp = build_lineart(sc, source)
    return sc, source, la_ob, mod


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument(
        "--engine",
        default="eevee",
        choices=("eevee", "cycles"),
        help="render engine for --output (the toon shading is EEVEE-only)",
    )
    p.add_argument(
        "--no-contour",
        action="store_true",
        help="falsifier: use_contour=False, still assert True",
    )
    args = p.parse_args(argv)

    print(f"binary version: {bpy.app.version} ({bpy.app.version_string})")
    sc, source, la_ob, mod = build_scene()
    if args.no_contour:
        mod.use_contour = False

    code = check(sc, source, la_ob, mod)
    if code:
        return code

    if args.output:
        rcode = render_still(sc, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("gp-lineart-contour OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
