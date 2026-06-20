#!/usr/bin/env python3
"""Generate the standalone examples gallery page from examples/gallery.json.

This page is a LOCAL, this-repo gallery that rides alongside the fleet-generated
docs/index.html (which build_site.py owns and overwrites). It writes ONLY to
docs/gallery/ so it never collides with the fleet build's docs/index.html,
docs/fonts/, or docs/assets/.

examples/gallery.json is the forward-compatible source of truth: when the fleet
template gains examples support, it consumes the same data and this script and
page are retired. Run after editing gallery.json:

    python scripts/build_gallery.py

Stdlib only (no Jinja2), so the Pages workflow can regenerate it without extra deps.
"""
import html
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "examples" / "gallery.json"
OUT = REPO / "docs" / "gallery" / "index.html"

CARD = """      <article class="card">
        <a class="card-media" href="{href}">
          <img src="{hero}" alt="{name} — {teaches_plain}" loading="lazy" width="1280" />
        </a>
        <div class="card-body">
          <h2><a href="{href}">{name}</a></h2>
          <p class="teaches">{teaches}</p>
          <p class="witnesses"><span class="tag">witnesses</span> {witnesses}</p>
          <a class="card-link" href="{href}">View example &rarr;</a>
        </div>
      </article>"""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Examples Gallery — Blender Developer Tools</title>
  <meta name="description" content="Runnable, smoke-gated Blender Python examples — each executed headless on Blender 4.5 LTS and 5.1, so every render reflects code that actually runs." />
  <style>
    :root {{
      --accent: #7c3aed; --accent-light: #a78bfa;
      --bg: #0d1117; --bg2: #161b22; --card: #161b22;
      --text: #e6edf3; --text-dim: #9da7b3; --border: #30363d;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: linear-gradient(180deg, var(--bg), var(--bg2)); color: var(--text);
      line-height: 1.6; min-height: 100vh; }}
    a {{ color: var(--accent-light); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    header {{ max-width: 1100px; margin: 0 auto; padding: 3rem 1.5rem 1.5rem; }}
    .back {{ font-size: 0.875rem; color: var(--text-dim); }}
    h1 {{ font-size: 2rem; margin: 0.75rem 0 0.5rem; }}
    header p {{ color: var(--text-dim); max-width: 60ch; }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 1.5rem; display: grid;
      grid-template-columns: 1fr; gap: 1.5rem; }}
    .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px;
      overflow: hidden; display: flex; flex-direction: column; }}
    .card-media {{ display: block; background: #0b0e13; }}
    .card-media img {{ display: block; width: 100%; height: auto; }}
    .card-body {{ padding: 1.25rem 1.5rem 1.5rem; }}
    .card-body h2 {{ font-size: 1.25rem; margin-bottom: 0.5rem; }}
    .card-body h2 a {{ color: var(--text); }}
    .teaches {{ color: var(--text); margin-bottom: 0.6rem; }}
    .witnesses {{ color: var(--text-dim); font-size: 0.9rem; margin-bottom: 0.9rem; }}
    .tag {{ display: inline-block; font-size: 0.72rem; text-transform: uppercase;
      letter-spacing: 0.05em; color: var(--accent-light); border: 1px solid var(--accent);
      border-radius: 999px; padding: 0.05rem 0.5rem; margin-right: 0.35rem; }}
    .card-link {{ font-weight: 500; }}
    footer {{ max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem 3rem;
      color: var(--text-dim); font-size: 0.85rem; border-top: 1px solid var(--border); }}
    @media (min-width: 720px) {{
      main {{ grid-template-columns: 1fr 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <a class="back" href="../">&larr; Blender Developer Tools</a>
    <h1>Examples Gallery</h1>
    <p>Runnable, smoke-gated demos. Each is executed headless on Blender 4.5 LTS and 5.1 by the
    <code>blender-smoke</code> workflow, so every render reflects code that actually runs.</p>
  </header>
  <main>
{cards}
  </main>
  <footer>
    Generated from <code>examples/gallery.json</code> by <code>scripts/build_gallery.py</code>.
    &nbsp;&bull;&nbsp; CC-BY-NC-ND-4.0
  </footer>
</body>
</html>
"""


def strip_to_page_relative(repo_rel: str) -> str:
    """docs/gallery/assets/x.webp -> assets/x.webp (relative to the gallery page)."""
    prefix = "docs/gallery/"
    return repo_rel[len(prefix):] if repo_rel.startswith(prefix) else repo_rel


def main() -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    base = data["repoBaseUrl"].rstrip("/")
    examples = data["examples"]
    if not examples:
        print("ERROR: no examples in gallery.json", file=sys.stderr)
        return 2

    cards = []
    for ex in examples:
        hero_rel = strip_to_page_relative(ex["hero"])
        if not (REPO / ex["hero"]).is_file():
            print(f"ERROR: hero image missing: {ex['hero']}", file=sys.stderr)
            return 3
        cards.append(CARD.format(
            href=html.escape(f"{base}/{ex['dir']}"),
            hero=html.escape(hero_rel),
            name=html.escape(ex["name"]),
            teaches=html.escape(ex["teaches"]),
            teaches_plain=html.escape(ex["teaches"].split(".")[0]),
            witnesses=html.escape(ex["witnessesFix"]),
        ))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(PAGE.format(cards="\n".join(cards)), encoding="utf-8")
    print(f"Wrote {OUT} ({len(examples)} examples)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
