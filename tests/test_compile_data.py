import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.dom import minidom

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))

from scripts import compile_data


def article_md(slug="demo-post", title="Demo", date="2026-09-01", extra=""):
    return (
        f"---\n"
        f"slug: {slug}\n"
        f'title: "{title}"\n'
        f'date: "{date}"\n'
        f"{extra}"
        f"---\n\n"
        f"正文内容\n"
    )


class CompileArticlesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.content = root / "content"
        self.content.mkdir()
        (root / "data").mkdir()
        site_src = root / "site" / "src"
        site_src.mkdir(parents=True)
        public = root / "site" / "public"
        public.mkdir(parents=True)
        self.patches = (
            patch.object(compile_data, "CONTENT_DIR", self.content),
            patch.object(compile_data, "DATA_DIR", root / "data"),
            patch.object(compile_data, "SITE_DATA_DIR", site_src),
            patch.object(compile_data, "PUBLIC_DIR", public),
        )
        for item in self.patches:
            item.start()
        self.addCleanup(self._tmp.cleanup)
        for item in self.patches:
            self.addCleanup(item.stop)

    def test_valid_article_compiles(self):
        (self.content / "a.md").write_text(article_md(), encoding="utf-8")
        articles = compile_data.compile_articles()
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["slug"], "demo-post")

    def test_duplicate_slug_is_rejected(self):
        (self.content / "a.md").write_text(article_md(slug="same-slug"), encoding="utf-8")
        (self.content / "b.md").write_text(article_md(slug="same-slug"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "slug 重复"):
            compile_data.compile_articles()

    def test_invalid_slug_is_rejected(self):
        (self.content / "a.md").write_text(article_md(slug="Bad_Slug"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "slug"):
            compile_data.compile_articles()

    def test_invalid_date_is_rejected(self):
        (self.content / "a.md").write_text(article_md(date="2026/09/01"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "date"):
            compile_data.compile_articles()

    def test_impossible_date_is_rejected(self):
        (self.content / "a.md").write_text(article_md(date="2026-13-40"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "有效日期"):
            compile_data.compile_articles()

    def test_overlong_title_is_rejected(self):
        (self.content / "a.md").write_text(article_md(title="长" * 201), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "title"):
            compile_data.compile_articles()

    def test_invalid_tags_are_rejected(self):
        (self.content / "a.md").write_text(
            article_md(extra="tags: [\"ok\", \"\"]\n"), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "tags"):
            compile_data.compile_articles()

    def test_source_url_validated_and_propagated(self):
        (self.content / "a.md").write_text(
            article_md(extra="source_url: \"https://blog.example.com/post/1\"\n"), encoding="utf-8"
        )
        articles = compile_data.compile_articles()
        self.assertEqual(articles[0]["source_url"], "https://blog.example.com/post/1")

    def test_source_url_must_be_https(self):
        (self.content / "a.md").write_text(
            article_md(extra="source_url: \"http://blog.example.com/1\"\n"), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "source_url"):
            compile_data.compile_articles()

    def test_source_url_absent_is_allowed_for_legacy_articles(self):
        (self.content / "a.md").write_text(article_md(), encoding="utf-8")
        articles = compile_data.compile_articles()
        self.assertIsNone(articles[0]["source_url"])

    def test_sitemap_is_well_formed_xml(self):
        (self.content / "a.md").write_text(article_md(), encoding="utf-8")
        articles = compile_data.compile_articles()
        compile_data.generate_sitemap([{"slug": "deepseek"}, {"slug": "groq"}], articles)
        sitemap_path = compile_data.PUBLIC_DIR / "sitemap.xml"
        parsed = minidom.parse(str(sitemap_path))
        locs = {node.firstChild.nodeValue for node in parsed.getElementsByTagName("loc")}
        self.assertIn("https://freetokens.info/article/demo-post/", locs)
        self.assertIn("https://freetokens.info/platform/deepseek/", locs)
        self.assertIn("https://freetokens.info/en/platform/groq/", locs)


if __name__ == "__main__":
    unittest.main()
