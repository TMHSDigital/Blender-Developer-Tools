"""A jerry can prop shaded three ways — a runnable example.

Witnesses the shading contract a game prop's silhouette depends on (engines
generally, FiveM/GTA-style prop workflows specifically): which edges read
hard and which read smooth is mesh DATA, and since Blender 4.1 it is carried
by face smooth flags plus a `sharp_edge` attribute — `use_auto_smooth` is
gone. AI-generated Blender code still emits the pre-4.1 API
(`mesh.use_auto_smooth = True`, `bpy.ops.object.shade_auto_smooth()`), so
this example asserts what the supported versions actually expose:

  legacy API    — use_auto_smooth, use_custom_normals, calc_normals are
                  AttributeError on BOTH 4.5 LTS and 5.1
  by-angle data — `mesh.set_sharp_from_angle(angle)` + face smooth flags:
                  the sharp set lands EXACTLY where an independently
                  recomputed dihedral angle crosses the threshold
  normal welds  — through depsgraph evaluation, loops across a smooth edge
                  share one normal (welded) and loops across a sharp edge
                  carry their face normals (split by the dihedral)
  custom normals— per-loop normals set with `normals_split_custom_set`
                  survive depsgraph evaluation within the int16 storage
                  quantization (3.9e-05 measured over 8196 loops, tol 2e-4),
                  unit length; the request pattern stays clear of the
                  encoder's 0.81-deg merge/snap threshold (see that check)
  divergence    — the legacy `shade_auto_smooth` OPERATOR needs the bundled
                  Smooth-by-Angle node-group asset: headless on 4.5 LTS it
                  returns {'CANCELLED'} ("Asset loading is unfinished") and
                  the mesh is UNTOUCHED — silent flat shading for any script
                  that ignores the return set; on 5.1 it FINISHES and adds
                  the NODES modifier. The portable path is the data API.

``--mismatch-angle`` marks sharp at 20° and still audits against the 30°
dihedral set, so the sharp-set match fails. That is the falsifier
(``--same-axis`` in export-preset-axis).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still: three fresh builds of the can
shaded flat (faceted corners, cap and handle), smooth-everywhere (the flat
fields smear, the pressed panels go pillowy) and by-angle (crisp creases,
smooth rounds), with the by-angle can's `sharp_edge` set read back from the
mesh and traced as thin cyan lines. The render path is gated by
gallery_framing (exit 10) and gallery_asset_quality (exit 11):

    blender --background --python custom_normals_shade.py --                 # check only
    blender --background --python custom_normals_shade.py -- --mismatch-angle
    blender --background --python custom_normals_shade.py -- --output c.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Matrix, Vector

# Shared Layer 1 framing + asset-quality gates (render path only) — see
# gallery_framing.py for the import contract.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
import gallery_framing  # noqa: E402
import gallery_asset_quality  # noqa: E402

ANGLE_DEG = 30.0          # shade-by-angle threshold
ANGLE = math.radians(ANGLE_DEG)
TOL_NORMAL = 2e-4         # custom-normal readback: int16 storage quantizes to ~7.5e-05
TOL_UNIT = 1e-6           # unit-length tolerance for evaluated normals (measured 4.5e-08)
TOL_SMOOTH = 1e-3         # loop-normal equality across a welded (smooth) edge
TOL_SHARP = 5e-3          # radians: split-normal angle vs dihedral across a sharp edge
CUSTOM_TILT = math.radians(20.0)  # custom-normal round-trip request (see that check)

# ---------------------------------------------------------------------------
# Prop construction. A 20-litre-style jerry can in scene units: a pressed
# steel shell (rounded side band, X-stamped front and back faces: four
# raised rounded-triangle panels with 45-degree walls, the X is the channel
# between them), a weld-seam bead round the band, a triple carry handle on
# welded feet, and a spout with red seal, cap, cam lever, hinge and locking
# pin. Every part is its own closed manifold mesh (the game-prop norm), and
# the facet angles are chosen for the by-angle contract: curved surfaces
# step at <= 22.5 deg (smooth under the 30 deg threshold), pressed creases
# break at 45 or 90 deg (sharp), nothing sits near 30.
#
# A `wear` POINT attribute (1 on exposed convex edges, 0 a support ring
# away) drives the paint-chip mask in the material; support rings are
# coplanar, so they add no shading break and no dihedral.
# ---------------------------------------------------------------------------

W, H, D = 1.30, 1.80, 0.62      # shell width (X), height (Z), depth (Y)
R = 0.24                        # front-view corner radius of the side band
CORNER_SEGS = 4                 # 22.5 deg facets: smooth under the threshold
EDGE_BAND = 0.07                # side-band wear ring distance from each face
FACE_BORDER = 0.04              # flat border inside the face outline
PANEL_MARGIN = 0.015
CHANNEL = 0.045                 # half-width of the X channel between panels
PANEL_R = 0.09                  # panel base corner radius
PRESS_H = 0.04                  # panel height; 45 deg walls (run == rise)
ARC_STEP = 10.0                 # max degrees per panel-corner facet
FIELD_STEP = 0.08               # max straight-run edge length (fill quality)
WEAR = "wear"

HANDLE_Y = 0.10
HANDLE_X = (-0.50, -0.22, 0.06)  # left leg, centre post, right leg
HANDLE_TOP = H + 0.26
SPOUT_AT = (0.27, -0.07)
SPOUT_TILT = 12.0               # degrees, leaning out over the corner


def signed_volume(me):
    """Divergence-theorem volume; positive when face winding points outward."""
    vol = 0.0
    for p in me.polygons:
        vs = [me.vertices[i].co for i in p.vertices]
        v0 = vs[0]
        for i in range(1, len(vs) - 1):
            vol += v0.dot(vs[i].cross(vs[i + 1])) / 6.0
    return vol


def finish_mesh(name, bm, matrix=None):
    me = bpy.data.meshes.new(name)
    try:
        if matrix is not None:
            bmesh.ops.transform(bm, matrix=matrix, verts=bm.verts)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    if signed_volume(me) < 0.0:  # pin outward winding by the closed form
        for p in me.polygons:
            p.flip()
    return obj


def rrect(inset, segs=CORNER_SEGS):
    """(x, z) loop of the shell's front-view rounded rectangle, inset by
    `inset`, CCW in (x, z). Corners include both arc ends, so the straight
    runs between them are exactly axis-aligned; the runs are split every
    ~FIELD_STEP so the pressed-face fill triangulates without slivers."""
    rr = R - inset
    cx = W / 2 - R
    corners = ((cx, R, -90), (cx, H - R, 0), (-cx, H - R, 90), (-cx, R, 180))
    pts = []
    for k, (ccx, ccz, a0) in enumerate(corners):
        for i in range(segs + 1):
            a = math.radians(a0 + 90.0 * i / segs)
            pts.append((ccx + rr * math.cos(a), ccz + rr * math.sin(a)))
        nx, nz, b0 = corners[(k + 1) % 4]
        q = (nx + rr * math.cos(math.radians(b0)), nz + rr * math.sin(math.radians(b0)))
        p0 = pts[-1]
        cuts = max(1, math.ceil(math.hypot(q[0] - p0[0], q[1] - p0[1]) / FIELD_STEP))
        pts.extend((p0[0] + (q[0] - p0[0]) * t / cuts, p0[1] + (q[1] - p0[1]) * t / cuts)
                   for t in range(1, cuts))
    return pts


def _ccw(poly):
    area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1]
               - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
    return poly if area > 0 else poly[::-1]


def _inset_poly(poly, d):
    """Convex CCW polygon with every edge moved inward by d."""
    n = len(poly)
    lines = []
    for i in range(n):
        p, q = Vector(poly[i]), Vector(poly[(i + 1) % n])
        t = (q - p).normalized()
        lines.append((p + Vector((-t.y, t.x)) * d, t))
    out = []
    for i in range(n):
        (p1, t1), (p2, t2) = lines[i - 1], lines[i]
        den = t1.x * t2.y - t1.y * t2.x
        s = ((p2.x - p1.x) * t2.y - (p2.y - p1.y) * t2.x) / den
        out.append(p1 + t1 * s)
    return out


def rounded_outline(tri, off, r):
    """Arc samples [(core point, angle)] of a convex polygon inset by `off`
    with its corners rounded to radius r. Sampling a smaller radius with
    the same list gives a concentric outline (a 45-deg wall or a flat ring
    between them)."""
    core = _inset_poly(_ccw(tri), off + r)
    n = len(core)
    samples = []
    for i in range(n):
        t_in = (core[i] - core[i - 1]).normalized()
        t_out = (core[(i + 1) % n] - core[i]).normalized()
        a0 = math.atan2(-t_in.x, t_in.y)          # outward normal, incoming edge
        a1 = math.atan2(-t_out.x, t_out.y)        # outward normal, outgoing edge
        sweep = (a1 - a0) % (2.0 * math.pi)
        k = max(1, math.ceil(math.degrees(sweep) / ARC_STEP))
        samples.extend((core[i], a0 + sweep * j / k) for j in range(k + 1))
        run = core[(i + 1) % n] - core[i]
        cuts = max(1, math.ceil(run.length / FIELD_STEP))
        samples.extend((core[i] + run * (t / cuts), a1) for t in range(1, cuts))
    return samples


def panel_triangles():
    """The four stamped panels; the X is what is left between them."""
    a = W / 2 - FACE_BORDER - PANEL_MARGIN
    zt, zb, zc = H - FACE_BORDER - PANEL_MARGIN, FACE_BORDER + PANEL_MARGIN, H / 2
    return [((-a, zt), (0.0, zc), (a, zt)), ((-a, zb), (a, zb), (0.0, zc)),
            ((-a, zt), (-a, zb), (0.0, zc)), ((a, zb), (a, zt), (0.0, zc))]


def pressed_face(bm, wl, outline, y0, s):
    """Front (s=-1) or back (s=+1) face: flat border ring, four raised
    panels, and a triangle fill of the flat field between them."""
    inner = [bm.verts.new((x, y0, z)) for x, z in rrect(FACE_BORDER)]
    n = len(inner)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((outline[i], outline[j], inner[j], inner[i]))
    fill = [bm.edges.get((inner[i], inner[(i + 1) % n])) for i in range(n)]
    for tri in panel_triangles():
        samples = rounded_outline(tri, CHANNEL, PANEL_R)

        def ring(r, lift, wear):
            vs = []
            for c, a in samples:
                v = bm.verts.new((c.x + r * math.cos(a), y0 + s * lift, c.y + r * math.sin(a)))
                v[wl] = wear
                vs.append(v)
            return vs
        base = ring(PANEL_R, 0.0, 0.15)
        top = ring(PANEL_R - PRESS_H, PRESS_H, 1.0)
        top_in = ring(PANEL_R - PRESS_H - 0.022, PRESS_H, 0.0)
        m = len(base)
        for i in range(m):
            j = (i + 1) % m
            bm.faces.new((base[i], base[j], top[j], top[i]))
            bm.faces.new((top[i], top[j], top_in[j], top_in[i]))
        bm.faces.new(top_in)
        fill += [bm.edges.get((base[i], base[(i + 1) % m])) for i in range(m)]
    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False,
                            edges=fill, normal=(0.0, s, 0.0))


def build_shell(name):
    """Side band lofted along Y through wear-ring stations, capped by the
    two pressed faces. The face/band edge is a true 90-deg break."""
    bm = bmesh.new()
    wl = bm.verts.layers.float.new(WEAR)
    prof = rrect(0.0)
    n = len(prof)
    rings = []
    for y, wear in ((-D / 2, 1.0), (-D / 2 + EDGE_BAND, 0.0), (0.0, 0.0),
                    (D / 2 - EDGE_BAND, 0.0), (D / 2, 1.0)):
        ring = [bm.verts.new((x, y, z)) for x, z in prof]
        for v in ring:
            v[wl] = wear
        rings.append(ring)
    for ra, rb in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((ra[i], ra[j], rb[j], rb[i]))
    pressed_face(bm, wl, rings[0], -D / 2, -1.0)
    pressed_face(bm, wl, rings[-1], D / 2, 1.0)
    return finish_mesh(name, bm)


def sweep(name, path, section, axis, closed=False, wear=0.0, matrix=None):
    """Sweep a closed 2D section (u along the in-plane normal, v along
    `axis`) down a path lying in the plane normal to `axis`. Open paths are
    capped with ngons."""
    axis = Vector(axis)
    pts = [Vector(p) for p in path]
    n = len(pts)
    bm = bmesh.new()
    wl = bm.verts.layers.float.new(WEAR)
    rings = []
    for i, p in enumerate(pts):
        if closed:
            t = (pts[(i + 1) % n] - pts[i - 1])
        else:
            t = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        nrm = axis.cross(t.normalized()).normalized()   # outward for CCW paths
        ring = [bm.verts.new(p + nrm * u + axis * v) for u, v in section]
        for v in ring:
            v[wl] = wear
        rings.append(ring)
    k = len(section)
    for i in range(n if closed else n - 1):
        ra, rb = rings[i], rings[(i + 1) % n]
        for j in range(k):
            jj = (j + 1) % k
            bm.faces.new((ra[j], ra[jj], rb[jj], rb[j]))
    if not closed:
        bm.faces.new(rings[0])
        bm.faces.new(rings[-1][::-1])
    return finish_mesh(name, bm, matrix)


def circle(r, segs=16):
    return [(r * math.cos(2 * math.pi * i / segs), r * math.sin(2 * math.pi * i / segs))
            for i in range(segs)]


def lathe(name, profile, segments=16, closed=False, wear=None, matrix=None):
    """Spin an (r, z) profile around Z; r == 0 ends become poles, a closed
    profile makes a ring. `wear` is an optional per-profile-point list."""
    wear = list(wear) if wear else [0.0] * len(profile)
    bm = bmesh.new()
    wl = bm.verts.layers.float.new(WEAR)
    bot = top = None
    if not closed and profile[0][0] == 0.0:
        bot = bm.verts.new((0.0, 0.0, profile[0][1]))
        profile, wear = profile[1:], wear[1:]
    if not closed and profile[-1][0] == 0.0:
        top = bm.verts.new((0.0, 0.0, profile[-1][1]))
        profile, wear = profile[:-1], wear[:-1]
    rings = []
    for i in range(segments):
        a = 2.0 * math.pi * i / segments
        ring = [bm.verts.new((r * math.cos(a), r * math.sin(a), z)) for r, z in profile]
        for v, w in zip(ring, wear):
            v[wl] = w
        rings.append(ring)
    m = len(profile)
    for i in range(segments):
        j = (i + 1) % segments
        for k in range(m if closed else m - 1):
            kk = (k + 1) % m
            bm.faces.new((rings[i][k], rings[j][k], rings[j][kk], rings[i][kk]))
        if bot is not None:
            bm.faces.new((rings[j][0], rings[i][0], bot))
        if top is not None:
            bm.faces.new((rings[i][-1], rings[j][-1], top))
    return finish_mesh(name, bm, matrix)


def extrude_profile(name, poly, thickness, bevel, matrix=None, wear=0.6):
    """A flat plate from an (x, z) outline, thickness along Y, every edge
    chamfered — the cam lever."""
    bm = bmesh.new()
    wl = bm.verts.layers.float.new(WEAR)
    try:
        front = [bm.verts.new((x, -thickness / 2, z)) for x, z in poly]
        back = [bm.verts.new((x, thickness / 2, z)) for x, z in poly]
        n = len(poly)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((front[i], front[j], back[j], back[i]))
        bm.faces.new(front)
        bm.faces.new(back[::-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=1,
                        affect='EDGES', clamp_overlap=True)
        for v in bm.verts:
            v[wl] = wear
    except Exception:
        bm.free()
        raise
    return finish_mesh(name, bm, matrix)


def arc(cx, cz, r, a0, a1, steps):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / steps)),
             cz + r * math.sin(math.radians(a0 + (a1 - a0) * i / steps)))
            for i in range(steps + 1)]


def build_jerry_can(suffix=""):
    """All parts at world placement; returns {"shell", "handle", "neck", "parts"}."""
    def nm(base):
        return base + suffix

    shell = build_shell(nm("Shell"))
    parts = [shell]

    # weld seam: a chamfered bead swept round the side band at mid-depth
    bead = [(-0.012, -0.028), (0.010, -0.028), (0.021, -0.012),
            (0.021, 0.012), (0.010, 0.028), (-0.012, 0.028)]
    seam_path = [(x, 0.0, z) for x, z in rrect(0.0)]
    parts.append(sweep(nm("WeldSeam"), seam_path, bead, (0.0, 1.0, 0.0),
                       closed=True, wear=0.7))

    # triple carry handle: one bent tube over two legs, a centre post, and
    # three welded feet on the shell top
    x0, xm, x1 = HANDLE_X
    rb, zb = 0.09, H - 0.03
    hp = ([(x0, zb), (x0, HANDLE_TOP - rb)]
          + arc(x0 + rb, HANDLE_TOP - rb, rb, 180, 90, 4)[1:]
          + arc(x1 - rb, HANDLE_TOP - rb, rb, 90, 0, 4) + [(x1, zb)])
    handle = sweep(nm("Handle"), [(x, HANDLE_Y, z) for x, z in hp], circle(0.042),
                   (0.0, 1.0, 0.0), wear=0.45)
    parts.append(handle)
    parts.append(sweep(nm("HandlePost"), [(xm, HANDLE_Y, zb), (xm, HANDLE_Y, HANDLE_TOP)],
                       circle(0.036), (0.0, 1.0, 0.0), wear=0.3))
    foot = [(0.0, -0.02), (0.085, -0.02), (0.085, 0.006), (0.066, 0.025), (0.0, 0.025)]
    for i, x in enumerate(HANDLE_X):
        parts.append(lathe(nm(f"HandleFoot{i}"), foot, 16, wear=(0, 0, 1, 0.6, 0),
                           matrix=Matrix.Translation((x, HANDLE_Y, H))))

    # spout assembly, built on a local +Z axis and tilted out over the corner
    sm = (Matrix.Translation((SPOUT_AT[0], SPOUT_AT[1], H))
          @ Matrix.Rotation(math.radians(SPOUT_TILT), 4, 'Y'))
    neck = lathe(nm("Neck"), [(0.0, -0.06), (0.19, -0.06), (0.19, 0.02), (0.15, 0.06),
                              (0.15, 0.16), (0.165, 0.175), (0.165, 0.20), (0.15, 0.215),
                              (0.15, 0.22), (0.0, 0.22)], 16,
                 wear=(0, 0, 1, 0.3, 0, 0.3, 1, 0.3, 0, 0), matrix=sm)
    parts.append(neck)
    parts.append(lathe(nm("Seal"), [(0.13, 0.215), (0.188, 0.215), (0.198, 0.225),
                                    (0.198, 0.25), (0.188, 0.26), (0.13, 0.26)],
                       16, closed=True, matrix=sm))
    # cap: vertical skirt, then a dome in 22-deg steps (smooth by angle)
    cap_prof = [(0.0, 0.26), (0.205, 0.26), (0.205, 0.30), (0.190, 0.337),
                (0.155, 0.373), (0.091, 0.402), (0.0, 0.405)]
    parts.append(lathe(nm("Cap"), cap_prof, 16, wear=(0, 0.5, 0.9, 0.3, 0, 0, 0),
                       matrix=sm))
    lever = [(0.25, 0.27), (0.27, 0.31), (0.25, 0.36), (0.18, 0.43), (0.05, 0.445),
             (-0.24, 0.445), (-0.30, 0.43), (-0.30, 0.40), (-0.22, 0.39), (0.04, 0.41),
             (0.15, 0.395), (0.20, 0.33), (0.20, 0.29)]
    parts.append(extrude_profile(nm("CamLever"), lever, 0.08, 0.008, matrix=sm))
    parts.append(lathe(nm("Hinge"), [(0.0, -0.07), (0.035, -0.07), (0.035, 0.07), (0.0, 0.07)],
                       16, matrix=sm @ Matrix.Translation((0.22, 0.0, 0.30))
                       @ Matrix.Rotation(math.radians(90), 4, 'X')))
    parts.append(lathe(nm("LockPin"), [(0.0, -0.075), (0.024, -0.075), (0.024, 0.05),
                                       (0.04, 0.05), (0.04, 0.075), (0.0, 0.075)],
                       16, wear=(0, 0, 0, 1, 1, 0),
                       matrix=sm @ Matrix.Translation((-0.26, 0.0, 0.42))
                       @ Matrix.Rotation(math.radians(-90), 4, 'X')))

    return {"shell": shell, "handle": handle, "neck": neck, "parts": parts}


# ---------------------------------------------------------------------------
# The contract checks.
# ---------------------------------------------------------------------------

def manifold_dihedrals(me):
    """Independent recompute: {vertex-pair key: (degrees, v1, v2)} for edges
    with exactly two link faces, plus the count of non-manifold edges."""
    bm = bmesh.new()
    out = {}
    nonmanifold = 0
    try:
        bm.from_mesh(me)
        for e in bm.edges:
            if len(e.link_faces) != 2:
                nonmanifold += 1
                continue
            deg = math.degrees(e.link_faces[0].normal.angle(e.link_faces[1].normal))
            v1, v2 = e.verts[0].index, e.verts[1].index
            out[frozenset((v1, v2))] = (deg, v1, v2)
    finally:
        bm.free()
    return out, nonmanifold


def sharp_edge_keys(me):
    attr = me.attributes.get("sharp_edge")
    if attr is None:
        return set()
    return {frozenset((me.edges[i].vertices[0], me.edges[i].vertices[1]))
            for i, d in enumerate(attr.data) if d.value}


def check_api_surface(me):
    """The legacy shading API is gone on every supported version."""
    for gone in ("use_auto_smooth", "use_custom_normals", "calc_normals"):
        if hasattr(me, gone):
            print(f"ERROR: mesh still exposes {gone} on {bpy.app.version_string} — "
                  f"the pre-4.1 shading API must stay removed", file=sys.stderr)
            return 3
    for needed in ("normals_split_custom_set", "normals_split_custom_set_from_vertices",
                   "set_sharp_from_angle", "corner_normals", "has_custom_normals"):
        if not hasattr(me, needed):
            print(f"ERROR: mesh lacks {needed} on {bpy.app.version_string}",
                  file=sys.stderr)
            return 3
    print(f"api-surface: use_auto_smooth/use_custom_normals/calc_normals absent, "
          f"modern path present ({bpy.app.version_string})")
    return 0


def check_by_angle(objs, mismatch_angle=False):
    """set_sharp_from_angle must mark exactly the edges whose independently
    recomputed dihedral crosses the threshold — on every checked mesh."""
    mark = math.radians(20.0) if mismatch_angle else ANGLE
    total_sharp = total_manifold = 0
    for obj in objs:
        me = obj.data
        for p in me.polygons:
            p.use_smooth = True
        me.set_sharp_from_angle(angle=mark)
        dih, nonmanifold = manifold_dihedrals(me)
        if nonmanifold:
            print(f"ERROR: {obj.name}: {nonmanifold} non-manifold edge(s) — the "
                  f"dihedral test is undefined there", file=sys.stderr)
            return 4
        expect = {k for k, (deg, _, _) in dih.items() if deg > ANGLE_DEG}
        got = sharp_edge_keys(me)
        if got != expect:
            only_got = len(got - expect)
            only_exp = len(expect - got)
            print(f"ERROR: {obj.name}: sharp set mismatch vs independent dihedral "
                  f"test ({only_got} extra, {only_exp} missing of {len(expect)} "
                  f"expected)", file=sys.stderr)
            return 5
        total_sharp += len(got)
        total_manifold += len(dih)
        print(f"by-angle {obj.name}: edges={len(dih)} sharp={len(got)} "
              f"matches independent dihedral recompute (>{ANGLE_DEG:.0f}deg)")
    print(f"by-angle: {len(objs)} meshes, {total_manifold} manifold edges, "
          f"{total_sharp} sharp, exact set match")
    return 0


def check_normal_welds(obj):
    """Through depsgraph evaluation: loops across a smooth edge share one
    normal; loops across a sharp edge carry their face normals (split by the
    dihedral). The rendered shading, verified — not the attribute's say-so."""
    me = obj.data
    dih, _ = manifold_dihedrals(me)
    sharp = sharp_edge_keys(me)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg).to_mesh()
    try:
        # per manifold edge, per endpoint vertex, per polygon: the loop normal
        loop_normal = [tuple(l.normal) for l in ev.loops]
        poly_of_loop = [0] * len(ev.loops)
        for p in ev.polygons:
            for li in range(p.loop_start, p.loop_start + p.loop_total):
                poly_of_loop[li] = p.index
        by_edge = {}
        for li, l in enumerate(ev.loops):
            pi, vi = poly_of_loop[li], l.vertex_index
            for vj in ev.polygons[pi].vertices:
                if vj == vi:
                    continue
                k = frozenset((vi, vj))
                if k in dih:
                    by_edge.setdefault(k, {}).setdefault(vi, {})[pi] = loop_normal[li]
        max_smooth = 0.0
        max_sharp = 0.0
        unit_worst = 0.0
        for k, (deg, v1, v2) in dih.items():
            for v in (v1, v2):
                sides = by_edge.get(k, {}).get(v, {})
                if len(sides) != 2:
                    print(f"ERROR: edge {tuple(sorted(k))} endpoint v{v}: expected "
                          f"loop normals on both sides, got {len(sides)}", file=sys.stderr)
                    return 6
                n1, n2 = (Vector(s) for s in sides.values())
                unit_worst = max(unit_worst, abs(n1.length - 1.0), abs(n2.length - 1.0))
                if k in sharp:
                    err = abs(n1.angle(n2) - math.radians(deg))
                    max_sharp = max(max_sharp, err)
                else:
                    max_smooth = max(max_smooth, (n1 - n2).length)
        if unit_worst > TOL_UNIT:
            print(f"ERROR: evaluated normal off unit length by {unit_worst:.3e} "
                  f"(tol {TOL_UNIT})", file=sys.stderr)
            return 6
        if max_smooth > TOL_SMOOTH:
            print(f"ERROR: smooth edge not welded: loop normals differ by "
                  f"{max_smooth:.3e} (tol {TOL_SMOOTH})", file=sys.stderr)
            return 6
        if max_sharp > TOL_SHARP:
            print(f"ERROR: sharp edge split {max_sharp:.6f} rad off its dihedral "
                  f"(tol {TOL_SHARP})", file=sys.stderr)
            return 6
        print(f"normal-welds {obj.name}: smooth max deviation {max_smooth:.3e} "
              f"(tol {TOL_SMOOTH}), sharp max angle err {max_sharp:.3e} rad "
              f"(tol {TOL_SHARP}), unit err {unit_worst:.3e}")
    finally:
        obj.evaluated_get(dg).to_mesh_clear()
    return 0


def check_custom_normals_roundtrip(obj):
    """Per-loop custom normals survive depsgraph evaluation. Tolerance is the
    int16 storage quantization, measured 7.5e-05 on both versions.

    Each corner requests its face normal tilted CUSTOM_TILT toward the
    corner bisector — a distinct normal per corner, as a weighted-normal or
    bevel-softening pass writes. Blender's encoder (the lnor-space
    LNOR_SPACE_TRIGO_THRESHOLD, dot > 1 - 1e-4, ~0.81 deg) is not storage
    precision and must stay out of the measurement: requested normals in one
    fan closer than that are MERGED to their average (a pattern stepping
    ~7e-4 rad per loop over 4.5k loops measured 1.4e-02), and an in-plane
    angle from the space's reference edge under it is SNAPPED to zero (an
    arbitrary-direction pattern put 13 of 4.5k corners there, 9.1e-03).
    Aimed at the bisector, the in-plane angle is half the corner — never
    near zero on this mesh — so the round-trip isolates quantization."""
    me = obj.data
    n = len(me.loops)
    custom = [None] * n
    co = [v.co for v in me.vertices]
    for poly in me.polygons:
        fn = poly.normal
        vs = poly.vertices
        k = len(vs)
        for j in range(k):
            c = co[vs[j]]
            e_prev = (co[vs[j - 1]] - c).normalized()
            e_next = (co[vs[(j + 1) % k]] - c).normalized()
            bis = e_prev + e_next
            bis -= fn * bis.dot(fn)
            if bis.length < 1e-6:           # straight corner: perpendicular in-plane
                bis = fn.cross(e_next)
            custom[poly.loop_start + j] = (fn * math.cos(CUSTOM_TILT)
                                           + bis.normalized() * math.sin(CUSTOM_TILT))
    me.normals_split_custom_set(custom)
    if not me.has_custom_normals:
        print("ERROR: has_custom_normals False after normals_split_custom_set — "
              "no use_custom_normals flag exists to flip anymore", file=sys.stderr)
        return 7
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg).to_mesh()
    try:
        err = max((Vector(tuple(l.normal)) - custom[i]).length
                  for i, l in enumerate(ev.loops))
        unit = max(abs(Vector(tuple(l.normal)).length - 1.0) for l in ev.loops)
    finally:
        obj.evaluated_get(dg).to_mesh_clear()
    if err > TOL_NORMAL or unit > TOL_UNIT:
        print(f"ERROR: custom normals lost in evaluation: max_err {err:.3e} "
              f"(tol {TOL_NORMAL}), unit err {unit:.3e}", file=sys.stderr)
        return 7
    print(f"custom-normals: {n} loops survive depsgraph evaluation, "
          f"max_err {err:.3e} (tol {TOL_NORMAL}), unit err {unit:.3e}")
    return 0


def check_legacy_operator():
    """The shade_auto_smooth OPERATOR is a version-split trap: it builds the
    Smooth-by-Angle node-group modifier from a bundled asset. Headless on
    4.5 LTS the asset load never finishes and the op CANCELS — silently, no
    exception — leaving flat shading. On 5.1 it FINISHES with the modifier."""
    me = bpy.data.meshes.new("LegacyProbe")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new("LegacyProbe", me)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    try:
        result = bpy.ops.object.shade_auto_smooth(angle=ANGLE)
    except Exception as e:
        print(f"ERROR: shade_auto_smooth raised {type(e).__name__}: {e}",
              file=sys.stderr)
        return 8
    mods = [(m.name, m.type) for m in obj.modifiers]
    smooth = sum(1 for p in me.polygons if p.use_smooth)
    bpy.data.objects.remove(obj)
    bpy.data.meshes.remove(me)
    if bpy.app.version >= (5, 0, 0):
        ok = result == {'FINISHED'} and any(t == 'NODES' for _, t in mods) and smooth > 0
        detail = f"expect FINISHED + Smooth-by-Angle NODES modifier, got {result} mods={mods} smooth={smooth}"
    else:
        ok = result == {'CANCELLED'} and not mods and smooth == 0
        detail = f"expect CANCELLED headless (asset load never finishes) + untouched mesh, got {result} mods={mods} smooth={smooth}"
    if not ok:
        print(f"ERROR: legacy-operator divergence drifted: {detail}", file=sys.stderr)
        return 8
    print(f"legacy-op ({bpy.app.version_string}): {detail} — as asserted")
    return 0


# ---------------------------------------------------------------------------
# Render: three fresh builds of the same can, one per shading treatment —
# flat (every facet shows), smooth-everywhere (the shade_smooth-and-forget
# AI habit: flat faces smear into gradients, pressed panels go pillowy),
# and by-angle (the contract). Failure modes flank the truth.
# ---------------------------------------------------------------------------

def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def make_material(name, color, metallic, roughness, coat=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if coat:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.12
    return mat


def make_painted_steel(name, paint, steel):
    """Semi-gloss paint over steel, chipped where the `wear` attribute says
    an edge is exposed. Glossy enough (coat) that a highlight exposes every
    normal discontinuity — matte paint would hide the very differences this
    render exists to show."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    out = nodes["Material Output"]
    paint_bsdf = nodes["Principled BSDF"]
    paint_bsdf.inputs["Base Color"].default_value = (*paint, 1.0)
    paint_bsdf.inputs["Metallic"].default_value = 0.0
    paint_bsdf.inputs["Coat Weight"].default_value = 0.35
    paint_bsdf.inputs["Coat Roughness"].default_value = 0.18
    steel_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    steel_bsdf.inputs["Base Color"].default_value = (*steel, 1.0)
    steel_bsdf.inputs["Metallic"].default_value = 1.0
    steel_bsdf.inputs["Roughness"].default_value = 0.32

    coord = nodes.new("ShaderNodeTexCoord")
    chips = nodes.new("ShaderNodeTexNoise")
    chips.inputs["Scale"].default_value = 18.0
    chips.inputs["Detail"].default_value = 6.0
    links.new(coord.outputs["Object"], chips.inputs["Vector"])
    mottle = nodes.new("ShaderNodeTexNoise")
    mottle.inputs["Scale"].default_value = 4.0
    links.new(coord.outputs["Object"], mottle.inputs["Vector"])
    rough = nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.30
    rough.inputs["To Max"].default_value = 0.46
    links.new(mottle.outputs["Fac"], rough.inputs["Value"])
    links.new(rough.outputs["Result"], paint_bsdf.inputs["Roughness"])

    wear = nodes.new("ShaderNodeAttribute")
    wear.attribute_name = WEAR
    # chip = wear + (noise - 0.5) * 1.6, thresholded to a crisp paint edge
    jitter = nodes.new("ShaderNodeMath")
    jitter.operation = 'MULTIPLY_ADD'
    jitter.inputs[1].default_value = 1.6
    jitter.inputs[2].default_value = -0.8
    links.new(chips.outputs["Fac"], jitter.inputs[0])
    total = nodes.new("ShaderNodeMath")
    total.operation = 'ADD'
    links.new(wear.outputs["Fac"], total.inputs[0])
    links.new(jitter.outputs["Value"], total.inputs[1])
    mask = nodes.new("ShaderNodeMapRange")
    mask.inputs["From Min"].default_value = 0.86
    mask.inputs["From Max"].default_value = 0.92
    links.new(total.outputs["Value"], mask.inputs["Value"])

    mix = nodes.new("ShaderNodeMixShader")
    links.new(mask.outputs["Result"], mix.inputs["Fac"])
    links.new(paint_bsdf.outputs["BSDF"], mix.inputs[1])
    links.new(steel_bsdf.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


PART_MATERIAL = {"CamLever": "steel", "Hinge": "steel", "LockPin": "steel", "Seal": "seal"}


def shade(parts, mode):
    """The one variable across the three cans."""
    for o in parts:
        me = o.data
        for p in me.polygons:
            p.use_smooth = mode != "flat"
        if mode == "byangle":
            me.set_sharp_from_angle(angle=ANGLE)


def sharp_edge_overlay(parts, name, radius=0.0026):
    """Thin tubes along every edge the `sharp_edge` attribute marks — the
    contract's own output drawn onto the by-angle can, read back from the
    mesh rather than recomputed."""
    bm = bmesh.new()
    try:
        for o in parts:
            me = o.data
            attr = me.attributes.get("sharp_edge")
            if attr is None:
                continue
            for e, d in zip(me.edges, attr.data):
                if not d.value:
                    continue
                a, b = (me.vertices[i].co for i in e.vertices)
                t = (b - a).normalized()
                u = t.orthogonal().normalized()
                w = t.cross(u)
                ring = []
                for k in range(4):
                    ang = math.pi * 0.5 * k
                    off = (u * math.cos(ang) + w * math.sin(ang)) * radius
                    ring.append((bm.verts.new(a + off), bm.verts.new(b + off)))
                for k in range(4):
                    (a0, b0), (a1, b1) = ring[k], ring[(k + 1) % 4]
                    bm.faces.new((a0, a1, b1, b0))
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def render_still(can, path, engine):
    scene = bpy.context.scene
    mats = {
        "paint": make_painted_steel("OlivePaint", (0.085, 0.115, 0.030), (0.30, 0.30, 0.29)),
        "steel": make_material("BareSteel", (0.42, 0.41, 0.39), 1.0, 0.34),
        "seal": make_material("SealRed", (0.62, 0.035, 0.02), 0.0, 0.42),
    }

    # the checked can stays hidden; the gallery shows three fresh builds
    for o in can["parts"]:
        o.hide_render = True
    variants = {}
    for mode, x in (("flat", -1.62), ("smooth", 0.0), ("byangle", 1.62)):
        built = build_jerry_can("_" + mode)["parts"]
        shade(built, mode)
        for o in built:
            base = o.name[: -len(mode) - 1].rstrip("0123456789")
            o.data.materials.append(mats[PART_MATERIAL.get(base, "paint")])
            o.location = (x, 0.0, 0.0)
            o.rotation_euler = (0.0, 0.0, math.radians(-30.0))
        variants[mode] = built
    hero = [o for objs in variants.values() for o in objs]
    edges = sharp_edge_overlay(variants["byangle"], "SharpEdgeOverlay")
    glow = bpy.data.materials.new("SharpEdgeGlow")
    glow.use_nodes = True
    gb = glow.node_tree.nodes["Principled BSDF"]
    gb.inputs["Base Color"].default_value = (0.35, 0.85, 1.0, 1.0)
    gb.inputs["Emission Color"].default_value = (0.35, 0.85, 1.0, 1.0)
    gb.inputs["Emission Strength"].default_value = 1.0
    edges.data.materials.append(glow)
    edges.location = variants["byangle"][0].location
    edges.rotation_euler = variants["byangle"][0].rotation_euler

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    floor_me.materials.append(make_material("Studio", (0.03, 0.032, 0.037), 0.0, 0.7))
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

    def light(name, loc, energy, size, col, rot, size_y=None):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.color = col
        ld.size = size
        if size_y is not None:
            ld.shape = 'RECTANGLE'
            ld.size_y = size_y
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)
        return ob

    # key/fill/rim/wedge per docs/VISUAL-STYLE.md
    light("Key", (-4.0, -5.0, 6.0), 560.0, 4.5, (1.0, 0.96, 0.9), (50, 0, -38))
    light("Fill", (5.5, -3.5, 2.5), 110.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 55))
    light("Rim", (1.5, 4.5, 4.0), 320.0, 3.0, (0.6, 0.78, 1.0), (-58, 0, 170))
    light("Wedge", (1.2, 6.2, 3.0), 500.0, 6.0, (1.0, 0.76, 0.5), (70, 0, 12))
    # the shading audit light: a tall narrow strip low on the camera's left.
    # The pressed faces mirror it: a straight band broken cleanly at every
    # crease on by-angle, stepped on flat, bent into a smear on smooth.
    light("Strip", (-5.2, -5.6, 1.4), 320.0, 0.6, (0.92, 0.96, 1.0), (90, 0, -42), size_y=6.0)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.77, -8.0, 2.8)
    scene.collection.objects.link(cam)
    target = bpy.data.objects.new("Aim", None)
    target.location = (0.0, 0.0, 1.08)
    scene.collection.objects.link(target)
    con = cam.constraints.new('TRACK_TO')
    con.target = target
    scene.camera = cam

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
    # AgX would flatten the olive drab toward mud (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    bpy.context.view_layer.update()

    fcode = gallery_framing.check_framing(scene, cam, hero=hero, elements=hero + [edges],
                                          stage=[floor, wall])
    if fcode:
        return fcode
    aqcode = gallery_asset_quality.check_asset_quality(scene, cam, hero=variants["byangle"],
                                                       stage=[floor, wall])
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
    p.add_argument("--mismatch-angle", action="store_true",
                   help="mark sharp at 20° while auditing 30° (must fail)")
    args = p.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    can = build_jerry_can()

    for step in (lambda: check_api_surface(can["shell"].data),
                 lambda: check_by_angle(
                     [can["shell"], can["handle"], can["neck"]],
                     mismatch_angle=args.mismatch_angle),
                 lambda: check_normal_welds(can["shell"]),
                 lambda: check_custom_normals_roundtrip(can["shell"]),
                 check_legacy_operator):
        code = step()
        if code:
            return code

    if args.output:
        code = render_still(can, os.path.abspath(args.output), args.engine)
        if code:
            return code
        print(f"rendered still {args.output}")

    print("custom-normals-shade OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
