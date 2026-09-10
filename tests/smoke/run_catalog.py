"""Run every shipped example through run_example.classify via run_example.py.

Stops on the first FAIL (same fail-fast as the previous per-step YAML).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--blender", required=True)
    p.add_argument("--catalog", default=os.path.join(HERE, "catalog.json"))
    p.add_argument("--series", required=True)
    p.add_argument("--status", default=os.environ.get("BDT_SMOKE_STATUS"))
    p.add_argument("--out", required=True, help="scratch dir for --output renders")
    p.add_argument("--xvfb", action="store_true")
    args = p.parse_args(argv)

    with open(args.catalog, encoding="utf-8") as fh:
        catalog = json.load(fh)

    os.makedirs(args.out, exist_ok=True)
    runner = os.path.join(HERE, "run_example.py")
    n = 0
    for item in catalog:
        n += 1
        name = item["name"]
        script = item["script"]
        extra = list(item.get("args") or [])
        extra = [a.replace("$OUT", args.out) for a in extra]
        cmd = [
            sys.executable,
            runner,
            "--name",
            name,
            "--blender",
            args.blender,
            "--script",
            script,
            "--series",
            args.series,
            "--status",
            args.status or "",
        ]
        if args.xvfb:
            cmd.append("--xvfb")
        if item.get("min_version"):
            cmd.extend(["--min-version", item["min_version"]])
        if item.get("expect_sidecar"):
            cmd.extend([
                "--expect-sidecar",
                item["expect_sidecar"].replace("$OUT", args.out),
            ])
        if item.get("sidecar_contains"):
            cmd.extend(["--sidecar-contains", item["sidecar_contains"]])
        if extra:
            cmd.append("--")
            cmd.extend(extra)
        print(f"::group::{name}", flush=True)
        code = subprocess.call(cmd)
        print("::endgroup::", flush=True)
        if code != 0:
            print(f"catalog abort at {name} (exit {code})", file=sys.stderr)
            return code
        expect = item.get("expect_file")
        if expect:
            expect = expect.replace("$OUT", args.out)
            if not os.path.isfile(expect) or os.path.getsize(expect) == 0:
                print(f"ERROR: expected output missing {expect}", file=sys.stderr)
                return 1
    print(f"catalog finished {n} entries", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
