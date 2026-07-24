#!/usr/bin/env python3
"""Build a GitHub Pages site from plugin metadata and a Jinja2 template.

Reads .cursor-plugin/plugin.json, site.json, skills/, rules/, and
mcp-tools.json from a tool repository and renders a single-page site.
"""

import argparse
import datetime
import json
import re
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def load_json(path: Path) -> dict | list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Extract YAML frontmatter and return (metadata_dict, body_after_frontmatter)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text

    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}, text

    meta: dict[str, str] = {}
    for line in lines[1:end_idx]:
        if ":" in line and not line.strip().startswith("-"):
            key, _, val = line.partition(":")
            meta[key.strip().lower()] = val.strip()

    body = "".join(lines[end_idx + 1:])
    return meta, body


def _extract_tools_from_frontmatter(lines: list[str]) -> list[str]:
    """Parse a YAML list of tools from frontmatter lines (handles ``tools:`` key)."""
    tools: list[str] = []
    in_tools = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("tools:"):
            in_tools = True
            continue
        if in_tools:
            if stripped.startswith("- "):
                tools.append(stripped[2:].strip())
            else:
                break
    return tools


def _extract_trigger_section(body: str) -> list[str]:
    """Pull bullet items from the ``## Trigger`` section of a SKILL.md body."""
    triggers: list[str] = []
    in_trigger = False
    for line in body.splitlines():
        stripped = line.strip()
        if re.match(r"^##\s+Trigger", stripped, re.IGNORECASE):
            in_trigger = True
            continue
        if in_trigger:
            if stripped.startswith("##"):
                break
            if stripped.startswith("- "):
                triggers.append(stripped[2:].strip())
    return triggers


def _truncate_words(text: str, limit: int) -> str:
    """Cut *text* at a word boundary under *limit* chars, with an ellipsis."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def parse_skills(repo_root: Path) -> list[dict]:
    skills_dir = repo_root / "skills"
    if not skills_dir.is_dir():
        return []

    results = []
    for skill_dir in sorted(skills_dir.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue

        text = skill_file.read_text(encoding="utf-8", errors="replace")
        meta, body = parse_frontmatter(text)

        name = meta.get("name", "").replace("-", " ").replace("_", " ").title()
        if not name:
            name = skill_dir.name.replace("-", " ").replace("_", " ").title()
        description = _truncate_words(meta.get("description", ""), 200)

        if not description:
            for line in body.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                description = stripped[:200]
                break

        if not name or name == skill_dir.name.replace("-", " ").replace("_", " ").title():
            for line in body.splitlines():
                stripped = line.strip()
                if re.match(r"^#\s+\S", stripped):
                    name = re.sub(r"^#+\s*", "", stripped)
                    break

        fm_lines = text.splitlines()
        tools = _extract_tools_from_frontmatter(fm_lines)
        triggers = _extract_trigger_section(body)

        results.append({
            "name": name,
            "description": description,
            "category": skill_dir.name,
            "tools": tools,
            "triggers": triggers,
        })

    return results


def parse_rules(repo_root: Path) -> list[dict]:
    rules_dir = repo_root / "rules"
    if not rules_dir.is_dir():
        return []

    results = []
    for rule_file in sorted(rules_dir.iterdir()):
        if rule_file.suffix not in (".mdc", ".md"):
            continue

        text = rule_file.read_text(encoding="utf-8", errors="replace")
        lines = text.strip().splitlines()

        name = rule_file.stem.replace("-", " ").replace("_", " ").title()
        description = ""
        scope = ""

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("---"):
                continue
            if ":" in stripped and not description:
                key, _, val = stripped.partition(":")
                key_lower = key.strip().lower()
                if key_lower == "description":
                    description = _truncate_words(val.strip(), 200)
                elif key_lower in ("globs", "scope"):
                    scope = val.strip()
                continue
            if stripped and not description:
                description = stripped[:200]

        results.append({
            "name": name,
            "slug": rule_file.stem,
            "description": description,
            "scope": scope,
        })

    return results


def parse_changelog(repo_root: Path, max_entries: int = 2) -> list[dict]:
    """Parse a Keep-a-Changelog formatted CHANGELOG.md.

    Returns up to *max_entries* release entries (skipping ``[Unreleased]``),
    each as ``{ version, date, sections: [{ heading, items }] }``.
    """
    changelog_path = repo_root / "CHANGELOG.md"
    if not changelog_path.is_file():
        return []

    text = changelog_path.read_text(encoding="utf-8", errors="replace")
    entries: list[dict] = []
    current_entry: dict | None = None
    current_section: dict | None = None

    for line in text.splitlines():
        heading_match = re.match(r"^##\s+\[(.+?)\](?:\s*-\s*(.+))?", line)
        if heading_match:
            version = heading_match.group(1)
            date = (heading_match.group(2) or "").strip()
            if version.lower() == "unreleased":
                continue
            if current_entry is not None:
                if current_section:
                    current_entry["sections"].append(current_section)
                entries.append(current_entry)
                if len(entries) >= max_entries:
                    break
            current_entry = {"version": version, "date": date, "sections": []}
            current_section = None
            continue

        if current_entry is None:
            continue

        sub_match = re.match(r"^###\s+(.+)", line)
        if sub_match:
            if current_section:
                current_entry["sections"].append(current_section)
            current_section = {"heading": sub_match.group(1).strip(), "entries": []}
            continue

        if current_section is not None and line.strip().startswith("- "):
            current_section["entries"].append(line.strip()[2:].strip())

    if current_entry is not None:
        if current_section:
            current_entry["sections"].append(current_section)
        if len(entries) < max_entries:
            entries.append(current_entry)

    return entries


def load_examples(repo_root: Path) -> list[dict]:
    """Read examples/gallery.json (the gallery source of truth) when present.

    Hero paths in gallery.json are repo-root-relative (``docs/gallery/...``);
    the deployed site serves ``docs/`` as its root, so expose a site-relative
    ``heroSite`` alongside each entry."""
    gallery_path = repo_root / "examples" / "gallery.json"
    if not gallery_path.is_file():
        return []
    data = load_json(gallery_path)
    examples = data.get("examples", []) if isinstance(data, dict) else []
    for ex in examples:
        hero = ex.get("hero", "")
        ex["heroSite"] = hero[len("docs/"):] if hero.startswith("docs/") else hero
    return examples


def pick_featured(examples: list[dict]) -> list[dict]:
    """Landing-page showcase subset: entries carrying a ``featured_rank``
    integer in gallery.json, sorted by rank. Returns [] when nothing is
    curated; the template then falls back to the full list."""
    return sorted(
        (ex for ex in examples if isinstance(ex.get("featured_rank"), int)),
        key=lambda ex: ex["featured_rank"],
    )


def load_mcp_tools(repo_root: Path) -> list[dict]:
    mcp_file = repo_root / "mcp-tools.json"
    if not mcp_file.is_file():
        return []
    data = load_json(mcp_file)
    if isinstance(data, list):
        return data
    return []


# Tokens that should render upper-case when humanizing a package name into a
# display name (e.g. "screencast-mcp" -> "Screencast MCP").
_ACRONYMS = {"mcp", "api", "ai", "ui", "cfx", "cli", "sdk", "id", "os", "npm"}


def _humanize_package_name(name: str) -> str:
    """Turn an npm package name into a display name. ``@tmhs/screencast-mcp``
    becomes ``Screencast MCP``."""
    base = name.split("/")[-1] if name else ""
    words = [w for w in base.replace("_", "-").split("-") if w]
    return " ".join(w.upper() if w.lower() in _ACRONYMS else w.capitalize() for w in words)


def _clean_repo_url(url: str) -> str:
    url = re.sub(r"^git\+", "", url or "")
    url = re.sub(r"\.git$", "", url)
    return url


def load_plugin_meta(repo_root: Path, site: dict) -> dict:
    """Return the plugin metadata the template needs.

    Prefer ``.cursor-plugin/plugin.json`` when present (cursor plugins). When it
    is absent (MCP server repos do not ship one) fall back to ``site.json`` plus
    ``package.json`` for the display name, description, repository, version, and
    license, so the shared template can build an MCP-server site without a
    synthesized manifest."""
    plugin_path = repo_root / ".cursor-plugin" / "plugin.json"
    if plugin_path.is_file():
        return load_json(plugin_path)

    pkg_path = repo_root / "package.json"
    pkg = load_json(pkg_path) if pkg_path.is_file() else {}
    if not pkg and not site:
        print(
            f"ERROR: {plugin_path} not found and no package.json/site.json to "
            "fall back to",
            file=sys.stderr,
        )
        sys.exit(1)

    links = site.get("links") or {}
    repo = links.get("github", "")
    if not repo:
        repository = pkg.get("repository")
        if isinstance(repository, dict):
            repo = _clean_repo_url(repository.get("url", ""))
        elif isinstance(repository, str):
            repo = _clean_repo_url(repository)

    display = (
        site.get("title")
        or site.get("displayName")
        or _humanize_package_name(pkg.get("name", ""))
        or "Tool"
    )
    return {
        "displayName": display,
        "description": site.get("description") or pkg.get("description", ""),
        "repository": repo,
        "version": pkg.get("version", "0.0.0"),
        "license": pkg.get("license", "CC-BY-NC-ND-4.0"),
        "logo": site.get("logo"),
    }


def group_by_category(items: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for item in items:
        cat = item.get("category", "General") or "General"
        groups.setdefault(cat, []).append(item)
    return dict(sorted(groups.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        required=True,
        help="Path to the checked-out tool repository",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs"),
        help="Output directory (default: docs)",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    out_dir = args.out.resolve()
    template_dir = Path(__file__).parent.resolve()

    site_path = repo_root / "site.json"
    if not site_path.is_file():
        print(f"ERROR: {site_path} not found", file=sys.stderr)
        sys.exit(1)

    site = load_json(site_path)
    plugin = load_plugin_meta(repo_root, site)

    skills = parse_skills(repo_root)
    rules = parse_rules(repo_root)
    examples = load_examples(repo_root)
    featured = pick_featured(examples)
    mcp_tools = load_mcp_tools(repo_root)
    mcp_grouped = group_by_category(mcp_tools)
    changelog = parse_changelog(repo_root)

    context = {
        "plugin": plugin,
        "site": site,
        "skills": skills,
        "skill_count": len(skills),
        "rules": rules,
        "rule_count": len(rules),
        "examples": examples,
        "example_count": len(examples),
        "featured_examples": featured,
        "featured_count": len(featured),
        "snippet_count": len(plugin.get("snippets", [])),
        "template_count": len(plugin.get("templates", [])),
        # basenames for display: snippets/foo-bar.py -> foo-bar
        "snippets": [
            {"name": p.split("/")[-1].removesuffix(".py"), "path": p}
            for p in plugin.get("snippets", [])
        ],
        "templates": [
            {"name": p.split("/")[-1], "path": p}
            for p in plugin.get("templates", [])
        ],
        "mcp_tools": mcp_tools,
        "mcp_tool_count": len(mcp_tools),
        "mcp_grouped": mcp_grouped,
        "changelog": changelog,
        "has_changelog": len(changelog) > 0,
        "build_date": datetime.date.today().isoformat(),
    }

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
        keep_trailing_newline=True,
    )
    template = env.get_template("template.html.j2")
    html = template.render(**context)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"Wrote {out_dir / 'index.html'}")

    fonts_src = template_dir / "fonts"
    fonts_dst = out_dir / "fonts"
    if fonts_src.is_dir():
        if fonts_dst.exists():
            shutil.rmtree(fonts_dst)
        shutil.copytree(fonts_src, fonts_dst)
        print(f"Copied fonts to {fonts_dst}")

    assets_src = repo_root / "assets"
    assets_dst = out_dir / "assets"
    if assets_src.is_dir():
        if assets_dst.exists():
            shutil.rmtree(assets_dst)
        shutil.copytree(assets_src, assets_dst)
        print(f"Copied assets to {assets_dst}")

    print("Done.")


if __name__ == "__main__":
    main()
