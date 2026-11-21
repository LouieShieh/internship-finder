import tempfile
import unittest
from datetime import date
from pathlib import Path

from internship_finder.applied import AppliedIndex
from internship_finder.config import build_settings, load_config
from internship_finder.h1b import H1BIndex, normalize, read_export
from internship_finder.pipeline import Role, add_h1b, compare_with_applied, keep, merge, sort_key
from internship_finder.sources import Listing

ARCHIVE_CSV = (
    '"Fiscal Year",Employer,"Initial Approval","Initial Denial","Continuing Approval","Continuing Denial",NAICS\n'
    '2022,"AMAZON.COM SERVICES LLC",100,1,50,0,45\n'
    '2022,"AMAZON WEB SERVICES INC",20,0,10,0,51\n'
    '2023,"GOOGLE LLC",7,0,3,0,51\n'
    '2023,"BLOOMBERG L.P.",4,0,1,0,51\n'
    '2023,"EY LLP",9,0,0,0,54\n'
    '2023,"ACME HOLDINGS INC DBA ROCKET LABS",2,0,0,0,54\n'
).encode()


class H1BTest(unittest.TestCase):
    def setUp(self):
        self.index = H1BIndex(read_export(ARCHIVE_CSV))

    def test_normalize(self):
        self.assertEqual(normalize("AMAZON.COM SERVICES, L.L.C."), "amazon com services")
        self.assertEqual(normalize("The Goldman Sachs & Co. LLC"), "goldman sachs")
        self.assertEqual(normalize("Bloomberg L.P."), "bloomberg")

    def test_exact_and_prefix_matches(self):
        self.assertEqual(self.index.lookup("Google"), (10, "GOOGLE LLC", 1))
        self.assertEqual(self.index.lookup("Bloomberg"), (5, "BLOOMBERG L.P.", 1))
        self.assertEqual(self.index.lookup("Amazon"), (180, "AMAZON.COM SERVICES LLC", 2))
        self.assertEqual(self.index.lookup("AWS")[0], 30)

    def test_short_names_and_dba(self):
        self.assertEqual(self.index.lookup("EY")[0], 9)
        self.assertIsNone(self.index.lookup("E"))
        self.assertEqual(self.index.lookup("Rocket Labs")[0], 2)
        self.assertIsNone(self.index.lookup("Unknown Startup"))

    def test_years(self):
        self.assertEqual(self.index.describe(), "USCIS H-1B approvals FY2022-FY2023")

    def test_utf16_tab_separated_export(self):
        text = ("Fiscal Year\tEmployer (Petitioner) Name\tNew Employment Approval\tContinuation Approval\n"
                "2026\tACME INC\t1,200\t30\n")
        rows = read_export(b"\xff\xfe" + text.encode("utf-16-le"))
        self.assertEqual(rows, [(2026, "ACME INC", 1230)])

    def test_not_an_export(self):
        with self.assertRaises(ValueError):
            read_export(b"name,value\nx,1\n")


def listing(company="Acme", title="Software Engineer Intern", url="https://boards.greenhouse.io/acme/jobs/1",
            posted=date(2026, 11, 18), source="Simplify", sponsorship="", locations=("Austin, TX",)):
    return Listing(company=company, title=title, locations=list(locations), url=url, posted=posted, source=source,
                   sponsorship=sponsorship)


class PipelineTest(unittest.TestCase):
    today = date(2026, 11, 20)

    def test_keep_reasons(self):
        self.assertIsNone(keep(listing(), self.today, 14, set()))
        self.assertIn("sponsorship", keep(listing(sponsorship="no-sponsorship"), self.today, 14, set()))
        self.assertIn("exclusion", keep(listing(), self.today, 14, {"acme"}))
        self.assertIn("US", keep(listing(locations=["Toronto, ON"]), self.today, 14, set()))
        self.assertIn("tech", keep(listing(title="Marketing Intern"), self.today, 14, set()))
        self.assertIn("days", keep(listing(posted=date(2026, 10, 1)), self.today, 14, set()))
        self.assertIsNone(keep(listing(posted=None), self.today, 14, set()))

    def test_merge_by_title_and_by_link(self):
        rows = [
            listing(source="Simplify", posted=date(2026, 11, 18)),
            listing(source="vansh", url="https://go.vansh.nyc/x", posted=date(2026, 11, 17),
                    sponsorship="offers"),
            # Different wording, same posting link: still one role.
            listing(title="SWE Intern - Summer 2027", source="Speedy",
                    url="https://acme.com/careers?gh_jid=1"),
            listing(title="Data Intern", url="https://boards.greenhouse.io/acme/jobs/2"),
        ]
        roles = merge(rows, {"https://go.vansh.nyc/x": "https://boards.greenhouse.io/acme/jobs/1"})
        self.assertEqual(len(roles), 2)
        self.assertEqual(roles[0].sources, {"Simplify", "vansh", "Speedy"})
        self.assertEqual(roles[0].posted, date(2026, 11, 17))
        self.assertEqual(roles[0].sponsorship, {"offers"})

    def test_compare_with_applied(self):
        roles = merge([listing(), listing(title="Data Intern", url="https://boards.greenhouse.io/acme/jobs/2"),
                       listing(company="Beta", title="ML Intern", url="https://jobs.lever.co/beta/x")], {})
        index = AppliedIndex([("Acme Inc.", "Platform Intern", "https://boards.greenhouse.io/acme/jobs/1")])
        shortlist, hidden = compare_with_applied(roles, index, max_per_company=2)
        self.assertEqual([r.title for r in shortlist], ["Data Intern", "ML Intern"])
        self.assertEqual(hidden["already applied (same posting)"], 1)
        self.assertEqual(hidden["  of which caught only by the job link"], 1)
        self.assertEqual(shortlist[0].applied_at_company, 1)

    def test_add_h1b_and_minimum(self):
        index = H1BIndex(read_export(ARCHIVE_CSV))
        roles = [Role(company="Google", title="SWE"), Role(company="Tiny Startup", title="SWE")]
        self.assertEqual([r.h1b for r in add_h1b(roles, index)], [10, None])
        self.assertEqual([r.company for r in add_h1b(roles, index, minimum=5)], ["Google"])
        fresh = [Role(company="Google", title="SWE"), Role(company="Tiny Startup", title="SWE")]
        self.assertEqual([r.h1b for r in add_h1b(fresh, None, minimum=5)], [None, None])

    def test_sort_order(self):
        old = Role(company="A", title="x", posted=date(2026, 11, 1))
        new = Role(company="B", title="x", posted=date(2026, 11, 19))
        applied = Role(company="C", title="x", posted=date(2026, 11, 20), applied_at_company=1)
        step = Role(company="D", title="x", posted=date(2026, 11, 2), underclass=True)
        undated = Role(company="E", title="x")
        order = sorted([undated, applied, old, new, step], key=sort_key)
        self.assertEqual([r.company for r in order], ["D", "B", "A", "E", "C"])


class ConfigTest(unittest.TestCase):
    def test_config_file_and_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text('[search]\ndays = 7\n[applied]\npath = "apps.xlsx"\nfirst_data_row = 7\n'
                            '[filters]\ngraduation_window = ["2028-12", "2030-05"]\nexclude_files = ["mine.txt"]\n',
                            encoding="utf-8")
            values = load_config(path)
            self.assertEqual(values["applied"], Path(tmp).resolve() / "apps.xlsx")
            self.assertEqual(values["grad_window"], ((2028, 12), (2030, 5)))
            settings = build_settings(path, {"days": 3, "year": None})
            self.assertEqual((settings.days, settings.year, settings.applied_first_data_row), (3, 2027, 7))
            self.assertEqual(settings.exclusion_paths()[-1].name, "mine.txt")

    def test_unknown_key_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text("[search]\ndayz = 7\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
