"""Lightmap UV channel — the second UV layer engines need for baked lighting.

Witnesses the two-channel UV contract a bake pipeline depends on, on an
asset built to be reused (a market cart: bed, axle, two wheels, four posts,
arched canvas canopy — ground-level pivot, identity transforms, named
datablocks, watertight parts):

1. **The flag trap.** `uv_layers.new()` does NOT move the active flags:
   the first layer keeps `active` + `active_render`, so a UV op runs against
   channel 0 unless you move `active` yourself. Worse, the edit-mode UV ops
   CLEAR both flags — they must be re-asserted after the unwrap/pack
   sequence. The check pins: per part, exactly two layers named UVMap +
   UVLight, with `active == UVLight` (edit target) and
   `active_render == UVMap` (render target) at the end.
2. **Channel zero is untouched.** UV0 loops are snapshotted before the
   UVLight unwrap and compared after: max abs diff == 0 (tol 1e-6).
3. **Bounds.** Every UVLight loop sits inside [0, 1] within 1e-5.
4. **Non-overlap, independently computed.** UV1 triangles are binned into a
   spatial hash and tested pairwise with exact strict SAT (epsilon-separated,
   so shared edges/touching don't count) — never trusted from the packer.
5. **Margin.** lightmap_pack MARGIN_DIV semantics measured live: nominal
   margin == MARGIN_DIV * 0.01 UV units; the check requires the measured
   min island-pair distance >= half the nominal margin, printed.
6. **Island census.** Connected components of welded UV verts, counted
   independently, printed per part; loops conserved (no UV data lost).

Authoring hazards pinned while building this (see code comments):
- Holding a `MeshUVLoopLayer` reference across edit-mode UV ops and then
  iterating its `.data` SEGFAULTS Blender 4.5.11 headless
  (EXCEPTION_ACCESS_VIOLATION, repro 5/5); the same read survives on 5.1.2.
  Always re-fetch `mesh.uv_layers[name]` after CustomData-reallocating ops.
- `bpy.ops.uv.lightmap_pack` silently packs NOTHING (exit OK) when the
  active layer has no UVs yet — unwrap first, then pack.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python lightmap_uv_channel.py --                 # check only
    blender --background --python lightmap_uv_channel.py -- --output u.png  # + render
    blender --background --python lightmap_uv_channel.py -- --falsify f.png # overlapping atlas
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing
import gallery_asset_quality

TOL = 1e-6            # UV0 preservation tolerance
BOUNDS_TOL = 1e-5     # UV1 unit-square slack
MARGIN_DIV = 0.2      # packer request; nominal margin = MARGIN_DIV * 0.01
MARGIN_FACTOR = 0.5   # require measured min island distance >= this * nominal
SAT_EPS = 1e-9        # strict-separation epsilon: touching is not overlap
UV_WELD = 1e-6        # uv vert weld for island connectivity
BIN_N = 256           # spatial hash resolution over [0,1]^2

LAYER0 = "UVMap"
LAYER1 = "UVLight"


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


# ---------------------------------------------------------------------------
# Asset construction (bmesh, ground pivot at z=0; cart runs along X)
# ---------------------------------------------------------------------------

def _beveled_box(bm, dims, center, bevel=0.0, segments=2):
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x = v.co.x * dims[0] + center[0]
        v.co.y = v.co.y * dims[1] + center[1]
        v.co.z = v.co.z * dims[2] + center[2]
    if bevel > 0.0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=segments,
                        profile=0.5, affect="EDGES", clamp_overlap=True)


def _box(name, dims, center, bevel=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        _beveled_box(bm, dims, center, bevel)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def _wheel_disc(name, radius, width, center):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=24,
                              radius1=radius, radius2=radius, depth=width)
        # cone axis is Z; the wheel rolls around Y -> rotate verts, applied in data
        for v in bm.verts:
            x, y, z = v.co.x, v.co.y, v.co.z
            v.co = (x + center[0], z + center[1], y + center[2])
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.02, segments=2,
                        profile=0.5, affect="EDGES", clamp_overlap=True)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def _ring(name, r_out, r_in, width, center, segments=24):
    """Flat annulus (iron tire band) spun from a 4-vert profile, watertight."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        hw = width / 2
        prof = [(r_in, -hw), (r_out, -hw), (r_out, hw), (r_in, hw)]
        vs = [bm.verts.new((r, 0.0, z)) for r, z in prof]
        es = [bm.edges.new((vs[i], vs[(i + 1) % 4])) for i in range(4)]
        bmesh.ops.spin(bm, geom=vs + es, cent=(0.0, 0.0, 0.0),
                       axis=(0.0, 0.0, 1.0), dvec=(0.0, 0.0, 0.0),
                       angle=2 * math.pi, steps=segments, use_merge=True)
        for v in bm.verts:
            x, y, z = v.co.x, v.co.y, v.co.z
            v.co = (x + center[0], z + center[1], y + center[2])
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def _bolt_ring(name, count, ring_r, bolt_r, center):
    """count bolt heads on a ring around Y — one mesh, disconnected islands."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for i in range(count):
            a = 2 * math.pi * i / count
            cx, cz = center[0] + ring_r * math.cos(a), center[2] + ring_r * math.sin(a)
            before_v = set(bm.verts)
            bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=6, radius=bolt_r)
            for v in set(bm.verts) - before_v:
                v.co.x += cx
                v.co.y += center[1]
                v.co.z += cz
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def _arc_band(bm, xc, width, radius, thickness, z0, segments):
    """One arched sheet spanning x in [xc, xc+width], solidified with rims."""
    sweep = math.radians(120.0)
    a0 = math.radians(90.0) - sweep / 2
    outer, inner = [], []
    for i in range(segments + 1):
        a = a0 + sweep * i / segments
        ca, sa = math.cos(a), math.sin(a)
        outer.append(bm.verts.new((xc, radius * ca, z0 + radius * sa)))
        inner.append(bm.verts.new((xc, (radius - thickness) * ca,
                                   z0 + (radius - thickness) * sa)))
    def band(ring_o, ring_i):
        for i in range(segments):
            a, b = i, i + 1
            bm.faces.new((ring_o[a], ring_o[b], ring_i[b], ring_i[a]))
    outer_x2 = [bm.verts.new((v.co.x + width, v.co.y, v.co.z)) for v in outer]
    inner_x2 = [bm.verts.new((v.co.x + width, v.co.y, v.co.z)) for v in inner]
    band(outer, inner)               # underside (thickness face)
    band(inner_x2, outer_x2)         # top face
    for i in range(segments):        # the two long rims
        a, b = i, i + 1
        bm.faces.new((outer[a], outer_x2[a], outer_x2[b], outer[b]))
        bm.faces.new((inner[a], inner[b], inner_x2[b], inner_x2[a]))
    bm.faces.new((outer[0], inner[0], inner_x2[0], outer_x2[0]))
    bm.faces.new((outer[-1], outer_x2[-1], inner_x2[-1], inner[-1]))


def _canopy(name, width, radius, thickness, z0, segments=14):
    """Arched canvas sheet: an arc band solidified with a rim, watertight."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        _arc_band(bm, -width / 2, width, radius, thickness, z0, segments)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def _canopy_ribs(name, positions, width, radius, thickness, z0, segments=14):
    """Thin wooden ribs following the canopy arc, one mesh, N islands."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for px in positions:
            _arc_band(bm, px - width / 2, width, radius, thickness, z0, segments)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def _bolts(name, positions, radius):
    """Bolt head spheres at positions — one mesh, disconnected islands."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for px, py, pz in positions:
            before_v = set(bm.verts)
            bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=6, radius=radius)
            for v in set(bm.verts) - before_v:
                v.co.x += px
                v.co.y += py
                v.co.z += pz
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def _spokes(name, count, r0, r1, thick, center):
    """count straight spokes from r0 to r1 in the XZ plane around a Y axle
    through center: one mesh, disconnected watertight boxes."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for i in range(count):
            a = 2 * math.pi * (i + 0.5) / count
            ca, sa = math.cos(a), math.sin(a)
            before_v = set(bm.verts)
            bmesh.ops.create_cube(bm, size=1.0)
            for v in set(bm.verts) - before_v:
                # box along local X from r0 to r1, then rotate about Y
                x = v.co.x * (r1 - r0) + 0.5 * (r0 + r1)
                y = v.co.y * thick * 0.8
                z = v.co.z * thick
                v.co = (center[0] + x * ca - z * sa, center[1] + y,
                        center[2] + x * sa + z * ca)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def _beams(name, segments, w):
    """Square-section beams between point pairs: one mesh, disconnected
    watertight boxes. segments: [(p0, p1), ...]."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for p0, p1 in segments:
            a, b = Vector(p0), Vector(p1)
            axis = (b - a).normalized()
            side = axis.cross(Vector((0.0, 0.0, 1.0)))
            if side.length < 1e-6:
                side = Vector((1.0, 0.0, 0.0))
            side.normalize()
            up = side.cross(axis).normalized()
            h = w / 2
            corners = [side * sx * h + up * sz * h
                       for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            r0 = [bm.verts.new(a + c) for c in corners]
            r1 = [bm.verts.new(b + c) for c in corners]
            bm.faces.new(list(reversed(r0)))
            bm.faces.new(r1)
            for i in range(4):
                j = (i + 1) % 4
                bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def _multi_box(name, specs):
    """Several beveled boxes as one mesh (disconnected islands, each
    watertight). specs: (dims, center, bevel)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for dims, center, bevel in specs:
            before_e = set(bm.edges)
            before_v = set(bm.verts)
            bmesh.ops.create_cube(bm, size=1.0)
            new_edges = list(set(bm.edges) - before_e)
            for v in set(bm.verts) - before_v:
                v.co.x = v.co.x * dims[0] + center[0]
                v.co.y = v.co.y * dims[1] + center[1]
                v.co.z = v.co.z * dims[2] + center[2]
            if bevel > 0.0:
                bmesh.ops.bevel(bm, geom=new_edges, offset=bevel, segments=2,
                                profile=0.5, affect="EDGES", clamp_overlap=True)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def build_cart_meshes():
    """The cart as an assembly of named, watertight parts: real wheel
    assemblies (disc + hub + iron band + bolt ring), plank-grooved bed with
    side rails, corner brackets, and fasteners, and a ribbed canvas canopy."""
    parts = {}
    parts["Bed"] = _box("Cart.Bed", (2.2, 1.2, 0.22), (0.0, 0.0, 0.85), 0.03)
    parts["Bed.Rails"] = _multi_box("Cart.Bed.Rails", [
        ((2.2, 0.06, 0.18), (0.0, 0.57, 1.02), 0.015),
        ((2.2, 0.06, 0.18), (0.0, -0.57, 1.02), 0.015)])
    parts["Bed.Grooves"] = _multi_box("Cart.Bed.Grooves", [
        ((0.035, 1.14, 0.015), (x, 0.0, 0.9575), 0.0)
        for x in (-0.66, -0.22, 0.22, 0.66)])
    parts["Bed.Brackets"] = _multi_box("Cart.Bed.Brackets", [
        ((0.03, 0.13, 0.26), (sx * 1.105, sy * 0.535, 0.85), 0.008)
        for sx in (-1, 1) for sy in (-1, 1)])
    parts["Bed.Bolts"] = _bolts("Cart.Bed.Bolts", [
        (sx * 1.125, sy * 0.535, z) for sx in (-1, 1) for sy in (-1, 1)
        for z in (0.78, 0.92)], 0.018)
    parts["Axle"] = _wheel_disc("Cart.Axle", 0.05, 1.56, (0.55, 0.0, 0.5))
    parts["Axle.Caps"] = _multi_box("Cart.Axle.Caps", [
        ((0.14, 0.05, 0.14), (0.55, sy * 0.80, 0.5), 0.02) for sy in (-1, 1)])
    for tag, sy in (("L", 1.0), ("R", -1.0)):
        y = sy * 0.68
        # spoked wheel: a wooden felloe ring inside the iron tyre, eight
        # spokes, and the hub; the Disc part is the felloe (was a solid disc)
        parts[f"Wheel.{tag}.Disc"] = _ring(
            f"Cart.Wheel.{tag}.Disc", 0.438, 0.37, 0.09, (0.55, y, 0.45), 32)
        parts[f"Wheel.{tag}.Spokes"] = _spokes(
            f"Cart.Wheel.{tag}.Spokes", 8, 0.12, 0.385, 0.045, (0.55, y, 0.45))
        parts[f"Wheel.{tag}.Hub"] = _wheel_disc(
            f"Cart.Wheel.{tag}.Hub", 0.14, 0.16, (0.55, y, 0.45))
        parts[f"Wheel.{tag}.Band"] = _ring(
            f"Cart.Wheel.{tag}.Band", 0.47, 0.435, 0.10, (0.55, y, 0.45))
        parts[f"Wheel.{tag}.Bolts"] = _bolt_ring(
            f"Cart.Wheel.{tag}.Bolts", 6, 0.09, 0.02, (0.55, y + sy * 0.085, 0.45))
    # Each post runs from inside the bed up into the canopy's underside at
    # its own station, read off the canopy arc. A fixed 1.35 m post stopped
    # 0.33 m short of the arc, so the canopy floated over four sticks.
    # The top is sheared to follow the arc, so the bite is the same across
    # the post's width rather than deep on one side and open on the other.
    canopy_z0, canopy_r, canopy_t, post_bite = 1.9, 0.85, 0.04, 0.012
    post_z0 = 0.875
    r_in = canopy_r - canopy_t
    for tag, (px, py) in (("FL", (0.95, 0.48)), ("FR", (0.95, -0.48)),
                          ("RL", (-0.95, 0.48)), ("RR", (-0.95, -0.48))):
        top = canopy_z0 + math.sqrt(r_in * r_in - py * py) + post_bite
        me = _box(f"Cart.Post.{tag}", (0.09, 0.09, top - post_z0),
                  (px, py, 0.5 * (post_z0 + top)), 0.015)
        for v in me.vertices:
            if v.co.z > top - 0.05:
                arc = canopy_z0 + math.sqrt(r_in * r_in - v.co.y * v.co.y) + post_bite
                v.co.z += arc - top
        me.update()
        parts[f"Post.{tag}"] = me
    # draw shafts off the open (-X) end, a crossbar, and a prop leg the
    # cart rests on when unhitched: without them a two-wheeled cart tips
    parts["Shafts"] = _beams("Cart.Shafts", [
        ((-0.95, 0.40, 0.80), (-2.35, 0.36, 0.52)),
        ((-0.95, -0.40, 0.80), (-2.35, -0.36, 0.52)),
        ((-1.90, 0.40, 0.61), (-1.90, -0.40, 0.61)),
        ((-1.05, 0.0, 0.76), (-1.05, 0.0, 0.0)),
    ], 0.07)
    parts["Canopy"] = _canopy("Cart.Canopy", 2.3, canopy_r, canopy_t, canopy_z0)
    parts["Canopy.Ribs"] = _canopy_ribs("Cart.Canopy.Ribs", (-0.75, 0.0, 0.75),
                                        0.07, 0.875, 0.035, 1.9)
    return parts


# ---------------------------------------------------------------------------
# UV authoring
# ---------------------------------------------------------------------------

def write_uv0_box_projection(me):
    """Channel 0: deterministic dominant-axis box projection per face.
    Deliberately un-normalized (world-scale UVs) — this is the texture
    channel; only UV1 is asserted inside [0,1]."""
    layer = me.uv_layers[LAYER0]
    for poly in me.polygons:
        n = poly.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            layer.data[li].uv = ((co.y, co.z) if ax == 0
                                 else (co.x, co.z) if ax == 1 else (co.x, co.y))


def snapshot(layer):
    return [tuple(d.uv) for d in layer.data]


def author_uv1(ob, clobber=False):
    """Channel 1: smart_project then lightmap_pack into the ACTIVE layer.

    clobber=False: the correct pipeline — active moved to UVLight first, so
    channel 0 survives. clobber=True: the classic trap — active left on
    UVMap, so the unwrap+pack lands on channel 0 and destroys it.
    """
    me = ob.data
    if not clobber:
        for layer in me.uv_layers:
            layer.active = (layer.name == LAYER1)
            layer.active_render = (layer.name == LAYER0)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.1519, island_margin=0.0,
                             area_weight=False, correct_aspect=True,
                             scale_to_bounds=False)
    bpy.ops.uv.lightmap_pack(PREF_CONTEXT="ALL_FACES", PREF_PACK_IN_ONE=True,
                             PREF_NEW_UVLAYER=False, PREF_MARGIN_DIV=MARGIN_DIV)
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.select_set(False)
    # HAZARD (pinned while authoring): the ops above CLEAR layer.active and
    # layer.active_render — re-assert them or downstream bakes/renders pick
    # whatever Blender falls back to. And never read a held layer handle
    # here: iterating a stale MeshUVLoopLayer.data segfaults 4.5.11.
    if not clobber:
        for layer in me.uv_layers:
            layer.active = (layer.name == LAYER1)
            layer.active_render = (layer.name == LAYER0)


# ---------------------------------------------------------------------------
# Independent UV1 geometry analysis (never trusted from the packer)
# ---------------------------------------------------------------------------

def uv_tris(me, layer_name):
    """UV1 triangles per face (fan), plus a weld map for island connectivity."""
    layer = me.uv_layers[layer_name]
    tris = []
    for poly in me.polygons:
        pts = [tuple(layer.data[li].uv) for li in poly.loop_indices]
        for i in range(1, len(pts) - 1):
            tris.append((pts[0], pts[i], pts[i + 1]))
    return tris


def islands(me, layer_name):
    """Connected components of UV verts welded at UV_WELD precision."""
    layer = me.uv_layers[layer_name]
    parent = {}

    def find(k):
        parent.setdefault(k, k)
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def key(uv):
        return (round(uv[0] / UV_WELD), round(uv[1] / UV_WELD))

    for poly in me.polygons:
        ks = [find(key(tuple(layer.data[li].uv))) for li in poly.loop_indices]
        for k in ks[1:]:
            parent[find(k)] = ks[0]
    comps = {}
    for poly in me.polygons:
        for li in poly.loop_indices:
            comps.setdefault(find(key(tuple(layer.data[li].uv))), len(comps))
    return len(comps)


def _tri_overlap(t1, t2):
    """Strict 2D SAT: True only for area-positive overlap (SAT_EPS-separated,
    so shared edges and touching corners do not count)."""
    for tri in (t1, t2):
        for i in range(3):
            x1, y1 = tri[i]
            x2, y2 = tri[(i + 1) % 3]
            nx, ny = -(y2 - y1), (x2 - x1)
            nlen = math.hypot(nx, ny)
            if nlen < 1e-12:
                continue
            nx, ny = nx / nlen, ny / nlen
            p1 = [nx * p[0] + ny * p[1] for p in t1]
            p2 = [nx * p[0] + ny * p[1] for p in t2]
            if min(max(p1), max(p2)) - max(min(p1), min(p2)) < SAT_EPS:
                return False
    return True


def overlap_report(tris):
    """(overlapping pair count, worst measured overlap depth) via binned SAT."""
    bins = {}
    def bounds(t):
        return (min(p[0] for p in t), min(p[1] for p in t),
                max(p[0] for p in t), max(p[1] for p in t))
    for i, t in enumerate(tris):
        x0, y0, x1, y1 = bounds(t)
        for bx in range(max(0, int(x0 * BIN_N)), min(BIN_N - 1, int(x1 * BIN_N)) + 1):
            for by in range(max(0, int(y0 * BIN_N)), min(BIN_N - 1, int(y1 * BIN_N)) + 1):
                bins.setdefault((bx, by), []).append(i)
    pairs = set()
    hits = 0
    worst = 0.0
    for members in bins.values():
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                i, j = members[a], members[b]
                if (i, j) in pairs:
                    continue
                pairs.add((i, j))
                if _tri_overlap(tris[i], tris[j]):
                    hits += 1
    return hits


def min_island_distance(me, layer_name):
    """Min distance between distinct islands' UV edges (exact seg-seg)."""
    layer = me.uv_layers[layer_name]
    parent = {}

    def find(k):
        parent.setdefault(k, k)
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def key(uv):
        return (round(uv[0] / UV_WELD), round(uv[1] / UV_WELD))

    for poly in me.polygons:
        ks = [find(key(tuple(layer.data[li].uv))) for li in poly.loop_indices]
        for k in ks[1:]:
            parent[find(k)] = ks[0]
    edges = {}  # island root -> list of segments
    for poly in me.polygons:
        pts = [tuple(layer.data[li].uv) for li in poly.loop_indices]
        root = find(key(pts[0]))
        for i in range(len(pts)):
            edges.setdefault(root, []).append((pts[i], pts[(i + 1) % len(pts)]))

    def seg_dist(s1, s2):
        def pt_seg(p, s):
            (x, y), ((ax, ay), (bx, by)) = p, s
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            if L2 < 1e-18:
                return math.hypot(x - ax, y - ay)
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
            return math.hypot(x - (ax + t * dx), y - (ay + t * dy))
        if _seg_intersect(s1, s2):
            return 0.0
        return min(pt_seg(s1[0], s2), pt_seg(s1[1], s2),
                   pt_seg(s2[0], s1), pt_seg(s2[1], s1))

    def _seg_intersect(s1, s2):
        (ax, ay), (bx, by) = s1
        (cx, cy), (dx, dy) = s2
        def cross(ox, oy, px, py, qx, qy):
            return (px - ox) * (qy - oy) - (py - oy) * (qx - ox)
        d1 = cross(cx, cy, dx, dy, ax, ay)
        d2 = cross(cx, cy, dx, dy, bx, by)
        d3 = cross(ax, ay, bx, by, cx, cy)
        d4 = cross(ax, ay, bx, by, dx, dy)
        return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))

    roots = sorted(edges)
    best = float("inf")
    for i in range(len(roots)):
        for j in range(i + 1, len(roots)):
            for s1 in edges[roots[i]]:
                for s2 in edges[roots[j]]:
                    d = seg_dist(s1, s2)
                    if d < best:
                        best = d
    return best


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------

def check(overlap=False):
    meshes = build_cart_meshes()
    fails = []

    def fail(code, msg):
        print(f"ERROR ({code}): {msg}", file=sys.stderr)
        fails.append(code)

    # --- 0. positive control for the overlap detector -----------------------
    # "0 overlapping pairs" is only evidence if the detector can find one. A
    # blinded detector reports zero and the whole check passes: widening
    # SAT_EPS to 1e9 makes every axis test read as separated, and this example
    # still exited 0 before this control existed. Prove sensitivity and
    # strictness on hand-built triangles before trusting the scan.
    _overlapping = (((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)),
                    ((0.2, 0.2), (1.2, 0.2), (0.2, 1.2)))
    _disjoint = (((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)),
                 ((5.0, 5.0), (6.0, 5.0), (5.0, 6.0)))
    _touching = (((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)),
                 ((1.0, 0.0), (2.0, 0.0), (1.0, 1.0)))
    ctl = (_tri_overlap(*_overlapping), _tri_overlap(*_disjoint),
           _tri_overlap(*_touching))
    print(f"sat_control overlapping={ctl[0]} disjoint={ctl[1]} touching={ctl[2]} "
          f"(want True/False/False)")
    if ctl != (True, False, False):
        fail(7, f"SAT self-test {ctl} != (True, False, False) — the overlap "
                f"detector cannot detect, so a zero-overlap result proves "
                f"nothing")
        return fails[0]

    nominal_margin = MARGIN_DIV * 0.01
    total_islands = 0
    for suffix, me in meshes.items():
        l0 = me.uv_layers.new(name=LAYER0)
        me.uv_layers.new(name=LAYER1)
        write_uv0_box_projection(me)
        uv0_before = snapshot(me.uv_layers[LAYER0])

        ob = bpy.data.objects.new(me.name, me)
        bpy.context.collection.objects.link(ob)
        author_uv1(ob)
        if overlap and suffix == "Bed":
            drag_second_island(me)  # falsifier: the SAT scan must report it

        # re-fetch by name after CustomData-reallocating ops (see header)
        layers = me.uv_layers
        names = [l.name for l in layers]
        if names != [LAYER0, LAYER1]:
            fail(3, f"{suffix}: layers {names} != {[LAYER0, LAYER1]}")
        act = layers[LAYER1].active
        rnd = layers[LAYER0].active_render
        if not act or not rnd:
            fail(4, f"{suffix}: flags wrong after re-assert — "
                    f"{LAYER1}.active={act}, {LAYER0}.active_render={rnd} "
                    f"(edit-mode UV ops clear both; re-assert after the sequence)")

        uv0_after = snapshot(layers[LAYER0])
        drift = max((max(abs(a - b) for a, b in zip(u0, u1))
                     for u0, u1 in zip(uv0_before, uv0_after)), default=0.0)
        if len(uv0_before) != len(uv0_after) or drift > TOL:
            fail(5, f"{suffix}: channel 0 touched by the UV1 unwrap "
                    f"(loops {len(uv0_before)}->{len(uv0_after)}, drift {drift:.3e})")

        tris = uv_tris(me, LAYER1)
        out = [uv for t in tris for uv in t
               if not (-BOUNDS_TOL <= uv[0] <= 1 + BOUNDS_TOL
                       and -BOUNDS_TOL <= uv[1] <= 1 + BOUNDS_TOL)]
        if out:
            fail(6, f"{suffix}: {len(out)} UV1 loops outside [0,1], "
                    f"worst {out[0]}")

        hits = overlap_report(tris)
        if hits:
            fail(7, f"{suffix}: {hits} overlapping UV1 triangle pairs "
                    f"(independent SAT scan, not the packer's word)")

        n_islands = islands(me, LAYER1)
        total_islands += n_islands
        dist = min_island_distance(me, LAYER1)
        need = MARGIN_FACTOR * nominal_margin
        if dist < need:
            fail(8, f"{suffix}: min island distance {dist:.5f} < {need:.5f} "
                    f"(half of nominal margin {nominal_margin})")
        print(f"part {suffix}: loops={len(me.loops)} tris={len(tris)} "
              f"islands={n_islands} uv0_drift={drift:.1e} "
              f"overlap={hits} min_island_dist={dist:.5f} "
              f"flags ok={act and rnd}")

        # every part watertight
        bm = bmesh.new()
        try:
            bm.from_mesh(me)
            n_boundary = sum(1 for e in bm.edges if len(e.link_faces) != 2)
        finally:
            bm.free()
        if n_boundary:
            fail(9, f"{suffix}: {n_boundary} non-two-face edges — not watertight")

    if fails:
        return fails[0]
    print(f"lightmap-uv-channel OK parts={len(meshes)} islands={total_islands} "
          f"margin>={MARGIN_FACTOR}*{nominal_margin} uv0_drift=0 overlap=0")
    return 0


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def make_material(name, rgb, rough=0.6, metallic=0.0, emit=None, estr=0.0,
                  grain=None, bump=0.0):
    """grain=(stretch_xyz, scale, amount): noise over Object coordinates,
    squeezed along the axes the grain should run, multiplied into the base
    colour and roughness. bump>0 adds a fine noise bump (canvas weave, iron
    pitting). Render only - no check reads a material."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    if emit is not None:
        sock = b.inputs.get("Emission Color") or b.inputs["Emission"]
        sock.default_value = (*emit, 1.0)
        b.inputs["Emission Strength"].default_value = estr
    if grain or bump:
        coord = nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    if grain:
        stretch, scale, amount = grain
        mapping = nt.nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = stretch
        nt.links.new(coord, mapping.inputs["Vector"])
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = scale
        noise.inputs["Detail"].default_value = 7.0
        nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.32
        ramp.color_ramp.elements[1].position = 0.70
        ramp.color_ramp.elements[0].color = tuple(c * (1 - amount) for c in rgb) + (1.0,)
        ramp.color_ramp.elements[1].color = tuple(min(1.0, c * (1 + amount)) for c in rgb) + (1.0,)
        nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
        rmap = nt.nodes.new("ShaderNodeMapRange")
        rmap.inputs["To Min"].default_value = rough + 0.12
        rmap.inputs["To Max"].default_value = rough - 0.08
        nt.links.new(noise.outputs["Fac"], rmap.inputs["Value"])
        nt.links.new(rmap.outputs["Result"], b.inputs["Roughness"])
    if bump:
        fine = nt.nodes.new("ShaderNodeTexNoise")
        fine.inputs["Scale"].default_value = 180.0
        fine.inputs["Detail"].default_value = 4.0
        nt.links.new(coord, fine.inputs["Vector"])
        bn = nt.nodes.new("ShaderNodeBump")
        bn.inputs["Strength"].default_value = bump
        bn.inputs["Distance"].default_value = 0.003
        nt.links.new(fine.outputs["Fac"], bn.inputs["Height"])
        nt.links.new(bn.outputs["Normal"], b.inputs["Normal"])
    return mat


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

    light("Key", (-3.5, -4.5, 5.5), 430.0, 4.5, (1.0, 0.96, 0.9), (48, 0, -35))
    light("Fill", (5.0, -3.5, 2.5), 120.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 50))
    light("Rim", (1.5, 4.5, 3.5), 300.0, 3.0, (0.6, 0.78, 1.0), (-55, 0, 170))
    light("Wedge", (2.5, 5.5, 4.0), 420.0, 6.0, (1.0, 0.72, 0.42), (-68, 0, 190))
    return floor, wall


def drag_second_island(me):
    """Translate the mesh's second-largest UV1 face onto the largest one's
    anchor, shape intact. Shared by --overlap-islands (check path, exit 7)
    and --falsify (render path). Returns the dragged polygon index."""
    layer = me.uv_layers[LAYER1]
    polys = sorted(me.polygons, key=lambda p: p.area, reverse=True)
    big, second = polys[0], polys[1]
    anchor = tuple(layer.data[big.loop_indices[0]].uv)
    first = second.loop_indices[0]
    du = (anchor[0] - layer.data[first].uv[0],
          anchor[1] - layer.data[first].uv[1])
    for li in second.loop_indices:
        u, v = layer.data[li].uv
        layer.data[li].uv = (u + du[0], v + du[1])
    return second.index


def render_still(path, engine, falsify=False):
    """The cart beside its UV1 atlas board — island polygons built from the
    LIVE packed UVs, so a change in the atlas moves the board. Falsified:
    one island dragged onto another, overlap marked in emissive red."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene

    # bed planks run along X: grain squeezed in X streaks along the planks
    wood = make_material("Wood", (0.40, 0.22, 0.095), rough=0.55,
                         grain=((0.06, 1.0, 1.0), 26.0, 0.35))
    darkwood = make_material("DarkWood", (0.19, 0.11, 0.05), rough=0.66,
                             grain=((1.0, 1.0, 0.08), 30.0, 0.30))
    iron = make_material("Iron", (0.20, 0.20, 0.22), rough=0.38, metallic=0.9,
                         grain=((1.0, 1.0, 1.0), 14.0, 0.45), bump=0.25)
    canvas = make_material("Canvas", (0.70, 0.60, 0.42), rough=0.92,
                           grain=((1.0, 0.4, 1.0), 5.0, 0.18), bump=0.45)
    groovemat = make_material("Groove", (0.05, 0.04, 0.03), rough=0.9)

    mat_by_part = {
        "Bed": wood, "Bed.Rails": wood, "Bed.Grooves": groovemat,
        "Bed.Brackets": iron, "Bed.Bolts": iron,
        "Axle": iron, "Axle.Caps": iron,
        "Canopy": canvas, "Canopy.Ribs": darkwood, "Shafts": darkwood,
    }
    for tag in ("L", "R"):
        mat_by_part[f"Wheel.{tag}.Disc"] = darkwood
        mat_by_part[f"Wheel.{tag}.Spokes"] = darkwood
        mat_by_part[f"Wheel.{tag}.Hub"] = darkwood
        mat_by_part[f"Wheel.{tag}.Band"] = iron
        mat_by_part[f"Wheel.{tag}.Bolts"] = iron
    for tag in ("FL", "FR", "RL", "RR"):
        mat_by_part[f"Post.{tag}"] = darkwood

    parts_obs = []
    meshes = build_cart_meshes()
    for suffix, me in meshes.items():
        me.materials.append(mat_by_part[suffix])
        me.uv_layers.new(name=LAYER0)
        me.uv_layers.new(name=LAYER1)
        write_uv0_box_projection(me)
        ob = bpy.data.objects.new(me.name, me)
        sc.collection.objects.link(ob)
        author_uv1(ob, clobber=False)
        parts_obs.append(ob)

    # falsify: translate the Bed's SECOND-LARGEST UV1 island, shape intact,
    # onto the largest island's anchor — a big visible overlap, marked
    # emissive red on the board (tiny-strip overlaps would not read)
    dragged = set()
    if falsify:
        dragged.add(drag_second_island(meshes["Bed"]))

    # atlas board: the Bed's live UV1 as flat island polygons mapped onto the
    # board face — a change in the packed atlas moves the board geometry
    # The display: a slate atlas face in a walnut frame, standing on a walnut
    # plinth that carries a brass nameplate, with a faint quarter grid under
    # the islands so the [0,1] square the check bounds is visible.
    bx, by, bz = 2.05, 0.55, 1.30
    board_mat = make_material("Board", (0.030, 0.032, 0.036), rough=0.62,
                              grain=((1.0, 1.0, 1.0), 9.0, 0.25))
    board = _box("Atlas.Board", (0.08, 2.2, 2.0), (0.0, 0.0, 0.0), 0.02)
    board.materials.append(board_mat)
    board_ob = bpy.data.objects.new("Atlas.Board", board)
    board_ob.location = (bx, by, bz)
    sc.collection.objects.link(board_ob)
    walnut = make_material("Walnut", (0.13, 0.065, 0.03), rough=0.5,
                           grain=((1.0, 1.0, 1.0), 60.0, 0.16))
    brass = make_material("Brass", (0.80, 0.58, 0.26), rough=0.28, metallic=1.0,
                          grain=((1.0, 1.0, 1.0), 40.0, 0.12))
    fw = 0.09
    frame = _multi_box("Atlas.Frame", [
        ((0.14, 2.2 + 2 * fw, fw), (0.0, 0.0, 1.0 + fw / 2), 0.012),
        ((0.14, 2.2 + 2 * fw, fw), (0.0, 0.0, -1.0 - fw / 2), 0.012),
        ((0.14, fw, 2.0), (0.0, 1.1 + fw / 2, 0.0), 0.012),
        ((0.14, fw, 2.0), (0.0, -1.1 - fw / 2, 0.0), 0.012)])
    frame.materials.append(walnut)
    frame_ob = bpy.data.objects.new("Atlas.Frame", frame)
    frame_ob.location = (bx, by, bz)
    sc.collection.objects.link(frame_ob)
    plinth_top = bz - 1.0 - fw
    plinth = _box("Atlas.Plinth", (0.46, 2.55, plinth_top),
                  (bx, by, plinth_top / 2), 0.02)
    plinth.materials.append(walnut)
    plinth_ob = bpy.data.objects.new("Atlas.Plinth", plinth)
    sc.collection.objects.link(plinth_ob)
    plate = _box("Atlas.Plate", (0.012, 1.1, 0.13), (0.0, 0.0, 0.0), 0.004)
    plate.materials.append(brass)
    plate_ob = bpy.data.objects.new("Atlas.Plate", plate)
    plate_ob.location = (bx + 0.236, by, plinth_top / 2)
    sc.collection.objects.link(plate_ob)
    cu = bpy.data.curves.new("Atlas.Label", "FONT")
    cu.body = "UV1  LIGHTMAP"
    cu.size = 0.085
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    cu.extrude = 0.002
    cu.materials.append(make_material("Ink", (0.02, 0.018, 0.015), rough=0.6))
    label_ob = bpy.data.objects.new("Atlas.Label", cu)
    label_ob.location = (bx + 0.243, by, plinth_top / 2)
    label_ob.rotation_euler = (math.radians(90), 0.0, math.radians(90))
    sc.collection.objects.link(label_ob)
    grid_mat = make_material("Grid", (0.12, 0.13, 0.15), rough=0.5,
                             emit=(0.45, 0.5, 0.6), estr=0.35)
    lines = []
    for k in range(5):
        t = (k / 4 - 0.5) * 1.9
        lines.append(((0.004, 0.006, 1.9), (0.0, t, 0.0), 0.0))
        lines.append(((0.004, 1.9, 0.006), (0.0, 0.0, t), 0.0))
    grid = _multi_box("Atlas.Grid", lines)
    grid.materials.append(grid_mat)
    grid_ob = bpy.data.objects.new("Atlas.Grid", grid)
    grid_ob.location = (bx + 0.042, by, bz)
    sc.collection.objects.link(grid_ob)
    display = [board_ob, frame_ob, plinth_ob, plate_ob, label_ob, grid_ob]

    bed = meshes["Bed"]
    layer = bed.uv_layers[LAYER1]
    palette = [(0.95, 0.45, 0.15), (0.2, 0.75, 0.85), (0.55, 0.85, 0.3),
               (0.85, 0.3, 0.5), (0.95, 0.8, 0.25), (0.5, 0.55, 0.95),
               (0.7, 0.4, 0.9), (0.4, 0.85, 0.6)]
    iso_obs = []
    for fi, poly in enumerate(bed.polygons):
        pts = [tuple(layer.data[li].uv) for li in poly.loop_indices]
        me = bpy.data.meshes.new(f"Atlas.Island.{fi}")
        bm = bmesh.new()
        try:
            # board face: +X side; UV [0,1]^2 -> y,z on the face (u -> -y, v -> z)
            vs = [bm.verts.new((0.0, (0.5 - uv[0]) * 1.9, (uv[1] - 0.5) * 1.9))
                  for uv in pts]
            bm.faces.new(vs)
            bm.to_mesh(me)
        finally:
            bm.free()
        defect = fi in dragged
        rgb = (1.0, 0.12, 0.08) if defect else palette[fi % len(palette)]
        me.materials.append(make_material(f"IslandMat{fi}", rgb, rough=0.5,
                                          emit=rgb, estr=1.6 if defect else 0.5))
        ob = bpy.data.objects.new(f"Atlas.Island.{fi}", me)
        ob.location = (bx + 0.045 + (0.004 if fi in dragged else 0.0), by, bz)
        sc.collection.objects.link(ob)
        iso_obs.append(ob)

    floor, wall = build_studio(sc)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 47.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (5.9, -7.2, 2.8)
    sc.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.85, 0.1, 1.05)
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
        sc.eevee.taa_render_samples = 64
    sc.render.resolution_x = 1280
    sc.render.resolution_y = 720
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    # Standard, always — AgX would lift the stage toward grey (VISUAL-STYLE)
    sc.view_settings.view_transform = "Standard"
    hero = parts_obs
    fcode = gallery_framing.check_framing(
        sc, cam, hero=hero, elements=hero + display + iso_obs,
        stage=[floor, wall],
    )
    if fcode:
        return fcode
    aqcode = gallery_asset_quality.check_asset_quality(
        sc, cam, hero=hero, stage=[floor, wall])
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
    p.add_argument("--overlap-islands", action="store_true",
                   help="falsifier: drag the Bed's second-largest UV1 island onto "
                        "the largest before the overlap scan (exit 7)")
    p.add_argument("--falsify", default=None,
                   help="optional: render the overlapping-atlas variant here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output/--falsify (cycles for GPU-less hosts)")
    args = p.parse_args(argv)

    print(f"binary version: {bpy.app.version} ({bpy.app.version_string})")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    code = check(overlap=args.overlap_islands)
    if code:
        return code

    if args.output:
        rcode = render_still(os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    if args.falsify:
        rcode = render_still(os.path.abspath(args.falsify), args.engine, falsify=True)
        if rcode:
            return rcode
        print(f"rendered falsified variant {args.falsify}")

    print("lightmap-uv-channel OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
