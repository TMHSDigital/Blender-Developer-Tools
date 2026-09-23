#!/usr/bin/env python3
"""Generate the examples gallery from examples/gallery.json.

Emits the gallery index (docs/gallery/index.html) AND one detail page per
example (docs/gallery/<name>/index.html) with the hero render (click to
zoom), a run-it-yourself command, the example's README rendered inline, and
the full Python source syntax-highlighted at build time.

The index carries a sticky controls bar (search, tag chips, compact/detailed
density toggle, back-to-top) driven by inline vanilla JS — no external
dependencies. Everything is no-JS safe: compact density and chip collapsing
are applied only via JS-added classes, so with JavaScript disabled every
card renders expanded and readable.

This is a LOCAL, this-repo gallery that rides alongside the generated
docs/index.html (which scripts/site/build_site.py owns and overwrites). It
writes ONLY under docs/gallery/ so it never collides with the landing build's
docs/index.html, docs/fonts/, or docs/assets/.

examples/gallery.json is the source of truth for examples. showcase/gallery.json
is the source of truth for showcase pieces (``pieces`` key). This script merges
both into one docs/gallery/ index so each tree owns its JSON. Run after editing
either file, an example or showcase script, or a README:

    python scripts/build_gallery.py

Stdlib only (no Jinja2, no Pygments), so the Pages workflow can regenerate it
without extra deps. Uses token replacement (not str.format) so CSS braces
need no escaping.
"""
import html
import io
import json
import keyword
import posixpath
import re
import sys
import tokenize
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "examples" / "gallery.json"
SHOWCASE_DATA = REPO / "showcase" / "gallery.json"
OUT_DIR = REPO / "docs" / "gallery"

# Soft cap for gallery index card alt text (accessibility + layout).
_ALT_CAP = 160


def load_gallery_entries() -> tuple[dict, list]:
    """Examples gallery metadata plus concatenated example + showcase cards."""
    data = json.loads(DATA.read_text(encoding="utf-8"))
    entries = list(data["examples"])
    if SHOWCASE_DATA.is_file():
        show = json.loads(SHOWCASE_DATA.read_text(encoding="utf-8"))
        for piece in show.get("pieces", []):
            item = dict(piece)
            tags = list(item.get("tags") or [])
            if "showcase" not in tags:
                tags.append("showcase")
            item["tags"] = tags
            entries.append(item)
    return data, entries


def kind_noun(entry: dict) -> str:
    """Card noun for *entry*. Showcase pieces are not examples; say so.

    Both kinds share the gallery grid (``load_gallery_entries`` concatenates
    them), so every user-facing noun has to be derived per entry rather than
    hardcoded, or the chrome silently relabels 26 props as examples.
    """
    return "showcase piece" if "showcase" in (entry.get("tags") or []) else "example"


def first_sentence(text: str) -> str:
    """First sentence of *text*, splitting on period-followed-by-whitespace.

    Do not use ``str.split(".")[0]``: bpy teaches strings are full of dotted
    API paths (``bmesh.ops.create_grid``, ``bpy.context.temp_override``), and
    that split truncates mid-identifier.
    """
    m = re.search(r"\.\s+", text)
    if m:
        return text[: m.start() + 1].strip()
    return text.strip()


def card_alt(name: str, teaches: str, *, cap: int = _ALT_CAP) -> str:
    """Gallery card ``<img alt>``: ``{name} — {first sentence}``, length-capped."""
    first = first_sentence(teaches)
    if len(first) > cap:
        cut = first[:cap].rsplit(" ", 1)[0].rstrip(".,;: —-")
        first = (cut if cut else first[:cap].rstrip()) + "…"
    return f"{name} — {first}"


def assert_alts_survive_dotted_paths(examples: list) -> None:
    """Fail the build if any card alt is still truncated at the first ``.``.

    Catches regressions of the old ``teaches.split(".")[0]`` bug for every
    example whose first sentence contains a dotted identifier.
    """
    for ex in examples:
        teaches = ex["teaches"]
        name = ex["name"]
        alt = card_alt(name, teaches)
        first_dot = teaches.find(".")
        if first_dot < 0:
            continue
        # First "." is a real sentence end (EOS or whitespace after it).
        if first_dot == len(teaches) - 1 or teaches[first_dot + 1].isspace():
            continue
        suffix = alt.split(" — ", 1)[-1]
        if len(suffix) <= first_dot:
            raise SystemExit(
                f"gallery alt truncated at dotted API path for {name!r}: {alt!r}"
            )
        # Old bug would have produced exactly this string:
        legacy = f"{name} — {teaches.split('.')[0]}"
        if alt == legacy:
            raise SystemExit(
                f"gallery alt still matches legacy split('.')[0] for {name!r}: {alt!r}"
            )

# ---------------------------------------------------------------------------
# Shared page shell. __ROOT__ is the relative prefix from the page to the
# gallery root ("" for the index, "../" for detail pages); __SITEROOT__ is the
# prefix to the site root ("../" for the index, "../../" for detail pages).
# ---------------------------------------------------------------------------

SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  <meta name="description" content="__DESC__" />
  <link rel="canonical" href="__CANONICAL__" />
  <link rel="icon" href="__SITEROOT__assets/favicon.svg" type="image/svg+xml" />
  <meta name="theme-color" content="#1a1b1e" />
  <meta name="color-scheme" content="dark" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="__TITLE__" />
  <meta property="og:description" content="__DESC__" />
  <meta property="og:url" content="__CANONICAL__" />
  <meta property="og:image" content="__OGIMAGE__" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="__TITLE__" />
  <meta name="twitter:description" content="__DESC__" />
  <meta name="twitter:image" content="__OGIMAGE__" />
  <style>
    /* fonts are deployed by the landing build (docs/fonts/) */
    @font-face { font-family: 'Barlow Condensed'; font-weight: 600; font-display: swap;
      src: url('__SITEROOT__fonts/barlow-condensed-600.woff2') format('woff2'); }
    @font-face { font-family: 'Inter'; font-weight: 400; font-display: swap;
      src: url('__SITEROOT__fonts/inter-regular.woff2') format('woff2'); }
    @font-face { font-family: 'Inter'; font-weight: 500; font-display: swap;
      src: url('__SITEROOT__fonts/inter-medium.woff2') format('woff2'); }
    @font-face { font-family: 'JetBrains Mono'; font-weight: 400; font-display: swap;
      src: url('__SITEROOT__fonts/jetbrains-mono-regular.woff2') format('woff2'); }

    /* Blender-viewport system, shared with the landing page. Dark only. */
    :root {
      color-scheme: dark;
      --bg: #1a1b1e; --surface: #222327; --surface-2: #2a2b30; --bg2: #131417;
      --border: #3a3b40; --text: #e8e9eb; --text-dim: #9698a0;
      --select: #ff8c19; --ok: #6dc96d;
      --radius: 4px; --radius-lg: 6px; --maxw: 1080px;
      --font-display: 'Barlow Condensed', 'Arial Narrow', sans-serif;
      --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
      --font-mono: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
      --code-k: #ff7b72; --code-s: #a5d6ff; --code-c: #9698a0; --code-n: #79c0ff;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html { scroll-behavior: smooth; }
    body { font-family: var(--font-sans); background: var(--bg); color: var(--text);
      line-height: 1.6; min-height: 100vh; -webkit-font-smoothing: antialiased; }
    a { color: var(--select); text-decoration: none; }
    a:hover { text-decoration: underline; }
    :focus-visible { outline: 2px solid var(--select); outline-offset: 2px; border-radius: 3px; }
    ::selection { background: color-mix(in srgb, var(--select) 40%, transparent); }
    .skip { position: absolute; left: -999px; top: 0; background: var(--select); color: #1a1b1e;
      padding: 0.5rem 1rem; border-radius: var(--radius); z-index: 10; font-weight: 500; }
    .skip:focus { left: 0.5rem; top: 0.5rem; }
    .hud { font-family: var(--font-mono); font-size: 0.6875rem; letter-spacing: 0.04em;
      color: var(--text-dim); text-transform: uppercase; }

    .topbar { position: sticky; top: 0; z-index: 5; display: flex; align-items: center;
      justify-content: space-between; gap: 1rem; padding: 0 1.25rem; height: 46px;
      background: color-mix(in srgb, var(--surface) 92%, transparent);
      backdrop-filter: blur(10px); border-bottom: 1px solid var(--border); }
    .topbar .back { color: var(--text-dim); font-size: 0.8125rem; font-weight: 500; }
    .topbar .back:hover { color: var(--select); text-decoration: none; }
    .topbar-right { display: flex; align-items: center; gap: 0.85rem; }
    .topbar-right .ghlink { color: var(--text-dim); font-size: 0.8125rem; font-weight: 500; }
    .topbar-right .ghlink:hover { color: var(--select); text-decoration: none; }

    header.hero { max-width: var(--maxw); margin: 0 auto; padding: 2.75rem 1.25rem 1.25rem; }
    header.hero h1 { font-family: var(--font-display); font-weight: 600; text-transform: uppercase;
      font-size: clamp(2.2rem, 5vw, 3.4rem); letter-spacing: 0.005em; line-height: 0.98; }
    header.hero p { color: var(--text-dim); max-width: 62ch; margin-top: 0.7rem; font-size: 1rem; }

    /* ---- index: sticky controls (search, density toggle, tag chips) ---- */
    .controls { position: sticky; top: 46px; z-index: 4;
      background: color-mix(in srgb, var(--bg) 94%, transparent);
      backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--border); }
    .controls-inner { max-width: var(--maxw); margin: 0 auto; padding: 0.55rem 1.25rem 0.6rem;
      display: flex; flex-direction: column; gap: 0.5rem; }
    .controls-row { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
    .searchwrap { position: relative; flex: 1 1 240px; min-width: 150px; }
    .searchwrap input { width: 100%; background: var(--surface-2); border: 1px solid var(--border);
      color: var(--text); border-radius: var(--radius); padding: 0.34rem 1.9rem 0.34rem 0.7rem;
      font-family: var(--font-sans); font-size: 0.85rem; line-height: 1.4; }
    .searchwrap input:focus { border-color: var(--select); outline: none; }
    .searchwrap input::placeholder { color: var(--text-dim); }
    .searchwrap input::-webkit-search-cancel-button { -webkit-appearance: none; appearance: none; }
    .q-clear { position: absolute; right: 0.2rem; top: 50%; transform: translateY(-50%);
      background: none; border: none; color: var(--text-dim); font-size: 1.05rem; line-height: 1;
      cursor: pointer; padding: 0.25rem 0.45rem; border-radius: 3px; }
    .q-clear:hover { color: var(--select); }
    .count { font-family: var(--font-mono); font-size: 0.68rem; letter-spacing: 0.04em;
      text-transform: uppercase; color: var(--text-dim); white-space: nowrap; }
    .density { display: flex; border: 1px solid var(--border); border-radius: var(--radius);
      overflow: hidden; }
    .density-btn { background: var(--surface-2); border: none; color: var(--text-dim); cursor: pointer;
      font-family: var(--font-mono); font-size: 0.68rem; letter-spacing: 0.04em;
      text-transform: uppercase; padding: 0.36rem 0.7rem; transition: color 0.15s, background 0.15s; }
    .density-btn + .density-btn { border-left: 1px solid var(--border); }
    .density-btn:hover { color: var(--select); }
    .density-btn.active { background: var(--select); color: #1a1b1e; }
    .tags-toggle { display: none; background: var(--surface-2); border: 1px solid var(--border);
      color: var(--text-dim); border-radius: 3px; padding: 0.3rem 0.7rem; cursor: pointer;
      font-family: var(--font-mono); font-size: 0.7rem; letter-spacing: 0.04em; text-transform: uppercase; }
    .tags-toggle:hover, .tags-toggle.has-active { color: var(--select); border-color: var(--select); }

    /* Tag chips wrap by default (no-JS safe). With JS the row becomes a scroll
       strip on wide viewports and collapses behind the Tags toggle on narrow
       ones, so the sticky bar never eats the mobile viewport. */
    .chips { display: flex; flex-wrap: wrap; gap: 0.4rem; }
    html.js .chips { flex-wrap: nowrap; overflow-x: auto; padding-bottom: 0.25rem;
      scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
    html.js .chips::-webkit-scrollbar { height: 5px; }
    html.js .chips::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
    .chip { background: var(--surface-2); border: 1px solid var(--border); color: var(--text-dim);
      border-radius: 3px; padding: 0.22rem 0.7rem; font-size: 0.72rem; font-weight: 400;
      font-family: var(--font-mono); cursor: pointer; white-space: nowrap; flex: 0 0 auto;
      transition: color 0.15s, border-color 0.15s; }
    .chip:hover { color: var(--select); border-color: var(--select); }
    .chip.active { color: #1a1b1e; background: var(--select); border-color: var(--select); }
    @media (max-width: 719px) {
      html.js .tags-toggle { display: inline-block; }
      html.js .chips { display: none; }
      html.js .chips.open { display: flex; flex-wrap: wrap; overflow-y: auto; max-height: 40vh; }
    }

    /* Compact density: hero + name + one-line teaser. The description and
       WITNESSES text stay in the DOM (searchable, screen-reader reachable,
       present with JS disabled when the class is never applied) but are
       visually collapsed. Applied only by JS via the density-compact class. */
    html.density-compact .grid { gap: 1rem; }
    html.density-compact .card-body { padding: 0.65rem 0.9rem 0.7rem; }
    html.density-compact .card-body h2 { font-size: 0.88rem; margin-bottom: 0.15rem; }
    html.density-compact .teaches { font-size: 0.8rem; color: var(--text-dim); margin-bottom: 0;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    html.density-compact .witnesses { position: absolute; width: 1px; height: 1px; margin: -1px;
      padding: 0; overflow: hidden; clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap; }
    html.density-compact .card-link { display: none; }
    .noresults { color: var(--text-dim); text-align: center; padding: 3rem 1rem; font-size: 0.95rem; }
    .noresults .chip { margin-left: 0.6rem; }
    .to-top { position: fixed; right: 1.25rem; bottom: 1.25rem; z-index: 6; cursor: pointer;
      background: var(--surface-2); border: 1px solid var(--border); color: var(--text-dim);
      border-radius: var(--radius); padding: 0.45rem 0.75rem;
      font-family: var(--font-mono); font-size: 0.7rem; letter-spacing: 0.04em;
      text-transform: uppercase; opacity: 0; visibility: hidden;
      transition: opacity 0.2s, visibility 0.2s, color 0.15s, border-color 0.15s; }
    .to-top.show { opacity: 1; visibility: visible; }
    .to-top:hover { color: var(--select); border-color: var(--select); }

    main { max-width: var(--maxw); margin: 0 auto; padding: 1rem 1.25rem 2rem; }
    .grid { display: grid; grid-template-columns: 1fr; gap: 1.5rem; align-items: stretch; }
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
      overflow: hidden; display: flex; flex-direction: column;
      outline: 2px solid transparent; outline-offset: -1px;
      transition: outline-color 0.12s ease, border-color 0.12s ease; }
    .card:hover { border-color: var(--select); outline-color: var(--select); }
    .card.hidden { display: none; }
    .card-media { display: block; background: var(--bg2); line-height: 0; }
    .card-media img { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover; }
    .card-body { padding: 1.15rem 1.4rem 1.45rem; display: flex; flex-direction: column; flex: 1 1 auto; }
    .card-body h2 { font-family: var(--font-mono); font-size: 1rem; font-weight: 400; margin-bottom: 0.5rem; }
    .card-body h2 a { color: var(--text); }
    .card-body h2 a:hover { color: var(--select); text-decoration: none; }
    .teaches { color: var(--text); margin-bottom: 0.7rem; font-size: 0.92rem; }
    .witnesses { color: var(--text-dim); font-size: 0.85rem; margin-bottom: 1rem; }
    .tag { display: inline-block; font-family: var(--font-mono); font-size: 0.62rem; text-transform: uppercase;
      letter-spacing: 0.06em; color: var(--select); border: 1px solid color-mix(in srgb, var(--select) 55%, transparent);
      border-radius: 3px; padding: 0.08rem 0.5rem; margin-right: 0.4rem; vertical-align: 1px; }
    .card-link { font-weight: 600; font-size: 0.95rem; margin-top: auto; }

    /* ---- detail page ---- */
    .detail-hero { border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden;
      background: var(--bg2); padding: 0; display: block; width: 100%; cursor: zoom-in; line-height: 0; }
    .detail-hero img { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover; }
    .zoom-hint { color: var(--text-dim); font-size: 0.78rem; margin-top: 0.4rem; }
    .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0);
      white-space: nowrap; }
    .callout { border: 1px solid color-mix(in srgb, var(--select) 45%, var(--border));
      border-left: 3px solid var(--select); border-radius: var(--radius);
      background: color-mix(in srgb, var(--select) 7%, var(--surface));
      padding: 0.85rem 1.1rem; margin: 1.5rem 0; font-size: 0.95rem; }
    .runline { display: flex; align-items: stretch; gap: 0.5rem; margin: 1.5rem 0; }
    .runline pre { flex: 1 1 auto; background: var(--surface-2); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 0.7rem 0.9rem; overflow-x: auto;
      font-family: var(--font-mono); font-size: 0.83rem; line-height: 1.5; }
    .copy-btn { flex: 0 0 auto; background: var(--surface-2); border: 1px solid var(--border);
      color: var(--text-dim); border-radius: var(--radius); padding: 0 0.85rem; cursor: pointer;
      font-family: var(--font-sans); font-size: 0.82rem; font-weight: 500; transition: color 0.15s, border-color 0.15s; }
    .copy-btn:hover { color: var(--select); border-color: var(--select); }
    .detail-section { margin-top: 2.25rem; }
    .detail-section > h2 { font-family: var(--font-display); font-weight: 600; text-transform: uppercase;
      font-size: 1.45rem; letter-spacing: 0.005em; padding-bottom: 0.5rem;
      border-bottom: 1px solid var(--border); margin-bottom: 1rem; }

    .md h1, .md h2, .md h3 { letter-spacing: -0.01em; margin: 1.4rem 0 0.6rem; line-height: 1.25; }
    .md h1 { font-size: 1.35rem; } .md h2 { font-size: 1.15rem; } .md h3 { font-size: 1rem; }
    .md p { margin: 0.7rem 0; }
    .md ul, .md ol { margin: 0.7rem 0 0.7rem 1.4rem; }
    .md li { margin: 0.3rem 0; }
    .md .table-wrap { overflow-x: auto; margin: 0.9rem 0; }
    .md table { border-collapse: collapse; font-size: 0.86rem; min-width: 100%; }
    .md th, .md td { text-align: left; vertical-align: top; padding: 0.4rem 0.75rem 0.4rem 0;
      border-bottom: 1px solid var(--border); }
    .md th { color: var(--text-dim); font-weight: 600; white-space: nowrap; }
    .md code { background: var(--surface-2); border: 1px solid var(--border); padding: 0.08rem 0.35rem;
      border-radius: 4px; font-family: var(--font-mono); font-size: 0.84em; }
    .md pre { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius);
      padding: 0.85rem 1rem; overflow-x: auto; margin: 0.9rem 0; }
    .md pre code { background: none; border: none; padding: 0; font-size: 0.83rem; line-height: 1.55; }

    .src pre { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius);
      padding: 1rem 1.1rem; overflow-x: auto; font-family: var(--font-mono);
      font-size: 0.82rem; line-height: 1.55; }
    .src .k { color: var(--code-k); } .src .s { color: var(--code-s); }
    .src .c { color: var(--code-c); font-style: italic; } .src .n { color: var(--code-n); }
    .src-meta { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem;
      flex-wrap: wrap; margin-bottom: 0.6rem; color: var(--text-dim); font-size: 0.85rem; }
    .src-meta code { font-family: var(--font-mono); font-size: 0.82rem; }

    .lightbox { border: 0; margin: 0; padding: 2rem; width: 100%; height: 100%; max-width: none;
      max-height: none; background: rgba(0,0,0,0.85); cursor: zoom-out; }
    .lightbox[open] { display: flex; align-items: center; justify-content: center; }
    .lightbox::backdrop { background: transparent; }
    .lightbox img { max-width: 100%; max-height: 100%; border-radius: var(--radius); }
    .lightbox-close { position: absolute; top: 0.9rem; right: 0.9rem; background: var(--surface-2);
      color: var(--text); border: 1px solid var(--border); border-radius: var(--radius);
      font: 500 0.8rem var(--font-sans); padding: 0.4rem 0.75rem; cursor: pointer; }
    .lightbox-close:hover { border-color: var(--select); color: var(--select); }

    footer { border-top: 1px solid var(--border); background: var(--surface); margin-top: 2rem; }
    footer .statusbar { max-width: var(--maxw); margin: 0 auto; padding: 0.55rem 1.25rem;
      display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
      font-family: var(--font-mono); font-size: 0.6875rem; letter-spacing: 0.04em;
      text-transform: uppercase; color: var(--text-dim); }
    footer .statusbar code { font-family: inherit; text-transform: none; }

    @media (min-width: 720px) { .grid { grid-template-columns: 1fr 1fr; gap: 1.75rem; } }
    @media (min-width: 560px) { html.density-compact .grid { grid-template-columns: 1fr 1fr; gap: 1rem; } }
    @media (min-width: 900px) { html.density-compact .grid { grid-template-columns: repeat(3, 1fr); } }
    @media (min-width: 1560px) {
      html.density-compact .controls-inner,
      html.density-compact main { max-width: 1400px; }
      html.density-compact .grid { grid-template-columns: repeat(4, 1fr); }
    }
    @media (prefers-reduced-motion: reduce) {
      html { scroll-behavior: auto; }
      .card { transition: none; }
      .card:hover { transform: none; }
      .to-top { transition: none; }
    }
  </style>__HEADJS__
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <div class="topbar">
    <a class="back" href="__BACKHREF__"><span aria-hidden="true">&larr;</span> __BACKLABEL__</a>
    <div class="topbar-right">
      <a class="ghlink" href="__REPO__">GitHub</a>
    </div>
  </div>
__CONTENT__
  <footer>
    <div class="statusbar">
      <span>generated from __SOURCE__</span>
      <span>CC-BY-NC-ND-4.0</span>
      <span style="color: var(--ok);">exit 0</span>
    </div>
  </footer>
  <script>
__PAGEJS__
  </script>
</body>
</html>
"""

# Index-only head script: runs before first paint so the persisted/default
# density never flashes as a full-height detailed page first. Adds the `js`
# class that gates every JS-only affordance (collapsible chips, scroll strip);
# with JS disabled no class is ever applied and every card renders expanded.
INDEX_HEADJS = """
  <script>
    (function () {
      var de = document.documentElement;
      de.classList.add('js');
      var d = 'compact';
      var m = location.hash.match(/(?:^|[#&])d=(compact|detailed)/);
      if (m) { d = m[1]; }
      else {
        try {
          var s = localStorage.getItem('bdt-gallery-density');
          if (s === 'compact' || s === 'detailed') d = s;
        } catch (e) {}
      }
      if (d === 'compact') de.classList.add('density-compact');
    })();
  </script>"""

INDEX_JS = """
    (function () {
      var de = document.documentElement;
      var grid = document.getElementById('grid');
      var cards = Array.prototype.slice.call(grid.querySelectorAll('.card'));
      var chipsEl = document.getElementById('chips');
      var chips = Array.prototype.slice.call(chipsEl.querySelectorAll('.chip'));
      var q = document.getElementById('q');
      var qClear = document.getElementById('qClear');
      var count = document.getElementById('count');
      var noResults = document.getElementById('noResults');
      var resetFilters = document.getElementById('resetFilters');
      var densityBtns = Array.prototype.slice.call(document.querySelectorAll('.density-btn'));
      var tagsToggle = document.getElementById('tagsToggle');
      var toTop = document.getElementById('toTop');
      var total = cards.length;
      var COUNT_LABEL = '__COUNT_LABEL__';
      var LS_KEY = 'bdt-gallery-density';
      var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      // Searchable text is the card's own DOM text: name, teaches, and the
      // WITNESSES line (visually collapsed in compact mode, still in the DOM).
      var haystacks = cards.map(function (c) { return c.textContent.toLowerCase(); });
      var state = { q: '', tag: '', density: 'compact' };

      function parseHash() {
        var out = {};
        location.hash.replace(/^#/, '').split('&').forEach(function (kv) {
          var i = kv.indexOf('=');
          if (i < 0) return;
          var k = kv.slice(0, i), v = kv.slice(i + 1);
          try { v = decodeURIComponent(v); } catch (e) {}
          if (k === 'q' || k === 'tag' || k === 'd') out[k] = v;
        });
        return out;
      }

      function writeHash() {
        var parts = [];
        if (state.q) parts.push('q=' + encodeURIComponent(state.q));
        if (state.tag) parts.push('tag=' + encodeURIComponent(state.tag));
        parts.push('d=' + state.density);
        history.replaceState(null, '', location.pathname + location.search + '#' + parts.join('&'));
      }

      function syncChips() {
        chips.forEach(function (c) {
          c.classList.toggle('active', (c.getAttribute('data-tag') || '') === state.tag);
        });
        tagsToggle.classList.toggle('has-active', !!state.tag);
        // The chip row is collapsed on narrow screens; name the active tag
        // on the toggle so a shared #tag= link is visibly filtered.
        tagsToggle.textContent = state.tag ? 'Tags: ' + state.tag : 'Tags';
      }

      function applyDensity() {
        de.classList.toggle('density-compact', state.density === 'compact');
        densityBtns.forEach(function (b) {
          var on = b.getAttribute('data-density') === state.density;
          b.classList.toggle('active', on);
          b.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
        try { localStorage.setItem(LS_KEY, state.density); } catch (e) {}
      }

      function applyFilters() {
        var query = state.q.trim().toLowerCase();
        var shown = 0;
        cards.forEach(function (card, i) {
          var tagOK = !state.tag || (card.getAttribute('data-tags') || '').split(' ').indexOf(state.tag) !== -1;
          var qOK = !query || haystacks[i].indexOf(query) !== -1;
          var show = tagOK && qOK;
          card.classList.toggle('hidden', !show);
          if (show) shown++;
        });
        count.textContent = (query || state.tag) ? (shown + ' of ' + total) : COUNT_LABEL;
        noResults.hidden = shown !== 0;
        qClear.hidden = !state.q;
      }

      q.addEventListener('input', function () {
        state.q = q.value;
        applyFilters();
        writeHash();
      });
      qClear.addEventListener('click', function () {
        q.value = ''; state.q = '';
        applyFilters(); writeHash(); q.focus();
      });
      chips.forEach(function (chip) {
        chip.addEventListener('click', function () {
          state.tag = chip.getAttribute('data-tag') || '';
          syncChips(); applyFilters(); writeHash();
        });
      });
      densityBtns.forEach(function (b) {
        b.addEventListener('click', function () {
          state.density = b.getAttribute('data-density');
          applyDensity(); writeHash();
        });
      });
      resetFilters.addEventListener('click', function () {
        state.q = ''; state.tag = ''; q.value = '';
        syncChips(); applyFilters(); writeHash(); q.focus();
      });
      tagsToggle.addEventListener('click', function () {
        var open = chipsEl.classList.toggle('open');
        tagsToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      });

      document.addEventListener('keydown', function (e) {
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        var ae = document.activeElement;
        var typing = ae && /^(INPUT|TEXTAREA|SELECT)$/.test(ae.tagName);
        if (e.key === '/' && !typing) {
          e.preventDefault();
          q.focus();
          q.select();
        } else if (e.key === 'Escape' && ae === q) {
          q.value = ''; state.q = '';
          applyFilters(); writeHash(); q.blur();
        }
      });

      function onScroll() { toTop.classList.toggle('show', window.scrollY > 600); }
      window.addEventListener('scroll', onScroll, { passive: true });
      onScroll();
      toTop.addEventListener('click', function () {
        window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' });
      });

      // Restore state: URL hash wins; density falls back to localStorage.
      var h = parseHash();
      state.q = h.q || '';
      state.tag = h.tag || '';
      if (h.d === 'compact' || h.d === 'detailed') state.density = h.d;
      else {
        try {
          var s = localStorage.getItem(LS_KEY);
          if (s === 'compact' || s === 'detailed') state.density = s;
        } catch (e) {}
      }
      // A tag in the hash that no chip knows would silently show zero cards.
      var known = chips.some(function (c) { return (c.getAttribute('data-tag') || '') === state.tag; });
      if (!known) state.tag = '';
      q.value = state.q;
      syncChips();
      applyDensity();
      applyFilters();
    })();
"""

DETAIL_JS = """
    (function () {
      var hero = document.getElementById('heroZoom');
      var box = document.getElementById('lightbox');
      if (hero && box) {
        // <dialog>.showModal() traps focus, closes on Escape, and returns
        // focus to the hero button on close. Any click inside closes it.
        hero.addEventListener('click', function () { box.showModal(); });
        box.addEventListener('click', function () { box.close(); });
      }
      var copy = document.getElementById('copyRun');
      if (copy) {
        copy.addEventListener('click', function () {
          var cmd = document.getElementById('runCmd').textContent;
          navigator.clipboard.writeText(cmd).then(function () {
            copy.textContent = 'Copied!';
            setTimeout(function () { copy.textContent = 'Copy'; }, 1500);
          });
        });
      }
    })();
"""

CARD = """      <article class="card" data-tags="__TAGS__">
        <a class="card-media" href="__HREF__" tabindex="-1" aria-hidden="true">
          <img src="__HERO__" alt="__ALT__" loading="lazy" decoding="async" />
        </a>
        <div class="card-body">
          <h2><a href="__HREF__">__NAME__</a></h2>
          <p class="teaches">__TEACHES__</p>
          <p class="witnesses"><span class="tag">witnesses</span> __WITNESSES__</p>
          <a class="card-link" href="__HREF__">View __KIND__<span class="sr-only"> __NAME__</span> <span aria-hidden="true">&rarr;</span></a>
        </div>
      </article>"""


# ---------------------------------------------------------------------------
# Build-time Python syntax highlighting (stdlib tokenize; no Pygments).
# ---------------------------------------------------------------------------

_FSTRING_TYPES = {
    getattr(tokenize, name, -1)
    for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END")
}


def highlight_python(src: str) -> str:
    """Return HTML for *src* with keyword/string/comment/number spans."""
    line_starts = [0]
    for line in src.splitlines(keepends=True):
        line_starts.append(line_starts[-1] + len(line))

    def offset(row: int, col: int) -> int:
        return line_starts[row - 1] + col

    out: list[str] = []
    last = 0
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            start, end = offset(*tok.start), offset(*tok.end)
            if start < last:  # overlapping synthetic token (NEWLINE/INDENT)
                continue
            if start > last:
                out.append(html.escape(src[last:start]))
            cls = None
            if tok.type == tokenize.COMMENT:
                cls = "c"
            elif tok.type == tokenize.STRING or tok.type in _FSTRING_TYPES:
                cls = "s"
            elif tok.type == tokenize.NUMBER:
                cls = "n"
            elif tok.type == tokenize.NAME and keyword.iskeyword(tok.string):
                cls = "k"
            text = html.escape(src[start:end])
            out.append(f'<span class="{cls}">{text}</span>' if cls and text else text)
            last = end
    except tokenize.TokenError:
        return html.escape(src)
    out.append(html.escape(src[last:]))
    return "".join(out)


# ---------------------------------------------------------------------------
# Minimal Markdown renderer for the example READMEs (headings, paragraphs,
# ordered and unordered lists, pipe tables, fenced code, inline
# code/bold/emphasis/links/images). Relative links are resolved against the
# example's directory on GitHub.
# ---------------------------------------------------------------------------

_INLINE = re.compile(
    r"`([^`]+)`"
    r"|\*\*(.+?)\*\*"
    r"|(?<![*\w])\*(?![\s*])([^*\n]+?)(?<!\s)\*(?![*\w])"
    r"|(!?)\[([^\]]+)\]\(([^)]+)\)"
)
_OL_ITEM = re.compile(r"^\d+\.\s+")
_TABLE_SEP = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")
# A README's leading `![alt](preview.webp)` repeats the hero the page already shows.
_PREVIEW_IMAGE = re.compile(r"^!\[[^\]]*\]\((\./)?preview\.webp\)$")


def render_inline(text: str, resolve) -> str:
    out = []
    pos = 0
    for m in _INLINE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        if m.group(1) is not None:
            out.append(f"<code>{html.escape(m.group(1))}</code>")
        elif m.group(2) is not None:
            out.append(f"<strong>{render_inline(m.group(2), resolve)}</strong>")
        elif m.group(3) is not None:
            out.append(f"<em>{render_inline(m.group(3), resolve)}</em>")
        else:
            # An inline image becomes a link carrying its alt text: the gallery
            # only publishes the hero, so the image file itself lives on GitHub.
            href = html.escape(resolve(m.group(6)), quote=True)
            out.append(f'<a href="{href}">{render_inline(m.group(5), resolve)}</a>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def _split_row(row: str) -> list[str]:
    """Split a pipe-table row on `|` outside backtick code spans."""
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    cells, cur, in_code = [], [], False
    for ch in row:
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    cells.append("".join(cur).strip())
    return cells


def _starts_block(lines: list[str], i: int) -> bool:
    s = lines[i].strip()
    if s.startswith(("#", "- ", "```")) or _OL_ITEM.match(s):
        return True
    return (s.startswith("|") and i + 1 < len(lines)
            and bool(_TABLE_SEP.match(lines[i + 1].strip())))


def md_to_html(text: str, resolve, skip_first_h1: bool = True) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    seen_h1 = False
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            code: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # closing fence
            out.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
            continue

        m = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            if level == 1 and skip_first_h1 and not seen_h1:
                seen_h1 = True
                i += 1
                continue
            out.append(f"<h{level}>{render_inline(m.group(2), resolve)}</h{level}>")
            i += 1
            continue

        if _PREVIEW_IMAGE.match(stripped):
            i += 1
            continue

        if (stripped.startswith("|") and i + 1 < len(lines)
                and _TABLE_SEP.match(lines[i + 1].strip())):
            head = _split_row(stripped)
            i += 2  # header row + separator
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1
            ths = "".join(f'<th scope="col">{render_inline(c, resolve)}</th>' for c in head)
            trs = "".join(
                "<tr>" + "".join(f"<td>{render_inline(c, resolve)}</td>" for c in r) + "</tr>"
                for r in rows)
            out.append(f'<div class="table-wrap"><table><thead><tr>{ths}</tr></thead>'
                       f"<tbody>{trs}</tbody></table></div>")
            continue

        ordered = bool(_OL_ITEM.match(stripped))
        if stripped.startswith("- ") or ordered:
            marker = _OL_ITEM if ordered else re.compile(r"^- ")
            items: list[str] = []
            while i < len(lines):
                cur = lines[i].strip()
                mm = marker.match(cur)
                if mm:
                    items.append(cur[mm.end():])
                elif cur and lines[i].startswith("  ") and items:
                    items[-1] += " " + cur  # wrapped continuation line
                else:
                    break
                i += 1
            lis = "".join(f"<li>{render_inline(it, resolve)}</li>" for it in items)
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>{lis}</{tag}>")
            continue

        para: list[str] = [stripped]
        i += 1
        while i < len(lines):
            if not lines[i].strip() or _starts_block(lines, i):
                break
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{render_inline(' '.join(para), resolve)}</p>")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

def page_relative(repo_rel: str) -> str:
    """docs/gallery/assets/x.webp -> assets/x.webp (relative to the gallery root)."""
    prefix = "docs/gallery/"
    return repo_rel[len(prefix):] if repo_rel.startswith(prefix) else repo_rel


def find_script(ex_dir: Path) -> Path | None:
    scripts = sorted(p for p in ex_dir.glob("*.py") if p.is_file())
    return scripts[0] if scripts else None


def make_resolver(repo_base: str, ex_dir: str):
    """Resolve README-relative links against the example dir on GitHub."""
    def resolve(url: str) -> str:
        if re.match(r"^[a-z]+://", url) or url.startswith("#"):
            return url
        return f"{repo_base}/{posixpath.normpath(posixpath.join(ex_dir, url))}"
    return resolve


def shell(*, title: str, desc: str, canonical: str, og_image: str,
          site_root: str, back_href: str, back_label: str, repo_url: str,
          content: str, page_js: str, head_js: str = "",
          sources: tuple[str, ...] = ("examples/gallery.json",)) -> str:
    return (SHELL
            .replace("__TITLE__", html.escape(title))
            .replace("__DESC__", html.escape(desc, quote=True))
            .replace("__CANONICAL__", html.escape(canonical, quote=True))
            .replace("__OGIMAGE__", html.escape(og_image, quote=True))
            .replace("__SITEROOT__", site_root)
            .replace("__BACKHREF__", back_href)
            .replace("__BACKLABEL__", html.escape(back_label))
            .replace("__REPO__", html.escape(repo_url, quote=True))
            .replace("__SOURCE__", " + ".join(
                f"<code>{html.escape(s)}</code>" for s in sources))
            .replace("__PAGEJS__", page_js)
            .replace("__HEADJS__", head_js)
            # Content last, so README and source text are never scanned for
            # the other placeholders.
            .replace("__CONTENT__", content))


def build_detail(ex: dict, *, base: str, repo_root_url: str, site: str) -> str:
    noun = kind_noun(ex)
    kind_title = "Showcase" if noun == "showcase piece" else "Examples"
    name = ex["name"]
    ex_dir = REPO / ex["dir"]
    script = find_script(ex_dir)
    hero_file = page_relative(ex["hero"]).split("/")[-1]

    parts: list[str] = []
    parts.append('  <header class="hero">')
    parts.append(f'    <h1>{html.escape(name)}</h1>')
    parts.append(f'    <p>{html.escape(ex["teaches"])}</p>')
    parts.append("  </header>")
    parts.append('  <main id="main">')
    parts.append(f'    <button class="detail-hero" id="heroZoom" type="button" aria-label="Zoom {html.escape(name)} render">')
    parts.append(f'      <img src="../assets/{html.escape(hero_file)}" alt="{html.escape(name)} render" width="1280" height="720" />')
    parts.append("    </button>")
    parts.append(f'    <p class="zoom-hint">Rendered headless by the {noun} itself — click to zoom.</p>')
    parts.append(f'    <div class="callout"><span class="tag">witnesses</span> {html.escape(ex["witnessesFix"])}</div>')

    if script is not None:
        cmd = f"blender --background --python {ex['dir']}/{script.name} --"
        parts.append('    <div class="runline">')
        parts.append(f'      <pre id="runCmd">{html.escape(cmd)}</pre>')
        parts.append('      <button class="copy-btn" id="copyRun" type="button">Copy</button>')
        parts.append("    </div>")

    readme = ex_dir / "README.md"
    if readme.is_file():
        resolve = make_resolver(base, ex["dir"])
        parts.append('    <section class="detail-section md">')
        parts.append(md_to_html(readme.read_text(encoding="utf-8"), resolve))
        parts.append("    </section>")

    if script is not None:
        blob = f"{base}/{ex['dir']}/{script.name}"
        parts.append('    <section class="detail-section src">')
        parts.append("      <h2>Source</h2>")
        parts.append('      <div class="src-meta">')
        parts.append(f"        <code>{html.escape(ex['dir'])}/{html.escape(script.name)}</code>")
        parts.append(f'        <a href="{html.escape(blob, quote=True)}">View on GitHub &rarr;</a>')
        parts.append("      </div>")
        parts.append(f"      <pre>{highlight_python(script.read_text(encoding='utf-8'))}</pre>")
        parts.append("    </section>")

    parts.append("  </main>")
    parts.append('  <dialog class="lightbox" id="lightbox" aria-label="Full-size render">')
    parts.append('    <button class="lightbox-close" type="button" autofocus>Close</button>')
    parts.append(f'    <img src="../assets/{html.escape(hero_file)}" alt="{html.escape(name)} render, full size" />')
    parts.append("  </dialog>")

    return shell(
        title=f"{name} — {kind_title} — Blender Developer Tools",
        desc=ex["teaches"],
        canonical=f"{site}/gallery/{name}/" if site else "",
        og_image=f"{site}/gallery/assets/{hero_file}" if site else "",
        site_root="../../",
        back_href="../",
        back_label="Examples and Showcase",
        repo_url=repo_root_url,
        content="\n".join(parts),
        page_js=DETAIL_JS,
        sources=(("showcase/gallery.json",) if noun == "showcase piece"
                 else ("examples/gallery.json",)),
    )


def build_index(data: dict, *, base: str, repo_root_url: str, site: str) -> str:
    examples = data["examples"]
    title = data.get("title", "Examples and Showcase")
    desc = data.get("description", "")
    total = len(examples)
    # Showcase pieces share this grid but are not examples. Count and
    # label them separately; the merged total only means anything while
    # filtering, where it is rendered as "N of M" with no noun attached.
    showcase_total = sum(1 for ex in examples if "showcase" in (ex.get("tags") or []))
    example_total = total - showcase_total
    count_label = (
        f"{example_total} examples, {showcase_total} showcase pieces"
        if showcase_total
        else f"{example_total} examples"
    )

    all_tags = sorted({t for ex in examples for t in ex.get("tags", [])})
    chips_html = ""
    if all_tags:
        chips = ['<button class="chip active" data-tag="" type="button">All</button>']
        chips += [
            f'<button class="chip" data-tag="{html.escape(t, quote=True)}" type="button">{html.escape(t)}</button>'
            for t in all_tags
        ]
        chips_html = ('      <div class="chips" id="chips" role="toolbar" aria-label="Filter by topic">\n        '
                      + "\n        ".join(chips) + "\n      </div>\n")

    # Sticky controls bar. Every control is inert but harmless with JS
    # disabled: the search box and toggles do nothing, the count already reads
    # correctly, and all cards render expanded (the compact class is JS-only).
    controls = (
        '  <div class="controls">\n'
        '    <div class="controls-inner">\n'
        '      <div class="controls-row">\n'
        '        <div class="searchwrap">\n'
        '          <input id="q" type="search" placeholder="Search the gallery (press /)"\n'
        '            autocomplete="off" spellcheck="false" aria-label="Search examples and showcase pieces" />\n'
        '          <button class="q-clear" id="qClear" type="button" aria-label="Clear search" hidden>&times;</button>\n'
        '        </div>\n'
        f'        <span class="count" id="count" role="status" aria-live="polite">{html.escape(count_label)}</span>\n'
        '        <div class="density" role="group" aria-label="Card density">\n'
        '          <button class="density-btn" data-density="compact" type="button" aria-pressed="false">Compact</button>\n'
        '          <button class="density-btn" data-density="detailed" type="button" aria-pressed="false">Detailed</button>\n'
        '        </div>\n'
        '        <button class="tags-toggle" id="tagsToggle" type="button" aria-expanded="false" aria-controls="chips">Tags</button>\n'
        '      </div>\n'
        + chips_html +
        '    </div>\n'
        '  </div>\n'
    )

    cards = []
    for ex in examples:
        alt = card_alt(ex["name"], ex["teaches"])
        cards.append(
            CARD
            .replace("__TAGS__", html.escape(" ".join(ex.get("tags", [])), quote=True))
            .replace("__HREF__", html.escape(f'{ex["name"]}/', quote=True))
            .replace("__HERO__", html.escape(page_relative(ex["hero"]), quote=True))
            .replace("__ALT__", html.escape(alt, quote=True))
            .replace("__NAME__", html.escape(ex["name"]))
            .replace("__KIND__", kind_noun(ex))
            .replace("__TEACHES__", html.escape(ex["teaches"]))
            .replace("__WITNESSES__", html.escape(ex["witnessesFix"]))
        )

    content = (
        '  <header class="hero">\n'
        f"    <h1>{html.escape(title)}</h1>\n"
        f"    <p>{html.escape(desc)}</p>\n"
        "  </header>\n"
        + controls
        + '  <main id="main">\n    <div class="grid" id="grid">\n'
        + "\n".join(cards)
        + "\n    </div>\n"
        + '    <p class="noresults" id="noResults" hidden>Nothing matches the current filters.\n'
        + '      <button class="chip" id="resetFilters" type="button">Clear search and tags</button></p>\n'
        + "  </main>\n"
        + '  <button class="to-top" id="toTop" type="button"><span aria-hidden="true">&uarr;</span> Top</button>'
    )

    og_image = f"{site}/gallery/assets/{page_relative(examples[0]['hero']).split('/')[-1]}" if site else ""
    return shell(
        title=f"{title} — Blender Developer Tools",
        desc=desc,
        canonical=f"{site}/gallery/" if site else "",
        og_image=og_image,
        site_root="../",
        back_href="../",
        back_label="Blender Developer Tools",
        repo_url=repo_root_url,
        content=content,
        page_js=INDEX_JS.replace("__COUNT_LABEL__", count_label),
        head_js=INDEX_HEADJS,
        sources=("examples/gallery.json", "showcase/gallery.json"),
    )


def main() -> int:
    data, examples = load_gallery_entries()
    data = dict(data)
    data["examples"] = examples
    base = data["repoBaseUrl"].rstrip("/")
    repo_root_url = base.split("/tree/")[0]  # strip /tree/<ref> -> repo home
    site = data.get("siteBaseUrl", "").rstrip("/")
    examples = data["examples"]
    if not examples:
        print("ERROR: no examples in gallery.json", file=sys.stderr)
        return 2

    for ex in examples:
        if not (REPO / ex["hero"]).is_file():
            print(f"ERROR: hero image missing: {ex['hero']}", file=sys.stderr)
            return 3
        if find_script(REPO / ex["dir"]) is None:
            print(f"ERROR: no .py script in {ex['dir']}", file=sys.stderr)
            return 4

    assert_alts_survive_dotted_paths(examples)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(
        build_index(data, base=base, repo_root_url=repo_root_url, site=site),
        encoding="utf-8",
    )
    for ex in examples:
        page_dir = OUT_DIR / ex["name"]
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(
            build_detail(ex, base=base, repo_root_url=repo_root_url, site=site),
            encoding="utf-8",
        )

    # A renamed or removed entry would otherwise leave its old page published
    # forever. Only folders this generator wrote qualify: a lone index.html
    # and nothing else, so assets/, contact-sheets/ and asset-sheets/ are safe.
    names = {ex["name"] for ex in examples}
    for d in sorted(p for p in OUT_DIR.iterdir() if p.is_dir() and p.name not in names):
        if [c.name for c in d.iterdir()] == ["index.html"]:
            (d / "index.html").unlink()
            d.rmdir()
            print(f"Removed stale page {d.relative_to(REPO)}")

    n_showcase = sum(1 for ex in examples if "showcase" in (ex.get("tags") or []))
    print(
        f"Wrote {OUT_DIR / 'index.html'} + {len(examples)} detail pages "
        f"({len(examples) - n_showcase} examples, {n_showcase} showcase pieces)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
