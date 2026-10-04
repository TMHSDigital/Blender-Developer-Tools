"""Host-side runner: invoke one Blender script, classify PASS / SKIP / FAIL.

Usage:
  python tests/smoke/run_example.py --name NAME --blender BIN --script PATH
      [--series 5.2] [--min-version 5.0] [--xvfb]
      [--expect-sidecar FILE] [--sidecar-contains TEXT]
      [--forbid-skip] [--status FILE] [--timeout SECONDS]
      -- extra args passed after Blender's `--`

--timeout (default $BDT_SMOKE_TIMEOUT or 900 s) bounds one Blender run. On
expiry the whole process group (xvfb-run and Blender) is killed and the run is
recorded as FAIL "timeout after Ns", so one hang cannot eat the CI job.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
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
    cmd = [args.blender, "--background", "--python-exit-code", "1", "--python", args.script, "--"]
    cmd.extend(args.script_args)
    if args.xvfb:
        cmd = ["xvfb-run", "-a"] + cmd
    return cmd


DEFAULT_TIMEOUT = 900


def _kill_tree(proc):
    """Kill proc and everything it spawned (xvfb-run starts Blender as a child)."""
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, check=False)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def stream(cmd, env=None, timeout=None):
    """Run cmd, echo its combined output live, return (exit code or None, output).

    None means the run was killed after `timeout` seconds. Output is decoded as
    UTF-8 with replacement: Blender writes UTF-8 whatever the host locale is,
    and a strict cp1252 decode would raise mid-run and orphan Blender.
    """
    popen_kw = {"start_new_session": True} if os.name == "posix" else {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        **popen_kw,
    )
    chunks = []

    def pump():
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            chunks.append(line)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    try:
        proc.wait(timeout=timeout)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        proc.wait()
        code = None
    reader.join(timeout=10)
    return code, "".join(chunks)


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

    code, output = stream(cmd, env=env, timeout=args.timeout)
    if code is None:
        proc_exit = None
        status, detail = "FAIL", f"timeout after {args.timeout:g}s (process group killed)"
    else:
        proc_exit = code
        status, detail = classify(
            proc_exit=proc_exit,
            output=output,
            min_version=args.min_version,
            blender_version=args.series,
            forbid_skip=args.forbid_skip,
            expect_sidecar=bool(sidecar),
            sidecar_path=sidecar,
            sidecar_contains=args.sidecar_contains,
            expect_exit=args.expect_exit,
            expect_sidecar_fail=args.expect_sidecar_fail,
        )
    record = {
        "name": args.name,
        "status": status,
        "detail": detail,
        "proc_exit": proc_exit,
        "ts": _now(),
    }
    if args.expect_exit is not None or args.expect_sidecar_fail:
        record["falsifier"] = True
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
        "--expect-exit", type=int, default=None,
        help="falsifier run: PASS only if Blender exits exactly this code",
    )
    p.add_argument(
        "--expect-sidecar-fail", action="store_true",
        help="falsifier run: PASS only if the script exits 0 and the sidecar check fails",
    )
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
    p.add_argument(
        "--timeout", type=float,
        default=float(os.environ.get("BDT_SMOKE_TIMEOUT") or DEFAULT_TIMEOUT),
        help="seconds before the run is killed and recorded as FAIL",
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
