#!/usr/bin/env python3
"""Generate the examples gallery from examples/gallery.json.

Emits the gallery index (docs/gallery/index.html) AND one detail page per
example (docs/gallery/<name>/index.html) with the hero render (click to
zoom), a run-it-yourself command, the example's README rendered inline, and
a link to the script on GitHub (the source is linked, not inlined, so a page
does not change when only its script does).

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
import hashlib
import html
import json
import posixpath
import re
import sys
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "examples" / "gallery.json"
SHOWCASE_DATA = REPO / "showcase" / "gallery.json"
OUT_DIR = REPO / "docs" / "gallery"
TOKENS_CSS = REPO / "scripts" / "site" / "tokens.css"

# The shared header/footer (scripts/site/chrome.py), also used by the landing build.
sys.path.insert(0, str(REPO / "scripts" / "site"))
import chrome  # noqa: E402

SITE_TITLE = "Blender Developer Tools"
# One license string for every footer: the landing build reads the same
# manifest field, so the two cannot disagree (#454).
LICENSE = json.loads((REPO / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"))["license"]

# Slug words that a plain .capitalize() would mangle in a display title.
TITLE_WORDS = {
    "gn": "GN", "sdf": "SDF", "gltf": "glTF", "vse": "VSE", "uv": "UV", "lod": "LOD",
    "png": "PNG", "exr": "EXR", "ao": "AO", "usd": "USD", "gp": "GP", "bmesh": "BMesh",
}


def display_title(entry: dict) -> str:
    """``title`` from gallery.json when present, else the slug as words:
    ``gn-sdf-remesh`` -> ``GN SDF Remesh``."""
    if entry.get("title"):
        return entry["title"]
    return " ".join(TITLE_WORDS.get(w, w.capitalize()) for w in entry["name"].split("-"))


def thumb_path(hero: str) -> str:
    """``…-hero.webp`` -> ``…-hero-640.webp`` (written by scripts/make_thumbs.py)."""
    return re.sub(r"\.webp$", "-640.webp", hero)


# Card renders: srcset lets a compact card or a 1x screen take the 640 variant.
CARD_SIZES = "(min-width: 900px) 340px, (min-width: 560px) 50vw, 100vw"
MINI_SIZES = "(min-width: 560px) 340px, 100vw"

# Social card for the gallery index, shared with the landing page (site.json).
OG_CARD_SIZE = (1200, 630)
OG_CARD_ALT = ("Four renders from the examples gallery: a red low-poly hatchback, a soccer "
               "ball, gold spikes aimed at a glowing sphere, and two spheres on pedestals "
               "labelled linked and unlinked")

# Upper bound for an entry's ``alt`` (one descriptive sentence, never truncated).
ALT_MAX = 200

# Showcase categories, in display order: key -> chip label. Every showcase
# piece must carry one of these keys as ``category``; examples carry none.
CATEGORIES = {
    "village": "Village",
    "sports": "Sports",
    "nature": "Nature",
    "household": "Household",
    "vehicles": "Vehicles",
    "terrain": "Terrain",
}


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


def check_alts(entries: list) -> None:
    """Every entry needs an ``alt``: one sentence saying what its still shows.

    Alts used to be derived from ``teaches``, which describes the API, not the
    picture, and was cut at 160 characters (#213). A description cannot be
    derived; it has to be written, so a missing one fails the build.
    """
    for e in entries:
        alt = (e.get("alt") or "").strip()
        if not alt:
            raise SystemExit(f"gallery entry {e['name']!r} has no 'alt': add one sentence "
                             "describing what its still shows")
        if len(alt) > ALT_MAX:
            raise SystemExit(f"gallery entry {e['name']!r} alt is {len(alt)} chars "
                             f"(max {ALT_MAX}); describe the still in one sentence")
        if "`" in alt:
            # An attribute cannot carry <code>, so a backtick would be read
            # aloud and shown literally; teaches/witnessesFix render it (#368).
            raise SystemExit(f"gallery entry {e['name']!r} alt contains a backtick; "
                             "alt text is plain prose")


def inline_code(text: str) -> str:
    """Escape text and render its `backtick` spans as <code>, as the landing
    page does. Unbalanced backticks stay literal."""
    parts = html.escape(text).split("`")
    if len(parts) % 2 == 0:
        return "`".join(parts)
    return "".join(f"<code>{p}</code>" if i % 2 else p for i, p in enumerate(parts))


def check_categories(entries: list) -> None:
    """Every showcase piece names a known ``category``; no example names one.

    The category chips are built from the values present, so a typo would
    silently spawn a one-card chip instead of failing.
    """
    for e in entries:
        cat = e.get("category")
        if kind_noun(e) == "showcase piece":
            if cat not in CATEGORIES:
                raise SystemExit(f"showcase piece {e['name']!r} has category {cat!r}; "
                                 f"expected one of {', '.join(CATEGORIES)}")
        elif cat is not None:
            raise SystemExit(f"example {e['name']!r} has a 'category'; only showcase pieces do")

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
__CANONICALTAGS__  <link rel="icon" href="__SITEROOT__assets/favicon.svg" type="image/svg+xml" />
  <meta name="theme-color" content="#1a1b1e" />
  <meta name="color-scheme" content="dark" />
  <meta property="og:type" content="__OGTYPE__" />
  <meta property="og:title" content="__TITLE__" />
  <meta property="og:description" content="__DESC__" />
__OGIMAGETAGS__  <meta property="og:site_name" content="Blender Developer Tools" />
  <meta name="twitter:title" content="__TITLE__" />
  <meta name="twitter:description" content="__DESC__" />
  <link rel="preload" href="__SITEROOT__fonts/inter-regular.woff2" as="font" type="font/woff2" crossorigin />
  <link rel="preload" href="__SITEROOT__fonts/inter-medium.woff2" as="font" type="font/woff2" crossorigin />
  <link rel="preload" href="__SITEROOT__fonts/barlow-condensed-600.woff2" as="font" type="font/woff2" crossorigin />
  <link rel="preload" href="__SITEROOT__fonts/jetbrains-mono-regular.woff2" as="font" type="font/woff2" crossorigin />
  <link rel="stylesheet" href="__GALLERYROOT__gallery.css?v=__CSSV__" />
  <script>document.documentElement.classList.add('js');</script>__HEADJS__
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
__HEADER__
__CONTENT__
__FOOTER__
  <p class="sr-only" id="srStatus" role="status" aria-live="polite"></p>
  <script>
__CHROMEJS__
__PAGEJS__
  </script>
</body>
</html>
"""

# One stylesheet for every gallery page, written to docs/gallery/gallery.css
# (cached once instead of inlined into each page). __TOKENS__ and __CHROME__
# are filled from scripts/site/tokens.css and scripts/site/chrome.py.
GALLERY_CSS = """    /* fonts are deployed by the landing build (docs/fonts/); this file is
       docs/gallery/gallery.css, so ../fonts/ is relative to it */
    @font-face { font-family: 'Barlow Condensed'; font-weight: 600; font-display: swap;
      src: url('../fonts/barlow-condensed-600.woff2') format('woff2'); }
    @font-face { font-family: 'Inter'; font-weight: 400; font-display: swap;
      src: url('../fonts/inter-regular.woff2') format('woff2'); }
    @font-face { font-family: 'Inter'; font-weight: 500; font-display: swap;
      src: url('../fonts/inter-medium.woff2') format('woff2'); }
    @font-face { font-family: 'JetBrains Mono'; font-weight: 400; font-display: swap;
      src: url('../fonts/jetbrains-mono-regular.woff2') format('woff2'); }

    /* Palette and type: scripts/site/tokens.css, shared with the landing page. */
__TOKENS__
__CHROME__
    :root {
      --radius: 4px; --radius-lg: 6px; --maxw: var(--chrome-maxw);
      --code-k: #ff7b72; --code-s: #a5d6ff; --code-c: var(--dim); --code-n: #79c0ff;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html { scroll-behavior: smooth; }
    body { font-family: var(--font-sans); background: var(--bg); color: var(--text);
      line-height: 1.6; min-height: 100vh; -webkit-font-smoothing: antialiased; }
    a { color: var(--select); text-decoration: none; }
    a:hover { text-decoration: underline; }
    :focus-visible { outline: 2px solid var(--select); outline-offset: 2px; border-radius: 3px; }
    ::selection { background: color-mix(in srgb, var(--select) 40%, transparent); }
    .skip { position: absolute; left: -999px; top: 0; background: var(--select); color: var(--on-select);
      padding: 0.5rem 1rem; border-radius: var(--radius); z-index: 10; font-weight: 500; }
    .skip:focus { left: 0.5rem; top: 0.5rem; }
    .hud { font-family: var(--font-mono); font-size: 0.6875rem; letter-spacing: 0.04em;
      color: var(--text-dim); text-transform: uppercase; }

    .crumbs { font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.04em;
      text-transform: uppercase; color: var(--text-dim); margin-bottom: 0.9rem; }
    .crumbs ol { list-style: none; display: flex; flex-wrap: wrap; gap: 0.2rem 0.5rem; }
    .crumbs li + li::before { content: '/'; margin-right: 0.5rem; color: var(--border); }
    .crumbs a { color: var(--text-dim); }
    .crumbs a:hover { color: var(--select); text-decoration: none; }
    .slug { font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-dim); }
    header.hero .slug { margin-top: 0.35rem; font-size: 0.85rem; }

    /* Page headers are centered (title, slug, intro, crumbs); dense content
       below (README prose, source, tables) stays left for reading. */
    header.hero { max-width: var(--maxw); margin: 0 auto; padding: 2.75rem 1.25rem 1.25rem; text-align: center; }
    header.hero .crumbs ol { justify-content: center; }
    header.hero h1 { font-family: var(--font-display); font-weight: 600; text-transform: uppercase;
      font-size: clamp(2.2rem, 5vw, 3.4rem); letter-spacing: 0.005em; line-height: 0.98; }
    header.hero p { color: var(--text-dim); max-width: 62ch; margin: 0.7rem auto 0; font-size: 1rem; }
    /* Check-only examples: the line that explains the rendered vs total gap.
       Summary centered with the header; the list inside is left for reading. */
    .check-only { max-width: 62ch; margin: 0.8rem auto 0; font-size: 0.9rem; color: var(--text-dim); }
    .check-only summary { cursor: pointer; width: fit-content; margin: 0 auto; }
    .check-only summary:hover { color: var(--text); }
    .check-only > div { text-align: left; margin-top: 0.6rem; }
    .check-only ul { margin: 0.5rem 0 0 1.1rem; }
    .check-only li { margin: 0.25rem 0; }
    .check-only a { color: var(--text); text-decoration: underline; text-underline-offset: 2px; font-family: var(--font-mono); font-size: 0.85rem; }
    .check-only code { font-family: var(--font-mono); font-size: 0.85em; }

    /* ---- index: filter bar ----
       Wide: one pinned row (search | kind | sort | card density), then a
       centered topics panel (categories + topic chips), then one results
       line. Phones fold everything behind a single Filters button. */
    .controls { position: sticky; top: 46px; z-index: 4;
      background: color-mix(in srgb, var(--bg) 94%, transparent);
      backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--border); }
    .controls-inner { max-width: var(--maxw); margin: 0 auto; padding: 0.55rem 1.25rem 0.6rem;
      display: flex; flex-direction: column; gap: 0.5rem; }
    .controls-row { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
    .searchwrap { position: relative; flex: 1 1 260px; min-width: 150px; }
    .searchwrap input { width: 100%; min-height: 36px; background: var(--surface-2); border: 1px solid var(--border);
      color: var(--text); border-radius: var(--radius); padding: 0.4rem 1.9rem 0.4rem 0.8rem;
      font-family: var(--font-sans); font-size: 0.875rem; line-height: 1.4; }
    .searchwrap input:focus { border-color: var(--select); outline: none; }
    .searchwrap input::placeholder { color: var(--text-dim); }
    .searchwrap input::-webkit-search-cancel-button { -webkit-appearance: none; appearance: none; }
    .q-clear { position: absolute; right: 0.2rem; top: 50%; transform: translateY(-50%);
      background: none; border: none; color: var(--text-dim); font-size: 1.05rem; line-height: 1;
      cursor: pointer; padding: 0.25rem 0.45rem; border-radius: 3px; }
    .q-clear:hover { color: var(--select); }
    .count { font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.04em;
      text-transform: uppercase; color: var(--text-dim); white-space: nowrap; }
    .results { text-align: center; margin: 1rem auto 0; padding: 0 1.25rem; }
    .view-controls { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
    .density { display: flex; border: 1px solid var(--border); border-radius: var(--radius);
      overflow: hidden; }
    .density-btn { background: var(--surface-2); border: none; color: var(--text-dim); cursor: pointer;
      font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.04em; min-height: 34px;
      text-transform: uppercase; padding: 0.4rem 0.8rem; transition: color 0.15s, background 0.15s; }
    .density-btn + .density-btn { border-left: 1px solid var(--border); }
    .density-btn:hover { color: var(--select); }
    .density-btn.active { background: var(--select); color: var(--on-select); }
    /* Card density is a view option, not a filter: selected state stays neutral
       so orange only ever means "this is filtering the grid". */
    .view-mode .density-btn.active { background: var(--border); color: var(--text); }
    /* Segmented groups clip overflow, so the ring has to sit inside. */
    .density-btn:focus-visible, .chip:focus-visible { outline-offset: -2px; }
    /* On a selected (orange) button an orange ring vanishes into the fill
       (#397): draw a dark inset ring instead, ~7.8:1 against --select. */
    .density-btn.active:focus-visible, .cat-btn.active:focus-visible,
    .chip.active:focus-visible { outline: 2px solid var(--on-select); outline-offset: -4px; }
    .sort select { background: var(--surface-2); border: 1px solid var(--border); color: var(--text-dim);
      border-radius: var(--radius); padding: 0.4rem 0.6rem; min-height: 36px; cursor: pointer;
      font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.04em; text-transform: uppercase; }
    .sort select:hover, .sort select:focus { color: var(--select); border-color: var(--select); outline: none; }

    /* Topics panel: category tabs, then topic chips. */
    .filters { display: flex; flex-direction: column; align-items: center; gap: 0.8rem; }
    .cats { justify-content: center; }
    .cats[hidden] { display: none; }
    .cats .density { flex: 0 0 auto; }
    .cats-label { font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.04em;
      text-transform: uppercase; color: var(--text-dim); flex: 0 0 auto; }
    .filters-toggle { display: none; background: var(--surface-2); border: 1px solid var(--border);
      color: var(--text-dim); border-radius: var(--radius); padding: 0.4rem 0.8rem; cursor: pointer; min-height: 36px;
      font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.04em; text-transform: uppercase;
      white-space: nowrap; }
    .filters-toggle:hover, .filters-toggle.has-active { color: var(--select); border-color: var(--select); }
    .cat-btn { background: var(--surface-2); border: none; color: var(--text-dim); cursor: pointer;
      font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.04em; white-space: nowrap; min-height: 34px;
      text-transform: uppercase; padding: 0.4rem 0.8rem; transition: color 0.15s, background 0.15s; }
    .cat-btn + .cat-btn { border-left: 1px solid var(--border); }
    .cat-btn:hover { color: var(--select); }
    .cat-btn.active { background: var(--select); color: var(--on-select); }
    .cat-btn:focus-visible { outline-offset: -2px; }

    /* Topic chips wrap in full by default (no-JS safe). With JS they collapse
       to two rows behind a "Show all" toggle; no nested scrollbar. */
    .chips { display: flex; flex-wrap: wrap; justify-content: center; gap: 0.4rem; }
    html.js .chips { max-height: 3.5rem; overflow: hidden; }
    html.js .chips.expanded { max-height: none; }
    .chips-more { background: none; border: none; color: var(--text-dim); cursor: pointer; padding: 0.15rem 0.5rem;
      font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.04em; text-decoration: underline;
      text-underline-offset: 3px; }
    .chips-more:hover { color: var(--select); }
    .chips-more[hidden] { display: none; }
    .chip { background: var(--surface-2); border: 1px solid var(--border); color: var(--text-dim);
      border-radius: 3px; padding: 0.22rem 0.7rem; font-size: 0.72rem; font-weight: 400;
      font-family: var(--font-mono); cursor: pointer; white-space: nowrap; flex: 0 0 auto;
      transition: color 0.15s, border-color 0.15s; }
    .chip:hover { color: var(--select); border-color: var(--select); }
    .chip.active { color: var(--on-select); background: var(--select); border-color: var(--select); }
    .chip .n { font-size: 0.66rem; margin-left: 0.15rem; }  /* inherits chip color: full contrast */
    /* Active-filter pills live in the pinned row, so a filter is visible and
       removable even after the topics panel scrolls away. */
    .active-filters { flex: 0 0 100%; display: flex; flex-wrap: wrap; align-items: center; gap: 0.35rem; }
    .active-filters[hidden] { display: none; }
    .pill { background: var(--surface-2); border: 1px solid var(--select); color: var(--text); cursor: pointer;
      border-radius: 3px; padding: 0.1rem 0.5rem; font-family: var(--font-mono); font-size: 0.72rem; }
    .pill:hover { color: var(--select); }
    .pill-clear { border-color: var(--border); color: var(--text-dim); }
    @media (max-width: 639px) { .active-filters { display: none; } }

    /* Wide screens: only the search row stays pinned; the topics panel scrolls
       away with the page ("/" or scrolling up brings it back). */
    @media (min-width: 640px) {
      .controls, .controls-inner { display: contents; }
      .controls-main { position: sticky; top: 46px; z-index: 4;
        padding: 0.6rem max(1.25rem, calc((100% - var(--maxw)) / 2 + 1.25rem));
        background: color-mix(in srgb, var(--bg) 94%, transparent);
        backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
        border-bottom: 1px solid var(--border); }
      .filters { width: calc(100% - 2.5rem); max-width: calc(var(--maxw) - 2.5rem); margin: 1.1rem auto 0;
        padding: 1.1rem 1.25rem 1rem; background: var(--surface); border: 1px solid var(--border);
        border-radius: var(--radius-lg); }
    }
    @media (max-width: 639px) {
      .controls-inner { padding: 0.45rem 1rem 0.5rem; gap: 0.4rem; }
      .controls-row { gap: 0.4rem; }
      .density-btn, .cat-btn { padding: 0.4rem 0.55rem; }
      .results { margin-top: 0.7rem; }
      html.js .searchwrap { flex: 1 1 0; min-width: 0; }
      html.js .filters-toggle { display: inline-block; }
      html.js .view-controls { display: none; flex: 0 0 100%; }
      html.js .controls.open .view-controls { display: flex; }
      html.js .filters { display: none; max-height: calc(100vh - 230px); max-height: calc(100dvh - 230px); overflow-y: auto;
        padding: 0.4rem 0 0.2rem; border-top: 1px solid var(--border); }
      html.js .filters.open { display: flex; }
      html.js .filters .chips { max-height: none; overflow: visible; }
      html.js .chips-more { display: none; }
      /* Category tabs wrap as separate bordered buttons instead of clipping. */
      html.js .cats { flex-wrap: wrap; }
      html.js .cats .density { flex: 0 1 auto; flex-wrap: wrap; justify-content: center; gap: 0.4rem;
        border: none; overflow: visible; }
      html.js .cats .cat-btn { border: 1px solid var(--border); border-radius: var(--radius); }
      html.js .cats .cat-btn.active { border-color: var(--select); }
    }

    /* Compact density: hero + name + one-line teaser. The description and
       WITNESSES text stay in the DOM (searchable, screen-reader reachable,
       present with JS disabled when the class is never applied) but are
       visually collapsed. Applied only by JS via the density-compact class. */
    html.density-compact .grid { gap: 1rem; }
    html.density-compact .card-body { padding: 0.65rem 0.9rem 0.7rem; }
    html.density-compact .card-body h2 { font-size: 0.95rem; margin-bottom: 0.15rem; }
    html.density-compact .teaches { font-size: 0.8rem; color: var(--text-dim); margin-bottom: 0;
      display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden; }
    html.density-compact .witnesses { position: absolute; width: 1px; height: 1px; margin: -1px;
      padding: 0; overflow: hidden; clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap; }
    html.density-compact .card-body .slug { display: none; }
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
    .card { position: relative; }
    .card:hover, .card:focus-within { border-color: var(--select); outline-color: var(--select); }
    /* One link per card: the title's ::after covers the whole card, so the
       render and body are clickable without a second, duplicate link. */
    .card .stretch::after { content: ''; position: absolute; inset: 0; z-index: 1; }
    .card .stretch:focus-visible { outline: none; }
    .card.hidden { display: none; }
    .card-media { display: block; background: var(--bg2); line-height: 0; overflow: hidden; position: relative; }
    /* Kind badge: examples are the default, so only showcase pieces are marked. */
    .card[data-kind="showcase"] .card-media::after { content: "Showcase"; position: absolute; top: 0.5rem; left: 0.5rem;
      background: color-mix(in srgb, var(--bg) 82%, transparent); color: var(--text); border: 1px solid var(--border);
      border-radius: 3px; padding: 0.12rem 0.45rem; line-height: 1.4; font-family: var(--font-mono);
      font-size: 0.68rem; letter-spacing: 0.04em; text-transform: uppercase; pointer-events: none; }
    .card-media img { display: block; width: 100%; height: auto; aspect-ratio: 16 / 9; object-fit: cover;
      transition: transform 0.35s ease, opacity 0.3s ease; }
    .card:hover .card-media img { transform: scale(1.03); }
    html.js .grid .card-media img { opacity: 0; }
    html.js .grid .card-media img.is-loaded { opacity: 1; }
    .card-body { padding: 1.15rem 1.4rem 1.45rem; display: flex; flex-direction: column; flex: 1 1 auto; }
    .card-body h2 { font-size: 1.02rem; font-weight: 500; line-height: 1.3; }
    .card-body h2 a { color: var(--text); }
    .card-body h2 a:hover, .card:hover .card-body h2 a { color: var(--select); text-decoration: none; }
    .card-body .slug { margin: 0.1rem 0 0.5rem; }
    .teaches { color: var(--text); margin-bottom: 0.7rem; font-size: 0.92rem; }
    .witnesses { color: var(--text-dim); font-size: 0.85rem; margin-bottom: 1rem; }
    .tag { display: inline-block; font-family: var(--font-mono); font-size: 0.62rem; text-transform: uppercase;
      letter-spacing: 0.06em; color: var(--select); border: 1px solid color-mix(in srgb, var(--select) 55%, transparent);
      border-radius: 3px; padding: 0.08rem 0.5rem; margin-right: 0.4rem; vertical-align: 1px; }
    .card-link { font-weight: 600; font-size: 0.95rem; margin-top: auto; color: var(--select); }

    /* ---- detail page ---- */
    .detail-hero { border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden;
      background: var(--bg2); padding: 0; display: block; width: 100%; cursor: zoom-in; line-height: 0; }
    .detail-hero img { display: block; width: 100%; height: auto; aspect-ratio: 16 / 9; object-fit: cover; }
    .zoom-hint { color: var(--text-dim); font-size: 0.78rem; margin-top: 0.4rem; text-align: center; }
    .sr-only { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden;
      clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap; border: 0; }
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
    .detail-section { margin-top: 2.25rem; scroll-margin-top: 60px; }
    .detail-section > h2 { font-family: var(--font-display); font-weight: 600; text-transform: uppercase;
      font-size: 1.45rem; letter-spacing: 0.005em; padding-bottom: 0.5rem;
      border-bottom: 1px solid var(--border); margin-bottom: 1rem; }

    .md h1, .md h2, .md h3 { letter-spacing: -0.01em; margin: 1.4rem 0 0.6rem; line-height: 1.25; }
    .md h1 { font-size: 1.35rem; } .md h2 { font-size: 1.15rem; } .md h3 { font-size: 1rem; }
    .md p { margin: 0.7rem 0; }
    .md > p, .md > ul, .md > ol, .md > h2, .md > h3 { max-width: 75ch; }
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

    .src-meta { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem;
      flex-wrap: wrap; margin-bottom: 0.6rem; color: var(--text-dim); font-size: 0.85rem; }
    .src-meta code { font-family: var(--font-mono); font-size: 0.82rem; }

    /* ---- detail page: pager, tags, related, anchors, code blocks ---- */
    .pager { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 0.75rem;
      margin: 0 0 1.25rem; font-size: 0.85rem; }
    .pager-foot { margin: 2.5rem 0 0; padding-top: 1rem; border-top: 1px solid var(--border); }
    .pager a { color: var(--text-dim); font-family: var(--font-mono); font-size: 0.8rem;
      display: flex; align-items: baseline; gap: 0.35em; min-width: 0; white-space: nowrap; }
    /* Only the name truncates; the arrow is its own box so it never clips (#399). */
    .pager-label { overflow: hidden; text-overflow: ellipsis; min-width: 0; }
    .pager a:hover { color: var(--select); text-decoration: none; }
    .pager [rel="next"] { justify-content: flex-end; }
    .pager-pos { text-align: center; }
    @media (max-width: 559px), (hover: none) { .pager-keys { display: none; } }
    .pager kbd { font-family: var(--font-mono); font-size: 0.65rem; border: 1px solid var(--border);
      border-radius: 3px; padding: 0 0.3rem; margin: 0 0.1rem; }
    .taglist, .jumpnav { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 0.4rem; margin: -0.5rem 0 1.5rem; }
    #related > h2 { text-align: center; }
    .jumpnav { margin: 1.25rem 0 0; }
    /* anchored sections land below the sticky site header */
    .detail-section, .md h2[id] { scroll-margin-top: 4rem; }
    .taglist a, .jumpnav a { font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-dim);
      background: var(--surface-2); border: 1px solid var(--border); border-radius: 3px;
      padding: 0.12rem 0.6rem; transition: color 0.15s, border-color 0.15s; }
    .taglist a:hover, .jumpnav a:hover { color: var(--select); border-color: var(--select); text-decoration: none; }
    .related-grid { display: grid; grid-template-columns: 1fr; gap: 1rem; }
    @media (min-width: 560px) { .related-grid { grid-template-columns: repeat(3, 1fr); } }
    .card.mini .card-body { padding: 0.65rem 0.9rem 0.75rem; }
    .card.mini h3 { font-size: 0.9rem; font-weight: 500; margin-bottom: 0.2rem; }
    .card.mini h3 a { color: var(--text); }
    .card.mini h3 a:hover, .card.mini:hover h3 a { color: var(--select); text-decoration: none; }
    .card.mini p { color: var(--text-dim); font-size: 0.78rem; line-height: 1.45;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .md h1, .md h2, .md h3 { scroll-margin-top: 60px; }
    .anchor { color: var(--text-dim); margin-left: 0.4rem; font-weight: 400; opacity: 0;
      transition: opacity 0.15s; }
    .md h1:hover .anchor, .md h2:hover .anchor, .md h3:hover .anchor, .anchor:focus-visible { opacity: 1; }
    .anchor:hover { color: var(--select); text-decoration: none; }
    .codewrap { position: relative; }
    .codewrap > .copy-btn { position: absolute; top: 0.45rem; right: 0.45rem; padding: 0.2rem 0.55rem;
      font-size: 0.72rem; opacity: 0; transition: opacity 0.15s, color 0.15s, border-color 0.15s; }
    .codewrap:hover > .copy-btn, .codewrap > .copy-btn:focus-visible, .codewrap > .copy-btn.done { opacity: 1; }
    @media (hover: none) { .codewrap > .copy-btn { opacity: 1; } }
    .copy-btn.done { color: var(--ok); border-color: var(--ok); }
    .copy-btn.fail { color: var(--code-k); border-color: var(--code-k); }

    .lightbox { border: 0; margin: 0; padding: 2rem; width: 100%; height: 100%; max-width: none;
      max-height: none; background: var(--scrim); cursor: zoom-out; }
    /* margin:auto (not align/justify-content) centers without clipping the
       top-left of a native-size image that overflows a small viewport. */
    .lightbox[open] { display: flex; overflow: auto; }
    .lightbox::backdrop { background: transparent; }
    .lightbox img { margin: auto; max-width: 100%; max-height: 100%; border-radius: var(--radius);
      cursor: zoom-in; }
    .lightbox.native img { max-width: none; max-height: none; cursor: zoom-out; }
    .lightbox-bar { position: absolute; top: 0.9rem; right: 0.9rem; display: flex; gap: 0.5rem; }
    .lightbox-close { background: var(--surface-2);
      color: var(--text); border: 1px solid var(--border); border-radius: var(--radius);
      font: 500 0.8rem var(--font-sans); padding: 0.4rem 0.75rem; cursor: pointer; }
    .lightbox-close:hover { border-color: var(--select); color: var(--select); }

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
      *, *::before, *::after { transition: none !important; }
      .card:hover .card-media img { transform: none; }
    }
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
      var chips = chipsEl ? Array.prototype.slice.call(chipsEl.querySelectorAll('.chip')) : [];
      var q = document.getElementById('q');
      // Touch devices have no "/" key shortcut to advertise (#399).
      if (q && window.matchMedia && window.matchMedia('(hover: none)').matches) {
        q.placeholder = 'Search the gallery';
      }
      var qClear = document.getElementById('qClear');
      var count = document.getElementById('count');
      var noResults = document.getElementById('noResults');
      var resetFilters = document.getElementById('resetFilters');
      var densityBtns = Array.prototype.slice.call(document.querySelectorAll('[data-density]'));
      var kindBtns = Array.prototype.slice.call(document.querySelectorAll('[data-kind-filter]'));
      var catRow = document.getElementById('cats');
      var catBtns = Array.prototype.slice.call(document.querySelectorAll('[data-cat-filter]'));
      var CATS = catBtns.map(function (b) { return b.getAttribute('data-cat-filter'); });
      var sortSel = document.getElementById('sort');
      var filtersEl = document.getElementById('filters');
      var filtersToggle = document.getElementById('filtersToggle');
      var toTop = document.getElementById('toTop');
      var total = cards.length;
      var COUNT_LABEL = '__COUNT_LABEL__';
      var LS_KEY = 'bdt-gallery-density';
      // Read by detail pages: the Gallery crumb returns here, and the pager
      // walks the reader's filtered order instead of the full gallery.
      var SS_HASH = 'bdt-gallery-hash', SS_ORDER = 'bdt-gallery-order';
      var KINDS = ['', 'examples', 'showcase'];
      var SORTS = ['default', 'az', 'kind', 'cat'];
      var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      // data-search holds title, slug, teaches, tags and category. Each
      // query word must appear somewhere in it (AND), in any order.
      var haystacks = cards.map(function (c) { return c.getAttribute('data-search') || ''; });
      var cardTags = cards.map(function (c) { return (c.getAttribute('data-tags') || '').split(' '); });
      var knownTags = chips.map(function (c) { return c.getAttribute('data-tag') || ''; })
        .filter(function (t) { return t; });
      var state = { q: '', tags: [], kind: '', cat: '', sort: 'default', density: 'compact' };

      // Fade card renders in once decoded; images already complete (cache,
      // eager) are marked immediately so nothing stays invisible.
      cards.forEach(function (c) {
        var img = c.querySelector('.card-media img');
        if (!img) return;
        function done() { img.classList.add('is-loaded'); }
        if (img.complete) { done(); }
        else { img.addEventListener('load', done); img.addEventListener('error', done); }
      });

      function parseHash() {
        var out = {};
        location.hash.replace(/^#/, '').split('&').forEach(function (kv) {
          var i = kv.indexOf('=');
          if (i < 0) return;
          var k = kv.slice(0, i), v = kv.slice(i + 1);
          try { v = decodeURIComponent(v); } catch (e) {}
          if (k === 'q' || k === 'tag' || k === 'd' || k === 'k' || k === 'c' || k === 's') out[k] = v;
        });
        return out;
      }

      function filtered() {
        return !!(state.q.trim() || state.tags.length || state.kind || state.cat || state.sort !== 'default');
      }

      function remember() {
        try {
          sessionStorage.setItem(SS_HASH, location.hash);
          if (filtered()) {
            var order = [];
            Array.prototype.forEach.call(grid.children, function (c) {
              if (c.classList.contains('card') && !c.classList.contains('hidden')) {
                order.push(c.getAttribute('data-name'));
              }
            });
            sessionStorage.setItem(SS_ORDER, JSON.stringify(order));
          } else {
            sessionStorage.removeItem(SS_ORDER);
          }
        } catch (e) {}
      }

      // Discrete changes (chips, pills, kind, category, sort, reset) push a
      // history entry so Back undoes them; typing and density replace it.
      function writeHash(push) {
        var parts = [];
        if (state.q) parts.push('q=' + encodeURIComponent(state.q));
        if (state.tags.length) parts.push('tag=' + state.tags.map(encodeURIComponent).join(','));
        if (state.kind) parts.push('k=' + state.kind);
        if (state.cat) parts.push('c=' + state.cat);
        if (state.sort !== 'default') parts.push('s=' + state.sort);
        parts.push('d=' + state.density);
        var url = location.pathname + location.search + '#' + parts.join('&');
        if (push && url !== location.pathname + location.search + location.hash) history.pushState(null, '', url);
        else history.replaceState(null, '', url);
        remember();
      }
      var hashTimer = 0;
      function writeHashSoon() {
        clearTimeout(hashTimer);
        hashTimer = setTimeout(writeHash, 250);
      }

      function syncChips() {
        chips.forEach(function (c) {
          var t = c.getAttribute('data-tag') || '';
          var on = t ? state.tags.indexOf(t) !== -1 : state.tags.length === 0;
          c.classList.toggle('active', on);
          c.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
      }

      function syncSeg(btns, attr, value) {
        btns.forEach(function (b) {
          var on = b.getAttribute(attr) === value;
          b.classList.toggle('active', on);
          b.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
      }

      // The phone drawer button names how many filters are on, so a shared
      // filtered link never looks unfiltered with the drawer shut.
      function syncFiltersToggle() {
        var n = state.tags.length + (state.kind ? 1 : 0) + (state.cat ? 1 : 0) +
          (state.sort !== 'default' ? 1 : 0);
        filtersToggle.textContent = n ? 'Filters (' + n + ')' : 'Filters';
        filtersToggle.classList.toggle('has-active', n > 0);
      }

      // One removable pill per active filter, in the pinned search row.
      var pillsEl = document.getElementById('activeFilters');
      function syncPills() {
        if (!pillsEl) return;
        var items = state.tags.map(function (t) { return { label: t, drop: function () { state.tags.splice(state.tags.indexOf(t), 1); } }; });
        if (state.kind) items.push({ label: state.kind, drop: function () { state.kind = ''; } });
        if (state.cat) items.push({ label: state.cat, drop: function () { state.cat = ''; } });
        pillsEl.textContent = '';
        items.forEach(function (it) {
          var b = document.createElement('button');
          b.type = 'button'; b.className = 'pill';
          b.textContent = it.label + ' \\u00d7';
          b.setAttribute('aria-label', 'Remove filter: ' + it.label);
          b.addEventListener('click', function () {
            it.drop(); syncChips(); applyFilters(); writeHash(true);
          });
          pillsEl.appendChild(b);
        });
        if (items.length > 1) {
          var all = document.createElement('button');
          all.type = 'button'; all.className = 'pill pill-clear'; all.textContent = 'Clear all';
          all.addEventListener('click', function () { if (resetFilters) resetFilters.click(); });
          pillsEl.appendChild(all);
        }
        pillsEl.hidden = items.length === 0;
      }

      // Topic chips collapse to two rows; "Show all N topics" reveals the rest.
      var moreBtn = document.getElementById('chipsMore');
      function chipClipped(el) {
        return el.getBoundingClientRect().bottom > chipsEl.getBoundingClientRect().bottom + 1;
      }
      function setChipsExpanded(on) {
        chipsEl.classList.toggle('expanded', on);
        moreBtn.setAttribute('aria-expanded', on ? 'true' : 'false');
        moreBtn.textContent = on ? 'Show fewer topics' : 'Show all ' + (chips.length - 1) + ' topics';
      }
      function measureChips() {
        if (!chipsEl || !moreBtn) return;
        var was = chipsEl.classList.contains('expanded');
        chipsEl.classList.remove('expanded');
        var over = chipsEl.scrollHeight > chipsEl.clientHeight + 2;
        if (was) chipsEl.classList.add('expanded');
        moreBtn.hidden = !over && !was;
      }
      if (chipsEl && moreBtn) {
        moreBtn.addEventListener('click', function () {
          setChipsExpanded(!chipsEl.classList.contains('expanded'));
        });
        // Keyboard focus never lands on a clipped chip: reveal the row first.
        chipsEl.addEventListener('focusin', function (e) {
          if (!chipsEl.classList.contains('expanded') && chipClipped(e.target)) setChipsExpanded(true);
        });
        window.addEventListener('resize', measureChips);
      }

      function applyDensity() {
        de.classList.toggle('density-compact', state.density === 'compact');
        syncSeg(densityBtns, 'data-density', state.density);
        try { localStorage.setItem(LS_KEY, state.density); } catch (e) {}
      }

      function applySort() {
        var order = cards.slice();
        if (state.sort === 'az') {
          order.sort(function (a, b) {
            var x = a.getAttribute('data-name'), y = b.getAttribute('data-name');
            return x < y ? -1 : x > y ? 1 : 0;
          });
        } else if (state.sort === 'kind' || state.sort === 'cat') {
          // Stable by gallery order within each group. Examples have no
          // category and sort first; showcase pieces follow CATEGORIES order.
          var rank = function (c) {
            if (c.getAttribute('data-kind') !== 'showcase') return -1;
            return state.sort === 'cat' ? CATS.indexOf(c.getAttribute('data-category')) : 0;
          };
          var pos = new Map(cards.map(function (c, i) { return [c, i]; }));
          order.sort(function (a, b) { return (rank(a) - rank(b)) || (pos.get(a) - pos.get(b)); });
        }
        order.forEach(function (c) { grid.appendChild(c); });
        sortSel.value = state.sort;
        syncFiltersToggle();
      }

      function applyFilters() {
        var words = state.q.trim().toLowerCase().split(/\\s+/).filter(function (w) { return w; });
        var shown = 0;
        // Categories only partition showcase pieces; the examples view has
        // none, so it hides the row and drops any category left selected.
        if (state.kind === 'examples') state.cat = '';
        if (catRow) catRow.hidden = state.kind === 'examples';
        cards.forEach(function (card, i) {
          var kindOK = !state.kind || card.getAttribute('data-kind') === state.kind;
          var catOK = !state.cat || card.getAttribute('data-category') === state.cat;
          var tagOK = state.tags.every(function (t) { return cardTags[i].indexOf(t) !== -1; });
          var qOK = words.every(function (w) { return haystacks[i].indexOf(w) !== -1; });
          var show = kindOK && catOK && tagOK && qOK;
          card.classList.toggle('hidden', !show);
          if (show) shown++;
        });
        count.textContent = (words.length || state.tags.length || state.kind || state.cat) ? (shown + ' of ' + total) : COUNT_LABEL;
        noResults.hidden = shown !== 0;
        qClear.hidden = !state.q;
        syncSeg(kindBtns, 'data-kind-filter', state.kind);
        syncSeg(catBtns, 'data-cat-filter', state.cat);
        syncFiltersToggle();
        syncPills();
      }

      q.addEventListener('input', function () {
        state.q = q.value;
        applyFilters();
        writeHashSoon();
      });
      qClear.addEventListener('click', function () {
        q.value = ''; state.q = '';
        applyFilters(); writeHash(); q.focus();
      });
      // "All" clears the tag set; any other chip toggles itself, and
      // several active chips narrow the grid (AND, not OR).
      chips.forEach(function (chip) {
        chip.addEventListener('click', function () {
          var t = chip.getAttribute('data-tag') || '';
          if (!t) { state.tags = []; }
          else {
            var at = state.tags.indexOf(t);
            if (at === -1) state.tags.push(t); else state.tags.splice(at, 1);
          }
          syncChips(); applyFilters(); writeHash(true);
        });
      });
      // The chip row is one toolbar tab stop; arrows, Home and End move
      // within it (roving tabindex) instead of 35 separate Tab presses.
      if (chips.length) {
        var roving = 0;
        function rove(i) {
          chips[roving].tabIndex = -1;
          roving = (i + chips.length) % chips.length;
          chips[roving].tabIndex = 0;
        }
        chips.forEach(function (c, i) {
          c.tabIndex = i === 0 ? 0 : -1;
          c.addEventListener('focus', function () { rove(i); });
        });
        chipsEl.addEventListener('keydown', function (e) {
          var i = chips.indexOf(document.activeElement);
          if (i === -1) return;
          var to = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 :
            e.key === 'Home' ? 0 : e.key === 'End' ? chips.length - 1 : null;
          if (to === null) return;
          e.preventDefault();
          rove(to);
          chips[roving].focus();
          chips[roving].scrollIntoView({ block: 'nearest', inline: 'nearest' });
        });
      }
      kindBtns.forEach(function (b) {
        b.addEventListener('click', function () {
          state.kind = b.getAttribute('data-kind-filter');
          applyFilters(); writeHash(true);
        });
      });
      // A category only exists among showcase pieces, so picking one moves
      // the kind control to Showcase instead of leaving "All" lit.
      catBtns.forEach(function (b) {
        b.addEventListener('click', function () {
          state.cat = b.getAttribute('data-cat-filter');
          if (state.cat) state.kind = 'showcase';
          applyFilters(); writeHash(true);
        });
      });
      sortSel.addEventListener('change', function () {
        state.sort = SORTS.indexOf(sortSel.value) !== -1 ? sortSel.value : 'default';
        applySort(); writeHash(true);
      });
      densityBtns.forEach(function (b) {
        b.addEventListener('click', function () {
          state.density = b.getAttribute('data-density');
          applyDensity(); writeHash();
        });
      });
      resetFilters.addEventListener('click', function () {
        state.q = ''; state.tags = []; state.kind = ''; state.cat = ''; state.sort = 'default';
        q.value = '';
        syncChips(); applySort(); applyFilters(); writeHash(true); q.focus();
      });
      filtersToggle.addEventListener('click', function () {
        var open = filtersEl.classList.toggle('open');
        document.querySelector('.controls').classList.toggle('open', open);
        filtersToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
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

      // Restore state from the URL hash; density falls back to localStorage.
      function restore() {
        // #check-only (the landing page links it) is an anchor, not filter state.
        var co = document.getElementById('check-only');
        if (co && location.hash === '#check-only') co.open = true;
        var h = parseHash();
        state.q = h.q || '';
        state.kind = KINDS.indexOf(h.k) !== -1 ? h.k : '';
        state.cat = h.c && CATS.indexOf(h.c) !== -1 ? h.c : '';
        state.sort = SORTS.indexOf(h.s) !== -1 ? h.s : 'default';
        state.tags = [];
        // Tags arrive comma-separated. "showcase" is the kind filter now, not
        // a chip, but older links still say #tag=showcase. A tag no chip
        // knows would silently show zero cards, so it is dropped.
        (h.tag || '').split(',').forEach(function (t) {
          if (t === 'showcase') { state.kind = 'showcase'; }
          else if (knownTags.indexOf(t) !== -1 && state.tags.indexOf(t) === -1) { state.tags.push(t); }
        });
        if (state.cat) state.kind = 'showcase';
        if (h.d === 'compact' || h.d === 'detailed') state.density = h.d;
        else {
          try {
            var s = localStorage.getItem(LS_KEY);
            if (s === 'compact' || s === 'detailed') state.density = s;
          } catch (e) {}
        }
        q.value = state.q;
        syncChips();
        // A deep-linked tag may sit off-screen in the chip scroll strip.
        var firstOn = chipsEl && chipsEl.querySelector('.chip.active[data-tag]:not([data-tag=""])');
        measureChips();
        if (firstOn && moreBtn && chipClipped(firstOn)) setChipsExpanded(true);
        applyDensity();
        applySort();
        applyFilters();
        remember();
      }
      // The header's Examples / Showcase links only change the hash here.
      window.addEventListener('hashchange', restore);
      restore();
    })();
"""

DETAIL_JS = """
    (function () {
      var hero = document.getElementById('heroZoom');
      var box = document.getElementById('lightbox');
      if (hero && box) {
        // <dialog>.showModal() traps focus, closes on Escape, and returns
        // focus to the hero button on close. The dialog fills the viewport,
        // so a click whose target is the dialog itself is a backdrop click.
        var full = box.querySelector('img');
        var nativeBtn = document.getElementById('lightboxNative');
        function setNative(on) {
          box.classList.toggle('native', on);
          nativeBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
          nativeBtn.textContent = on ? 'Fit to screen' : 'Actual size';
        }
        hero.addEventListener('click', function () { setNative(false); box.showModal(); });
        box.addEventListener('click', function (e) { if (e.target === box) box.close(); });
        document.getElementById('lightboxClose').addEventListener('click', function () { box.close(); });
        full.addEventListener('click', function () { setNative(!box.classList.contains('native')); });
        nativeBtn.addEventListener('click', function () { setNative(!box.classList.contains('native')); });
      }

      var srStatus = document.getElementById('srStatus');
      function announce(msg) {
        srStatus.textContent = '';
        setTimeout(function () { srStatus.textContent = msg; }, 50);
      }

      // Back to the gallery with the filters the reader left it with, and
      // page through that filtered order when there is one (both written by
      // the gallery index into sessionStorage; absent, the static links stay).
      var here = location.pathname.replace(/[/]$/, '').split('/').pop();
      try {
        var savedHash = sessionStorage.getItem('bdt-gallery-hash');
        var crumb = document.getElementById('crumbGallery');
        if (crumb && savedHash) crumb.setAttribute('href', '../' + savedHash);
        var order = JSON.parse(sessionStorage.getItem('bdt-gallery-order') || 'null');
        var at = order ? order.indexOf(here) : -1;
        if (at !== -1) {
          Array.prototype.forEach.call(document.querySelectorAll('.pager'), function (nav) {
            function slot(name, rel) {
              if (!name) return document.createElement('span');
              var a = document.createElement('a');
              a.rel = rel; a.href = '../' + name + '/';
              a.setAttribute('aria-label', (rel === 'prev' ? 'Previous' : 'Next') + ' in your filter: ' + name);
              a.innerHTML = rel === 'prev'
                ? '<span aria-hidden="true">&larr;</span> ' + name
                : name + ' <span aria-hidden="true">&rarr;</span>';
              return a;
            }
            var pos = nav.querySelector('.pager-pos');
            var keys = pos.querySelector('.pager-keys');
            nav.replaceChild(slot(order[at - 1], 'prev'), nav.firstElementChild);
            nav.replaceChild(slot(order[at + 1], 'next'), nav.lastElementChild);
            pos.textContent = (at + 1) + ' of ' + order.length + ' in your filter';
            if (keys) pos.appendChild(keys);
            nav.setAttribute('aria-label', 'Your filtered gallery');
          });
        }
      } catch (e) {}

      // Clipboard API first; execCommand for non-secure origins (file://,
      // plain-http previews) where navigator.clipboard is undefined.
      function copyText(text) {
        if (navigator.clipboard && window.isSecureContext) {
          return navigator.clipboard.writeText(text);
        }
        return new Promise(function (resolve, reject) {
          var ta = document.createElement('textarea');
          ta.value = text;
          ta.setAttribute('readonly', '');
          ta.style.position = 'fixed'; ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          var ok = false;
          try { ok = document.execCommand('copy'); } catch (e) {}
          document.body.removeChild(ta);
          if (ok) { resolve(); } else { reject(); }
        });
      }
      function wireCopy(btn, getText) {
        btn.addEventListener('click', function () {
          copyText(getText()).then(function () {
            btn.textContent = 'Copied'; btn.classList.add('done'); announce('Copied to clipboard');
          }, function () {
            btn.textContent = 'Copy failed'; btn.classList.add('fail'); announce('Copy failed');
          }).then(function () {
            setTimeout(function () {
              btn.textContent = 'Copy'; btn.classList.remove('done', 'fail');
            }, 1600);
          });
        });
      }
      var copy = document.getElementById('copyRun');
      if (copy) {
        wireCopy(copy, function () { return document.getElementById('runCmd').textContent; });
      }
      Array.prototype.forEach.call(document.querySelectorAll('.md pre'), function (block) {
        var wrap = block;
        if (block.tagName === 'PRE') {
          wrap = document.createElement('div');
          block.parentNode.insertBefore(wrap, block);
          wrap.appendChild(block);
        }
        wrap.classList.add('codewrap');
        var btn = document.createElement('button');
        btn.type = 'button'; btn.className = 'copy-btn'; btn.textContent = 'Copy';
        var src = block.tagName === 'PRE' ? block : block.querySelector('.code-lines');
        btn.setAttribute('aria-label', 'Copy code');
        wireCopy(btn, function () { return src.textContent; });
        wrap.appendChild(btn);
      });

      // Left/right arrows page between entries, but only when nothing has
      // focus and nothing is selected: a focused control, a scrolled code
      // block, or a text selection keeps its own arrow keys. A click inside a
      // code block does not always move focus (or a selection), so also keep
      // the arrows when the last click landed in one that scrolls sideways
      // (#398).
      var lastPointer = null;
      document.addEventListener('pointerdown', function (e) { lastPointer = e.target; }, true);
      document.addEventListener('keydown', function (e) {
        if (e.ctrlKey || e.altKey || e.metaKey || e.shiftKey) return;
        if (box && box.open) return;
        var scroller = lastPointer && lastPointer.closest
          && lastPointer.closest('pre, .code-lines, .codewrap');
        if (scroller && scroller.scrollWidth > scroller.clientWidth) return;
        var ae = document.activeElement;
        if (ae && ae !== document.body && ae !== document.documentElement) return;
        var sel = window.getSelection && window.getSelection();
        if (sel && !sel.isCollapsed) return;
        var rel = e.key === 'ArrowLeft' ? 'prev' : e.key === 'ArrowRight' ? 'next' : '';
        if (!rel) return;
        var a = document.querySelector('.pager a[rel="' + rel + '"]');
        if (a) { location.href = a.href; }
      });
    })();
"""

CARD = """      <article class="card" data-tags="__TAGS__" data-kind="__KINDKEY__"__CATATTR__ data-name="__NAME__" data-search="__SEARCH__">
        <div class="card-media">
          <img src="__THUMB__" srcset="__THUMB__ 640w, __HERO__ 1280w" sizes="__SIZES__" alt="__ALT__" width="1280" height="720" loading="__LOADING__" decoding="async" />
        </div>
        <div class="card-body">
          <h2><a class="stretch" href="__HREF__">__TITLE__</a></h2>
          <p class="slug">__NAME__</p>
          <p class="teaches">__TEACHES__</p>
          <p class="witnesses"><span class="tag">witnesses</span> __WITNESSES__</p>
          <span class="card-link" aria-hidden="true">View __KIND__ &rarr;</span>
        </div>
      </article>"""

# Compact card for a detail page's Related strip (same visual family as CARD).
MINI_CARD = """        <article class="card mini">
          <div class="card-media">
            <img src="__THUMB__" srcset="__THUMB__ 640w, __HERO__ 1280w" sizes="__SIZES__" alt="__ALT__" width="1280" height="720" loading="lazy" decoding="async" />
          </div>
          <div class="card-body">
            <h3><a class="stretch" href="__HREF__">__TITLE__</a></h3>
            <p>__TEACHES__</p>
          </div>
        </article>"""

# Cards above the fold on a typical desktop load eagerly; the rest stay lazy.
EAGER_CARDS = 4



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


# Ids the detail page itself uses; a README heading must never collide with them.
RESERVED_IDS = frozenset({"main", "heroZoom", "lightbox", "runCmd", "copyRun", "related", "related-h", "source"})


def slugify(text: str, seen: set[str]) -> str:
    """GitHub-style heading slug from raw Markdown heading text, unique within *seen*."""
    plain = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links/images -> label
    plain = re.sub(r"[`*_]", "", plain).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", plain).strip("-") or "section"
    candidate, n = slug, 1
    while candidate in seen or candidate in RESERVED_IDS:
        candidate = f"{slug}-{n}"
        n += 1
    seen.add(candidate)
    return candidate


def md_to_html(text: str, resolve, skip_first_h1: bool = True) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    seen_h1 = False
    slugs: set[str] = set()
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
            out.append(f'<pre tabindex="0"><code>{html.escape(chr(10).join(code))}</code></pre>')
            continue

        m = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            if level == 1 and skip_first_h1 and not seen_h1:
                seen_h1 = True
                i += 1
                continue
            hid = slugify(m.group(2), slugs)
            out.append(f'<h{level} id="{hid}">{render_inline(m.group(2), resolve)}'
                       f'<a class="anchor" href="#{hid}" aria-label="Link to this section">#</a>'
                       f"</h{level}>")
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


def tokens_css() -> str:
    """The shared palette, minus its header comment (the landing page's copy
    carries it)."""
    text = TOKENS_CSS.read_text(encoding="utf-8")
    m = re.search(r"^[ \t]*:root\s*\{", text, re.M)
    if m is None:
        raise SystemExit(f"{TOKENS_CSS.relative_to(REPO)} has no :root block")
    return text[m.start():].rstrip()


def gallery_css() -> str:
    """The full docs/gallery/gallery.css text: tokens + shared chrome + gallery."""
    return (GALLERY_CSS
            .replace("__TOKENS__", tokens_css())
            .replace("__CHROME__", chrome.CSS.strip("\n")))


def css_version(css: str) -> str:
    """Short content hash for the stylesheet URL, so a deploy never pairs new
    markup with a cached old stylesheet."""
    return hashlib.sha256(css.encode("utf-8")).hexdigest()[:10]


def shell(*, title: str, desc: str, canonical: str, og_image: str,
          og_size: tuple[int, int], og_alt: str, og_type: str,
          site_root: str, gallery_root: str, repo_url: str, css_v: str,
          content: str, page_js: str, head_js: str = "",
          sources: tuple[str, ...] = ("examples/gallery.json",),
          twitter_image: str = "", twitter_alt: str = "") -> str:
    canon = ""
    if canonical:
        c = html.escape(canonical, quote=True)
        canon = (f'  <link rel="canonical" href="{c}" />\n'
                 f'  <meta property="og:url" content="{c}" />\n')
    if og_image:
        img, alt = html.escape(og_image, quote=True), html.escape(og_alt, quote=True)
        # og:image stays a JPEG/PNG (several scrapers skip webp); X renders
        # webp, so a page may give twitter:image its own hero instead.
        timg = html.escape(twitter_image or og_image, quote=True)
        talt = html.escape(twitter_alt or og_alt, quote=True)
        og = (f'  <meta property="og:image" content="{img}" />\n'
              f'  <meta property="og:image:width" content="{og_size[0]}" />\n'
              f'  <meta property="og:image:height" content="{og_size[1]}" />\n'
              f'  <meta property="og:image:alt" content="{alt}" />\n'
              '  <meta name="twitter:card" content="summary_large_image" />\n'
              f'  <meta name="twitter:image" content="{timg}" />\n'
              f'  <meta name="twitter:image:alt" content="{talt}" />\n')
    else:
        og = '  <meta name="twitter:card" content="summary" />\n'
    source_html = " + ".join(f"<code>{html.escape(s)}</code>" for s in sources)
    return (SHELL
            .replace("__TITLE__", html.escape(title))
            .replace("__DESC__", html.escape(desc, quote=True))
            .replace("__CANONICALTAGS__", canon)
            .replace("__OGIMAGETAGS__", og)
            .replace("__OGTYPE__", og_type)
            .replace("__SITEROOT__", site_root)
            .replace("__GALLERYROOT__", gallery_root)
            .replace("__CSSV__", css_v)
            .replace("__HEADER__", chrome.header(
                root=site_root, repo=repo_url, title=SITE_TITLE, home_anchors=False).rstrip("\n"))
            .replace("__FOOTER__", chrome.footer(
                root=site_root, repo=repo_url, title=SITE_TITLE, license_=LICENSE,
                source_html=source_html).rstrip("\n"))
            .replace("__CHROMEJS__", chrome.JS.strip("\n"))
            .replace("__PAGEJS__", page_js)
            .replace("__HEADJS__", head_js)
            # Content last, so README and source text are never scanned for
            # the other placeholders.
            .replace("__CONTENT__", content))


def related_entries(ex: dict, entries: list, limit: int = 3) -> list:
    """Entries sharing the most topic tags with *ex*; gallery order breaks ties.

    ``showcase`` is a kind marker, not a topic, so it never counts as shared.
    """
    mine = set(ex.get("tags") or []) - {"showcase"}
    scored = []
    for i, other in enumerate(entries):
        if other["name"] == ex["name"]:
            continue
        shared = len(mine & (set(other.get("tags") or []) - {"showcase"}))
        if shared:
            scored.append((-shared, i, other))
    return [o for _, _, o in sorted(scored, key=lambda t: t[:2])[:limit]]


def pager_html(prev: dict | None, nxt: dict | None, pos: int, total: int, noun: str,
               *, foot: bool = False) -> str:
    """Prev/next links between entries of one kind. Never wraps."""
    plural = "showcase pieces" if noun == "showcase piece" else "examples"
    def link(e: dict | None, rel: str) -> str:
        if e is None:
            return "<span></span>"
        n = html.escape(e["name"])
        name = f'<span class="pager-label">{n}</span>'
        label = (f'<span aria-hidden="true">&larr;</span>{name}' if rel == "prev"
                 else f'{name}<span aria-hidden="true">&rarr;</span>')
        return (f'<a rel="{rel}" href="../{html.escape(e["name"], quote=True)}/" '
                f'aria-label="{"Previous" if rel == "prev" else "Next"} {noun}: {n}">{label}</a>')
    cls = "pager pager-foot" if foot else "pager"
    hint = "" if foot else '<span class="pager-keys"> &middot; <kbd>&larr;</kbd><kbd>&rarr;</kbd></span>'
    return (f'    <nav class="{cls}" aria-label="{plural.capitalize()}">'
            f'{link(prev, "prev")}'
            f'<span class="pager-pos hud">{pos} of {total} {plural}{hint}</span>'
            f'{link(nxt, "next")}</nav>')


def build_detail(ex: dict, entries: list, *, base: str, repo_root_url: str, site: str,
                 css_v: str) -> str:
    noun = kind_noun(ex)
    kind_title = "Showcase" if noun == "showcase piece" else "Examples"
    name = ex["name"]
    ex_dir = REPO / ex["dir"]
    script = find_script(ex_dir)
    hero_file = page_relative(ex["hero"]).split("/")[-1]

    peers = [e for e in entries if kind_noun(e) == noun]
    idx = next(i for i, e in enumerate(peers) if e["name"] == name)
    prev = peers[idx - 1] if idx > 0 else None
    nxt = peers[idx + 1] if idx + 1 < len(peers) else None

    parts: list[str] = []
    kind_key = "showcase" if noun == "showcase piece" else "examples"
    parts.append('  <header class="hero">')
    # The Gallery crumb's href is upgraded by JS to the filters the reader left.
    parts.append('    <nav class="crumbs" aria-label="Breadcrumb"><ol>'
                 '<li><a href="../" id="crumbGallery">Gallery</a></li>'
                 f'<li><a href="../#k={kind_key}">{kind_title}</a></li>'
                 f'<li aria-current="page">{html.escape(name)}</li></ol></nav>')
    parts.append(f'    <h1>{html.escape(display_title(ex))}</h1>')
    parts.append(f'    <p class="slug">{html.escape(ex["dir"])}/</p>')
    parts.append(f'    <p>{inline_code(ex["teaches"])}</p>')
    parts.append("  </header>")
    parts.append('  <main id="main">')
    parts.append(pager_html(prev, nxt, idx + 1, len(peers), noun))
    parts.append(f'    <button class="detail-hero" id="heroZoom" type="button" aria-label="View full size: {html.escape(ex["alt"], quote=True)}">')
    parts.append(f'      <img src="../assets/{html.escape(hero_file)}" alt="{html.escape(ex["alt"], quote=True)}" width="1280" height="720" fetchpriority="high" />')
    parts.append("    </button>")
    parts.append(f'    <p class="zoom-hint">Rendered headless by the {noun} itself. Select it to enlarge.</p>')
    parts.append(f'    <div class="callout"><span class="tag">witnesses</span> {inline_code(ex["witnessesFix"])}</div>')
    cat = ex.get("category")
    if cat:
        parts.append(f'    <p class="taglist"><span class="tag">category</span> '
                     f'<a href="../#k=showcase&amp;c={html.escape(cat, quote=True)}">'
                     f'{html.escape(CATEGORIES[cat])}</a></p>')
    tags = ex.get("tags") or []
    if tags:
        links = " ".join(
            f'<a href="../#tag={html.escape(urllib.parse.quote(t), quote=True)}">{html.escape(t)}</a>'
            for t in tags)
        parts.append(f'    <p class="taglist"><span class="tag">tags</span> {links}</p>')

    if script is not None:
        cmd = f"blender --background --python {ex['dir']}/{script.name} --"
        parts.append('    <div class="runline">')
        parts.append(f'      <pre id="runCmd" tabindex="0">{html.escape(cmd)}</pre>')
        parts.append('      <button class="copy-btn" id="copyRun" type="button">Copy</button>')
        parts.append("    </div>")

    readme = ex_dir / "README.md"
    readme_html = ""
    if readme.is_file():
        resolve = make_resolver(base, ex["dir"])
        readme_html = md_to_html(readme.read_text(encoding="utf-8"), resolve)

    # Jump links only to anchors that exist on this page (README headings vary).
    related = related_entries(ex, entries)
    jumps = [(label, anchor) for label, anchor, present in (
        ("Run", "run", 'id="run"' in readme_html),
        ("Exit codes", "exit-codes", 'id="exit-codes"' in readme_html),
        ("Source", "source", script is not None),
        ("Related", "related", bool(related)),
    ) if present]
    if len(jumps) >= 2:
        links = " ".join(f'<a href="#{a}">{label}</a>' for label, a in jumps)
        parts.append(f'    <nav class="jumpnav" aria-label="On this page"><span class="tag">jump to</span> {links}</nav>')

    if readme_html:
        parts.append('    <section class="detail-section md">')
        parts.append(readme_html)
        parts.append("    </section>")

    if script is not None:
        # Link the script rather than inline it: inlined, highlighted source
        # made every detail page several times its script's size and rewrote
        # the page on every script edit (the bulk of repo history growth).
        blob = f"{base.replace('/tree/', '/blob/', 1)}/{ex['dir']}/{script.name}"
        parts.append('    <section class="detail-section src" id="source">')
        parts.append("      <h2>Source</h2>")
        parts.append('      <div class="src-meta">')
        parts.append(f"        <code>{html.escape(ex['dir'])}/{html.escape(script.name)}</code>")
        parts.append(f'        <a href="{html.escape(blob, quote=True)}">View the script on GitHub &rarr;</a>')
        parts.append("      </div>")
        parts.append("    </section>")

    if related:
        parts.append('    <section class="detail-section" id="related" aria-labelledby="related-h">')
        parts.append('      <h2 id="related-h">Related</h2>')
        parts.append('      <div class="related-grid">')
        for r in related:
            parts.append(
                MINI_CARD
                .replace("__HREF__", html.escape(f'../{r["name"]}/', quote=True))
                .replace("__THUMB__", html.escape("../" + page_relative(thumb_path(r["hero"])), quote=True))
                .replace("__HERO__", html.escape("../" + page_relative(r["hero"]), quote=True))
                .replace("__SIZES__", MINI_SIZES)
                .replace("__ALT__", html.escape(r["alt"], quote=True))
                .replace("__TITLE__", html.escape(display_title(r)))
                .replace("__TEACHES__", inline_code(r["teaches"])))
        parts.append("      </div>")
        parts.append("    </section>")

    parts.append(pager_html(prev, nxt, idx + 1, len(peers), noun, foot=True))
    parts.append("  </main>")
    parts.append('  <dialog class="lightbox" id="lightbox" aria-label="Full-size render">')
    parts.append('    <div class="lightbox-bar">'
                 '<button class="lightbox-close" id="lightboxNative" type="button" aria-pressed="false">Actual size</button>'
                 '<button class="lightbox-close" id="lightboxClose" type="button" autofocus>Close</button></div>')
    parts.append(f'    <img src="../assets/{html.escape(hero_file)}" alt="{html.escape(ex["alt"], quote=True)}" />')
    parts.append("  </dialog>")

    return shell(
        title=f"{display_title(ex)} ({name}) — {kind_title} — Blender Developer Tools",
        desc=ex["teaches"],
        canonical=f"{site}/gallery/{name}/" if site else "",
        og_image=f"{site}/assets/og-card.jpg" if site else "",
        og_size=OG_CARD_SIZE,
        og_alt=OG_CARD_ALT,
        twitter_image=f"{site}/gallery/assets/{hero_file}" if site else "",
        twitter_alt=ex["alt"],
        og_type="article",
        site_root="../../",
        gallery_root="../",
        css_v=css_v,
        repo_url=repo_root_url,
        content="\n".join(parts),
        page_js=DETAIL_JS,
        sources=(("showcase/gallery.json",) if noun == "showcase piece"
                 else ("examples/gallery.json",)),
    )


# Terminal punctuation followed by whitespace and a capital or backtick; a
# dotted API path (`Object.evaluated_get`) never ends a sentence (see #68).
_SENTENCE_END = re.compile(r"(?<!\be\.g)(?<!\bi\.e)(?<!\bvs)[.!?](?=\s+[A-Z`(])")


def first_sentence(text: str) -> str:
    m = _SENTENCE_END.search(text)
    return text[:m.end()] if m else text


def check_only_examples() -> list[dict]:
    """Examples with no render (``render: false`` in examples/index.json):
    their witness is a data fact, so they have no gallery card (#453)."""
    path = REPO / "examples" / "index.json"
    if not path.is_file():
        return []
    return [e for e in json.loads(path.read_text(encoding="utf-8")) if not e.get("render")]


def check_only_html(rendered: int, repo_root_url: str) -> str:
    """One header line explaining why the gallery shows fewer examples than
    the repo has, expanding to the list of check-only examples."""
    items = check_only_examples()
    if not items:
        return ""
    lis = "\n".join(
        f'          <li><a href="{html.escape(repo_root_url + "/tree/main/" + e["path"], quote=True)}">'
        f'{html.escape(e["name"])}</a>: {inline_code(first_sentence(e.get("summary", "")))}</li>'
        for e in items
    )
    return (
        '    <details class="check-only" id="check-only">\n'
        f"      <summary>{rendered} rendered &middot; {len(items)} check-only examples "
        "(data contracts with nothing to see)</summary>\n"
        "      <div>\n"
        "        A check-only example asserts a fact no render can show, such as a datablock name,\n"
        "        an RNA attribute, a post-exit sidecar or a topology count. It runs in the same\n"
        "        smoke workflow on every PR, with its own falsifier; its source is on GitHub.\n"
        f"        <ul>\n{lis}\n        </ul>\n"
        "      </div>\n"
        "    </details>\n"
    )


def build_index(data: dict, *, base: str, repo_root_url: str, site: str, css_v: str) -> str:
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

    all_tags = sorted({t for ex in examples for t in ex.get("tags", [])} - {"showcase"})
    chips_html = ""
    if all_tags:
        chips = ['<button class="chip active" data-tag="" type="button" aria-pressed="true">All</button>']
        tag_counts = {t: sum(1 for ex in examples if t in ex.get("tags", [])) for t in all_tags}
        chips += [
            f'<button class="chip" data-tag="{html.escape(t, quote=True)}" type="button" aria-pressed="false">'
            f'{html.escape(t)} <span class="n">{tag_counts[t]}</span></button>'
            for t in all_tags
        ]
        chips_html = ('      <div class="chips" id="chips" role="toolbar" aria-label="Filter by topic (combine several)">\n        '
                      + "\n        ".join(chips) + "\n      </div>\n"
                      f'      <button class="chips-more" id="chipsMore" type="button" aria-expanded="false" hidden>Show all {len(all_tags)} topics</button>\n')

    # Category row: only categories that have pieces get a button, in
    # CATEGORIES order, each labelled with its piece count.
    cat_counts: dict[str, int] = {}
    for ex in examples:
        if ex.get("category"):
            cat_counts[ex["category"]] = cat_counts.get(ex["category"], 0) + 1
    cats_html = ""
    if cat_counts:
        btns = ['          <button class="cat-btn" data-cat-filter="" type="button" aria-pressed="true">All</button>']
        btns += [
            f'          <button class="cat-btn" data-cat-filter="{key}" type="button" aria-pressed="false">'
            f'{html.escape(label)} <span aria-hidden="true">{cat_counts[key]}</span></button>'
            for key, label in CATEGORIES.items() if key in cat_counts
        ]
        cats_html = ('      <div class="controls-row cats" id="cats">\n'
                     '        <span class="cats-label" id="catsLabel">Showcase category</span>\n'
                     '        <div class="density" role="group" aria-labelledby="catsLabel">\n'
                     + "\n".join(btns) + "\n        </div>\n      </div>\n")

    # Sticky controls bar. Every control is inert but harmless with JS
    # disabled: the search box and toggles do nothing, the count already reads
    # correctly, and all cards render expanded (the compact class is JS-only).
    controls = (
        '  <div class="controls">\n'
        '    <div class="controls-inner">\n'
        '      <div class="controls-row controls-main">\n'
        '        <div class="searchwrap">\n'
        '          <input id="q" name="q" type="search" placeholder="Search the gallery (press /)"\n'
        '            autocomplete="off" spellcheck="false" aria-label="Search examples and showcase pieces" />\n'
        '          <button class="q-clear" id="qClear" type="button" aria-label="Clear search" hidden>&times;</button>\n'
        '        </div>\n'
        '        <button class="filters-toggle" id="filtersToggle" type="button" aria-expanded="false" aria-controls="filters">Filters</button>\n'
        '        <div class="view-controls">\n'
        '          <div class="density" role="group" aria-label="Show">\n'
        '            <button class="density-btn" data-kind-filter="" type="button" aria-pressed="true">All</button>\n'
        '            <button class="density-btn" data-kind-filter="examples" type="button" aria-pressed="false">Examples</button>\n'
        '            <button class="density-btn" data-kind-filter="showcase" type="button" aria-pressed="false">Showcase</button>\n'
        '          </div>\n'
        '          <label class="sort"><span class="sr-only">Sort</span>\n'
        '            <select id="sort">\n'
        '              <option value="default">Gallery order</option>\n'
        '              <option value="az">Name A&ndash;Z</option>\n'
        '              <option value="kind">Examples first</option>\n'
        '              <option value="cat">By category</option>\n'
        '            </select>\n'
        '          </label>\n'
        '          <div class="density view-mode" role="group" aria-label="Card density">\n'
        '            <button class="density-btn" data-density="compact" type="button" aria-pressed="false">Compact</button>\n'
        '            <button class="density-btn" data-density="detailed" type="button" aria-pressed="false">Detailed</button>\n'
        '          </div>\n'
        '        </div>\n'
        '        <div class="active-filters" id="activeFilters" aria-label="Active filters" hidden></div>\n'
        '      </div>\n'
        '      <div class="filters" id="filters">\n'
        + cats_html
        + chips_html +
        '      </div>\n'
        '    </div>\n'
        '  </div>\n'
        f'  <p class="count results" id="count" role="status" aria-live="polite">{html.escape(count_label)}</p>\n'
    )

    cards = []
    for i, ex in enumerate(examples):
        alt = ex["alt"]
        # Search covers what a reader would type: title, slug, the teaching
        # line, tags and category. Not the WITNESSES prose or link labels.
        search = " ".join([display_title(ex), ex["name"], ex["teaches"],
                           " ".join(ex.get("tags", [])),
                           CATEGORIES.get(ex.get("category") or "", "")]).lower()
        cards.append(
            CARD
            .replace("__LOADING__", ("eager\" fetchpriority=\"high" if i == 0 else "eager")
                     if i < EAGER_CARDS else "lazy")
            .replace("__TAGS__", html.escape(" ".join(ex.get("tags", [])), quote=True))
            .replace("__SEARCH__", html.escape(search, quote=True))
            .replace("__HREF__", html.escape(f'{ex["name"]}/', quote=True))
            .replace("__THUMB__", html.escape(page_relative(thumb_path(ex["hero"])), quote=True))
            .replace("__HERO__", html.escape(page_relative(ex["hero"]), quote=True))
            .replace("__SIZES__", CARD_SIZES)
            .replace("__ALT__", html.escape(alt, quote=True))
            .replace("__TITLE__", html.escape(display_title(ex)))
            .replace("__NAME__", html.escape(ex["name"]))
            .replace("__KINDKEY__", "showcase" if kind_noun(ex) == "showcase piece" else "examples")
            .replace("__CATATTR__", f' data-category="{html.escape(ex["category"], quote=True)}"'
                     if ex.get("category") else "")
            .replace("__KIND__", kind_noun(ex))
            .replace("__TEACHES__", inline_code(ex["teaches"]))
            .replace("__WITNESSES__", inline_code(ex["witnessesFix"]))
        )

    content = (
        '  <header class="hero">\n'
        '    <nav class="crumbs" aria-label="Breadcrumb"><ol><li><a href="../">Home</a></li>'
        '<li aria-current="page">Gallery</li></ol></nav>\n'
        f"    <h1>{html.escape(title)}</h1>\n"
        f"    <p>{html.escape(desc)}</p>\n"
        + check_only_html(example_total, repo_root_url)
        + "  </header>\n"
        + controls
        + '  <main id="main">\n    <div class="grid" id="grid">\n'
        + "\n".join(cards)
        + "\n    </div>\n"
        + '    <p class="noresults" id="noResults" hidden>Nothing matches the current filters.\n'
        + '      <button class="chip" id="resetFilters" type="button">Clear all filters</button></p>\n'
        + "  </main>\n"
        + '  <button class="to-top" id="toTop" type="button"><span aria-hidden="true">&uarr;</span> Top</button>'
    )

    # The landing build copies repo-root assets/ (og-card.jpg included) to docs/assets/.
    # A 1200x630 JPEG is the size and format every link-preview scraper accepts.
    return shell(
        title=f"{title} — Blender Developer Tools",
        desc=desc,
        canonical=f"{site}/gallery/" if site else "",
        og_image=f"{site}/assets/og-card.jpg" if site else "",
        og_size=OG_CARD_SIZE,
        og_alt=OG_CARD_ALT,
        og_type="website",
        site_root="../",
        gallery_root="",
        css_v=css_v,
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
        if not (REPO / thumb_path(ex["hero"])).is_file():
            print(f"ERROR: 640px card variant missing: {thumb_path(ex['hero'])}; "
                  "run python scripts/make_thumbs.py", file=sys.stderr)
            return 5

    check_alts(examples)
    check_categories(examples)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    css = gallery_css()
    css_v = css_version(css)
    (OUT_DIR / "gallery.css").write_text(css, encoding="utf-8", newline="\n")
    (OUT_DIR / "index.html").write_text(
        build_index(data, base=base, repo_root_url=repo_root_url, site=site, css_v=css_v),
        encoding="utf-8", newline="\n",
    )
    for ex in examples:
        page_dir = OUT_DIR / ex["name"]
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(
            build_detail(ex, examples, base=base, repo_root_url=repo_root_url, site=site,
                         css_v=css_v),
            encoding="utf-8", newline="\n",
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
