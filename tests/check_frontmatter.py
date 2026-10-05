#!/usr/bin/env python3
"""Validate skill and rule frontmatter by parsing the leading YAML block.

Only the first ``---`` block is read (a Markdown horizontal rule later in the
body cannot satisfy a missing key). Skills need name (matching the directory),
description and standards-version. Rules need description, standards-version, a
boolean alwaysApply, and non-empty globs given as a string or a list of strings.

    python tests/check_frontmatter.py [--root PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def front(path: Path) -> tuple[dict | None, str]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return None, "missing opening ---"
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return None, "frontmatter is not closed by ---"
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        return None, f"invalid YAML: {exc}"
    if not isinstance(data, dict):
        return None, "frontmatter is not a mapping"
    return data, ""


def need_str(data: dict, key: str, label: str, errors: list[str]) -> None:
    if not isinstance(data.get(key), str) or not data[key].strip():
        errors.append(f"{label}: '{key}' must be a non-empty string")


SKILL_DESCRIPTION_MAX = 1024


def check(root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted((root / "skills").glob("*/SKILL.md")):
        label = path.relative_to(root).as_posix()
        data, why = front(path)
        if data is None:
            errors.append(f"{label}: {why}")
            continue
        for key in ("name", "description", "standards-version"):
            need_str(data, key, label, errors)
        if data.get("name") != path.parent.name:
            errors.append(f"{label}: name {data.get('name')!r} != directory {path.parent.name!r}")
        desc = data.get("description")
        if isinstance(desc, str):
            # Agents pick a skill from its description alone, so it must say
            # when to use it; 1024 is the Agent Skills format's cap (#357, #396).
            if len(desc) > SKILL_DESCRIPTION_MAX:
                errors.append(f"{label}: description is {len(desc)} chars, over "
                              f"{SKILL_DESCRIPTION_MAX}")
            if "Use when" not in desc:
                errors.append(f"{label}: description has no 'Use when ...' trigger clause")
    for path in sorted((root / "rules").glob("*.mdc")):
        label = path.relative_to(root).as_posix()
        data, why = front(path)
        if data is None:
            errors.append(f"{label}: {why}")
            continue
        for key in ("description", "standards-version"):
            need_str(data, key, label, errors)
        if not isinstance(data.get("alwaysApply"), bool):
            errors.append(f"{label}: 'alwaysApply' must be a boolean (got {data.get('alwaysApply')!r})")
        globs = data.get("globs")
        ok = (isinstance(globs, str) and globs.strip()) or (
            isinstance(globs, list) and globs and all(isinstance(g, str) and g.strip() for g in globs)
        )
        if not ok:
            errors.append(f"{label}: 'globs' must be a non-empty string or list of strings")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    errors = check(Path(ap.parse_args().root))
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    if errors:
        return 1
    print("skill and rule frontmatter valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
