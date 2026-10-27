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
- mcpServers: the core plugin declares none (the live session is opt-in,
  #483). live-session/ (the blender-live-session plugin) declares the same
  file in both of its manifests, and every server in it runs the Blender Lab
  MCP from a full 40-hex commit pin with --exclude-newer, so neither the
  server nor its dependencies float to unreviewed releases (#484)
- live-session manifests: same name, description, version, homepage and
  license as each other, the marketplace entries, and (homepage, license) the
  core plugin
- .codex-plugin/plugin.json: same name, description, version, homepage,
  license and keywords as the others; its interface websiteURL, privacyPolicyURL
  and termsOfServiceURL are the site, its privacy/ and its terms/ pages, and
  build_site.py renders both pages (plugin directories read them, #511); its
  skills path and icon files exist

Run: python tests/check_manifest_meta.py      (exit 0 ok, 1 on mismatch)
"""
from __future__ import annotations

import ast
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE_NEWER = re.compile(r"^\d{4}-\d{2}-\d{2}(T[\d:]+Z)?$")
PINNED_MCP = re.compile(r"^git\+https://projects\.blender\.org/lab/blender_mcp\.git@[0-9a-f]{40}#subdirectory=mcp$")


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

    for name, manifest in ((".cursor-plugin/plugin.json", cursor), (".claude-plugin/plugin.json", claude)):
        if "mcpServers" in manifest:
            errors.append(f"{name} declares mcpServers; the MCP server belongs to the opt-in "
                          "live-session/ plugin (#483)")

    live_cursor = load("live-session/.cursor-plugin/plugin.json")
    live_claude = load("live-session/.claude-plugin/plugin.json")
    live_ref = live_cursor.get("description")
    market_live = {
        ".cursor-plugin/marketplace.json": cursor_market,
        ".claude-plugin/marketplace.json": claude_market,
    }
    for where, market in market_live.items():
        entry = next((e for e in market.get("plugins", []) if e.get("name") == live_cursor.get("name")), None)
        if entry is None:
            errors.append(f"{where} does not list {live_cursor.get('name')!r}")
        elif entry.get("description") != live_ref:
            errors.append(f"{where} {live_cursor.get('name')} description differs from "
                          "live-session/.cursor-plugin/plugin.json")
    for key in ("name", "description", "version", "homepage", "license", "mcpServers"):
        if live_claude.get(key) != live_cursor.get(key):
            errors.append(f"live-session manifests disagree on {key}: "
                          f"{live_claude.get(key)!r} != {live_cursor.get(key)!r}")
    for key in ("homepage", "license", "version"):
        if live_cursor.get(key) != cursor.get(key):
            errors.append(f"live-session {key} {live_cursor.get(key)!r} != core {cursor.get(key)!r}")

    codex = load(".codex-plugin/plugin.json")
    for key in ("name", "description", "version", "homepage", "license"):
        if codex.get(key) != cursor.get(key):
            errors.append(f".codex-plugin/plugin.json {key} {codex.get(key)!r} != "
                          f".cursor-plugin/plugin.json {cursor.get(key)!r}")
    if set(codex.get("keywords", [])) != kw_claude:
        errors.append(".codex-plugin/plugin.json keywords differ from .claude-plugin/plugin.json")
    if "mcpServers" in codex:
        errors.append(".codex-plugin/plugin.json declares mcpServers; the MCP server belongs to "
                      "the opt-in live-session/ plugin (#483)")
    skills = codex.get("skills", "")
    if not isinstance(skills, str) or not (root / skills).is_dir():
        errors.append(f".codex-plugin/plugin.json skills {skills!r} is not a directory")
    # Read LEGAL_PAGES without importing build_site.py (it needs Jinja2).
    tree = ast.parse((root / "scripts" / "site" / "build_site.py").read_text(encoding="utf-8"))
    LEGAL_PAGES = next((ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                        and any(getattr(t, "id", "") == "LEGAL_PAGES" for t in n.targets)), ())
    iface = codex.get("interface") or {}
    site_root = home.rstrip("/") + "/"
    want = {"websiteURL": site_root,
            "privacyPolicyURL": f"{site_root}privacy/",
            "termsOfServiceURL": f"{site_root}terms/"}
    for key, url in want.items():
        if iface.get(key) != url:
            errors.append(f".codex-plugin/plugin.json interface.{key} {iface.get(key)!r} != {url!r}")
    for slug in ("privacy", "terms"):
        if slug not in LEGAL_PAGES:
            errors.append(f"scripts/site/build_site.py LEGAL_PAGES does not render {slug}/, "
                          "which the Codex manifest links")
    for key in ("composerIcon", "logo"):
        path = iface.get(key)
        if path and not (root / path).is_file():
            errors.append(f".codex-plugin/plugin.json interface.{key} {path!r} does not exist")

    mcp = live_cursor.get("mcpServers")
    if not isinstance(mcp, str) or not (root / "live-session" / mcp).is_file():
        errors.append(f"live-session mcpServers {mcp!r} is not a file in live-session/")
    else:
        rel = f"live-session/{mcp.removeprefix('./')}"
        servers = load(rel).get("mcpServers") or {}
        if not servers:
            errors.append(f"{rel} declares no mcpServers")
        for name, server in servers.items():
            args = server.get("args", [])
            src = args[args.index("--from") + 1] if "--from" in args[:-1] else ""
            if server.get("command") != "uvx" or not PINNED_MCP.match(src):
                errors.append(f"{rel} server {name!r} must run uvx --from the Blender Lab repo "
                              "pinned to a full commit SHA")
            newer = args[args.index("--exclude-newer") + 1] if "--exclude-newer" in args[:-1] else ""
            if not EXCLUDE_NEWER.match(newer):
                errors.append(f"{rel} server {name!r} must pass --exclude-newer <date> so its "
                              "dependencies resolve to what was reviewed with the pin (#484)")
    return errors


def main() -> int:
    errors = check()
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    if errors:
        return 1
    print("Manifest metadata consistent: description, homepage, license, keywords, logo, "
          "Codex manifest and its site/privacy/terms URLs, live-session plugin and its "
          "pinned MCP server")
    return 0


if __name__ == "__main__":
    sys.exit(main())
