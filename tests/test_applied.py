import tempfile
import unittest
import zipfile
from pathlib import Path

from internship_finder.applied import AppliedIndex, column_index, find_columns, read_applied

WORKBOOK = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Notes" sheetId="1" r:id="rId1"/><sheet name="Job Tracker" sheetId="2" r:id="rId2"/></sheets>
</workbook>"""
RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="worksheet"/>
  <Relationship Id="rId2" Target="worksheets/sheet2.xml" Type="worksheet"/>
</Relationships>"""
SHARED = """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>Position Format</t></si><si><t>Organization</t></si><si><t>Job Title</t></si><si><t>Posting URL</t></si>
  <si><t>Example Co</t></si><si><t>Example Intern</t></si><si><t>Acme</t></si><si><t>SWE Intern</t></si>
</sst>"""


def sheet(rows):
    cells = "".join(f'<row r="{n}">' + "".join(cell for cell in row) + "</row>" for n, row in rows)
    return ('<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/'
            f'spreadsheetml/2006/main"><sheetData>{cells}</sheetData></worksheet>')


def s(ref, index):
    return f'<c r="{ref}" t="s"><v>{index}</v></c>'


def inline(ref, text):
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def make_xlsx(path):
    tracker = sheet([
        (1, [inline("A1", "My applications")]),
        (3, [s("B3", 0), s("D3", 1), s("E3", 2), s("F3", 3)]),
        (4, [s("D4", 4), s("E4", 5)]),  # an example row the template ships with
        (5, [s("D5", 6), s("E5", 7), inline("F5", "https://boards.greenhouse.io/acme/jobs/42")]),
        (6, [inline("D6", "Beta"), inline("E6", "Data Intern")]),
    ])
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("xl/workbook.xml", WORKBOOK)
        book.writestr("xl/_rels/workbook.xml.rels", RELS)
        book.writestr("xl/sharedStrings.xml", SHARED)
        book.writestr("xl/worksheets/sheet1.xml", sheet([(1, [inline("A1", "nothing here")])]))
        book.writestr("xl/worksheets/sheet2.xml", tracker)


class ReadAppliedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_column_index(self):
        self.assertEqual([column_index(c) for c in ("A", "D", "Z", "AA")], [0, 3, 25, 26])

    def test_csv_with_header_detection(self):
        path = self.dir / "applied.csv"
        path.write_text("Company,Role,Link,Status\nAcme,SWE Intern,https://x.com/job/12345,Applied\n,,,\n",
                        encoding="utf-8")
        self.assertEqual(read_applied(path), [("Acme", "SWE Intern", "https://x.com/job/12345")])

    def test_title_beats_position(self):
        rows = [(1, {0: "Position Format", 1: "Company", 2: "Job Title"})]
        self.assertEqual(find_columns(rows), (1, {"company": 1, "title": 2, "url": None}))

    def test_xlsx_sheet_header_and_first_row(self):
        path = self.dir / "tracker.xlsx"
        make_xlsx(path)
        self.assertEqual(read_applied(path, sheet="tracker", first_data_row=5), [
            ("Acme", "SWE Intern", "https://boards.greenhouse.io/acme/jobs/42"), ("Beta", "Data Intern", "")])
        self.assertEqual(len(read_applied(path, sheet="tracker")), 3)  # includes the example row
        with self.assertRaises(ValueError):
            read_applied(path, sheet="missing")

    def test_explicit_columns(self):
        path = self.dir / "tracker.xlsx"
        make_xlsx(path)
        rows = read_applied(path, sheet="Tracker", first_data_row=5,
                            columns={"company": "D", "title": "E", "url": "F"})
        self.assertEqual(rows[0][0], "Acme")


class AppliedIndexTest(unittest.TestCase):
    def setUp(self):
        self.index = AppliedIndex([
            ("Modernizing Medicine", "Software Engineer Intern",
             "https://modmed.wd1.myworkdayjobs.com/careers/job/FL/SWE-Intern_R100"),
            ("Acme", "Data Science Intern", "https://boards.greenhouse.io/acme/jobs/42"),
            ("Acme", "Security Intern", ""),
        ])

    def test_same_posting(self):
        self.assertEqual(self.index.check("ACME Corp", "Anything", ["https://boards.greenhouse.io/acme/jobs/42"]),
                         (2, "same posting"))

    def test_similar_title(self):
        self.assertEqual(self.index.check("Acme", "Data Science Intern - Summer 2027", []), (2, "similar title"))

    def test_other_role_at_company(self):
        self.assertEqual(self.index.check("Acme", "Backend Engineer Intern", []), (2, ""))

    def test_same_job_site_account_under_another_name(self):
        url = "https://modmed.wd1.myworkdayjobs.com/careers/job/FL/Data-Intern_R200"
        self.assertEqual(self.index.check("ModMed", "Data Engineering Intern", [url]), (1, ""))
        self.assertEqual(self.index.check("ModMed", "Data Engineering Intern", []), (0, ""))

    def test_short_names_need_an_exact_match(self):
        index = AppliedIndex([("EY", "Tech Intern", "")])
        self.assertEqual(index.check("Eyeo", "Tech Intern", []), (0, ""))
        self.assertEqual(index.check("EY", "Tech Intern", []), (1, "similar title"))


if __name__ == "__main__":
    unittest.main()
