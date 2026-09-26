"""Geometry Nodes Instance-on-Points grid — a runnable example.

Witnesses the geometry-nodes-python construction contract for instancing:
a generative GeometryNodeTree (Mesh Grid → Instance on Points → Realize
Instances → Transform → Set Shade Smooth → Set Material) attached as a
NODES modifier, with no Group Input geometry. The instance is a modeled
DSA-profile keycap read in through an Object Info node, so the grid
becomes the key field of a 3x3 macropad.

The check asserts the closed-form evaluated topology — verts = grid points
× keycap verts, faces = grid points × keycap faces, both derived from the
keycap's construction parameters, not measured off it — proving the
instances were realized, not left as instance references the mesh never
sees. It also asserts that the corner keycap sits at its closed-form grid
coordinate and lift, that Set Material carried the keycap plastic, and that
a second Set Material driven by a position field landed the accent plastic
on exactly one keycap, the front-right "enter" key.

``--one-cell`` builds a 1x1 grid and still asserts 3x3 realized topology,
so eight keycaps are missing and the count gate (exit 4) fails. That is
the falsifier (``--same-axis`` in export-preset-axis).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python gn_instance_grid.py --                 # check only
    blender --background --python gn_instance_grid.py -- --one-cell      # must fail
    blender --background --python gn_instance_grid.py -- --output g.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse

# Shared Layer 1 helpers (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

GRID_X = 3
GRID_Y = 3
PITCH = 1.2                     # key pitch, grid spacing between points
GRID_SIZE = PITCH * (GRID_X - 1)
GRID_POINTS = GRID_X * GRID_Y
GRID_HALF = GRID_SIZE / 2       # Mesh Grid spans [-GRID_HALF, +GRID_HALF]
SWITCH_LIFT = 0.22              # Transform: caps ride on the switch housings

# DSA-profile keycap: a loft of rounded-rectangle rings, bottom to top, then
# a fan down into the spherical-looking dish. (half-width, corner radius, z)
CAP_RINGS = (
    (0.55, 0.10, 0.00),   # skirt foot
    (0.55, 0.10, 0.07),   # vertical skirt
    (0.435, 0.14, 0.54),  # tapered wall
    (0.415, 0.13, 0.60),  # edge roll
    (0.375, 0.11, 0.625), # top rim
    (0.25, 0.08, 0.60),   # dish slope
)
CAP_DISH_Z = 0.565
CAP_TOP = max(z for _w, _r, z in CAP_RINGS)
CORNER_SEGS = 4
RING_VERTS = 4 * (CORNER_SEGS + 1)
# closed form: every ring plus the dish centre; ring-to-ring quads, the dish
# fan and one bottom n-gon
CAP_VERTS = len(CAP_RINGS) * RING_VERTS + 1
CAP_FACES = (len(CAP_RINGS) - 1) * RING_VERTS + RING_VERTS + 1
EXPECT_VERTS = GRID_POINTS * CAP_VERTS
EXPECT_FACES = GRID_POINTS * CAP_FACES
# corner (+x, +y) keycap: centred on its grid point, foot at the switch lift
CORNER_CENTER = (GRID_HALF, GRID_HALF)
CORNER_Z = (SWITCH_LIFT, SWITCH_LIFT + CAP_TOP)
# accent ("enter") keycap: the front-right grid point
ACCENT_CENTER = (GRID_HALF, -GRID_HALF)

MAT_PLASTIC = "Keycap.PBT"
MAT_ACCENT = "Keycap.Accent"


# ---------------------------------------------------------------- modeling

def rounded_ring(bm, cx, cy, hw, hd, r, z, segs=CORNER_SEGS):
    """Rounded rectangle, 4 * (segs + 1) verts, counter-clockwise."""
    verts = []
    corners = ((hw - r, hd - r, 0.0), (-(hw - r), hd - r, 90.0),
               (-(hw - r), -(hd - r), 180.0), (hw - r, -(hd - r), 270.0))
    for ox, oy, a0 in corners:
        for i in range(segs + 1):
            a = math.radians(a0 + 90.0 * i / segs)
            verts.append(bm.verts.new((cx + ox + r * math.cos(a),
                                       cy + oy + r * math.sin(a), z)))
    return verts


def circle_ring(bm, cx, cy, radii, z):
    n = len(radii)
    return [bm.verts.new((cx + radii[i] * math.cos(2 * math.pi * i / n),
                          cy + radii[i] * math.sin(2 * math.pi * i / n), z))
            for i in range(n)]


def bridge(bm, a, b, mat=0):
    n = len(a)
    faces = []
    for i in range(n):
        j = (i + 1) % n
        f = bm.faces.new((a[i], a[j], b[j], b[i]))
        f.material_index = mat
        faces.append(f)
    return faces


def cap_ngon(bm, ring, mat=0):
    f = bm.faces.new(ring)
    f.material_index = mat
    return f


def finish(bm, me, smooth=True):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        f.smooth = smooth
    bm.to_mesh(me)
    me.update()


def build_keycap_mesh():
    """The instance: one DSA keycap, topology fixed by CAP_RINGS/CORNER_SEGS."""
    me = bpy.data.meshes.new("KeycapDSA")
    bm = bmesh.new()
    try:
        rings = [rounded_ring(bm, 0.0, 0.0, w, w, r, z) for w, r, z in CAP_RINGS]
        for a, b in zip(rings, rings[1:]):
            bridge(bm, a, b)
        centre = bm.verts.new((0.0, 0.0, CAP_DISH_Z))
        top = rings[-1]
        for i in range(RING_VERTS):
            bm.faces.new((top[i], top[(i + 1) % RING_VERTS], centre))
        cap_ngon(bm, list(reversed(rings[0])))
        finish(bm, me)
    finally:
        bm.free()
    # the hidden underside must not bend the skirt's smooth normals: the foot
    # ring (the first RING_VERTS verts created) is marked sharp
    for e in me.edges:
        a, b = e.vertices
        if a < RING_VERTS and b < RING_VERTS:
            e.use_edge_sharp = True
    return me


def build_instance_grid_tree(source, plastic=None, accent=None,
                             grid_x=GRID_X, grid_y=GRID_Y):
    tree = bpy.data.node_groups.new("InstanceGrid", 'GeometryNodeTree')
    # generative: no Group Input — the tree owns the geometry
    tree.interface.new_socket(
        name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry',
    )
    go = tree.nodes.new('NodeGroupOutput')

    grid = tree.nodes.new('GeometryNodeMeshGrid')
    grid.inputs["Size X"].default_value = PITCH * (grid_x - 1)
    grid.inputs["Size Y"].default_value = PITCH * (grid_y - 1)
    grid.inputs["Vertices X"].default_value = grid_x
    grid.inputs["Vertices Y"].default_value = grid_y

    # the modeled keycap, in its own local space
    info = tree.nodes.new('GeometryNodeObjectInfo')
    info.transform_space = 'ORIGINAL'
    info.inputs["Object"].default_value = source

    iop = tree.nodes.new('GeometryNodeInstanceOnPoints')
    realize = tree.nodes.new('GeometryNodeRealizeInstances')
    xform = tree.nodes.new('GeometryNodeTransform')
    # caps are built foot-at-z=0; lift them onto the switch housings
    xform.inputs["Translation"].default_value = (0.0, 0.0, SWITCH_LIFT)

    # the keycap's loops are laid out for smooth shading; its foot ring
    # carries sharp edges from the source mesh, which realize preserves
    shade = tree.nodes.new('GeometryNodeSetShadeSmooth')
    shade.inputs["Shade Smooth"].default_value = True

    tree.links.new(grid.outputs["Mesh"], iop.inputs["Points"])
    tree.links.new(info.outputs["Geometry"], iop.inputs["Instance"])
    tree.links.new(iop.outputs["Instances"], realize.inputs["Geometry"])
    tree.links.new(realize.outputs["Geometry"], xform.inputs["Geometry"])
    tree.links.new(xform.outputs["Geometry"], shade.inputs["Geometry"])
    out_socket = shade.outputs["Geometry"]

    if plastic is not None:
        set_mat = tree.nodes.new('GeometryNodeSetMaterial')
        set_mat.inputs["Material"].default_value = plastic
        tree.links.new(out_socket, set_mat.inputs["Geometry"])
        out_socket = set_mat.outputs["Geometry"]

    if accent is not None:
        # Selection field, evaluated per face: face centre in the front-right
        # cell (x > +GRID_HALF - PITCH/2 and y < -GRID_HALF + PITCH/2)
        pos = tree.nodes.new('GeometryNodeInputPosition')
        sep = tree.nodes.new('ShaderNodeSeparateXYZ')
        gx = tree.nodes.new('ShaderNodeMath')
        gx.operation = 'GREATER_THAN'
        gx.inputs[1].default_value = GRID_HALF - PITCH / 2
        ly = tree.nodes.new('ShaderNodeMath')
        ly.operation = 'LESS_THAN'
        ly.inputs[1].default_value = -GRID_HALF + PITCH / 2
        both = tree.nodes.new('ShaderNodeMath')
        both.operation = 'MULTIPLY'
        tree.links.new(pos.outputs["Position"], sep.inputs[0])
        tree.links.new(sep.outputs["X"], gx.inputs[0])
        tree.links.new(sep.outputs["Y"], ly.inputs[0])
        tree.links.new(gx.outputs[0], both.inputs[0])
        tree.links.new(ly.outputs[0], both.inputs[1])
        set_acc = tree.nodes.new('GeometryNodeSetMaterial')
        set_acc.inputs["Material"].default_value = accent
        tree.links.new(out_socket, set_acc.inputs["Geometry"])
        tree.links.new(both.outputs[0], set_acc.inputs["Selection"])
        out_socket = set_acc.outputs["Geometry"]

    tree.links.new(out_socket, go.inputs["Geometry"])
    return tree


def pbr(name, color, rough, metal=0.0, emit=None, strength=0.0, coat=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if coat:
        b.inputs["Coat Weight"].default_value = coat
    if emit is not None:
        b.inputs["Emission Color"].default_value = (*emit, 1.0)
        b.inputs["Emission Strength"].default_value = strength
    return mat


def build(one_cell=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # the modeled instance; never rendered itself, only read by Object Info
    src = bpy.data.objects.new("Macropad.KeycapSource", build_keycap_mesh())
    src.hide_render = True
    bpy.context.collection.objects.link(src)

    # carrier mesh is unused by the generative tree; one vertex is enough
    me = bpy.data.meshes.new("KeyfieldCarrier")
    me.vertices.add(1)
    obj = bpy.data.objects.new("Macropad.Keycaps", me)
    bpy.context.collection.objects.link(obj)

    # warm cream PBT and a saturated orange accent (docs/VISUAL-STYLE.md)
    plastic = pbr(MAT_PLASTIC, (0.80, 0.70, 0.52), 0.55)
    accent = pbr(MAT_ACCENT, (1.0, 0.25, 0.03), 0.5)

    gx = gy = 1 if one_cell else GRID_X
    tree = build_instance_grid_tree(src, plastic=plastic, accent=accent,
                                    grid_x=gx, grid_y=gy)
    mod = obj.modifiers.new("instance_grid", 'NODES')
    mod.node_group = tree
    return obj, src


# ---------------------------------------------------------------- check

def check(obj):
    base = len(obj.data.vertices)
    if base != 1:
        print(f"ERROR: carrier should have 1 vertex, got {base}", file=sys.stderr)
        return 3

    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    em = ev.to_mesh()
    try:
        got_v = len(em.vertices)
        got_f = len(em.polygons)
        mat_names = [m.name if m is not None else None for m in em.materials]
        # corner keycap: every vert inside the (+x, +y) cell
        lim = GRID_HALF - PITCH / 2
        corner = [v.co.copy() for v in em.vertices if v.co.x > lim and v.co.y > lim]
        acc_idx = mat_names.index(MAT_ACCENT) if MAT_ACCENT in mat_names else -1
        acc_faces = [p for p in em.polygons if p.material_index == acc_idx]
        acc_verts = {vi for p in acc_faces for vi in p.vertices}
        acc_xy = ((sum(em.vertices[i].co.x for i in acc_verts) / len(acc_verts),
                   sum(em.vertices[i].co.y for i in acc_verts) / len(acc_verts))
                  if acc_verts else (float("nan"), float("nan")))
    finally:
        ev.to_mesh_clear()

    # the headline claim first: realized topology is grid points x keycap
    if got_v != EXPECT_VERTS or got_f != EXPECT_FACES:
        print(f"ERROR: evaluated topology verts={got_v} faces={got_f} != "
              f"expected verts={EXPECT_VERTS} faces={EXPECT_FACES}",
              file=sys.stderr)
        return 4

    if len(corner) != CAP_VERTS:
        print(f"ERROR: corner cell holds {len(corner)} verts, expected one keycap "
              f"({CAP_VERTS})", file=sys.stderr)
        return 5

    if MAT_PLASTIC not in mat_names or MAT_ACCENT not in mat_names:
        print(f"ERROR: Set Material did not carry {MAT_PLASTIC} and {MAT_ACCENT} "
              f"onto the evaluated mesh (materials={mat_names})", file=sys.stderr)
        return 6

    # bbox of the corner keycap: centred on the grid point, foot at the lift
    cx = (min(c.x for c in corner) + max(c.x for c in corner)) / 2
    cy = (min(c.y for c in corner) + max(c.y for c in corner)) / 2
    z0 = min(c.z for c in corner)
    z1 = max(c.z for c in corner)
    for got, exp, axis in ((cx, CORNER_CENTER[0], 'x'), (cy, CORNER_CENTER[1], 'y'),
                           (z0, CORNER_Z[0], 'z-min'), (z1, CORNER_Z[1], 'z-max')):
        if abs(got - exp) > 1e-3:
            print(f"ERROR: corner keycap {axis}={got:.4f} != {exp:.4f}",
                  file=sys.stderr)
            return 7

    # the position-field selection must pick exactly one whole keycap
    if (len(acc_faces) != CAP_FACES
            or abs(acc_xy[0] - ACCENT_CENTER[0]) > 1e-3
            or abs(acc_xy[1] - ACCENT_CENTER[1]) > 1e-3):
        print(f"ERROR: accent selection covered {len(acc_faces)} faces centred at "
              f"({acc_xy[0]:.3f},{acc_xy[1]:.3f}); expected {CAP_FACES} faces at "
              f"{ACCENT_CENTER}", file=sys.stderr)
        return 9

    print(f"grid={GRID_X}x{GRID_Y} points={GRID_POINTS} cap={CAP_VERTS}v/{CAP_FACES}f "
          f"eval_verts={got_v} eval_faces={got_f} "
          f"corner=({cx:.2f},{cy:.2f},z {z0:.2f}..{z1:.2f}) "
          f"accent={len(acc_faces)}f@({acc_xy[0]:.2f},{acc_xy[1]:.2f}) "
          f"materials={mat_names}")
    return 0


# ---------------------------------------------------------------- render

def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


CASE_H = 0.68          # case top surface
PLATE_Z = 0.30         # recessed plate the switches sit on
CASE_CY = 0.62         # case centre is pushed back to hold the knob strip
CASE_HW, CASE_HD = 2.05, 2.72
STRIP_Y = 2.62         # knob / screen strip behind the key well


def mesh_object(name, me, parent, mats):
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    ob.parent = parent
    bpy.context.scene.collection.objects.link(ob)
    return ob


def build_case(mats, parent):
    """Anodized case with a recessed key well; plate is material slot 1."""
    me = bpy.data.meshes.new("MacropadCase")
    bm = bmesh.new()
    try:
        r = rounded_ring
        foot = r(bm, 0, CASE_CY, CASE_HW - 0.04, CASE_HD - 0.04, 0.30, 0.0)
        wall0 = r(bm, 0, CASE_CY, CASE_HW, CASE_HD, 0.34, 0.05)
        wall1 = r(bm, 0, CASE_CY, CASE_HW, CASE_HD, 0.34, CASE_H - 0.07)
        chamf = r(bm, 0, CASE_CY, CASE_HW - 0.06, CASE_HD - 0.06, 0.28, CASE_H)
        rim = r(bm, 0, 0, 1.86, 1.86, 0.14, CASE_H)
        lip = r(bm, 0, 0, 1.86, 1.86, 0.14, CASE_H - 0.03)
        well = r(bm, 0, 0, 1.86, 1.86, 0.14, PLATE_Z)
        bridge(bm, foot, wall0)
        bridge(bm, wall0, wall1)
        bridge(bm, wall1, chamf)
        bridge(bm, chamf, rim)
        bridge(bm, rim, lip)
        bridge(bm, lip, well, mat=1)
        cap_ngon(bm, well, mat=1)
        cap_ngon(bm, list(reversed(foot)))
        finish(bm, me)
    finally:
        bm.free()
    me.set_sharp_from_angle(angle=math.radians(40))
    return mesh_object("Macropad.Case", me, parent, mats)


def build_switches(mat, parent):
    me = bpy.data.meshes.new("MacropadSwitches")
    bm = bmesh.new()
    try:
        for i in range(GRID_X):
            for j in range(GRID_Y):
                x = -GRID_HALF + i * PITCH
                y = -GRID_HALF + j * PITCH
                a = rounded_ring(bm, x, y, 0.40, 0.40, 0.05, PLATE_Z, 1)
                b = rounded_ring(bm, x, y, 0.37, 0.37, 0.05, PLATE_Z + SWITCH_LIFT, 1)
                bridge(bm, a, b)
                cap_ngon(bm, b)
                cap_ngon(bm, list(reversed(a)))
        finish(bm, me, smooth=False)
    finally:
        bm.free()
    return mesh_object("Macropad.Switches", me, parent, [mat])


def build_knob(brass, collar_mat, mark_mat, parent):
    x, y = 1.15, STRIP_Y
    # collar ring the knob turns in
    cme = bpy.data.meshes.new("MacropadKnobCollar")
    bm = bmesh.new()
    try:
        n = 48
        a = circle_ring(bm, x, y, [0.50] * n, CASE_H)
        b = circle_ring(bm, x, y, [0.50] * n, CASE_H + 0.05)
        c = circle_ring(bm, x, y, [0.45] * n, CASE_H + 0.08)
        bridge(bm, a, b)
        bridge(bm, b, c)
        cap_ngon(bm, c)
        cap_ngon(bm, list(reversed(a)))
        finish(bm, cme)
    finally:
        bm.free()
    cme.set_sharp_from_angle(angle=math.radians(40))
    collar = mesh_object("Macropad.KnobCollar", cme, parent, [collar_mat])

    # knurled body: alternating radii around the barrel, chamfered crown
    kme = bpy.data.meshes.new("MacropadKnob")
    bm = bmesh.new()
    try:
        n = 64
        knurl = [0.40 if i % 2 else 0.37 for i in range(n)]
        z0 = CASE_H + 0.08
        rings = [
            circle_ring(bm, x, y, [0.34] * n, z0),
            circle_ring(bm, x, y, knurl, z0 + 0.04),
            circle_ring(bm, x, y, knurl, z0 + 0.52),
            circle_ring(bm, x, y, [0.37] * n, z0 + 0.58),
            circle_ring(bm, x, y, [0.33] * n, z0 + 0.62),
            circle_ring(bm, x, y, [0.30] * n, z0 + 0.60),
        ]
        for p, q in zip(rings, rings[1:]):
            bridge(bm, p, q)
        cap_ngon(bm, rings[-1])
        cap_ngon(bm, list(reversed(rings[0])))
        finish(bm, kme)
    finally:
        bm.free()
    kme.set_sharp_from_angle(angle=math.radians(30))
    knob = mesh_object("Macropad.Knob", kme, parent, [brass])

    # pointer line inlaid in the crown's dished face
    mme = bpy.data.meshes.new("MacropadKnobMark")
    bm = bmesh.new()
    try:
        zt = z0 + 0.605
        a = rounded_ring(bm, x - 0.09, y + 0.12, 0.035, 0.13, 0.03, zt, 2)
        b = rounded_ring(bm, x - 0.09, y + 0.12, 0.035, 0.13, 0.03, zt + 0.01, 2)
        bridge(bm, a, b)
        cap_ngon(bm, b)
        cap_ngon(bm, list(reversed(a)))
        finish(bm, mme, smooth=False)
    finally:
        bm.free()
    mark = mesh_object("Macropad.KnobMark", mme, parent, [mark_mat])
    return [collar, knob, mark]


def build_screen(glass, bar_mat, parent):
    x, y = -0.55, STRIP_Y
    sme = bpy.data.meshes.new("MacropadScreen")
    bm = bmesh.new()
    try:
        a = rounded_ring(bm, x, y, 0.95, 0.36, 0.06, CASE_H)
        b = rounded_ring(bm, x, y, 0.95, 0.36, 0.06, CASE_H + 0.025)
        c = rounded_ring(bm, x, y, 0.92, 0.33, 0.04, CASE_H + 0.03)
        bridge(bm, a, b)
        bridge(bm, b, c)
        cap_ngon(bm, c)
        cap_ngon(bm, list(reversed(a)))
        finish(bm, sme, smooth=False)
    finally:
        bm.free()
    screen = mesh_object("Macropad.Screen", sme, parent, [glass])

    # level meter on the OLED: eight bars, one per key column pair
    bme = bpy.data.meshes.new("MacropadScreenBars")
    bm = bmesh.new()
    try:
        heights = (0.20, 0.34, 0.46, 0.30, 0.52, 0.40, 0.24, 0.14)
        zt = CASE_H + 0.031
        for i, h in enumerate(heights):
            bx = x - 0.70 + i * 0.20
            by = y - 0.24 + h / 2
            a = rounded_ring(bm, bx, by, 0.065, h / 2, 0.02, zt, 1)
            b = rounded_ring(bm, bx, by, 0.065, h / 2, 0.02, zt + 0.004, 1)
            bridge(bm, a, b)
            cap_ngon(bm, b)
            cap_ngon(bm, list(reversed(a)))
        finish(bm, bme, smooth=False)
    finally:
        bm.free()
    bars = mesh_object("Macropad.ScreenBars", bme, parent, [bar_mat])
    return [screen, bars]


def render_still(obj, src, path, engine):
    import gallery_framing
    import gallery_asset_quality

    scene = bpy.context.scene

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

    # the whole macropad hangs off one empty, turned so the key field reads
    # as a grid in depth
    pad = bpy.data.objects.new("Macropad", None)
    pad.rotation_euler = (0.0, 0.0, math.radians(22))
    pad.location = (0.0, -0.35, 0.0)
    scene.collection.objects.link(pad)
    for ob in (obj, src):
        ob.parent = pad
    # the key field sits on the recessed plate; the hidden source rides inside
    obj.location = (0.0, 0.0, PLATE_Z)
    src.location = (0.0, 0.0, PLATE_Z)

    anod = pbr("Macropad.Anodized", (0.035, 0.11, 0.48), 0.38, metal=0.35, coat=0.3)
    plate = pbr("Macropad.Plate", (0.018, 0.019, 0.024), 0.45, metal=0.5)
    housing = pbr("Macropad.Housing", (0.045, 0.045, 0.05), 0.55)
    brass = pbr("Macropad.Brass", (0.92, 0.60, 0.26), 0.28, metal=1.0)
    collar = pbr("Macropad.Collar", (0.03, 0.03, 0.035), 0.4, metal=0.8)
    mark = pbr("Macropad.Mark", (0.02, 0.02, 0.02), 0.5,
               emit=(1.0, 0.35, 0.06), strength=4.0)
    glass = pbr("Macropad.Glass", (0.006, 0.007, 0.009), 0.12)
    bars = pbr("Macropad.Oled", (0.02, 0.02, 0.02), 0.5,
               emit=(0.15, 0.95, 0.85), strength=3.0)

    case = build_case([anod, plate], pad)
    switches = build_switches(housing, pad)
    knob_parts = build_knob(brass, collar, mark, pad)
    screen_parts = build_screen(glass, bars, pad)
    parts = [case, switches, obj, *knob_parts, *screen_parts]

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (-0.3, -0.2, 0.45)
    scene.collection.objects.link(aim)

    def light(name, loc, energy, size, col):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.size = size
        ld.color = col
        # EEVEE: jittered soft shadows, otherwise the filtered shadow map
        # mottles the smooth keycap tops (no-op attribute on Cycles)
        if hasattr(ld, "use_shadow_jitter"):
            ld.use_shadow_jitter = True
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        scene.collection.objects.link(ob)
        lc = ob.constraints.new('TRACK_TO')
        lc.target = aim
        lc.track_axis = 'TRACK_NEGATIVE_Z'
        lc.up_axis = 'UP_Y'

    # warm shaped key, faint cool fill, cool rim, warm wedge on the back
    # wall (docs/VISUAL-STYLE.md)
    light("Key", (-4.5, -5.0, 7.0), 520.0, 5.0, (1.0, 0.96, 0.9))
    light("Fill", (6.5, -4.0, 2.5), 90.0, 9.0, (0.75, 0.85, 1.0))
    light("Rim", (2.0, 6.5, 4.5), 350.0, 4.0, (0.6, 0.78, 1.0))
    wedge = bpy.data.lights.new("Wedge", 'AREA')
    wedge.energy = 450.0
    wedge.size = 6.0
    wedge.color = (1.0, 0.76, 0.5)
    wob = bpy.data.objects.new("Wedge", wedge)
    wob.location = (2.5, 6.0, 4.5)
    wob.rotation_euler = (math.radians(-68), 0.0, math.radians(190))
    scene.collection.objects.link(wob)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (4.9, -8.7, 6.7)
    scene.collection.objects.link(cam)
    scene.camera = cam
    track = cam.constraints.new('TRACK_TO')
    track.target = aim
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'

    scene.render.engine = 'CYCLES' if engine == 'cycles' else eevee_engine_id()
    if engine == 'cycles':
        scene.cycles.samples = 64
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path
    # Standard, not AgX: AgX washes the cobalt case and the orange accent
    # toward pastel (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'

    # Layer 1 framing gate (exit 10) and asset-quality floors (exit 11) run
    # before the beauty render so a defective composition ships no artifact.
    fcode = gallery_framing.check_framing(
        scene, cam, hero=parts, elements=parts, stage=[floor, wall])
    if fcode:
        return fcode
    aqcode = gallery_asset_quality.check_asset_quality(
        scene, cam, hero=parts + [src], stage=[floor, wall])
    if aqcode:
        return aqcode
    bpy.ops.render.render(write_still=True)
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
    p.add_argument("--one-cell", action="store_true",
                   help="instance a 1x1 grid (must fail)")
    args = p.parse_args(argv)

    obj, src = build(one_cell=args.one_cell)
    code = check(obj)
    if code:
        return code

    if args.output:
        code = render_still(obj, src, os.path.abspath(args.output), args.engine)
        if code:
            return code
        print(f"rendered still {args.output}")

    print("gn-instance-grid OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
