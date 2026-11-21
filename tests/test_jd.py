import json
import unittest
from unittest import mock

from internship_finder import jd
from internship_finder.jd import JDCheck, graduation_mismatch, plain_text, scan

BODY = "About the role: you will build services. Qualifications: Python. "
WINDOW = ((2028, 12), (2030, 5))  # graduating between December 2028 and May 2030


def labels(text):
    return [label for label, _ in scan(BODY + text).flags]


class ScanTest(unittest.TestCase):
    def test_page_without_posting_text_is_unreadable(self):
        result = scan("<div id='root'></div> Loading...")
        self.assertFalse(result.readable)
        self.assertIn("could not read", result.summary())

    def test_no_restrictions(self):
        result = scan(BODY)
        self.assertEqual(result.flags, [])
        self.assertEqual(result.summary(), "no restriction wording found")

    def test_visa_wording(self):
        self.assertEqual(labels("We are unable to sponsor work visas for this role."), ["visa"])
        self.assertEqual(labels("Candidates must be authorized to work in the U.S. now and in the future."), ["visa"])
        self.assertEqual(labels("F-1 students on OPT are not eligible."), ["visa"])
        self.assertEqual(labels("Requires unrestricted work authorization."), ["visa"])

    def test_form_question_is_not_a_rule(self):
        self.assertEqual(labels("Will you now or in the future require sponsorship? Yes No"), [])

    def test_rule_next_to_form_question_still_counts(self):
        text = "Will you require sponsorship? Yes No. Note that we will not sponsor visas for interns."
        self.assertEqual(labels(text), ["visa"])

    def test_citizenship_and_export_control(self):
        self.assertEqual(labels("Must be a U.S. citizen."), ["citizenship/clearance"])
        self.assertEqual(labels("Ability to obtain a security clearance."), ["citizenship/clearance"])
        self.assertEqual(labels("This role requires access to ITAR-controlled data."), ["U.S. person/export control"])

    def test_class_year(self):
        self.assertEqual(labels("Open to rising seniors only."), ["class year"])
        self.assertEqual(labels("Must have junior or senior standing."), ["class year"])
        self.assertEqual(labels("You will work with a senior engineer."), [])

    def test_part_time(self):
        self.assertEqual(labels("This is a part-time role, 20 hours per week."), ["part-time/term-time"])
        self.assertEqual(labels("Have you worked here full-time / part-time before?"), [])

    def test_html_entities_and_markup(self):
        self.assertEqual(plain_text("<p>We&nbsp;can&#39;t sponsor</p><script>x()</script>"), " We can't sponsor ")


class ReaderTest(unittest.TestCase):
    """Job-site readers, with the network replaced by canned responses."""

    def read(self, url, responses):
        def fake_fetch(address, timeout=60):
            for prefix, body in responses.items():
                if address.startswith(prefix):
                    return body
            raise OSError(f"unexpected request: {address}")

        with mock.patch.object(jd, "final_url", lambda u: u), mock.patch.object(jd, "fetch", fake_fetch):
            return jd.job_description(url)

    def test_short_posting_from_an_api_is_readable(self):
        text = "We build tools for chip design. " * 8
        self.assertFalse(scan(text).readable)
        self.assertTrue(scan(text, from_api=True).readable)

    def test_workday(self):
        url = "https://acme.wd1.myworkdayjobs.com/en-US/Careers/job/Austin/SWE-Intern_R1"
        api = "https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/Careers/job/Austin/SWE-Intern_R1"
        body = json.dumps({"jobPostingInfo": {"jobDescription": "<p>We cannot sponsor visas.</p>"}})
        self.assertEqual(self.read(url, {api: body}), (" We cannot sponsor visas. ", True))

    def test_ukg_page_with_embedded_json(self):
        url = "https://recruiting2.ultipro.com/ACME1/JobBoard/abc/OpportunityDetail?opportunityId=12ab-34cd"
        detail = json.dumps({"Title": "Intern", "Description": "<p>Must be a U.S. citizen.</p>"})
        page = f"<script>var o = new US.Opportunity.CandidateOpportunityDetail({detail});</script>"
        self.assertEqual(self.read(url, {url: page}), (" Must be a U.S. citizen. ", True))

    def test_bamboohr(self):
        body = json.dumps({"result": {"jobOpening": {"description": "<p>Part-time, 20 hours per week</p>"}}})
        result = self.read("https://acme.bamboohr.com/careers/29", {"https://acme.bamboohr.com/careers/29/detail": body})
        self.assertEqual(result, (" Part-time, 20 hours per week ", True))

    def test_unknown_site_falls_back_to_the_page(self):
        self.assertEqual(self.read("https://example.com/jobs/1", {"https://example.com": "<p>Hello</p>"}),
                         (" Hello ", False))

    def test_unreachable_page(self):
        self.assertEqual(self.read("https://example.com/jobs/1", {}), ("", False))


class GraduationTest(unittest.TestCase):
    def check(self, text, window=WINDOW):
        return scan(BODY + text, window)

    def test_years_are_listed(self):
        result = self.check("Expected graduation between December 2028 and May 2029.")
        self.assertEqual(result.grad_years, [2028, 2029])
        self.assertFalse(result.grad_mismatch)
        self.assertIn("graduation years mentioned: 2028, 2029", result.summary())

    def test_years_outside_window(self):
        self.assertTrue(self.check("Class of 2027 only.").grad_mismatch)

    def test_window_ending_before_your_month(self):
        self.assertTrue(self.check("Graduating between December 2027 and June 2028.").grad_mismatch)
        self.assertFalse(self.check("Graduating between May 2028 and December 2028.").grad_mismatch)
        self.assertFalse(self.check("Graduating in spring 2028 or later.").grad_mismatch)

    def test_no_window_means_no_warning(self):
        self.assertFalse(self.check("Class of 2027 only.", window=None).grad_mismatch)
        self.assertFalse(graduation_mismatch("", [], WINDOW))

    def test_summary_marks_mismatch(self):
        summary = JDCheck(readable=True, grad_years=[2027], grad_mismatch=True).summary()
        self.assertEqual(summary, "no restriction wording found | ⚠ graduation years mentioned: 2027")


if __name__ == "__main__":
    unittest.main()
