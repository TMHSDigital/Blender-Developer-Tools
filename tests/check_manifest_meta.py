#!/usr/bin/env python3
"""The Cursor and Claude Code manifests must describe the plugin the same way (#454).

Both plugin listings are where install decisions get made, so they must not
drift apart again. Checks, with .cursor-plugin/plugin.json as the reference:

- description: identical in both plugin.json files and both marketplace
  plugin entries
- homepage: the site (site.json "canonical") in both plugin.json files
- license: identical in both plugin.json files and in the committed gallery
  footer (the landing footer reads the Cursor manifest directly)
- keywords: the same set, apart from the agent-specific "cursor-plugin"
- logo: the Cursor manifest names one, it exists, and the plugin-dist build
  ships it (scripts/build_plugin_dist.py FILES)

Run: python tests/check_manifest_meta.py      (exit 0 ok, 1 on mismatch)
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def check() -> list[str]:
    root = ROOT
    errors: list[str] = []
    cursor = load(".cursor-plugin/plugin.json")
    cursor_market = load(".cursor-plugin/marketplace.json")
    claude = load(".claude-plugin/plugin.json")
    claude_market = load(".claude-plugin/marketplace.json")
    site = load("site.json")

    ref = cursor.get("description", "")
    others = {
        ".claude-plugin/plugin.json description": claude.get("description"),
        ".cursor-plugin/marketplace.json plugin description":
            (cursor_market.get("plugins") or [{}])[0].get("description"),
        ".claude-plugin/marketplace.json plugin description":
            (claude_market.get("plugins") or [{}])[0].get("description"),
    }
    for where, value in others.items():
        if value != ref:
            errors.append(f"{where} differs from .cursor-plugin/plugin.json description")

    home = site.get("canonical", "")
    for name, manifest in ((".cursor-plugin/plugin.json", cursor), (".claude-plugin/plugin.json", claude)):
        if manifest.get("homepage") != home:
            errors.append(f"{name} homepage {manifest.get('homepage')!r} != site.json canonical {home!r}")

    lic = cursor.get("license", "")
    if claude.get("license") != lic:
        errors.append(f".claude-plugin/plugin.json license {claude.get('license')!r} != {lic!r}")
    gallery = root / "docs" / "gallery" / "index.html"
    if gallery.is_file() and f"<span>{html.escape(lic)}</span>" not in gallery.read_text(encoding="utf-8"):
        errors.append(f"docs/gallery/index.html footer does not show the license {lic!r}; "
                      "run python scripts/build_gallery.py")

    kw_cursor = set(cursor.get("keywords", [])) - {"cursor-plugin"}
    kw_claude = set(claude.get("keywords", []))
    if kw_cursor != kw_claude:
        errors.append(f"keywords differ: only Cursor {sorted(kw_cursor - kw_claude)}, "
                      f"only Claude {sorted(kw_claude - kw_cursor)}")

    logo = cursor.get("logo")
    if not logo:
        errors.append(".cursor-plugin/plugin.json has no logo")
    else:
        if not (root / logo).is_file():
            errors.append(f".cursor-plugin/plugin.json logo {logo!r} does not exist")
        sys.path.insert(0, str(root / "scripts"))
        from build_plugin_dist import FILES  # noqa: E402
        if logo not in FILES:
            errors.append(f"logo {logo!r} is not shipped in the plugin-dist build "
                          "(scripts/build_plugin_dist.py FILES)")
    return errors


def main() -> int:
    errors = check()
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    if errors:
        return 1
    print("Manifest metadata consistent: description, homepage, license, keywords, logo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
