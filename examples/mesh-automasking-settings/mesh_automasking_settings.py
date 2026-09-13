"""MeshAutomaskingSettings move — a runnable example.

Witnesses the 5.2 move of sculpt automasking RNA off ``Brush`` into
``MeshAutomaskingSettings``, reached via ``.mesh_automasking_settings``.
The old ``Brush.use_automasking_*`` / ``Brush.automasking_*`` attributes
are a bool/float you can read on 4.5 LTS and 5.1; the same getattr raises
AttributeError on 5.2. Version-guarded code (current location, with a
Brush fallback) reads on all three.

Pathology: no geometry, no gallery still. Factory-empty has zero brushes;
the script creates one with ``bpy.data.brushes.new(..., mode="SCULPT")``.
``mode="SCULPT"`` is load-bearing on 5.2: a default-mode ``new(name)``
leaves ``mesh_automasking_settings is None``.

Subset (location move + nested identifier shortening, not all 18+):

- ``use_automasking_topology`` — bool, same identifier in both places
- ``use_automasking_cavity`` — bool, same identifier in both places
- cavity factor — ``Brush.automasking_cavity_factor`` vs
  ``MeshAutomaskingSettings.cavity_factor``

    blender --background --python mesh_automasking_settings.py --
    blender --background --python mesh_automasking_settings.py -- --assume-brush-attrs
"""
import argparse
import sys

import bpy

MOVED_AT = (5, 2, 0)
BRUSH_NAME = "ProbeBrush"


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def type_present():
    return hasattr(bpy.types, "MeshAutomaskingSettings")


def read_current(brush):
    """Version-safe reader. None mas falls through to the Brush attrs."""
    mas = getattr(brush, "mesh_automasking_settings", None)
    if mas is not None:
        return (
            mas.use_automasking_topology,
            mas.use_automasking_cavity,
            mas.cavity_factor,
        )
    return (
        brush.use_automasking_topology,
        brush.use_automasking_cavity,
        brush.automasking_cavity_factor,
    )


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    n_before = len(bpy.data.brushes)
    brush = bpy.data.brushes.new(BRUSH_NAME, mode="SCULPT")
    return brush, n_before


def check(brush, n_before, assume_brush_attrs=False):
    ver = tuple(bpy.app.version)
    legacy = ver < MOVED_AT
    require_brush_attrs = assume_brush_attrs or legacy
    print(
        f"blender={ver} assume_brush_attrs={assume_brush_attrs} "
        f"legacy={legacy} require_brush_attrs={require_brush_attrs} "
        f"n_brushes_before={n_before} created={BRUSH_NAME!r}"
    )

    if brush is None or brush.bl_rna.identifier != "Brush":
        return fail("SCULPT brush was not created", 3)

    present = type_present()
    print(f"MeshAutomaskingSettings_type={present}")
    if legacy and present:
        return fail(
            f"MeshAutomaskingSettings exists on {ver}; it must not before 5.2",
            4,
        )
    if not legacy and not present:
        return fail(
            f"MeshAutomaskingSettings missing on {ver}; 5.2+ must define it",
            4,
        )

    has_topo = hasattr(brush, "use_automasking_topology")
    has_cavity = hasattr(brush, "use_automasking_cavity")
    has_factor = hasattr(brush, "automasking_cavity_factor")
    mas = getattr(brush, "mesh_automasking_settings", None)
    print(
        f"brush.use_automasking_topology={has_topo} "
        f"use_automasking_cavity={has_cavity} "
        f"automasking_cavity_factor={has_factor} "
        f"mesh_automasking_settings={mas!r}"
    )

    if require_brush_attrs:
        if not (has_topo and has_cavity and has_factor):
            return fail(
                "old Brush automasking attributes missing when required "
                f"(topo={has_topo} cavity={has_cavity} factor={has_factor})",
                5,
            )
        try:
            topo = brush.use_automasking_topology
            cavity = brush.use_automasking_cavity
            factor = brush.automasking_cavity_factor
        except AttributeError as exc:
            return fail(f"old Brush getattr raised on {ver}: {exc}", 5)
        print(
            f"legacy_read topology={topo!r} cavity={cavity!r} "
            f"automasking_cavity_factor={factor!r}"
        )
        if type(topo) is not bool or type(cavity) is not bool:
            return fail(
                f"legacy topology/cavity not bool: {type(topo).__name__}/"
                f"{type(cavity).__name__}",
                5,
            )
        if type(factor) is not float:
            return fail(
                f"legacy automasking_cavity_factor is "
                f"{type(factor).__name__}={factor!r}, not float",
                5,
            )
    else:
        if has_topo or has_cavity or has_factor:
            return fail(
                "old Brush automasking attributes still present on 5.2+",
                6,
            )
        if mas is None:
            return fail(
                "mesh_automasking_settings is None on 5.2+ "
                "(create with mode='SCULPT')",
                6,
            )

    try:
        topo, cavity, factor = read_current(brush)
    except AttributeError as exc:
        return fail(f"current-location read raised: {exc}", 7)
    print(
        f"current_read topology={topo!r} cavity={cavity!r} "
        f"cavity_factor={factor!r}"
    )
    if type(topo) is not bool or type(cavity) is not bool:
        return fail(
            f"current topology/cavity not bool: {type(topo).__name__}/"
            f"{type(cavity).__name__}",
            7,
        )
    if type(factor) is not float:
        return fail(
            f"current cavity_factor is {type(factor).__name__}={factor!r}, "
            "not float",
            7,
        )
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument(
        "--assume-brush-attrs",
        action="store_true",
        help="falsification: read automasking off Brush as if it never moved",
    )
    args = p.parse_args(argv)

    brush, n_before = build()
    code = check(brush, n_before, assume_brush_attrs=args.assume_brush_attrs)
    if code:
        return code
    print("mesh-automasking-settings OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
