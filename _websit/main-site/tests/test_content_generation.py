import unittest

from scripts.generate_content import generate_wechat_article


class ContentGenerationTests(unittest.TestCase):
    def test_wechat_output_escapes_platform_fields(self):
        output = generate_wechat_article(
            [
                {
                    "name": '<img src=x onerror="alert(1)">',
                    "intro": '<a href="https://evil.example">click</a>',
                    "tags": ["\u9650\u65f6"],
                    "free_quota": {
                        "type": "\u9650\u65f6",
                        "amount": "<script>alert(1)</script>",
                        "unit": "tokens",
                        "conditions": ['<iframe src="https://evil.example">'],
                    },
                }
            ]
        )
        self.assertNotIn("<script>alert(1)</script>", output)
        self.assertNotIn("<img src=x", output)
        self.assertNotIn('<a href="https://evil.example">', output)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", output)


if __name__ == "__main__":
    unittest.main()
