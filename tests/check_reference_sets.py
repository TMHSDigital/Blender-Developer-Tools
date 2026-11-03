#!/usr/bin/env python3
"""CLAUDE.md names the same gallery reference sets as scripts/gallery_refs.py (#523).

The sets used to be parsed out of CLAUDE.md prose by scripts/asset_sheet.py
(rewording one sentence broke the tool and emptied a gate's list) or hard-coded
in scripts/contact_sheet.py while CLAUDE.md claimed to be canonical. The code
now reads scripts/gallery_refs.py; this check keeps the CLAUDE.md bullets an
accurate mirror. It fails loudly when a bullet cannot be found, never passes on
an empty read.

    python tests/check_reference_sets.py      (exit 0 ok, 1 on drift)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from gallery_refs import ASSET_SET, CONTACT_SET  # noqa: E402

# Bullet label in CLAUDE.md -> the set it must name.
BULLETS = {
    "Contact-sheet gate": CONTACT_SET,
    "Asset-sheet gate": ASSET_SET,
}


def bullet(text: str, label: str) -> str | None:
    """The CLAUDE.md list item whose bold label starts with `label`."""
    m = re.search(rf"^- \*\*{re.escape(label)}[^\n]*(?:\n(?!- |\n|#)[^\n]*)*", text, re.M)
    return m.group(0) if m else None


def named_set(item: str) -> list[str]:
    """Backticked names after 'currently', up to the end of that sentence."""
    m = re.search(r"currently(.+?)(?:\.\s|;|\s—\s(?![`]))", item, re.S)
    span = m.group(1) if m else ""
    return re.findall(r"`([a-z0-9-]+)`", span)


def check(root: Path = ROOT) -> list[str]:
    text = (root / "CLAUDE.md").read_text(encoding="utf-8")
    errors = []
    for label, want in BULLETS.items():
        item = bullet(text, label)
        if item is None:
            errors.append(f"CLAUDE.md has no '- **{label}' bullet")
            continue
        got = named_set(item)
        if not got:
            errors.append(f"CLAUDE.md '{label}' bullet names no set after 'currently'")
        elif set(got) != set(want):
            errors.append(f"CLAUDE.md '{label}' names {got}, scripts/gallery_refs.py has {list(want)}")
    return errors


def main() -> int:
    errors = check()
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    if not errors:
        print(f"reference sets match CLAUDE.md: contact {len(CONTACT_SET)}, asset {len(ASSET_SET)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
