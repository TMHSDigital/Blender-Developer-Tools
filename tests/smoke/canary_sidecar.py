"""Harness canary: write $BDT_SMOKE_SIDECAR then exit 0.

The host runner asserts the file after this process dies. Pass --omit-sidecar
to prove a missing sidecar is FAIL. Not a shipped example. No gallery still.
"""
import os
import sys

omit = "--omit-sidecar" in sys.argv
path = os.environ.get("BDT_SMOKE_SIDECAR")
if not omit:
    if not path:
        print("ERROR: BDT_SMOKE_SIDECAR unset", file=sys.stderr)
        sys.exit(1)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("sidecar-ok\n")
    print(f"wrote sidecar {path}", flush=True)
else:
    print("omitting sidecar (canary red path)", flush=True)
sys.exit(0)
