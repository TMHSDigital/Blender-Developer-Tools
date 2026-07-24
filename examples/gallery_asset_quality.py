"""Gallery asset-quality measurement — the numeric form of the Layer 1
"modeled with intent" rule (docs/VISUAL-STYLE.md).

gallery_framing measures where the subject sits in the frame. This module
measures the subject itself: whether the model reads as designed rather
than placeholder. Same call pattern: render-path only (the check-only path
never imports it), printed measured values, non-zero exit on violation.

Floors (calibrated against the gallery's own best- and weakest-modeled
assets — the calibration table lives in docs/VISUAL-STYLE.md):

- **materials** — distinct materials across the hero's parts. A single
  flat Principled slot across an entire prop is the gallery's most
  reliable placeholder predictor.
- **parts** — named mesh parts the hero is assembled from, excluding
  default datablock names (Cube, Sphere, Plane, ...). Designed assets are
  assembled, not dumped.
- **edge90** — fraction of manifold mesh edges whose dihedral angle is
  90° ± EDGE90_DEG. Unbroken right angles everywhere means no bevel, no
  chamfer, no shading break — manufactured props catch light on treated
  edges. (Fraction, not count: big props carry honest structural corners.)
- **compactness** — silhouette perimeter²/area from an alpha matte of the
  hero (the same EEVEE matte approach gallery_framing uses for fill).
  Scale-invariant: a rectangle scores ~16–20, a circle ~12.6, a prop with
  fixtures, cutouts, and protrusions scores higher.

The floors are a cheap filter, not the standard — see the Goodhart note in
docs/VISUAL-STYLE.md. Bolting meaningless greebles onto a box satisfies
every number here and still fails the asset sheet, which is the deciding
gate.

Sharing mechanism matches gallery_framing: consumers add the examples
directory to sys.path from their own __file__ and import this module. The
check-only path of every example stays free of it, so smoke runtimes are
unaffected.
"""
import math
import os
import sys
import tempfile

import bpy
import bmesh

EXIT_ASSET_QUALITY = 11

# Calibrated against reference assets (collision-hull-proxy,
# custom-normals-shade, vertex-weight-limit, lod-decimate-chain) and the
# gallery's weakest; the measurement table lives in docs/VISUAL-STYLE.md.
MATERIALS_MIN = 2         # for heroes with >= 2 parts (see scope note below)
DOMINANT_MAT_MAX = 0.75   # dominant material's share of hero parts (parts >= 2)
EDGE90_DEG = 2.0          # window around a right angle, degrees
EDGE90_MAX_FRAC = 0.75    # gear teeth peak at 0.667; raw boxes score 1.0
COMPACTNESS_MIN = None    # DROPPED as a gate floor: soccer-ball 10.0,
                          # bmesh-gear 18.3, turntable 19.1 are genuinely
                          # good low-scorers. Printed as information only.
PARTS_MIN = None          # DROPPED: vertex-weight-limit's mech arm is a
                          # single skinned mesh and is reference-quality.
                          # Naming (no default names) is kept instead.

MATTE_WIDTH = 320
ALPHA_THRESHOLD = 0.5

DEFAULT_NAMES = {
    "cube", "sphere", "uvsphere", "plane", "cylinder", "cone", "torus",
    "grid", "monkey", "suzanne", "icosphere", "circle", "beziercurve",
}


def _eevee_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def _as_list(objs):
    if objs is None:
        return []
    if isinstance(objs, bpy.types.Object):
        return [objs]
    return [ob for ob in objs if ob is not None]


def _hero_meshes(hero):
    meshes = []
    for ob in hero:
        if ob.type == "MESH" and ob.data is not None:
            meshes.append((ob.name, ob.data))
    return meshes


def measure_parts(hero):
    """(part count, offending default-ish names)."""
    meshes = _hero_meshes(hero)
    bad = [name for name, _ in meshes
           if name.lower().split(".")[0] in DEFAULT_NAMES]
    return len(meshes), bad


def measure_materials(hero):
    """(distinct materials across all hero slots, names, dominant share,
    dominant name). Distinct counts every slot; the dominant share counts
    the first slot per part — the flat-single-material placeholder signal
    on assembled assets."""
    from collections import Counter
    distinct = set()
    primary = Counter()
    for _, me in _hero_meshes(hero):
        slots = [m for m in me.materials if m is not None]
        for slot in slots:
            distinct.add(slot.name)
        primary[slots[0].name if slots else "<none>"] += 1
    total = sum(primary.values()) or 1
    dominant_name, dominant_n = primary.most_common(1)[0]
    return len(distinct), sorted(distinct), dominant_n / total, dominant_name


def measure_edge90(hero):
    """Fraction of two-face edges with dihedral angle in 90 ± EDGE90_DEG.

    Boundary edges (open kit ends, sheet rims) are excluded — they have no
    dihedral to treat. Angles are face-normal angles on manifold edges.
    """
    total = 0
    right = 0
    for _, me in _hero_meshes(hero):
        bm = bmesh.new()
        try:
            bm.from_mesh(me)
            for e in bm.edges:
                if len(e.link_faces) != 2:
                    continue
                total += 1
                n1 = e.link_faces[0].normal
                n2 = e.link_faces[1].normal
                ang = math.degrees(n1.angle(n2))
                if abs(ang - 90.0) <= EDGE90_DEG:
                    right += 1
        finally:
            bm.free()
    return (right / total) if total else 0.0, right, total


def _matte_render(scene, camera, hide, path, width, height):
    """One small EEVEE alpha-matte render; caller-hidden state restored.
    Mirrors gallery_framing._matte_render's approach (stage hidden,
    film_transparent, low samples)."""
    rd = scene.render
    saved = {
        "engine": rd.engine,
        "res": (rd.resolution_x, rd.resolution_y, rd.resolution_percentage),
        "film": rd.film_transparent,
        "filepath": rd.filepath,
        "fmt": rd.image_settings.file_format,
        "cmode": rd.image_settings.color_mode,
        "cam": scene.camera,
    }
    touched = []
    try:
        try:
            saved["samples"] = scene.eevee.taa_render_samples
        except AttributeError:
            saved["samples"] = None
        rd.engine = _eevee_id()
        rd.resolution_x, rd.resolution_y, rd.resolution_percentage = width, height, 100
        rd.film_transparent = True
        rd.image_settings.file_format = "PNG"
        rd.image_settings.color_mode = "RGBA"
        rd.filepath = path
        scene.camera = camera
        for ob in hide:
            if not ob.hide_render:
                touched.append(ob)
                ob.hide_render = True
        if saved["samples"] is not None:
            scene.eevee.taa_render_samples = 8
        bpy.ops.render.render(write_still=True, scene=scene.name)
    finally:
        for ob in touched:
            ob.hide_render = False
        rd.engine = saved["engine"]
        rd.resolution_x, rd.resolution_y, rd.resolution_percentage = saved["res"]
        rd.film_transparent = saved["film"]
        rd.image_settings.file_format = saved["fmt"]
        rd.image_settings.color_mode = saved["cmode"]
        rd.filepath = saved["filepath"]
        scene.camera = saved["cam"]
        if saved["samples"] is not None:
            scene.eevee.taa_render_samples = saved["samples"]


def measure_compactness(scene, camera, hero, stage=()):
    """Silhouette perimeter²/area from an alpha matte of the hero alone.

    Scale- and framing-invariant: the same shape scores the same fill or
    far. Rectangle ~16-20, circle ~12.6, fixtures/cutouts raise it.
    """
    render_types = {"MESH", "CURVE", "SURFACE", "FONT", "META", "VOLUME",
                    "GPENCIL", "GREASEPENCIL"}
    stage_set = set(_as_list(stage))
    hero_set = set(_as_list(hero))
    hide = [ob for ob in scene.objects
            if ob.type in render_types and ob not in hero_set] + [
            ob for ob in stage_set if ob.type in render_types]
    hide = list({id(ob): ob for ob in hide}.values())

    rd = scene.render
    aspect_h = max(1, round(MATTE_WIDTH * rd.resolution_y / max(1, rd.resolution_x)))
    fd, tmp = tempfile.mkstemp(suffix=".png", prefix="aq_matte_")
    os.close(fd)
    try:
        _matte_render(scene, camera, hide, tmp, MATTE_WIDTH, aspect_h)
        img = bpy.data.images.load(tmp, check_existing=False)
        try:
            w, h = img.size
            px = img.pixels[:]
        finally:
            bpy.data.images.remove(img)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    mask = [[px[(y * w + x) * 4 + 3] > ALPHA_THRESHOLD for x in range(w)]
            for y in range(h)]
    area = 0
    perim = 0
    for y in range(h):
        for x in range(w):
            if not mask[y][x]:
                continue
            area += 1
            if (x == 0 or not mask[y][x - 1]) or (x == w - 1 or not mask[y][x + 1]) \
               or (y == 0 or not mask[y - 1][x]) or (y == h - 1 or not mask[y + 1][x]):
                perim += 1
    if area == 0:
        return 0.0, 0, 0
    return perim * perim / area, perim, area


class AssetQualityResult:
    def __init__(self):
        self.parts = 0
        self.bad_names = []
        self.materials = 0
        self.mat_names = []
        self.dominant_share = 0.0
        self.dominant_name = ""
        self.edge90 = 0.0
        self.edge_right = 0
        self.edge_total = 0
        self.compactness = 0.0
        self.perimeter = 0
        self.area = 0

    def report(self):
        def mark(ok):
            return "ok" if ok else "FAIL"
        name_ok = not self.bad_names
        mat_ok = self.parts < 2 or (self.materials >= MATERIALS_MIN
                                    and self.dominant_share <= DOMINANT_MAT_MAX)
        edge_ok = self.edge90 <= EDGE90_MAX_FRAC
        return "\n".join([
            f"aq_naming default_names={self.bad_names or 'none'} {mark(name_ok)}",
            f"aq_materials n={self.materials} floor={MATERIALS_MIN} "
            f"dominant={self.dominant_name}@{self.dominant_share:.2f} "
            f"ceiling={DOMINANT_MAT_MAX} (applies at parts>=2, n={self.parts}) "
            f"{mark(mat_ok)}",
            f"aq_edge90 frac={self.edge90:.3f} ({self.edge_right}/{self.edge_total}) "
            f"ceiling={EDGE90_MAX_FRAC} {mark(edge_ok)}",
            f"aq_compactness {self.compactness:.1f} (perim={self.perimeter} "
            f"area={self.area}) informational-only",
        ])


def measure_asset_quality(scene, camera, hero, stage=()):
    """Measure the floors for one staged hero. Returns AssetQualityResult."""
    hero = _as_list(hero)
    res = AssetQualityResult()
    res.parts, res.bad_names = measure_parts(hero)
    (res.materials, res.mat_names,
     res.dominant_share, res.dominant_name) = measure_materials(hero)
    res.edge90, res.edge_right, res.edge_total = measure_edge90(hero)
    res.compactness, res.perimeter, res.area = measure_compactness(
        scene, camera, hero, stage=stage)
    return res


def check_asset_quality(scene, camera, hero, stage=(), *,
                        materials_min=MATERIALS_MIN, dominant_max=DOMINANT_MAT_MAX,
                        edge90_max=EDGE90_MAX_FRAC):
    """Measure, print, gate: 0 pass, EXIT_ASSET_QUALITY (11) on violation.

    Render path only — never call from an example's check-only path.
    Floors: no default datablock names; for assembled heroes (parts >= 2)
    at least two materials with the dominant share under the ceiling;
    right-angle edge fraction under the ceiling. Compactness is measured
    and printed but never gated (dropped: fails genuinely good simple
    subjects — see module docstring and docs/VISUAL-STYLE.md).
    """
    res = measure_asset_quality(scene, camera, hero, stage=stage)
    print(res.report())
    failures = []
    if res.bad_names:
        failures.append(f"default datablock names {res.bad_names}")
    if res.parts >= 2 and res.materials < materials_min:
        failures.append(f"materials {res.materials}<{materials_min} "
                        f"on a {res.parts}-part hero")
    if res.edge90 > edge90_max:
        failures.append(f"edge90 {res.edge90:.3f}>{edge90_max}")
    if failures:
        print("ERROR: asset-quality violation — " + "; ".join(failures),
              file=sys.stderr)
        return EXIT_ASSET_QUALITY
    print("aq_ok")
    return 0
