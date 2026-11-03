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
import shlex
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

GALLERY_ASSETS = REPO / "scripts" / "site" / "gallery"


def _gallery_asset(name: str) -> str:
    """The gallery's CSS and JS live as real files (#528) so editors can lint
    and highlight them; __PLACEHOLDER__ tokens in them are filled below."""
    return (GALLERY_ASSETS / name).read_text(encoding="utf-8")


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
GALLERY_CSS = _gallery_asset("gallery.css")


# Index-only head script: runs before first paint so the persisted/default
# density never flashes as a full-height detailed page first. Adds the `js`
# class that gates every JS-only affordance (collapsible chips, scroll strip);
# with JS disabled no class is ever applied and every card renders expanded.
INDEX_HEADJS = _gallery_asset("index-head.js")

INDEX_JS = _gallery_asset("index.js")

DETAIL_JS = _gallery_asset("detail.js")

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
RESERVED_IDS = frozenset({"main", "heroZoom", "lightbox", "runCmd", "copyRun", "falsifyCmd", "copyFalsify",
                          "related", "related-h", "source"})


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

    idx_row = example_index().get(name)
    if idx_row:
        since = idx_row.get("min_version", "4.5")
        runs = [label for ver, label in SMOKED_SERIES if version_key(ver) >= version_key(since)]
        skip = f" (skips below {since})" if since != SMOKED_SERIES[0][0] else ""
        parts.append(f'    <p class="taglist"><span class="tag">runs on</span> '
                     f'{" &middot; ".join(html.escape(r) for r in runs)}{html.escape(skip)}</p>')

    if script is not None:
        cmd = f"blender --background --python {ex['dir']}/{script.name} --"
        parts.append('    <div class="runline">')
        parts.append(f'      <pre id="runCmd" tabindex="0">{html.escape(cmd)}</pre>')
        parts.append('      <button class="copy-btn" id="copyRun" type="button">Copy</button>')
        parts.append("    </div>")
        fals = next((f for f in (idx_row or {}).get("falsifiers", []) if "expect_exit" in f), None)
        if fals:
            only = f", on {fals['min_version']}+" if fals.get("min_version") else ""
            parts.append(f'    <p class="taglist"><span class="tag">falsify it</span> '
                         f'Breaks the contract on purpose and must exit {int(fals["expect_exit"])}{html.escape(only)}</p>')
            parts.append('    <div class="runline falsify">')
            parts.append(f'      <pre id="falsifyCmd" tabindex="0">{html.escape(cmd + " " + shlex.join(fals["args"]))}</pre>')
            parts.append('      <button class="copy-btn" id="copyFalsify" type="button">Copy</button>')
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


# The series blender-smoke.yml runs every example on (5.1 on the weekly cron).
SMOKED_SERIES = (("4.5", "4.5 LTS"), ("5.1", "5.1"), ("5.2", "5.2 LTS"))


def version_key(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


_EXAMPLE_INDEX: dict | None = None


def example_index() -> dict[str, dict]:
    """examples/index.json rows by name; showcase pieces have none."""
    global _EXAMPLE_INDEX
    if _EXAMPLE_INDEX is None:
        path = REPO / "examples" / "index.json"
        rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        _EXAMPLE_INDEX = {r["name"]: r for r in rows}
    return _EXAMPLE_INDEX


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
