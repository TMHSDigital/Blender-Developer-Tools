#!/usr/bin/env python3
"""Check every internal link and image on the built site resolves.

Run after both builds have written into docs/ (the landing build is not
committed, so CI builds it first):

    python scripts/site/build_site.py --repo-root . --out docs
    python tests/check_site_links.py

Walks docs/index.html, docs/404.html and docs/gallery/**/index.html. Each
relative or site-absolute ``href``/``src`` must name a file under docs/ (a
directory means its index.html), and each ``#fragment`` must match an ``id``
on the target page; every ``srcset`` candidate counts as a reference too, and
``og:image``/``twitter:image``/``og:url`` must be absolute URLs. Fragments carrying ``=`` are gallery filter state
(``#tag=mesh``, ``#k=showcase``), not anchors, and are skipped. Every
``<img>`` must carry an ``alt`` attribute. Exits 1 listing every failure.
"""

from __future__ import annotations

import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"


class PageScan(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.refs: list[tuple[int, str, str]] = []  # (line, attr, url)
        self.imgs_without_alt: list[int] = []
        self.bad_meta: list[tuple[int, str]] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        line = self.getpos()[0]
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "a" and a.get("name"):
            self.ids.add(a["name"])
        for key in ("href", "src"):
            if a.get(key) and tag in ("a", "img", "link", "script"):
                self.refs.append((line, key, a[key]))
        # Each srcset candidate is "URL [descriptor]"; every URL must resolve.
        if a.get("srcset") and tag in ("img", "source"):
            for cand in a["srcset"].split(","):
                if cand.strip():
                    self.refs.append((line, "srcset", cand.split()[0]))
        # Link-preview scrapers do not resolve relative og/twitter image URLs.
        prop = a.get("property") or a.get("name") or ""
        if tag == "meta" and prop in ("og:image", "twitter:image", "og:url"):
            if not (a.get("content") or "").startswith(("https://", "http://")):
                self.bad_meta.append((line, prop))
        if tag == "img" and "alt" not in a:
            self.imgs_without_alt.append(line)


def scan(path: Path, cache: dict[Path, PageScan]) -> PageScan:
    if path not in cache:
        p = PageScan()
        p.feed(path.read_text(encoding="utf-8"))
        cache[path] = p
    return cache[path]


def site_base() -> str:
    """Path component of the canonical URL, e.g. /Blender-Developer-Tools/."""
    site = json.loads((REPO / "site.json").read_text(encoding="utf-8"))
    base = urlparse(site.get("canonical", "")).path or "/"
    return base if base.endswith("/") else base + "/"


def resolve(page: Path, url: str, base: str) -> Path | None:
    """Local file a reference points at, or None when it leaves the site."""
    u = urlparse(url)
    if u.scheme or u.netloc:
        return None
    path = unquote(u.path)
    if not path:
        return page
    if path.startswith("/"):
        if not path.startswith(base):
            return DOCS / "__outside_site_base__"
        target = DOCS / path[len(base):]
    else:
        target = page.parent / path
    if path.endswith("/") or target.is_dir():
        target = target / "index.html"
    return target.resolve()


def main() -> int:
    if not (DOCS / "index.html").is_file():
        print("ERROR: docs/index.html missing; run scripts/site/build_site.py first",
              file=sys.stderr)
        return 2
    pages = [DOCS / "index.html", DOCS / "404.html",
             *sorted((DOCS / "gallery").glob("**/index.html"))]
    base = site_base()
    cache: dict[Path, PageScan] = {}
    failures: list[str] = []
    n_refs = 0

    for page in pages:
        rel = page.relative_to(DOCS).as_posix()
        s = scan(page, cache)
        for line in s.imgs_without_alt:
            failures.append(f"{rel}:{line}: <img> without alt")
        for line, prop in s.bad_meta:
            failures.append(f"{rel}:{line}: {prop} is not an absolute URL")
        for line, key, url in s.refs:
            if url.startswith(("mailto:", "data:", "javascript:")):
                continue
            target = resolve(page, url, base)
            if target is None:
                continue
            n_refs += 1
            if not target.is_file():
                failures.append(f"{rel}:{line}: {key}={url!r} -> missing {target}")
                continue
            frag = urlparse(url).fragment
            if frag and "=" not in frag and target.suffix == ".html":
                if unquote(frag) not in scan(target, cache).ids:
                    failures.append(f"{rel}:{line}: {key}={url!r} -> no id {frag!r} "
                                    f"in {target.relative_to(DOCS).as_posix()}")

    for f in failures:
        print(f"FAIL {f}")
    print(f"{len(pages)} pages, {n_refs} internal references, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
