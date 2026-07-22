"""Gallery framing measurement — the numeric form of VISUAL-STYLE Layer 1 framing.

Layer 1 mandates: the hero subject fills 70–90 % of the frame in at least
one axis, and nothing that matters touches or crosses a frame edge. This
module turns that prose into measured numbers so renders are gated by
measurement instead of eyeballing.

Sharing mechanism (the only cross-example import in this repository):
examples stay standalone-runnable —
`blender --background --python examples/<name>/<script>.py --` from the
repository root — because each consumer adds the examples directory to
`sys.path` resolved from its own `__file__`, never from the CWD:

    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
    import gallery_framing

The import is cheap and inert; measurement runs only when the example's
`--output` render path calls `check_framing`. The check-only path (what
`blender-smoke.yml` runs) never renders a matte, so smoke runtimes are
unaffected by consumers of this module.

Two measurement strategies:

- ``silhouette`` (default): hides the stage (floor/wall/backdrop), sets
  ``film_transparent``, renders a small low-sample EEVEE alpha matte, and
  thresholds the alpha channel for the true occupied-pixel extent. Exact
  for any shape — round, angled, or concave subjects measure as their real
  silhouette. Costs one or two cheap extra renders (one for the hero fill,
  one for the all-elements margin union; shared when they coincide).
- ``projection``: projects each object's world-space bounding-box corners
  through the camera with `bpy_extras.object_utils.world_to_camera_view`
  and unions the NDC extent. No extra render, but the projected bbox
  overestimates round or camera-angled subjects (a valve's bbox is wider
  than its silhouette). Choose it when the subject is boxy and render
  time matters; expect a few percent more fill than silhouette reports.

Reported separately, per the Layer 1 rule's two clauses:

- **Fill** — measured on the hero only (the thing the example is about).
  Must reach 70–90 % of frame width or height in at least one axis, and
  neither axis may exceed 90 %.
- **Margin** — measured on the union of every element that matters:
  hero, in-scene placards/labels, comparison props, overlay markers.
  Every edge must clear by >= ``MARGIN_MIN`` (2 % of the frame dimension).
  Union extent is equivalent to per-element extents for edge clearance:
  the union clears an edge iff every element clears it.

Enforcement: `check_framing` prints the measured values on success (same
log style as every other check here) and returns exit code 10 on
violation. Framing is a Layer 1 mandatory identity rule and the render
path is the gallery-artifact path, so a defective composition fails the
render exactly like a failed contract check fails the witness. The gate
runs only on the opt-in render path; check-only semantics (non-zero ==
API-contract drift) are unchanged.
"""
import os
import sys
import tempfile

import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

FILL_MIN = 0.70
FILL_MAX = 0.90
MARGIN_MIN = 0.02
ALPHA_THRESHOLD = 0.5
MATTE_WIDTH = 320
EXIT_FRAMING = 10

DEFAULT_STRATEGY = "silhouette"

_RENDER_TYPES = {
    "MESH", "CURVE", "SURFACE", "FONT", "META", "VOLUME",
    "GPENCIL", "GREASEPENCIL",  # 4.2- id vs GPv3 (4.3+/5.x)
}


def _eevee_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


class FramingResult:
    """Measured framing for one staged scene. Fractions of frame dimension."""

    def __init__(self, strategy):
        self.strategy = strategy
        self.fill_x = 0.0          # hero extent, fraction of frame width
        self.fill_y = 0.0          # hero extent, fraction of frame height
        self.margins = {"left": 0.0, "right": 0.0, "bottom": 0.0, "top": 0.0}
        self.touches = []          # edges where the union silhouette reaches the edge
        self.crosses = []          # edges where projection puts geometry past the edge
        self.note = ""

    @property
    def fill_ok(self):
        over = max(self.fill_x, self.fill_y) > FILL_MAX
        in_band = any(FILL_MIN <= f <= FILL_MAX for f in (self.fill_x, self.fill_y))
        return in_band and not over

    @property
    def margins_ok(self):
        return all(m >= MARGIN_MIN for m in self.margins.values()) and not self.touches and not self.crosses

    @property
    def ok(self):
        return self.fill_ok and self.margins_ok

    def report(self):
        def mark(flag):
            return "ok" if flag else "FAIL"

        touch = ",".join(self.touches) if self.touches else "none"
        cross = ",".join(self.crosses) if self.crosses else "none"
        lines = [
            f"framing_fill x={self.fill_x:.3f} y={self.fill_y:.3f} "
            f"band={FILL_MIN:.2f}..{FILL_MAX:.2f} max={max(self.fill_x, self.fill_y):.3f} "
            f"{mark(self.fill_ok)}",
            f"framing_margins left={self.margins['left']:.3f} right={self.margins['right']:.3f} "
            f"bottom={self.margins['bottom']:.3f} top={self.margins['top']:.3f} "
            f"min={MARGIN_MIN:.3f} {mark(self.margins_ok)}",
            f"framing_edges touch={touch} cross={cross}",
            f"framing_strategy {self.strategy} {self.note}".rstrip(),
        ]
        if self.ok:
            lines.append("framing_ok")
        return "\n".join(lines)


def _as_list(objs):
    if objs is None:
        return []
    if isinstance(objs, bpy.types.Object):
        return [objs]
    return [ob for ob in objs if ob is not None]


def _renderables(scene):
    return [
        ob for ob in scene.objects
        if ob.type in _RENDER_TYPES and not ob.hide_render
    ]


def _extent_to_result(extent, res):
    """extent = (x0, y0, x1, y1) fractions, image origin bottom-left."""
    x0, y0, x1, y1 = extent
    res.fill_x = x1 - x0
    res.fill_y = y1 - y0


def _margins_to_result(extent, res, crossing):
    x0, y0, x1, y1 = extent
    res.margins = {"left": x0, "right": 1.0 - x1, "bottom": y0, "top": 1.0 - y1}
    eps = 1e-9
    for edge, m in res.margins.items():
        if m < -eps:
            (res.crosses if crossing else res.touches).append(edge)
        elif m <= eps:
            res.touches.append(edge)


def _projected_extent(scene, camera, objects):
    """Union NDC extent of world-space bbox corners. Assumes all corners in
    front of the camera (true for every staged gallery scene)."""
    bpy.context.view_layer.update()
    pts = []
    for ob in objects:
        for c in ob.bound_box:
            ndc = world_to_camera_view(scene, camera, ob.matrix_world @ Vector(c))
            pts.append(ndc)
    if not pts:
        return None
    return (
        min(p.x for p in pts), min(p.y for p in pts),
        max(p.x for p in pts), max(p.y for p in pts),
    )


def _matte_render(scene, camera, path, width, height):
    """One small EEVEE alpha-matte render with all caller-hidden state restored."""
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
    try:
        saved["samples"] = scene.eevee.taa_render_samples
    except AttributeError:
        saved["samples"] = None
    try:
        rd.engine = _eevee_id()
        rd.resolution_x, rd.resolution_y, rd.resolution_percentage = width, height, 100
        rd.film_transparent = True
        rd.image_settings.file_format = "PNG"
        rd.image_settings.color_mode = "RGBA"
        rd.filepath = path
        scene.camera = camera
        if saved["samples"] is not None:
            scene.eevee.taa_render_samples = 8
        bpy.ops.render.render(write_still=True)
    finally:
        rd.engine = saved["engine"]
        rd.resolution_x, rd.resolution_y, rd.resolution_percentage = saved["res"]
        rd.film_transparent = saved["film"]
        rd.image_settings.file_format = saved["fmt"]
        rd.image_settings.color_mode = saved["cmode"]
        rd.filepath = saved["filepath"]
        scene.camera = saved["cam"]
        if saved["samples"] is not None:
            scene.eevee.taa_render_samples = saved["samples"]


def _alpha_extent(path):
    """Occupied-pixel extent (fractions) from a rendered alpha matte."""
    img = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = img.size
        px = img.pixels[:]
    finally:
        bpy.data.images.remove(img)
    alpha = px[3::4]
    col_has = [False] * w
    row_has = [False] * h
    for y in range(h):
        base = y * w
        for x in range(w):
            if alpha[base + x] > ALPHA_THRESHOLD:
                col_has[x] = True
                row_has[y] = True
    if not any(col_has):
        return None
    x0 = col_has.index(True) / w
    x1 = (w - 1 - col_has[::-1].index(True) + 1) / w
    y0 = row_has.index(True) / h
    y1 = (h - 1 - row_has[::-1].index(True) + 1) / h
    return (x0, y0, x1, y1)


def _silhouette_measure(scene, camera, hero, elements, stage, res):
    hero_set = set(hero)
    margin_set = set(elements) | hero_set
    stage_set = set(stage)

    visible = [ob for ob in _renderables(scene) if ob not in stage_set]
    share = set(visible) == hero_set  # margin matte == hero matte

    rd = scene.render
    aspect_h = max(1, round(MATTE_WIDTH * rd.resolution_y / max(1, rd.resolution_x)))

    touched = {}
    fd, tmp = tempfile.mkstemp(suffix=".png", prefix="framing_matte_")
    os.close(fd)
    try:
        # Pass 1 — margins: hide the stage only; union of everything that matters.
        for ob in stage_set:
            if not ob.hide_render:
                touched[ob] = ob.hide_render
                ob.hide_render = True
        _matte_render(scene, camera, tmp, MATTE_WIDTH, aspect_h)
        margin_extent = _alpha_extent(tmp)

        # Pass 2 — fill: hide every renderable except the hero.
        hero_extent = margin_extent if share else None
        if hero_extent is None:
            for ob in _renderables(scene):
                if ob not in hero_set and ob not in touched:
                    touched[ob] = ob.hide_render
                    ob.hide_render = True
            _matte_render(scene, camera, tmp, MATTE_WIDTH, aspect_h)
            hero_extent = _alpha_extent(tmp)
    finally:
        for ob, prev in touched.items():
            ob.hide_render = prev
        if os.path.exists(tmp):
            os.remove(tmp)

    res.note = f"matte={MATTE_WIDTH}x{aspect_h} alpha>{ALPHA_THRESHOLD}"
    if hero_extent is not None:
        _extent_to_result(hero_extent, res)
    if margin_extent is not None:
        _margins_to_result(margin_extent, res, crossing=False)
    else:
        res.touches.extend(["left", "right", "bottom", "top"])


def _projection_measure(scene, camera, hero, elements, res):
    hero_extent = _projected_extent(scene, camera, hero)
    margin_extent = _projected_extent(scene, camera, list(set(elements) | set(hero)))
    res.note = "world-bbox union (overestimates round/angled subjects)"
    if hero_extent is not None:
        _extent_to_result(hero_extent, res)
    if margin_extent is not None:
        _margins_to_result(margin_extent, res, crossing=True)


def measure_framing(scene, camera, hero, elements, stage=(), strategy=DEFAULT_STRATEGY):
    """Measure framing for a fully staged scene. Returns a FramingResult.

    scene     — the staged scene (camera assigned or passed explicitly)
    camera    — the render camera object
    hero      — object or list: the subject the example is about (fill metric)
    elements  — list: everything that must clear the frame edges, including
                placards, labels, comparison props, overlay markers
                (hero is unioned in automatically)
    stage     — list: floor/wall/backdrop objects excluded from measurement
    strategy  — "silhouette" (default, exact) or "projection" (cheap, boxy)
    """
    hero = _as_list(hero)
    elements = _as_list(elements)
    stage = _as_list(stage)
    res = FramingResult(strategy)
    if strategy == "silhouette":
        _silhouette_measure(scene, camera, hero, elements, stage, res)
    elif strategy == "projection":
        _projection_measure(scene, camera, hero, elements, res)
    else:
        raise ValueError(f"unknown framing strategy {strategy!r}")
    return res


def check_framing(scene, camera, hero, elements, stage=(), strategy=DEFAULT_STRATEGY):
    """Measure, print the numbers, and gate: 0 pass, EXIT_FRAMING (10) on violation.

    Render path only — never call this from an example's check-only path.
    """
    res = measure_framing(scene, camera, hero, elements, stage=stage, strategy=strategy)
    print(res.report())
    if not res.ok:
        print(
            "ERROR: framing violation — Layer 1 requires fill "
            f"{FILL_MIN:.2f}..{FILL_MAX:.2f} in at least one axis and every "
            f"element clearing all edges by >= {MARGIN_MIN:.2f} "
            f"(fill_ok={res.fill_ok} margins_ok={res.margins_ok})",
            file=sys.stderr,
        )
        return EXIT_FRAMING
    return 0
