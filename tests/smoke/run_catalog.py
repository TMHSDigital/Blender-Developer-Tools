"""Run every shipped example through run_example.classify via run_example.py.

Runs every row and exits non-zero at the end listing all failures, so one PR
shows every broken example in one CI round-trip. ``--fail-fast`` restores
stop-at-first-failure. An empty catalog is a failure, not a pass.

Each row also lists ``falsifiers``: inputs that must break the contract. Every
one runs after the row's happy path and must fail exactly as declared
(``expect_exit: N``, or ``expect_sidecar_fail: true`` for a falsifier the
post-exit sidecar check catches). A check that can no longer fail turns the
job red here instead of passing silently. ``--no-falsifiers`` skips them.
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
    p.add_argument("--fail-fast", action="store_true", help="stop at the first failure")
    p.add_argument("--no-falsifiers", action="store_true",
                   help="run only the happy paths (local iteration; CI runs falsifiers)")
    args = p.parse_args(argv)

    with open(args.catalog, encoding="utf-8") as fh:
        catalog = json.load(fh)
    if not catalog:
        print("ERROR: catalog is empty; nothing would be smoke-tested", file=sys.stderr)
        return 1

    os.makedirs(args.out, exist_ok=True)
    runner = os.path.join(HERE, "run_example.py")
    n = 0
    n_falsifiers = 0
    failures = []
    def row_cmd(item, run_name, extra, falsifier=None):
        cmd = [
            sys.executable, runner,
            "--name", run_name,
            "--blender", args.blender,
            "--script", item["script"],
            "--series", args.series,
            "--status", args.status or "",
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
        if falsifier is not None:
            if falsifier.get("expect_sidecar_fail"):
                cmd.append("--expect-sidecar-fail")
            else:
                cmd.extend(["--expect-exit", str(falsifier["expect_exit"])])
        if extra:
            cmd.append("--")
            cmd.extend(extra)
        return cmd

    for item in catalog:
        n += 1
        name = item["name"]
        base_args = [a.replace("$OUT", args.out) for a in (item.get("args") or [])]
        print(f"::group::{name}", flush=True)
        code = subprocess.call(row_cmd(item, name, base_args))
        print("::endgroup::", flush=True)
        if code != 0:
            print(f"catalog FAIL {name} (exit {code})", file=sys.stderr)
            failures.append(f"{name} (exit {code})")
            if args.fail_fast:
                break
        else:
            expect = item.get("expect_file")
            if expect:
                expect = expect.replace("$OUT", args.out)
                if not os.path.isfile(expect) or os.path.getsize(expect) == 0:
                    print(f"ERROR: expected output missing {expect}", file=sys.stderr)
                    failures.append(f"{name} (missing {expect})")
                    if args.fail_fast:
                        break
        if args.no_falsifiers:
            continue
        for fz in item.get("falsifiers") or []:
            fargs = [a.replace("$OUT", args.out) for a in fz["args"]]
            label = f"{name} [falsifier {' '.join(fz['args'])}]"
            n_falsifiers += 1
            print(f"::group::{label}", flush=True)
            fcode = subprocess.call(row_cmd(item, label, base_args + fargs, fz))
            print("::endgroup::", flush=True)
            if fcode != 0:
                print(f"catalog FAIL {label}", file=sys.stderr)
                failures.append(label)
                if args.fail_fast:
                    break
        if failures and args.fail_fast:
            break
    print(f"catalog finished {n} of {len(catalog)} entries, {n_falsifiers} falsifier run(s)",
          flush=True)
    if failures:
        print(f"{len(failures)} catalog failure(s):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
