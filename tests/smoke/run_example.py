"""Host-side runner: invoke one Blender script, classify PASS / SKIP / FAIL.

Usage:
  python tests/smoke/run_example.py --name NAME --blender BIN --script PATH
      [--series 5.2] [--min-version 5.0] [--xvfb]
      [--expect-sidecar FILE] [--sidecar-contains TEXT]
      [--forbid-skip] [--status FILE]
      -- extra args passed after Blender's `--`
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from protocol import classify


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_status(path, record):
    if not path:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=True) + "\n")


def build_cmd(args):
    cmd = [args.blender, "--background", "--python", args.script, "--"]
    cmd.extend(args.script_args)
    if args.xvfb:
        cmd = ["xvfb-run", "-a"] + cmd
    return cmd


def run(args):
    sidecar = args.expect_sidecar
    env = os.environ.copy()
    if sidecar:
        env["BDT_SMOKE_SIDECAR"] = sidecar
        parent = os.path.dirname(sidecar)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if os.path.exists(sidecar):
            os.remove(sidecar)

    cmd = build_cmd(args)
    print(f"=== run_example {args.name} ===", flush=True)
    print(" ".join(cmd), flush=True)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    chunks = []
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        chunks.append(line)
    proc.wait()
    output = "".join(chunks)
    proc_exit = proc.returncode if proc.returncode is not None else 1

    status, detail = classify(
        proc_exit=proc_exit,
        output=output,
        min_version=args.min_version,
        blender_version=args.series,
        forbid_skip=args.forbid_skip,
        expect_sidecar=bool(sidecar),
        sidecar_path=sidecar,
        sidecar_contains=args.sidecar_contains,
    )
    record = {
        "name": args.name,
        "status": status,
        "detail": detail,
        "proc_exit": proc_exit,
        "ts": _now(),
    }
    append_status(args.status, record)

    if status == "PASS":
        print(f"[PASS] {args.name}", flush=True)
        return 0
    if status == "SKIP":
        print(f"[SKIP] {args.name}: {detail}", flush=True)
        # Expected skip must not fail the YAML step; summarize counts it.
        return 0
    print(f"[FAIL] {args.name}: {detail}", file=sys.stderr, flush=True)
    return 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--name", required=True)
    p.add_argument("--blender", required=True)
    p.add_argument("--script", required=True)
    p.add_argument("--series", default=None, help="matrix series, e.g. 5.2 or 4.5")
    p.add_argument("--min-version", default=None)
    p.add_argument("--xvfb", action="store_true")
    p.add_argument("--expect-sidecar", default=None)
    p.add_argument("--sidecar-contains", default=None)
    p.add_argument("--forbid-skip", action="store_true")
    p.add_argument(
        "--no-record",
        action="store_true",
        help="do not append to the status file (inverted canaries)",
    )
    p.add_argument(
        "--status",
        default=os.environ.get("BDT_SMOKE_STATUS"),
        help="JSONL status file (default $BDT_SMOKE_STATUS)",
    )
    p.add_argument("script_args", nargs=argparse.REMAINDER)
    args = p.parse_args(argv)
    if args.script_args and args.script_args[0] == "--":
        args.script_args = args.script_args[1:]
    if args.no_record:
        args.status = None
    elif not args.status:
        args.status = None
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
