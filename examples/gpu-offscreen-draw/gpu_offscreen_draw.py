"""GPU offscreen drawing without bgl — a runnable example.

Witnesses the ``gpu`` module path that replaced ``bgl``. It draws into a
``gpu.types.GPUOffScreen`` and reads the pixels back:

- ``gpu.init()`` makes drawing available under ``--background``. It is new
  in 5.2: 5.1 and earlier, including 4.5 LTS, raise "GPU functions for
  drawing are not available in background mode", so the example skips there.
- An opaque ``UNIFORM_COLOR`` quad covers exactly the pixels its NDC
  corners predict.
- ``gpu.state.blend_set('ALPHA')`` is what makes a half-transparent draw
  mix with what is under it. Without it the colour overwrites the target.
- ``POLYLINE_UNIFORM_COLOR`` draws a line ``lineWidth`` pixels thick. It is
  the way to get wide lines; ``bgl.glLineWidth`` is gone.
- ``bgl`` itself is gone on 5.x: ``importlib.util.find_spec('bgl')`` is
  ``None``. That is why bgl-based add-on code fails at import.

Pathology: no gallery still; the witness is pixel counts read back from the
GPU, which a render could only show, not prove.

    blender --background --python gpu_offscreen_draw.py --
    blender --background --python gpu_offscreen_draw.py -- --skip-blend    # 5
    blender --background --python gpu_offscreen_draw.py -- --thin-line     # 6
    blender --background --python gpu_offscreen_draw.py -- --expect-bgl    # 7
"""
import argparse
import importlib.util
import sys

import bpy

SIZE = 64
QUAD = 0.5          # NDC half-extent: covers SIZE/2 x SIZE/2 pixels
LINE_WIDTH = 6.0    # pixels, POLYLINE lineWidth
GPU_INIT_SINCE = (5, 2, 0)
SKIP_REASON = "gpu.init() (drawing under --background) is new in Blender 5.2"


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def read_rgba(fb):
    buf = fb.read_color(0, 0, SIZE, SIZE, 4, 0, "FLOAT")
    buf.dimensions = SIZE * SIZE * 4
    flat = list(buf)
    return [tuple(flat[i:i + 4]) for i in range(0, len(flat), 4)]


def pixel(rows, x, y):
    return rows[y * SIZE + x]


def draw_offscreen(draw):
    """Run draw() bound to a fresh offscreen; return its RGBA rows, then free it."""
    import gpu
    off = gpu.types.GPUOffScreen(SIZE, SIZE)
    try:
        with off.bind():
            fb = gpu.state.active_framebuffer_get()
            gpu.matrix.load_identity()
            draw(fb)
            rows = read_rgba(fb)
            del fb
    finally:
        off.free()
    return rows


def check_quad():
    import gpu
    from gpu_extras.batch import batch_for_shader

    def draw(fb):
        fb.clear(color=(0.0, 0.0, 0.0, 0.0))
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        corners = [(-QUAD, -QUAD), (QUAD, -QUAD), (QUAD, QUAD), (-QUAD, QUAD)]
        batch = batch_for_shader(shader, "TRI_FAN", {"pos": corners})
        shader.uniform_float("color", (1.0, 0.0, 0.0, 1.0))
        batch.draw(shader)

    rows = draw_offscreen(draw)
    covered = sum(1 for r, g, b, a in rows if r > 0.9 and a > 0.9)
    expected = int(SIZE * QUAD) ** 2
    print(f"quad: covered={covered} expected={expected}")
    if covered != expected:
        return fail(f"UNIFORM_COLOR quad covered {covered} pixels, expected {expected}", 4)
    return 0


def check_blend(skip_blend):
    import gpu
    from gpu_extras.batch import batch_for_shader

    def draw(fb):
        fb.clear(color=(0.0, 0.0, 1.0, 1.0))  # opaque blue underneath
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        full = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        batch = batch_for_shader(shader, "TRI_FAN", {"pos": full})
        shader.uniform_float("color", (1.0, 0.0, 0.0, 0.5))
        if not skip_blend:
            gpu.state.blend_set("ALPHA")
        try:
            batch.draw(shader)
        finally:
            gpu.state.blend_set("NONE")

    r, g, b, a = pixel(draw_offscreen(draw), SIZE // 2, SIZE // 2)
    print(f"blend: centre=({r:.3f}, {g:.3f}, {b:.3f}, {a:.3f}) skip_blend={skip_blend}")
    if not (abs(r - 0.5) < 0.02 and abs(b - 0.5) < 0.02):
        return fail(f"half-alpha red over blue gave ({r:.3f}, {g:.3f}, {b:.3f}); "
                    "expected a 50/50 mix: blend_set('ALPHA') was not in effect", 5)
    return 0


def check_line(thin_line):
    import gpu
    from gpu_extras.batch import batch_for_shader
    width = 1.0 if thin_line else LINE_WIDTH

    def draw(fb):
        fb.clear(color=(0.0, 0.0, 0.0, 0.0))
        shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
        batch = batch_for_shader(shader, "LINES", {"pos": [(-0.8, 0.0), (0.8, 0.0)]})
        shader.uniform_float("viewportSize", (SIZE, SIZE))
        shader.uniform_float("lineWidth", width)
        shader.uniform_float("color", (0.0, 1.0, 0.0, 1.0))
        batch.draw(shader)

    rows = draw_offscreen(draw)
    column = [pixel(rows, SIZE // 2, y) for y in range(SIZE)]
    thick = sum(1 for r, g, b, a in column if g > 0.5)
    print(f"line: lineWidth={width} thickness={thick}px at x={SIZE // 2}")
    if abs(thick - LINE_WIDTH) > 1:
        return fail(f"POLYLINE_UNIFORM_COLOR line is {thick}px thick, expected "
                    f"{LINE_WIDTH:.0f} +/- 1", 6)
    return 0


def check_no_bgl(expect_bgl):
    present = importlib.util.find_spec("bgl") is not None
    print(f"bgl: present={present} expect_bgl={expect_bgl}")
    if present != expect_bgl:
        return fail(f"bgl present={present}, expected {expect_bgl}: on 5.x it is removed, "
                    "so code that imports it fails before it draws anything", 7)
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--skip-blend", action="store_true",
                   help="falsification: draw the half-alpha quad without blend_set('ALPHA')")
    p.add_argument("--thin-line", action="store_true",
                   help="falsification: draw the polyline with lineWidth 1")
    p.add_argument("--expect-bgl", action="store_true",
                   help="falsification: the bgl-era assumption that the module exists")
    args = p.parse_args(argv)

    if tuple(bpy.app.version) < GPU_INIT_SINCE:
        print(f"SMOKE_SKIP: {SKIP_REASON}", flush=True)
        return 77

    import gpu
    try:
        gpu.init()
    except SystemError as e:
        return fail(f"gpu.init() failed under --background: {e}", 3)
    print(f"gpu backend: {gpu.platform.backend_type_get()}")

    for code in (check_quad(), check_blend(args.skip_blend), check_line(args.thin_line),
                 check_no_bgl(args.expect_bgl)):
        if code:
            return code
    print("gpu-offscreen-draw OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
