"""exit_pre post-exit sidecar — a runnable example.

Witnesses ``bpy.app.handlers.exit_pre`` from
``skills/drivers-and-app-handlers``. The callback fires as Blender dies.
This script does **not** write ``$BDT_SMOKE_SIDECAR`` in ``main``; the
handler writes it. The host runner (``tests/smoke/run_example.py``)
asserts the file after the process exits.

5.1+. 4.5 LTS has no ``exit_pre`` (AttributeError). Catalog
``min_version`` 5.0 is wrong — the floor is 5.1. Skip: ``SMOKE_SKIP``.
``--force-run`` bypasses the skip so 4.5 fails accessing ``exit_pre``.

No gallery still. There is no geometry.

    blender --background --python exit_pre_sidecar.py --
"""
import argparse
import atexit
import os
import sys

import bpy
from bpy.app.handlers import persistent

SKIP_REASON = "exit_pre requires Blender 5.1+"
MARKER = "exit_pre-ok"
MAIN_MARKER = "from-main"
WRONG_MARKER = "nope"
ATEXIT_MARKER = "atexit-ok"


def sidecar_path():
    path = os.environ.get("BDT_SMOKE_SIDECAR")
    if not path:
        print("ERROR: BDT_SMOKE_SIDECAR unset", file=sys.stderr)
        return None
    return path


def write_sidecar(text):
    path = sidecar_path()
    if not path:
        return False
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")
    return True


@persistent
def on_exit_write(*args):
    write_sidecar(MARKER)


@persistent
def on_exit_silent(*args):
    return


@persistent
def on_exit_wrong(*args):
    write_sidecar(WRONG_MARKER)


def on_atexit():
    write_sidecar(ATEXIT_MARKER)


def maybe_skip(force_run):
    if bpy.app.version >= (5, 1, 0):
        return 0
    if force_run:
        return 0
    print(f"SMOKE_SKIP: {SKIP_REASON}", flush=True)
    return 77


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument(
        "--force-run",
        action="store_true",
        help="bypass the 5.1 skip; 4.5 fails accessing handlers.exit_pre",
    )
    p.add_argument(
        "--silent-handler",
        action="store_true",
        help="falsification: register exit_pre that writes nothing",
    )
    p.add_argument(
        "--wrong-text",
        action="store_true",
        help="falsification: handler writes nope, not exit_pre-ok",
    )
    p.add_argument(
        "--no-handler",
        action="store_true",
        help="falsification: do not register exit_pre, do not write in main",
    )
    p.add_argument(
        "--write-in-main",
        action="store_true",
        help="falsification: write from-main in main without exit_pre",
    )
    p.add_argument(
        "--atexit-instead",
        action="store_true",
        help="falsification: atexit writes atexit-ok, not exit_pre",
    )
    args = p.parse_args(argv)

    skipped = maybe_skip(args.force_run)
    if skipped:
        return skipped

    if args.force_run and bpy.app.version < (5, 1, 0):
        try:
            bpy.app.handlers.exit_pre.append(on_exit_write)
        except AttributeError as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        print("ERROR: exit_pre existed on this Blender; 4.5 should AttributeError", file=sys.stderr)
        return 2

    if sidecar_path() is None:
        return 1

    if args.write_in_main:
        write_sidecar(MAIN_MARKER)
        print("wrote sidecar from main (no exit_pre)", flush=True)
        return 0

    if args.no_handler:
        print("no exit_pre registered", flush=True)
        return 0

    if args.atexit_instead:
        atexit.register(on_atexit)
        print("registered atexit, not exit_pre", flush=True)
        return 0

    if args.silent_handler:
        bpy.app.handlers.exit_pre.append(on_exit_silent)
        print("registered silent exit_pre", flush=True)
        return 0

    if args.wrong_text:
        bpy.app.handlers.exit_pre.append(on_exit_wrong)
        print("registered exit_pre writing nope", flush=True)
        return 0

    bpy.app.handlers.exit_pre.append(on_exit_write)
    print("registered exit_pre", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
