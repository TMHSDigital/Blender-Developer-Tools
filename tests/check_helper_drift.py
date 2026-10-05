#!/usr/bin/env python3
"""Report drift between the pipeline helpers showcase pieces copy inline.

Showcase scripts stay self-contained (showcase/README.md), so the pipeline
helpers are duplicated per piece. Nothing tied the copies together, and a fix
found on one piece stayed local: the `is_valid` guard on convex-hull interior
geometry reached 14 copies while 39 kept the unguarded body.

This hashes each top-level function (docstrings and comments ignored) across
showcase/*/*.py and, for every helper named in CANONICAL, lists the variants
and which pieces carry each. A helper may have at most its declared number of
variants; anything beyond that is drift. A helper marked `literals` is hashed
with string constants and ALL_CAPS names blanked, so a per-piece image name or
material index does not count as a new body.

Any function that calls bmesh.ops.convex_hull must be listed here, so a copy
renamed out of CANONICAL is reported instead of drifting unseen (#361).

    python tests/check_helper_drift.py            report; exit 0 (warn-only)
    python tests/check_helper_drift.py --strict   exit 1 when a helper drifts
    python tests/check_helper_drift.py --show NAME  print each variant's source

Validate runs it warn-only: per-piece tuning of a helper can be legitimate,
but it should be a decision recorded here, not an accident.
"""
from __future__ import annotations

import argparse
import ast
import collections
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# helper name -> variants allowed, and why more than one is justified.
CANONICAL = {
    "convex_hull_collider": (4, "one guarded body, plus: dissolve+triangulate for round "
                                "props (anvil, campfire, barrel, bucket), hull from bare "
                                "vertices (farm-tractor), per-group hulls (sea-stack-arch)"),
    "export_unity": (1, "one Unity glTF preset"),
    "hygiene_audit": (7, "per-piece audits report extra keys (euler, nv, edge90)"),
    "pack_uvs": (13, "island margins tuned per piece's texel density"),
    "assign_slots": (20, "material slot layout is per-piece by nature"),
    # #361: helpers that were copied under names the check never saw.
    "hull_collider": (15, "each piece's hull is bespoke: material-filtered points "
                          "(apothecary-shelf), compound per-ring hulls (toboggan); all "
                          "start from bare points, so the #386 edge fix does not apply"),
    "setup_bake_image": (3, "one body, plus the shelf/brazier family that drops the "
                            "BAKE_RES default and the no-UV early return, plus rope-bridge",
                         "literals"),
    "bake_normal": (4, "one body; deselect_all() instead of the inline loop (11 pieces), "
                       "a None guard (bowling-pins), one different bake() argument (grain-sacks)"),
    "face_area": (5, "equivalent fan-triangulation area, written five ways; some drop "
                     "the <3-vertex guard, which polygons never need"),
    "uv_stats": (7, "pairwise AABB overlap, plus a sorted sweep and a bucketed grid for "
                    "high-island pieces; the grid variant returns (..., 0.0, 0) on no UVs"),
    "zfight_pairs": (9, "two algorithms: shell-aware coplanar test (from grindstone) and "
                        "a centre-distance test that skips faces sharing a vertex"),
    "wire_normal": (10, "the baked normal goes under a bump node where the piece has one, "
                        "and each piece finds that node its own way", "literals"),
}

# Functions allowed to call bmesh.ops.convex_hull. Every one must be in CANONICAL.
HULL_CALL = ("bmesh", "ops", "convex_hull")


class _BlankLiterals(ast.NodeTransformer):
    def visit_Constant(self, n):
        return ast.Constant("") if isinstance(n.value, str) else n

    def visit_Name(self, n):
        return ast.Name("K", n.ctx) if n.id.isupper() else n


def _normalised(fn: ast.FunctionDef, literals: bool = False) -> str:
    node = ast.parse(ast.unparse(fn)).body[0]
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        node.body = body[1:] or [ast.Pass()]
    if literals:
        node = _BlankLiterals().visit(node)
    return ast.dump(node)


def _calls_hull(fn: ast.FunctionDef) -> bool:
    return any(isinstance(x, ast.Attribute) and x.attr == HULL_CALL[2]
               and ast.unparse(x.value) == ".".join(HULL_CALL[:2]) for x in ast.walk(fn))


def unlisted_hull_callers() -> list[str]:
    """`piece:function` for every bmesh.ops.convex_hull caller not in CANONICAL."""
    out = []
    for script in sorted(ROOT.glob("showcase/*/*.py")):
        for node in ast.parse(script.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef) and node.name not in CANONICAL \
                    and _calls_hull(node):
                out.append(f"{script.parent.name}:{node.name}")
    return out


def variants() -> dict[str, dict[str, list[tuple[str, str]]]]:
    """name -> hash -> [(piece, source)]"""
    out: dict = collections.defaultdict(lambda: collections.defaultdict(list))
    for script in sorted(ROOT.glob("showcase/*/*.py")):
        tree = ast.parse(script.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in CANONICAL:
                literals = "literals" in CANONICAL[node.name][2:]
                h = hashlib.sha1(_normalised(node, literals).encode()).hexdigest()[:8]
                out[node.name][h].append((script.parent.name, ast.unparse(node)))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--show", default=None)
    a = ap.parse_args(argv)
    found = variants()
    drift = False
    for name, (allowed, why, *_flags) in CANONICAL.items():
        groups = sorted(found.get(name, {}).items(), key=lambda kv: -len(kv[1]))
        n = len(groups)
        over = n > allowed
        drift |= over
        tag = "DRIFT" if over else "ok"
        print(f"{tag:5} {name}: {n} variant(s), allowed {allowed} ({why})")
        if over or a.show == name:
            for h, pieces in groups:
                names = ", ".join(p for p, _ in pieces)
                print(f"        {h} x{len(pieces)}: {names}")
                if a.show == name:
                    print("\n".join("          " + l for l in pieces[0][1].splitlines()))
    for caller in unlisted_hull_callers():
        drift = True
        print(f"DRIFT {caller} calls bmesh.ops.convex_hull but is not in CANONICAL")
    if drift:
        msg = "helper drift: copies of a shared helper disagree (see above)"
        if a.strict:
            print(f"::error::{msg}", file=sys.stderr)
            return 1
        print(f"::warning::{msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
