"""Shared site chrome: the header (brand + primary nav + mobile menu) and the
status-bar footer that every published page wears.

Imported by both builders, so the landing page and all gallery pages carry
one header and one footer:

- scripts/site/build_site.py passes the rendered strings into the Jinja
  context (emitted with ``| safe``);
- scripts/build_gallery.py imports this module through a ``__file__``-relative
  ``sys.path`` entry.

``root`` is the relative prefix from the page to the site root: ``""`` for
docs/index.html, ``"../"`` for the gallery index, ``"../../"`` for a gallery
detail page. Stdlib only; colors come from tokens.css, never from here.
"""
from __future__ import annotations

import html

ALL_TOOLS_URL = "https://tmhsdigital.github.io/Developer-Tools-Directory/"

# (label, path under the site root, key used for aria-current)
NAV = (
    ("Examples", "gallery/#k=examples", "examples"),
    ("Showcase", "gallery/#k=showcase", "showcase"),
    ("What's new", "#new", "new"),
    ("Skills", "#skills", "skills"),
    ("Rules", "#rules", "rules"),
    ("Snippets", "#snippets", "snippets"),
    ("Install", "#install", "install"),
)

CSS = """
    /* ---- shared chrome (scripts/site/chrome.py): header + footer ---- */
    .site-header { position: sticky; top: 0; z-index: 20;
      background: color-mix(in srgb, var(--panel) 92%, transparent);
      backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--border); }
    .site-header-inner { max-width: var(--chrome-maxw); margin: 0 auto; display: flex;
      align-items: center; gap: 1rem; padding: 0 1.25rem; min-height: 46px; }
    .site-brand { display: flex; align-items: center; gap: 0.6rem; font-weight: 700;
      font-size: 0.9rem; white-space: nowrap; color: var(--text); text-decoration: none; }
    .site-brand:hover { color: var(--select); text-decoration: none; }
    .site-brand-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--select); flex-shrink: 0; }
    .site-nav { margin-left: auto; }
    .site-nav ul { display: flex; flex-wrap: wrap; gap: 0.25rem 1.1rem; list-style: none; align-items: center; margin: 0; padding: 0; }
    .site-nav a { color: var(--dim); font-size: 0.8125rem; font-weight: 500; text-decoration: none;
      transition: color 0.15s; }
    .site-nav a:hover, .site-nav a[aria-current] { color: var(--select); text-decoration: none; }
    .site-nav .gh { border-left: 1px solid var(--border); padding-left: 1.1rem; }
    .site-menu-btn { display: none; margin-left: auto; align-items: center; gap: 0.45rem;
      background: var(--panel-2); border: 1px solid var(--border); border-radius: 4px;
      color: var(--text); font: 500 0.78rem var(--font-body); padding: 0.32rem 0.7rem; cursor: pointer; }
    .site-menu-btn:hover { border-color: var(--select); color: var(--select); }
    .site-menu-icon, .site-menu-icon::before, .site-menu-icon::after { display: block; width: 14px; height: 2px;
      background: currentColor; border-radius: 1px; position: relative; }
    .site-menu-icon::before, .site-menu-icon::after { content: ''; position: absolute; left: 0; }
    .site-menu-icon::before { top: -4px; } .site-menu-icon::after { top: 4px; }
    @media (max-width: 820px) {
      /* No JS: the nav wraps under the brand instead of hiding. */
      .site-header-inner { flex-wrap: wrap; padding-top: 0.4rem; padding-bottom: 0.4rem; }
      .site-nav { margin-left: 0; width: 100%; }
      html.js .site-header-inner { flex-wrap: nowrap; padding-top: 0; padding-bottom: 0; }
      html.js .site-menu-btn { display: inline-flex; }
      html.js .site-nav { display: none; position: absolute; left: 0; right: 0; top: 100%;
        background: var(--panel); border-bottom: 1px solid var(--border);
        box-shadow: 0 12px 24px color-mix(in srgb, var(--bg2) 70%, transparent); }
      html.js .site-header.open .site-nav { display: block; }
      html.js .site-nav ul { flex-direction: column; align-items: stretch; gap: 0; padding: 0.35rem 0; }
      html.js .site-nav a { display: block; padding: 0.7rem 1.25rem; font-size: 0.95rem; }
      html.js .site-nav .gh { border-left: 0; padding-left: 0; border-top: 1px solid var(--border); }
    }

    .site-footer { border-top: 1px solid var(--border); background: var(--panel); margin-top: 2rem; }
    .site-footer-inner { max-width: var(--chrome-maxw); margin: 0 auto; padding: 0.55rem 1.25rem;
      display: flex; align-items: center; gap: 0.4rem 1rem; flex-wrap: wrap;
      font-family: var(--font-mono); font-size: 0.6875rem; letter-spacing: 0.04em;
      text-transform: uppercase; color: var(--dim); }
    .site-footer-inner code { font-family: inherit; text-transform: none; }
    .site-footer .ok { color: var(--ok); }
    .site-footer .links { margin-left: auto; display: flex; flex-wrap: wrap; gap: 0.4rem 1rem; }
    .site-footer a { color: var(--dim); text-decoration: none; }
    .site-footer a:hover { color: var(--select); text-decoration: none; }
    @media (prefers-reduced-motion: reduce) { .site-nav a { transition: none; } }
"""

# Runs after the header is in the DOM. The menu is a disclosure, not a modal:
# Escape and picking a link close it and hand focus back to the button.
JS = """
    (function () {
      var hdr = document.querySelector('.site-header');
      var btn = hdr && hdr.querySelector('.site-menu-btn');
      if (!btn) return;
      function set(open, refocus) {
        hdr.classList.toggle('open', open);
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (!open && refocus) btn.focus();
      }
      btn.addEventListener('click', function () { set(!hdr.classList.contains('open'), false); });
      hdr.querySelectorAll('.site-nav a').forEach(function (a) {
        a.addEventListener('click', function () { set(false, false); });
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && hdr.classList.contains('open')) set(false, true);
      });
      document.addEventListener('click', function (e) {
        if (hdr.classList.contains('open') && !hdr.contains(e.target)) set(false, false);
      });
    })();
"""


def _e(s: str) -> str:
    return html.escape(s, quote=True)


def header(*, root: str, repo: str, title: str, current: str = "",
           home_anchors: bool = True) -> str:
    """The sticky site header.

    ``home_anchors`` is True on the landing page itself, where in-page
    section links stay bare ``#id``; elsewhere they point back at the root.
    """
    items = []
    for label, path, key in NAV:
        href = path if (home_anchors and path.startswith("#")) else root + path
        cur = ' aria-current="page"' if key == current else ""
        items.append(f'<li><a href="{_e(href)}"{cur}>{html.escape(label)}</a></li>')
    items.append(f'<li class="gh"><a href="{_e(repo)}">GitHub</a></li>')
    home = root or "./"
    return (
        '  <header class="site-header">\n'
        '    <div class="site-header-inner">\n'
        f'      <a class="site-brand" href="{_e(home)}"><span class="site-brand-dot" aria-hidden="true"></span>{html.escape(title)}</a>\n'
        '      <button class="site-menu-btn" type="button" aria-expanded="false" aria-controls="site-nav">'
        '<span class="site-menu-icon" aria-hidden="true"></span>Menu</button>\n'
        '      <nav class="site-nav" id="site-nav" aria-label="Primary">\n'
        '        <ul>' + "".join(items) + '</ul>\n'
        '      </nav>\n'
        '    </div>\n'
        '  </header>\n'
    )


def footer(*, root: str, repo: str, title: str, license_: str, version: str = "",
           build_date: str = "", source_html: str = "") -> str:
    """The status-bar footer. *source_html* is pre-escaped markup.

    The gallery passes no *version* or *build_date*: docs/gallery/ is committed
    and validate.yml fails on any diff from a fresh build, so a value that a
    release bump or the calendar changes would make every page stale.
    """
    cells = [f'<a href="{_e(root or "./")}">{html.escape(title)}</a>']
    if version:
        cells.append(f'<span>v{html.escape(version)}</span>')
    cells.append(f'<span>{html.escape(license_)}</span>')
    if build_date:
        cells.append(f'<span>built {html.escape(build_date)}</span>')
    if source_html:
        cells.append(f'<span>generated from {source_html}</span>')
    cells.append('<span class="ok">exit 0</span>')
    return (
        '  <footer class="site-footer">\n'
        '    <div class="site-footer-inner">\n'
        + "".join(f"      {c}\n" for c in cells) +
        '      <span class="links">'
        f'<a href="{_e(root)}gallery/">Gallery</a>'
        f'<a href="{_e(repo)}/releases">Releases</a>'
        f'<a href="{_e(repo)}/blob/main/CHANGELOG.md">Changelog</a>'
        f'<a href="{_e(repo)}">GitHub</a>'
        f'<a href="{_e(ALL_TOOLS_URL)}">All tools</a></span>\n'
        '    </div>\n'
        '  </footer>\n'
    )
