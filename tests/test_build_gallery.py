"""Unit tests for scripts/build_gallery.py's text helpers (#528). No Blender required.

Validate's only other check on the gallery generator regenerates docs/gallery
and diffs it against the committed copy, which is circular: a generator bug is
committed together with its output. PR #68 (card alts cut at dotted API paths
like `bmesh.ops`) shipped that way. These pin the helpers that turn README and
gallery.json text into HTML.

    python tests/test_build_gallery.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import build_gallery as bg  # noqa: E402


def ident(href: str) -> str:
    return href


class FirstSentence(unittest.TestCase):
    def test_dotted_api_path_does_not_end_the_sentence(self):
        text = "Uses bmesh.ops.create_cone to build a gear. Then checks it."
        self.assertEqual(bg.first_sentence(text), "Uses bmesh.ops.create_cone to build a gear.")

    def test_abbreviations_do_not_end_the_sentence(self):
        text = "Compares e.g. EEVEE vs. Cycles output. Second."
        self.assertEqual(bg.first_sentence(text), "Compares e.g. EEVEE vs. Cycles output.")

    def test_code_led_next_sentence(self):
        self.assertEqual(bg.first_sentence("One thing. `bpy.ops` next."), "One thing.")

    def test_single_sentence_is_returned_whole(self):
        self.assertEqual(bg.first_sentence("No terminal period"), "No terminal period")


class Slugify(unittest.TestCase):
    def test_github_style(self):
        self.assertEqual(bg.slugify("Exit codes (`--output`)", set()), "exit-codes-output")

    def test_duplicates_are_numbered(self):
        seen: set[str] = set()
        self.assertEqual([bg.slugify("Usage", seen) for _ in range(3)], ["usage", "usage-1", "usage-2"])

    def test_reserved_ids_are_never_used(self):
        for rid in ("main", "related", "source"):
            with self.subTest(rid=rid):
                self.assertNotIn(bg.slugify(rid, set()), bg.RESERVED_IDS)

    def test_link_label_and_empty(self):
        self.assertEqual(bg.slugify("[Docs](https://x.y/z)", set()), "docs")
        self.assertEqual(bg.slugify("***", set()), "section")


class RenderInline(unittest.TestCase):
    def test_plain_text_is_escaped(self):
        self.assertEqual(bg.render_inline("<script>a & b</script>", ident),
                         "&lt;script&gt;a &amp; b&lt;/script&gt;")

    def test_code_span_is_escaped(self):
        self.assertEqual(bg.render_inline("`<b>`", ident), "<code>&lt;b&gt;</code>")

    def test_nested_emphasis(self):
        # the form READMEs use (examples/vertex-color-ao: "**... *cached* ...**").
        # A closing "***" (em and strong ending together) is not supported; no
        # README uses it.
        self.assertEqual(bg.render_inline("**offsets along *cached* normals**", ident),
                         "<strong>offsets along <em>cached</em> normals</strong>")

    def test_link_href_is_quote_escaped(self):
        out = bg.render_inline('[x](a"b)', ident)
        self.assertIn('href="a&quot;b"', out)

    def test_image_becomes_a_link_with_its_alt(self):
        self.assertEqual(bg.render_inline("![a still](img.png)", ident), '<a href="img.png">a still</a>')


class InlineCode(unittest.TestCase):
    def test_balanced_spans(self):
        self.assertEqual(bg.inline_code("use `a<b`"), "use <code>a&lt;b</code>")

    def test_unbalanced_backtick_stays_literal(self):
        self.assertEqual(bg.inline_code("a ` b"), "a ` b")


class MdToHtml(unittest.TestCase):
    def test_table_cell_keeps_escaped_pipe_and_code_pipe(self):
        md = "| Code | Meaning |\n| --- | --- |\n| 3 | `a|b` failed |\n"
        out = bg.md_to_html(md, ident)
        self.assertIn("<td>3</td>", out)
        self.assertIn("<code>a|b</code>", out)

    def test_first_h1_is_skipped_by_default(self):
        md = "# Title\n\n## Usage\n\ntext\n"
        out = bg.md_to_html(md, ident)
        self.assertNotIn("Title", out)
        self.assertIn('id="usage"', out)
        self.assertIn("Title", bg.md_to_html(md, ident, skip_first_h1=False))

    def test_heading_never_takes_a_reserved_id(self):
        out = bg.md_to_html("# T\n\n## Related\n", ident)
        self.assertNotIn('id="related"', out)

    def test_ordered_list_and_code_fence(self):
        out = bg.md_to_html("# T\n\n1. one\n2. two\n\n```bash\na < b\n```\n", ident)
        self.assertIn("<ol>", out)
        self.assertIn("a &lt; b", out)


class CheckAlts(unittest.TestCase):
    def test_good_alt_passes(self):
        bg.check_alts([{"name": "x", "alt": "A gear on a dark stage."}])

    def test_bad_alts_fail(self):
        for alt in ("", "   ", "x" * (bg.ALT_MAX + 1), "uses `bpy`"):
            with self.subTest(alt=alt[:20]), self.assertRaises(SystemExit):
                bg.check_alts([{"name": "x", "alt": alt}])

    def test_missing_alt_fails(self):
        with self.assertRaises(SystemExit):
            bg.check_alts([{"name": "x"}])


class CardAlt(unittest.TestCase):
    def test_card_alt_is_the_source_alt_verbatim(self):
        # The #68 bug cut alts at dotted API paths; the card must carry the
        # whole source sentence, escaped, never a derived or truncated one.
        data, _ = bg.load_gallery_entries()
        entries = data["examples"]
        html = bg.build_index(data, base="", repo_root_url="https://example.invalid/",
                              site="https://example.invalid", css_v="0")
        import html as h
        for e in entries[:10]:
            with self.subTest(name=e["name"]):
                self.assertIn(f'alt="{h.escape(e["alt"], quote=True)}"', html)


if __name__ == "__main__":
    unittest.main()
