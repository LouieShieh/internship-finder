import unittest
from datetime import date

from internship_finder.sources import parse_automated, parse_simplify, parse_speedyapply, parse_vansh

TODAY = date(2026, 11, 20)


def item(**fields):
    base = {"active": True, "is_visible": True, "company_name": "Acme", "title": "Software Engineer Intern",
            "locations": ["Austin, TX"], "url": "https://example.com/job/1", "date_posted": 1795000000,
            "sponsorship": "Other"}
    base.update(fields)
    return base


class SimplifyTest(unittest.TestCase):
    def test_keeps_open_bachelor_roles_for_the_year(self):
        items = [
            item(terms=["Summer 2027"], degrees=["Bachelor's"]),
            item(terms=["Summer 2027"], degrees=[]),
            item(terms=["Summer 2026"]),
            item(terms=["Summer 2027"], degrees=["PhD"]),
            item(terms=["Summer 2027"], category="Hardware"),
            item(terms=["Summer 2027"], active=False),
        ]
        rows = parse_simplify(items, 2027)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].source, "Simplify")
        self.assertIsInstance(rows[0].posted, date)

    def test_sponsorship_markers(self):
        rows = parse_simplify([item(terms=["Summer 2027"], sponsorship="Does Not Offer Sponsorship"),
                               item(terms=["Summer 2027"], sponsorship="Offers Sponsorship"),
                               item(terms=["Summer 2027"], sponsorship="Other")], 2027)
        self.assertEqual([r.sponsorship for r in rows], ["no-sponsorship", "offers", ""])


class VanshTest(unittest.TestCase):
    def test_summer_only(self):
        rows = parse_vansh([item(season="Summer"), item(season="Fall"),
                            item(season="Summer", sponsorship="U.S. Citizenship is Required")], 2027)
        self.assertEqual([r.sponsorship for r in rows], ["", "citizens-only"])


class SpeedyApplyTest(unittest.TestCase):
    README = "\n".join([
        "| Company | Position | Location | Salary | Posting | Age |",
        "|---|---|---|---|---|---|",
        '| <a href="https://www.airbnb.com/"><strong>Airbnb</strong></a> | Software Engineering Intern | '
        'San Francisco, CA | $49/hr | <a href="https://careers.airbnb.com/positions/1?gh_jid=1"><img/></a> | 2d |',
        '| <a href="https://acme.com"><strong>Acme</strong></a> | Data Intern | Remote in US | '
        '<a href="https://acme.com/jobs/9"><img/></a> | 1mo |',
        "Not a table row",
    ])

    def test_six_and_five_column_tables(self):
        airbnb, acme = parse_speedyapply(self.README, TODAY)
        self.assertEqual((airbnb.company, airbnb.salary, airbnb.posted), ("Airbnb", "$49/hr", date(2026, 11, 18)))
        self.assertEqual(airbnb.url, "https://careers.airbnb.com/positions/1?gh_jid=1")
        self.assertEqual((acme.company, acme.salary, acme.posted), ("Acme", "", date(2026, 10, 21)))
        self.assertEqual(acme.locations, ["Remote in US"])


class AutomatedTest(unittest.TestCase):
    def test_season_dates_and_sponsorship(self):
        data = {"jobs": [
            {"company": "Acme", "title": "SWE Intern", "season": "Summer 2027", "location": "Austin, TX USA",
             "url": "u1", "posted_at": "2026-11-15T00:00:00Z", "sponsorship": "citizens-only"},
            {"company": "Acme", "title": "SWE Intern", "season": "Fall 2026", "seasons": ["Fall 2026", "Summer 2027"],
             "location": "Austin, TX USA", "url": "u2", "posted_at": None, "first_seen_at": "2026-11-16T01:14:46Z",
             "sponsorship": "unknown"},
            {"company": "Acme", "title": "SWE Intern", "season": "Not stated", "url": "u3"},
        ]}
        rows = parse_automated(data, 2027)
        self.assertEqual([r.url for r in rows], ["u1", "u2"])
        self.assertEqual(rows[0].sponsorship, "citizens-only")
        self.assertEqual(rows[1].sponsorship, "")
        self.assertEqual(rows[1].posted, date(2026, 11, 16))


if __name__ == "__main__":
    unittest.main()
