#!/usr/bin/env python3
"""Generate the examples gallery from examples/gallery.json.

Emits the gallery index (docs/gallery/index.html) AND one detail page per
example (docs/gallery/<name>/index.html) with the hero render (click to
zoom), a run-it-yourself command, the example's README rendered inline, and
the full Python source syntax-highlighted at build time.

This is a LOCAL, this-repo gallery that rides alongside the generated
docs/index.html (which scripts/site/build_site.py owns and overwrites). It
writes ONLY under docs/gallery/ so it never collides with the landing build's
docs/index.html, docs/fonts/, or docs/assets/.

examples/gallery.json is the source of truth. Run after editing gallery.json,
an example script, or an example README:

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
OUT_DIR = REPO / "docs" / "gallery"

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
  <meta name="theme-color" content="#0d1117" media="(prefers-color-scheme: dark)" />
  <meta name="theme-color" content="#f6f8fa" media="(prefers-color-scheme: light)" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="__TITLE__" />
  <meta property="og:description" content="__DESC__" />
  <meta property="og:url" content="__CANONICAL__" />
  <meta property="og:image" content="__OGIMAGE__" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="__TITLE__" />
  <meta name="twitter:description" content="__DESC__" />
  <meta name="twitter:image" content="__OGIMAGE__" />
  <!-- FOUC guard: apply the saved theme before first paint. Shares the 'theme'
       key with the landing page, so a visitor's choice carries across. -->
  <script>(function(){try{var t=localStorage.getItem('theme');if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t);}catch(e){}})();</script>
  <style>
    :root {
      --bg: #0d1117; --bg2: #161b22; --surface: #161b22; --surface-2: #1c2128;
      --border: #30363d; --text: #e6edf3; --text-dim: #8b949e;
      --accent: #7c3aed; --accent-light: #a78bfa;
      --radius: 8px; --radius-lg: 12px; --maxw: 1080px;
      --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
      --font-mono: ui-monospace, 'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace;
      --code-k: #ff7b72; --code-s: #a5d6ff; --code-c: #8b949e; --code-n: #79c0ff;
    }
    /* auto mode: follow the OS unless the user forced dark */
    @media (prefers-color-scheme: light) {
      :root:not([data-theme="dark"]) {
        --bg: #f6f8fa; --bg2: #ffffff; --surface: #ffffff; --surface-2: #f0f2f5;
        --border: #d0d7de; --text: #1f2328; --text-dim: #656d76;
        --code-k: #cf222e; --code-s: #0a3069; --code-c: #6e7781; --code-n: #0550ae;
      }
    }
    /* explicit override */
    [data-theme="light"] {
      --bg: #f6f8fa; --bg2: #ffffff; --surface: #ffffff; --surface-2: #f0f2f5;
      --border: #d0d7de; --text: #1f2328; --text-dim: #656d76;
      --code-k: #cf222e; --code-s: #0a3069; --code-c: #6e7781; --code-n: #0550ae;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html { scroll-behavior: smooth; }
    body { font-family: var(--font-sans); background: var(--bg); color: var(--text);
      line-height: 1.6; min-height: 100vh; -webkit-font-smoothing: antialiased; }
    a { color: var(--accent-light); text-decoration: none; }
    a:hover { text-decoration: underline; }
    :focus-visible { outline: 2px solid var(--accent-light); outline-offset: 2px; border-radius: 3px; }
    .skip { position: absolute; left: -999px; top: 0; background: var(--accent); color: #fff;
      padding: 0.5rem 1rem; border-radius: var(--radius); z-index: 10; }
    .skip:focus { left: 0.5rem; top: 0.5rem; }

    .topbar { position: sticky; top: 0; z-index: 5; display: flex; align-items: center;
      justify-content: space-between; gap: 1rem; padding: 0.75rem 1.25rem;
      background: color-mix(in srgb, var(--bg) 88%, transparent);
      backdrop-filter: blur(10px); border-bottom: 1px solid var(--border); }
    .topbar .back { color: var(--text-dim); font-size: 0.9rem; font-weight: 500; }
    .topbar .back:hover { color: var(--accent-light); }
    .topbar-right { display: flex; align-items: center; gap: 0.85rem; }
    .topbar-right .ghlink { color: var(--text-dim); font-size: 0.9rem; font-weight: 500; }
    .topbar-right .ghlink:hover { color: var(--accent-light); }
    .theme-toggle { background: var(--surface-2); border: 1px solid var(--border);
      color: var(--text); border-radius: var(--radius); padding: 0.35rem 0.6rem;
      font-size: 0.95rem; cursor: pointer; line-height: 1; transition: border-color 0.15s, background 0.15s; }
    .theme-toggle:hover { border-color: var(--accent-light); }

    header.hero { max-width: var(--maxw); margin: 0 auto; padding: 3rem 1.25rem 1.5rem; }
    header.hero h1 { font-size: clamp(1.9rem, 4vw, 2.6rem); letter-spacing: -0.02em; line-height: 1.15; }
    header.hero p { color: var(--text-dim); max-width: 62ch; margin-top: 0.6rem; font-size: 1.02rem; }

    /* ---- index: filter chips ---- */
    .chips { max-width: var(--maxw); margin: 0 auto; padding: 0 1.25rem 0.25rem;
      display: flex; flex-wrap: wrap; gap: 0.5rem; }
    .chip { background: var(--surface-2); border: 1px solid var(--border); color: var(--text-dim);
      border-radius: 999px; padding: 0.25rem 0.85rem; font-size: 0.82rem; font-weight: 500;
      font-family: var(--font-sans); cursor: pointer; transition: color 0.15s, border-color 0.15s; }
    .chip:hover { color: var(--accent-light); border-color: var(--accent); }
    .chip.active { color: #fff; background: var(--accent); border-color: var(--accent); }

    main { max-width: var(--maxw); margin: 0 auto; padding: 1rem 1.25rem 2rem; }
    .grid { display: grid; grid-template-columns: 1fr; gap: 1.5rem; align-items: stretch; }
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
      overflow: hidden; display: flex; flex-direction: column;
      transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease; }
    .card:hover { transform: translateY(-3px); border-color: color-mix(in srgb, var(--accent) 55%, var(--border));
      box-shadow: 0 8px 28px rgba(0,0,0,0.28); }
    .card.hidden { display: none; }
    .card-media { display: block; background: var(--bg2); line-height: 0; }
    .card-media img { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover; }
    .card-body { padding: 1.15rem 1.4rem 1.45rem; display: flex; flex-direction: column; flex: 1 1 auto; }
    .card-body h2 { font-size: 1.22rem; letter-spacing: -0.01em; margin-bottom: 0.5rem; }
    .card-body h2 a { color: var(--text); }
    .card-body h2 a:hover { color: var(--accent-light); text-decoration: none; }
    .teaches { color: var(--text); margin-bottom: 0.7rem; }
    .witnesses { color: var(--text-dim); font-size: 0.9rem; margin-bottom: 1rem; }
    .tag { display: inline-block; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--accent-light); border: 1px solid color-mix(in srgb, var(--accent) 60%, transparent);
      border-radius: 999px; padding: 0.08rem 0.55rem; margin-right: 0.4rem; vertical-align: 1px; }
    .card-link { font-weight: 600; font-size: 0.95rem; margin-top: auto; }

    /* ---- detail page ---- */
    .detail-hero { border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden;
      background: var(--bg2); padding: 0; display: block; width: 100%; cursor: zoom-in; line-height: 0; }
    .detail-hero img { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover; }
    .zoom-hint { color: var(--text-dim); font-size: 0.78rem; margin-top: 0.4rem; }
    .callout { border: 1px solid color-mix(in srgb, var(--accent) 45%, var(--border));
      border-left: 3px solid var(--accent); border-radius: var(--radius);
      background: color-mix(in srgb, var(--accent) 7%, var(--surface));
      padding: 0.85rem 1.1rem; margin: 1.5rem 0; font-size: 0.95rem; }
    .runline { display: flex; align-items: stretch; gap: 0.5rem; margin: 1.5rem 0; }
    .runline pre { flex: 1 1 auto; background: var(--surface-2); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 0.7rem 0.9rem; overflow-x: auto;
      font-family: var(--font-mono); font-size: 0.83rem; line-height: 1.5; }
    .copy-btn { flex: 0 0 auto; background: var(--surface-2); border: 1px solid var(--border);
      color: var(--text-dim); border-radius: var(--radius); padding: 0 0.85rem; cursor: pointer;
      font-family: var(--font-sans); font-size: 0.82rem; font-weight: 500; transition: color 0.15s, border-color 0.15s; }
    .copy-btn:hover { color: var(--accent-light); border-color: var(--accent); }
    .detail-section { margin-top: 2.25rem; }
    .detail-section > h2 { font-size: 1.15rem; letter-spacing: -0.01em; padding-bottom: 0.5rem;
      border-bottom: 1px solid var(--border); margin-bottom: 1rem; }

    .md h1, .md h2, .md h3 { letter-spacing: -0.01em; margin: 1.4rem 0 0.6rem; line-height: 1.25; }
    .md h1 { font-size: 1.35rem; } .md h2 { font-size: 1.15rem; } .md h3 { font-size: 1rem; }
    .md p { margin: 0.7rem 0; }
    .md ul { margin: 0.7rem 0 0.7rem 1.4rem; }
    .md li { margin: 0.3rem 0; }
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

    .lightbox { position: fixed; inset: 0; z-index: 50; display: none; align-items: center;
      justify-content: center; background: rgba(0,0,0,0.85); padding: 2rem; cursor: zoom-out; }
    .lightbox.open { display: flex; }
    .lightbox img { max-width: 100%; max-height: 100%; border-radius: var(--radius); }

    footer { max-width: var(--maxw); margin: 0 auto; padding: 2rem 1.25rem 3rem;
      color: var(--text-dim); font-size: 0.85rem; border-top: 1px solid var(--border); }
    footer code { background: var(--surface-2); padding: 0.1rem 0.35rem; border-radius: 4px; font-size: 0.82rem; }

    @media (min-width: 720px) { .grid { grid-template-columns: 1fr 1fr; gap: 1.75rem; } }
    @media (prefers-reduced-motion: reduce) {
      html { scroll-behavior: auto; }
      .card, .theme-toggle { transition: none; }
      .card:hover { transform: none; }
    }
  </style>
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <div class="topbar">
    <a class="back" href="__BACKHREF__"><span aria-hidden="true">&larr;</span> __BACKLABEL__</a>
    <div class="topbar-right">
      <a class="ghlink" href="__REPO__">GitHub</a>
      <button class="theme-toggle" id="themeToggle" type="button" aria-label="Theme: auto (click to change)">&#9788;</button>
    </div>
  </div>
__CONTENT__
  <footer>
    Generated from <code>examples/gallery.json</code> by <code>scripts/build_gallery.py</code>.
    &nbsp;&bull;&nbsp; CC-BY-NC-ND-4.0
  </footer>
  <script>
    (function () {
      var btn = document.getElementById('themeToggle');
      var root = document.documentElement;
      var order = ['auto', 'light', 'dark'];
      var glyph = { auto: '\\u263C', light: '\\u2600', dark: '\\u263D' };
      function get() { try { return localStorage.getItem('theme') || 'auto'; } catch (e) { return 'auto'; } }
      function apply(state) {
        if (state === 'light' || state === 'dark') root.setAttribute('data-theme', state);
        else root.removeAttribute('data-theme');
        try { if (state === 'auto') localStorage.removeItem('theme'); else localStorage.setItem('theme', state); } catch (e) {}
        btn.innerHTML = glyph[state]; btn.setAttribute('aria-label', 'Theme: ' + state + ' (click to change)');
      }
      apply(get());
      btn.addEventListener('click', function () {
        var next = order[(order.indexOf(get()) + 1) % order.length];
        apply(next);
      });
    })();
__PAGEJS__
  </script>
</body>
</html>
"""

INDEX_JS = """
    (function () {
      var chips = document.querySelectorAll('.chip');
      var cards = document.querySelectorAll('.card');
      chips.forEach(function (chip) {
        chip.addEventListener('click', function () {
          chips.forEach(function (c) { c.classList.remove('active'); });
          chip.classList.add('active');
          var tag = chip.getAttribute('data-tag');
          cards.forEach(function (card) {
            var tags = (card.getAttribute('data-tags') || '').split(' ');
            card.classList.toggle('hidden', !!tag && tags.indexOf(tag) === -1);
          });
        });
      });
    })();
"""

DETAIL_JS = """
    (function () {
      var hero = document.getElementById('heroZoom');
      var box = document.getElementById('lightbox');
      if (hero && box) {
        hero.addEventListener('click', function () { box.classList.add('open'); });
        box.addEventListener('click', function () { box.classList.remove('open'); });
        document.addEventListener('keydown', function (e) {
          if (e.key === 'Escape') box.classList.remove('open');
        });
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
        <a class="card-media" href="__HREF__" aria-label="__NAME__ example detail page">
          <img src="__HERO__" alt="__ALT__" loading="lazy" decoding="async" />
        </a>
        <div class="card-body">
          <h2><a href="__HREF__">__NAME__</a></h2>
          <p class="teaches">__TEACHES__</p>
          <p class="witnesses"><span class="tag">witnesses</span> __WITNESSES__</p>
          <a class="card-link" href="__HREF__">View example <span aria-hidden="true">&rarr;</span></a>
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
# unordered lists, fenced code, inline code/bold/links). Relative links are
# resolved against the example's directory on GitHub.
# ---------------------------------------------------------------------------

_INLINE = re.compile(r"`([^`]+)`|\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)]+)\)")


def render_inline(text: str, resolve) -> str:
    out = []
    pos = 0
    for m in _INLINE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        if m.group(1) is not None:
            out.append(f"<code>{html.escape(m.group(1))}</code>")
        elif m.group(2) is not None:
            out.append(f"<strong>{render_inline(m.group(2), resolve)}</strong>")
        else:
            href = html.escape(resolve(m.group(4)), quote=True)
            out.append(f'<a href="{href}">{render_inline(m.group(3), resolve)}</a>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


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

        if stripped.startswith("- "):
            items: list[str] = []
            while i < len(lines):
                cur = lines[i].strip()
                if cur.startswith("- "):
                    items.append(cur[2:])
                elif cur and lines[i].startswith("  ") and items:
                    items[-1] += " " + cur  # wrapped continuation line
                else:
                    break
                i += 1
            lis = "".join(f"<li>{render_inline(it, resolve)}</li>" for it in items)
            out.append(f"<ul>{lis}</ul>")
            continue

        para: list[str] = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt or nxt.startswith(("#", "- ", "```")):
                break
            para.append(nxt)
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
          content: str, page_js: str) -> str:
    return (SHELL
            .replace("__TITLE__", html.escape(title))
            .replace("__DESC__", html.escape(desc, quote=True))
            .replace("__CANONICAL__", html.escape(canonical, quote=True))
            .replace("__OGIMAGE__", html.escape(og_image, quote=True))
            .replace("__SITEROOT__", site_root)
            .replace("__BACKHREF__", back_href)
            .replace("__BACKLABEL__", html.escape(back_label))
            .replace("__REPO__", html.escape(repo_url, quote=True))
            .replace("__CONTENT__", content)
            .replace("__PAGEJS__", page_js))


def build_detail(ex: dict, *, base: str, repo_root_url: str, site: str) -> str:
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
    parts.append('    <p class="zoom-hint">Rendered headless by the example itself — click to zoom.</p>')
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
    parts.append('  <div class="lightbox" id="lightbox" role="dialog" aria-label="Full-size render">')
    parts.append(f'    <img src="../assets/{html.escape(hero_file)}" alt="{html.escape(name)} render, full size" />')
    parts.append("  </div>")

    return shell(
        title=f"{name} — Examples — Blender Developer Tools",
        desc=ex["teaches"],
        canonical=f"{site}/gallery/{name}/" if site else "",
        og_image=f"{site}/gallery/assets/{hero_file}" if site else "",
        site_root="../../",
        back_href="../",
        back_label="Examples Gallery",
        repo_url=repo_root_url,
        content="\n".join(parts),
        page_js=DETAIL_JS,
    )


def build_index(data: dict, *, base: str, repo_root_url: str, site: str) -> str:
    examples = data["examples"]
    title = data.get("title", "Examples Gallery")
    desc = data.get("description", "")

    all_tags = sorted({t for ex in examples for t in ex.get("tags", [])})
    chip_html = ""
    if all_tags:
        chips = ['<button class="chip active" data-tag="" type="button">All</button>']
        chips += [
            f'<button class="chip" data-tag="{html.escape(t, quote=True)}" type="button">{html.escape(t)}</button>'
            for t in all_tags
        ]
        chip_html = ('  <div class="chips" role="toolbar" aria-label="Filter examples by topic">\n    '
                     + "\n    ".join(chips) + "\n  </div>\n")

    cards = []
    for ex in examples:
        alt = f'{ex["name"]} — {ex["teaches"].split(".")[0]}'
        cards.append(
            CARD
            .replace("__TAGS__", html.escape(" ".join(ex.get("tags", [])), quote=True))
            .replace("__HREF__", html.escape(f'{ex["name"]}/', quote=True))
            .replace("__HERO__", html.escape(page_relative(ex["hero"]), quote=True))
            .replace("__ALT__", html.escape(alt, quote=True))
            .replace("__NAME__", html.escape(ex["name"]))
            .replace("__TEACHES__", html.escape(ex["teaches"]))
            .replace("__WITNESSES__", html.escape(ex["witnessesFix"]))
        )

    content = (
        '  <header class="hero">\n'
        f"    <h1>{html.escape(title)}</h1>\n"
        f"    <p>{html.escape(desc)}</p>\n"
        "  </header>\n"
        + chip_html
        + '  <main id="main">\n    <div class="grid">\n'
        + "\n".join(cards)
        + "\n    </div>\n  </main>"
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
        page_js=INDEX_JS,
    )


def main() -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
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

    print(f"Wrote {OUT_DIR / 'index.html'} + {len(examples)} detail pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
