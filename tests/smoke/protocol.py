"""Skip / pass / fail classification for the host smoke harness.

Blender example scripts have two legal ways to finish:

* exit 0 — ran and passed (then optional post-exit sidecar)
* exit 77 with a ``SMOKE_SKIP: <reason>`` line — unsupported on this Blender

Anything else is FAIL, including the vacuous-pass vector: printing a skip
marker and exiting 0, or exiting 77 on a version that should run.
"""
from __future__ import annotations

import os
from typing import Optional, Tuple

SKIP_EXIT = 77
SKIP_PREFIX = "SMOKE_SKIP:"

PASS = "PASS"
SKIP = "SKIP"
FAIL = "FAIL"


def parse_version(spec: str) -> Tuple[int, ...]:
    """'5.2' or '5.2.1' or '5.0' -> comparable tuple (pad to 3)."""
    parts = []
    for p in spec.strip().split("."):
        if not p.isdigit():
            raise ValueError(f"not a version spec: {spec!r}")
        parts.append(int(p))
    if not parts:
        raise ValueError(f"empty version spec: {spec!r}")
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def parse_skip_reason(output: str) -> Optional[str]:
    for line in output.splitlines():
        s = line.strip()
        if s.startswith(SKIP_PREFIX):
            reason = s[len(SKIP_PREFIX):].strip()
            return reason or None
    return None


def sidecar_ok(path: Optional[str], contains: Optional[str]) -> Tuple[bool, str]:
    if not path:
        return False, "sidecar path not set"
    if not os.path.isfile(path):
        return False, f"missing post-exit sidecar {path}"
    if os.path.getsize(path) == 0:
        return False, f"empty post-exit sidecar {path}"
    if contains:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if contains not in text:
            return False, f"sidecar missing expected text {contains!r}"
    return True, ""


def classify(
    *,
    proc_exit: int,
    output: str,
    min_version: Optional[str] = None,
    blender_version: Optional[str] = None,
    forbid_skip: bool = False,
    expect_sidecar: bool = False,
    sidecar_path: Optional[str] = None,
    sidecar_contains: Optional[str] = None,
) -> Tuple[str, str]:
    """Return (PASS|SKIP|FAIL, detail).

    Skip is legal only when ``min_version`` is set and ``blender_version``
    is strictly below it (and ``forbid_skip`` is false). An expected skip
    does not require a sidecar.
    """
    reason = parse_skip_reason(output)
    skipped = proc_exit == SKIP_EXIT

    if proc_exit == 0 and reason is not None:
        return FAIL, "SMOKE_SKIP marker with exit 0 (vacuous skip)"

    if skipped:
        if not reason:
            return FAIL, f"exit {SKIP_EXIT} without SMOKE_SKIP reason"
        if forbid_skip:
            return FAIL, f"skipped where skip is forbidden: {reason}"
        if min_version is None:
            return FAIL, f"skipped with no --min-version (unexpected): {reason}"
        if blender_version is None:
            return FAIL, f"skipped but blender version unknown: {reason}"
        if parse_version(blender_version) >= parse_version(min_version):
            return (
                FAIL,
                f"skipped on {blender_version} but min-version {min_version} "
                f"(should run): {reason}",
            )
        return SKIP, reason

    if proc_exit != 0:
        return FAIL, f"blender exit {proc_exit}"

    if expect_sidecar:
        ok, detail = sidecar_ok(sidecar_path, sidecar_contains)
        if not ok:
            return FAIL, detail

    return PASS, ""


def summarize_records(records):
    """records: iterable of dicts with 'status' key.

    Returns (passed, skipped, failed, harness_exit).
    harness_exit is 0 on mixed pass+skip, 1 if any FAIL, 2 if zero PASS.
    """
    passed = skipped = failed = 0
    for rec in records:
        st = rec["status"]
        if st == PASS:
            passed += 1
        elif st == SKIP:
            skipped += 1
        else:
            failed += 1
    if failed:
        return passed, skipped, failed, 1
    if passed == 0:
        return passed, skipped, failed, 2
    return passed, skipped, failed, 0
