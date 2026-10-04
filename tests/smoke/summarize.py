"""Print PASS/SKIP/FAIL counts from a JSONL status file.

Exit 0 if at least one PASS and no FAIL.
Exit 1 if any FAIL.
Exit 2 if every recorded example skipped (or nothing ran) — a green all-skip is illegal.

Falsifier runs (records with "falsifier": true) are counted and tabled
separately: a falsifier PASS means the contract broke as declared, so it must
not make an all-skip example run look green, and any falsifier FAIL is red.

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


def _table(title, records, counts, noun):
    passed, skipped, failed = counts
    lines = [
        title,
        "",
        f"**{passed} passed**, **{skipped} skipped**, **{failed} failed**",
        "",
        f"| {noun} | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for rec in records:
        detail = (rec.get("detail") or "").replace("|", "\\|")
        lines.append(f"| {rec['name']} | {rec['status']} | {detail} |")
    lines.append("")
    return lines


def render(records, passed, skipped, failed, falsifiers=(), fcounts=(0, 0, 0)):
    lines = _table("## Smoke summary", records, (passed, skipped, failed), "Example")
    if falsifiers:
        lines += _table("## Falsifiers (each must fail exactly as declared)",
                        falsifiers, fcounts, "Falsifier")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--status",
        default=os.environ.get("BDT_SMOKE_STATUS"),
        required=False,
    )
    args = p.parse_args(argv)
    allrec = load(args.status)
    records = [r for r in allrec if not r.get("falsifier")]
    falsifiers = [r for r in allrec if r.get("falsifier")]
    passed, skipped, failed, code = summarize_records(records)
    fpassed, fskipped, ffailed, _ = summarize_records(falsifiers)
    if ffailed and code == 0:
        code = 1
    text = render(records, passed, skipped, failed, falsifiers,
                  (fpassed, fskipped, ffailed))
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
