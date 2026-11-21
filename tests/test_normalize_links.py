import tempfile
import unittest
from pathlib import Path

from internship_finder.filters import is_tech, is_underclass_program, load_exclusions
from internship_finder.links import posting_keys, resolve_short_links
from internship_finder.normalize import company_key, is_us, similarity, title_tokens


class NormalizeTest(unittest.TestCase):
    def test_company_key_ignores_legal_words_and_parentheses(self):
        self.assertEqual(company_key("The Walt Disney Company (Parks)"), "waltdisney")
        self.assertEqual(company_key("Capital One, Inc."), company_key("capital one"))

    def test_title_tokens_drop_filler_years_and_place_names(self):
        tokens = title_tokens("Software Engineer Intern - Summer 2027 - Austin, TX", ["Austin, TX"])
        self.assertEqual(tokens, {"software", "engineer"})

    def test_similarity(self):
        self.assertEqual(similarity({"a", "b"}, {"a", "b"}), 1)
        self.assertEqual(similarity(set(), set()), 0)
        self.assertAlmostEqual(similarity({"a", "b"}, {"a", "c"}), 1 / 3)

    def test_is_us(self):
        self.assertTrue(is_us(["New York, NY"]))
        self.assertTrue(is_us(["Toronto, ON", "Remote in US"]))
        self.assertFalse(is_us(["Toronto, ON"]))
        self.assertFalse(is_us(["London, UK"]))


class FilterTest(unittest.TestCase):
    def test_tech_titles(self):
        self.assertTrue(is_tech("Software Engineering Intern"))
        self.assertTrue(is_tech("Machine Learning Intern"))
        self.assertFalse(is_tech("Mechanical Engineering Intern"))
        self.assertFalse(is_tech("PhD Research Intern, ML"))
        self.assertFalse(is_tech("Software Engineer Co-op"))
        self.assertFalse(is_tech("Marketing Intern"))

    def test_underclass_programs(self):
        self.assertTrue(is_underclass_program("STEP Intern 2027"))
        self.assertTrue(is_underclass_program("Explore Program - Freshman/Sophomore"))
        self.assertFalse(is_underclass_program("Software Engineer Intern"))

    def test_exclusion_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "excluded.txt"
            path.write_text("# comment\nAcme Inc   # no sponsorship\n\nBeta LLC\n", encoding="utf-8")
            self.assertEqual(load_exclusions([path, Path(tmp) / "missing.txt"]), {"acme", "beta"})


class PostingKeysTest(unittest.TestCase):
    def test_workday_reposted_copies_are_one_posting(self):
        a = "https://nvidia.wd5.myworkdayjobs.com/en-US/External/job/US-CA/AI-Intern_JR2029119-1"
        b = "https://nvidia.wd5.myworkdayjobs.com/External/job/US-CA/AI-Intern_JR2029119"
        self.assertEqual(posting_keys(a), posting_keys(b))
        self.assertEqual(posting_keys(a), ("workday:nvidia:jr2029119", "workday:nvidia"))

    def test_greenhouse_ids_are_global(self):
        board = posting_keys("https://boards.greenhouse.io/airbnb/jobs/8360478")
        custom = posting_keys("https://careers.airbnb.com/positions/8360478?gh_jid=8360478")
        self.assertEqual(board[0], "greenhouse:8360478")
        self.assertEqual(custom[0], "greenhouse:8360478")

    def test_other_job_sites(self):
        uuid = "0b7b1a9e-5f00-4a6b-9a65-1c2d3e4f5a6b"
        self.assertEqual(posting_keys(f"https://jobs.ashbyhq.com/ramp/{uuid}")[1], "ashby:ramp")
        self.assertEqual(posting_keys(f"https://jobs.lever.co/zoox/{uuid}")[0], f"lever:{uuid}")
        self.assertEqual(posting_keys("https://careers-acme.icims.com/jobs/12345/intern/job")[0],
                         "icims:careers-acme:12345")
        self.assertEqual(posting_keys("https://www.amazon.jobs/en/jobs/10553907/data-engineer-intern"),
                         ("amazon:amazon:10553907", "amazon:amazon"))

    def test_unknown_sites(self):
        self.assertEqual(posting_keys("https://example.com/careers/job/123456?utm_source=x"),
                         ("example.com/careers/job/123456", None))
        self.assertEqual(posting_keys("https://example.com/careers"), (None, None))
        self.assertEqual(posting_keys(""), (None, None))

    def test_short_links_are_resolved_once_and_cached(self):
        calls = []

        def resolver(url):
            calls.append(url)
            return "https://boards.greenhouse.io/acme/jobs/1"

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache.json"
            urls = ["https://go.vansh.nyc/abc", "https://example.com/job/1"]
            first = resolve_short_links(urls, cache, resolver=resolver)
            second = resolve_short_links(urls, cache, resolver=resolver)
        self.assertEqual(first, {"https://go.vansh.nyc/abc": "https://boards.greenhouse.io/acme/jobs/1"})
        self.assertEqual(second, first)
        self.assertEqual(calls, ["https://go.vansh.nyc/abc"])


if __name__ == "__main__":
    unittest.main()
