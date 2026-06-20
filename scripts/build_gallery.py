#!/usr/bin/env python3
"""Generate the standalone examples gallery page from examples/gallery.json.

This page is a LOCAL, this-repo gallery that rides alongside the fleet-generated
docs/index.html (which build_site.py owns and overwrites). It writes ONLY to
docs/gallery/ so it never collides with the fleet build's docs/index.html,
docs/fonts/, or docs/assets/.

examples/gallery.json is the forward-compatible source of truth: when the fleet
template gains examples support, it consumes the same data and this script and
page are retired. The visual direction here is the deliberate PROTOTYPE for that
fleet facelift -- see docs/gallery/DESIGN_NOTES.md. Run after editing gallery.json:

    python scripts/build_gallery.py

Stdlib only (no Jinja2), so the Pages workflow can regenerate it without extra deps.
Uses token replacement (not str.format) so CSS braces need no escaping.
"""
import html
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "examples" / "gallery.json"
OUT = REPO / "docs" / "gallery" / "index.html"

CARD = """      <article class="card">
        <a class="card-media" href="__HREF__" aria-label="__NAME__ example on GitHub">
          <img src="__HERO__" alt="__ALT__" loading="lazy" decoding="async" />
        </a>
        <div class="card-body">
          <h2><a href="__HREF__">__NAME__</a></h2>
          <p class="teaches">__TEACHES__</p>
          <p class="witnesses"><span class="tag">witnesses</span> __WITNESSES__</p>
          <a class="card-link" href="__HREF__">View example <span aria-hidden="true">&rarr;</span></a>
        </div>
      </article>"""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__ — Blender Developer Tools</title>
  <meta name="description" content="__DESC__" />
  <link rel="canonical" href="__CANONICAL__" />
  <link rel="icon" href="../assets/favicon.svg" type="image/svg+xml" />
  <meta name="theme-color" content="#0d1117" media="(prefers-color-scheme: dark)" />
  <meta name="theme-color" content="#f6f8fa" media="(prefers-color-scheme: light)" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="__TITLE__ — Blender Developer Tools" />
  <meta property="og:description" content="__DESC__" />
  <meta property="og:url" content="__CANONICAL__" />
  <meta property="og:image" content="__OGIMAGE__" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="__TITLE__ — Blender Developer Tools" />
  <meta name="twitter:description" content="__DESC__" />
  <meta name="twitter:image" content="__OGIMAGE__" />
  <!-- FOUC guard: apply the saved theme before first paint. Shares the 'theme'
       key with the fleet landing page, so a visitor's choice carries across. -->
  <script>(function(){try{var t=localStorage.getItem('theme');if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t);}catch(e){}})();</script>
  <style>
    :root {
      --bg: #0d1117; --bg2: #161b22; --surface: #161b22; --surface-2: #1c2128;
      --border: #30363d; --text: #e6edf3; --text-dim: #8b949e;
      --accent: #7c3aed; --accent-light: #a78bfa;
      --radius: 8px; --radius-lg: 12px; --maxw: 1080px;
      --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    }
    /* auto mode: follow the OS unless the user forced dark */
    @media (prefers-color-scheme: light) {
      :root:not([data-theme="dark"]) {
        --bg: #f6f8fa; --bg2: #ffffff; --surface: #ffffff; --surface-2: #f0f2f5;
        --border: #d0d7de; --text: #1f2328; --text-dim: #656d76;
      }
    }
    /* explicit override */
    [data-theme="light"] {
      --bg: #f6f8fa; --bg2: #ffffff; --surface: #ffffff; --surface-2: #f0f2f5;
      --border: #d0d7de; --text: #1f2328; --text-dim: #656d76;
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

    main { max-width: var(--maxw); margin: 0 auto; padding: 1rem 1.25rem 2rem;
      display: grid; grid-template-columns: 1fr; gap: 1.5rem; align-items: stretch; }
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
      overflow: hidden; display: flex; flex-direction: column;
      transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease; }
    .card:hover { transform: translateY(-3px); border-color: color-mix(in srgb, var(--accent) 55%, var(--border));
      box-shadow: 0 8px 28px rgba(0,0,0,0.28); }
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

    footer { max-width: var(--maxw); margin: 0 auto; padding: 2rem 1.25rem 3rem;
      color: var(--text-dim); font-size: 0.85rem; border-top: 1px solid var(--border); }
    footer code { background: var(--surface-2); padding: 0.1rem 0.35rem; border-radius: 4px; font-size: 0.82rem; }

    @media (min-width: 720px) { main { grid-template-columns: 1fr 1fr; gap: 1.75rem; } }
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
    <a class="back" href="../"><span aria-hidden="true">&larr;</span> Blender Developer Tools</a>
    <div class="topbar-right">
      <a class="ghlink" href="__REPO__">GitHub</a>
      <button class="theme-toggle" id="themeToggle" type="button" aria-label="Theme: auto (click to change)">&#9788;</button>
    </div>
  </div>
  <header class="hero">
    <h1>__TITLE__</h1>
    <p>__DESC__</p>
  </header>
  <main id="main">
__CARDS__
  </main>
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
  </script>
</body>
</html>
"""


def page_relative(repo_rel: str) -> str:
    """docs/gallery/assets/x.webp -> assets/x.webp (relative to the gallery page)."""
    prefix = "docs/gallery/"
    return repo_rel[len(prefix):] if repo_rel.startswith(prefix) else repo_rel


def main() -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    base = data["repoBaseUrl"].rstrip("/")
    repo_root_url = base.split("/tree/")[0]  # strip /tree/<ref> -> repo home
    site = data.get("siteBaseUrl", "").rstrip("/")
    title = data.get("title", "Examples Gallery")
    desc = data.get("description", "")
    examples = data["examples"]
    if not examples:
        print("ERROR: no examples in gallery.json", file=sys.stderr)
        return 2

    cards = []
    for ex in examples:
        if not (REPO / ex["hero"]).is_file():
            print(f"ERROR: hero image missing: {ex['hero']}", file=sys.stderr)
            return 3
        alt = f'{ex["name"]} — {ex["teaches"].split(".")[0]}'
        card = (CARD
                .replace("__HREF__", html.escape(f"{base}/{ex['dir']}"))
                .replace("__HERO__", html.escape(page_relative(ex["hero"])))
                .replace("__ALT__", html.escape(alt))
                .replace("__NAME__", html.escape(ex["name"]))
                .replace("__TEACHES__", html.escape(ex["teaches"]))
                .replace("__WITNESSES__", html.escape(ex["witnessesFix"])))
        cards.append(card)

    og_image = f"{site}/gallery/assets/{page_relative(examples[0]['hero']).split('/')[-1]}" if site else ""
    canonical = f"{site}/gallery/" if site else ""
    out_html = (PAGE
                .replace("__CARDS__", "\n".join(cards))
                .replace("__TITLE__", html.escape(title))
                .replace("__DESC__", html.escape(desc))
                .replace("__CANONICAL__", html.escape(canonical))
                .replace("__OGIMAGE__", html.escape(og_image))
                .replace("__REPO__", html.escape(repo_root_url)))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(out_html, encoding="utf-8")
    print(f"Wrote {OUT} ({len(examples)} examples)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
