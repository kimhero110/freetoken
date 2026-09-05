import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))

from scripts import rewrite_article


class SlugifyTests(unittest.TestCase):
    def test_from_title(self):
        self.assertEqual(rewrite_article.slugify("How to Save Tokens! 10x", "https://x.io"), "how-to-save-tokens-10x")

    def test_fallback_from_url(self):
        self.assertEqual(rewrite_article.slugify("", "https://blog.example.com/post/1"), "blog-example-com")
        self.assertEqual(rewrite_article.slugify("???", "https://blog.example.com/post"), "blog-example-com")

    def test_length_cap(self):
        self.assertLessEqual(len(rewrite_article.slugify("word " * 50, "https://x.io")), 60)


class ValidateOutputTests(unittest.TestCase):
    def base_parsed(self, **overrides):
        parsed = {"title": "T", "tags": ["a"], "body_md": "x" * 400}
        parsed.update(overrides)
        return parsed

    def test_valid(self):
        title, errors = rewrite_article.validate_output(self.base_parsed(), "https://x.io", "rewrite")
        self.assertEqual(title, "T")
        self.assertEqual(errors, [])

    def test_short_body_rejected_for_rewrite(self):
        _, errors = rewrite_article.validate_output(self.base_parsed(body_md="short"), "https://x.io", "rewrite")
        self.assertIn("body too short", errors)

    def test_outline_allows_shorter_body(self):
        _, errors = rewrite_article.validate_output(self.base_parsed(body_md="y" * 200), "https://x.io", "outline")
        self.assertEqual(errors, [])

    def test_bad_tags_rejected(self):
        _, errors = rewrite_article.validate_output(self.base_parsed(tags=[]), "https://x.io", "rewrite")
        self.assertIn("tags invalid", errors)
        _, errors = rewrite_article.validate_output(self.base_parsed(tags=["x" * 60]), "https://x.io", "rewrite")
        self.assertIn("tags invalid", errors)


class RenderMarkdownTests(unittest.TestCase):
    def test_source_url_is_forced_to_original(self):
        parsed = {"title": "T", "tags": ["a", "b"], "body_md": "正文", "summary": "S",
                  "title_en": "TE", "category": "实战指南", "summary_en": "SE"}
        rendered = rewrite_article.render_markdown(parsed, "my-slug", "https://original.example.com/x", "rewrite")
        self.assertIn('source_url: "https://original.example.com/x"', rendered)
        self.assertIn('slug: "my-slug"', rendered)
        self.assertIn("# T", rendered)
        self.assertNotIn('source_url: "https://evil"', rendered)

    def test_frontmatter_keys_within_whitelist(self):
        import re
        parsed = {"title": "T", "tags": ["a"], "body_md": "B", "summary": "S"}
        rendered = rewrite_article.render_markdown(parsed, "s", "https://o.io", "outline")
        frontmatter = rendered.split("---")[1]
        keys = {line.split(":")[0].strip() for line in frontmatter.splitlines() if ":" in line}
        self.assertTrue(keys <= rewrite_article.ALLOWED_FRONTMATTER, keys - rewrite_article.ALLOWED_FRONTMATTER)

    def test_outline_label_present(self):
        parsed = {"title": "T", "tags": ["a"], "body_md": "B"}
        rendered = rewrite_article.render_markdown(parsed, "s", "https://o.io", "outline")
        self.assertIn("提纲草稿", rendered)


if __name__ == "__main__":
    unittest.main()
