"""Print PASS/SKIP/FAIL counts from a JSONL status file.

Exit 0 if at least one PASS and no FAIL.
Exit 1 if any FAIL.
Exit 2 if every recorded example skipped (or nothing ran) — a green all-skip is illegal.

Writes GitHub step summary when $GITHUB_STEP_SUMMARY is set.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from protocol import summarize_records


def load(path):
    if not path or not os.path.isfile(path):
        return []
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def render(records, passed, skipped, failed):
    lines = [
        "## Smoke summary",
        "",
        f"**{passed} passed**, **{skipped} skipped**, **{failed} failed**",
        "",
        "| Example | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for rec in records:
        detail = (rec.get("detail") or "").replace("|", "\\|")
        lines.append(f"| {rec['name']} | {rec['status']} | {detail} |")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--status",
        default=os.environ.get("BDT_SMOKE_STATUS"),
        required=False,
    )
    args = p.parse_args(argv)
    records = load(args.status)
    passed, skipped, failed, code = summarize_records(records)
    text = render(records, passed, skipped, failed)
    print(text)
    if code == 2:
        print(
            "FAIL: every example skipped (or none ran); job is not green",
            file=sys.stderr,
        )
    gh = os.environ.get("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as fh:
            fh.write(text)
            fh.write("\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
