import tempfile
import unittest
from pathlib import Path

from tools import check_guide


class CheckGuideTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, text):
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_flags_subscription_guid(self):
        p = self._write("a.md", "구독: 11111111-2222-3333-4444-555555555555\n")
        self.assertTrue(check_guide.check_file(p))

    def test_flags_any_guid_like_object_or_tenant_id(self):
        p = self._write("a.md", "principalId: ABCDEF01-2345-6789-abcd-ef0123456789\n")
        self.assertTrue(check_guide.check_file(p))

    def test_flags_tenant_domain(self):
        p = self._write("a.md", "user@MngEnvMCAP000000.onmicrosoft.com\n")
        self.assertTrue(check_guide.check_file(p))

    def test_flags_any_upn_or_email(self):
        p = self._write("a.md", "로그인: someone@contoso.com\n")
        self.assertTrue(check_guide.check_file(p))

    def test_flags_double_quotes_inside_single_quoted_query(self):
        p = self._write("a.md", "```powershell\naz version --query '\"azure-cli\"' -o tsv\n```\n")
        self.assertTrue(any("--query" in e for e in check_guide.check_file(p)))

    def test_flags_broken_relative_link(self):
        p = self._write("a.md", "[다음](./nope.md)\n")
        errors = check_guide.check_file(p)
        self.assertTrue(any("nope.md" in e for e in errors))

    def test_flags_unescaped_pipe_in_table_code(self):
        bad = self._write("bad.md", "| a | b |\n|---|---|\n| `x | y` | z |\n")
        good = self._write("good.md", "| a | b |\n|---|---|\n| `x \\| y` | z |\n")
        self.assertTrue(check_guide.check_file(bad))
        self.assertEqual(check_guide.check_file(good), [])

    def test_clean_file_passes(self):
        self._write("next.md", "# 다음\n")
        p = self._write("a.md", "# 제목\n\n[다음](./next.md#top) [외부](https://example.com)\n\n```\n| `a | b` |\n```\n")
        self.assertEqual(check_guide.check_file(p), [])
        self.assertEqual(check_guide.main([str(p)]), 0)


if __name__ == "__main__":
    unittest.main()
