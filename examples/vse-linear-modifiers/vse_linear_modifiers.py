"""VSE strip.use_linear_modifiers removal — a runnable example.

Witnesses the 5.2 removal of ``Strip.use_linear_modifiers`` (the RNA
type is ``Strip`` on every targeted version; ``bpy.types.Sequence`` does
not exist on 4.5, 5.1 or 5.2). Access is a
bool on 4.5 LTS and 5.1; the same getattr/setattr raises AttributeError on
5.2. Version-guarded code (``hasattr`` then read) does not raise on any of
the three. Pathology: no geometry, no gallery still.

The default path asserts the behavior that is correct for *this* Blender —
present-and-bool below 5.2, AttributeError on 5.2+ — and still exits 0 on
all three. ``--assume-present`` is the naive script: read the attribute
unconditionally. That is red only on 5.2, where the attribute is gone.

    blender --background --python vse_linear_modifiers.py --
    blender --background --python vse_linear_modifiers.py -- --assume-present
"""
import argparse
import sys

import bpy

ATTR = "use_linear_modifiers"
REMOVED_AT = (5, 2, 0)


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def strips_coll(se):
    return se.strips if hasattr(se, "strips") else se.sequences


def new_color(coll, name, channel, start, length):
    """COLOR strip covering [start, start+length) — version-correct end kwarg."""
    if bpy.app.version >= (5, 0, 0):
        return coll.new_effect(
            name=name, type="COLOR", channel=channel,
            frame_start=start, length=length,
        )
    return coll.new_effect(
        name=name, type="COLOR", channel=channel,
        frame_start=start, frame_end=start + length,
    )


def guarded_read(strip):
    """Version-safe reader: never raises. None means the RNA is gone."""
    if hasattr(strip, ATTR):
        return getattr(strip, ATTR)
    return None


def check(strip, assume_present=False):
    ver = bpy.app.version
    legacy = ver < REMOVED_AT
    require_present = assume_present or legacy
    print(
        f"blender={ver} assume_present={assume_present} "
        f"legacy={legacy} require_present={require_present}"
    )

    present = hasattr(strip, ATTR)
    print(f"hasattr_{ATTR}={present}")

    if require_present:
        if not present:
            return fail(
                f"{ATTR} missing on {ver} — naive/legacy path requires it",
                4,
            )
        try:
            val = getattr(strip, ATTR)
        except AttributeError as exc:
            return fail(f"{ATTR} getattr raised on {ver}: {exc}", 4)
        if type(val) is not bool:
            return fail(f"{ATTR} is {type(val).__name__}={val!r}, not bool", 4)
        flipped = not val
        setattr(strip, ATTR, flipped)
        if getattr(strip, ATTR) is not flipped:
            return fail(f"{ATTR} setattr did not round-trip", 6)
        setattr(strip, ATTR, val)
        print(f"{ATTR}={val} round_trip_ok")
    else:
        if present:
            return fail(
                f"{ATTR} still present on {ver}; 5.2+ must have removed it",
                5,
            )
        try:
            getattr(strip, ATTR)
            return fail(f"{ATTR} getattr returned instead of AttributeError", 5)
        except AttributeError as exc:
            print(f"getattr AttributeError={exc}")

    try:
        guarded = guarded_read(strip)
    except AttributeError as exc:
        return fail(f"hasattr-guarded read still raised: {exc}", 7)
    print(f"guarded_read={guarded!r}")
    if require_present and guarded is None:
        return fail("guarded read returned None while the attribute exists", 7)
    if not require_present and guarded is not None:
        return fail("guarded read returned a value on 5.2+", 7)
    return 0


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    se = scene.sequence_editor_create()
    coll = strips_coll(se)
    strip = new_color(coll, "ProbeColor", channel=1, start=1, length=24)
    return strip


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument(
        "--assume-present",
        action="store_true",
        help="falsification: read use_linear_modifiers as if it still exists",
    )
    args = p.parse_args(argv)

    strip = build()
    if strip is None or strip.bl_rna.identifier != "ColorStrip":
        return fail("COLOR strip was not created", 3)

    code = check(strip, assume_present=args.assume_present)
    if code:
        return code
    print("vse-linear-modifiers OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
