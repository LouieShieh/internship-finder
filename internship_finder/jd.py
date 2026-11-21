"""Read a job description and flag wording that matters to F-1 students.

Pages are read through the job sites' public posting APIs where one exists, because most career pages are
JavaScript shells with no text in the HTML. The check is a keyword search: no flag is not proof that a role
accepts F-1 students, so always read the posting before applying.
"""

import html
import json
import re
from dataclasses import dataclass, field

from .net import fetch, final_url

TIMEOUT = 20

# Signs the text is a real posting rather than an empty page shell. Avoid words such as "skills" or "Job
# Description" that also appear as JSON keys or menu labels in Eightfold/Workday shells.
JD_WORDS = re.compile(r"qualification|responsibilit|requirement|you will|you['’]ll|you bring|about the role", re.I)

# Seniority words after "senior"/"junior" that mean a job level, not a class year ("senior engineer").
NOT_CLASS_YEAR = (r"(?!\s+(?:leader|engineer|manag|staff|exec|develop|direct|vice|team|member|scien|analy|associ|"
                  r"level|software|data|product|consult|partner|architect|technical|research))")

# (label, pattern, ignore). A match is skipped when `ignore` overlaps it: application-form questions and
# benefits fine print mention the same words without stating a rule.
CHECKS = [
    ("visa", re.compile(
        r"\b(not|unable to|cannot|can't|won't|no)\b[^.]{0,60}\bsponsor|"
        r"without (the )?(need for |requiring |company |employer |any )?[^.]{0,30}sponsorship|"
        r"sponsorship[^.]{0,40}(not (be )?(available|provided|offered))|"
        r"\b(f-?1|opt|cpt)\b[^.]{0,40}(not (be )?(eligible|accepted|considered)|ineligible)|"
        r"authori[sz]ed to work.{0,60}?\bnow (and|or) in the future|"  # ".{0,60}" because "U.S." contains dots
        r"unrestricted (work |employment )?authori[sz]ation",
        re.I),
     # "Will you now or in the future require sponsorship? Yes / No" is a form question, not a rule.
     re.compile(r"\b(will|do|would|are) you\b[^.?]{0,80}sponsor", re.I)),
    ("citizenship/clearance", re.compile(
        r"u\.?s\.? citizen(ship)? (is )?required|must be (a )?u\.?s\.? citizen|u\.?s\.? citizens? only|"
        r"(active|obtain|eligible for)[^.]{0,30}security clearance",
        re.I), None),
    ("U.S. person/export control", re.compile(r"u\.?s\.? persons?\b|\bitar\b|export licen[cs]e", re.I), None),
    ("class year", re.compile(
        r"\b(junior|senior)s? (or|and|/) (junior|senior)s? (standing|status|year)|"
        r"\b(junior|senior) (standing|status)\b|"
        r"\b(rising|current) (junior|senior)s?\b" + NOT_CLASS_YEAR + r"|"
        r"\b(must|should) be (a )?(junior|senior)\b" + NOT_CLASS_YEAR + r"|"
        r"\b(third|fourth|final|penultimate)[- ]year (student|undergrad\w*)|"
        r"(entering|going into) (their|your|the) (junior|senior|third|fourth|final) year",
        re.I), None),
    # F-1 students can't work off campus during the school year without separate authorization.
    ("part-time/term-time", re.compile(
        r"part[- ]time|year[- ]round|during the (academic|school) year|\b[12]\d\s*hours (per|a|each) week",
        re.I),
     # "Have you worked here full-time / part-time?", "part-time employment is a plus", benefits fine print.
     re.compile(r"full[- ]time\s*[/,]\s*part[- ]time|part[- ]time\s+(employ\w*|and temporary|jobs?\b)", re.I)),
]

GRAD = re.compile(r"(graduat\w*|class of|degree completion)[^.;]{0,120}", re.I)
GRAD_YEAR = re.compile(r"\b(20[2-3]\d)\b")
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
          "nov": 11, "dec": 12, "spring": 5, "summer": 8, "fall": 12, "autumn": 12, "winter": 12}
MONTH_YEAR = re.compile(r"\b(" + "|".join(MONTHS) + r")\w*\.?,?\s*(20[2-3]\d)\b", re.I)
OR_LATER = re.compile(r"(20[2-3]\d)\s*(or|and)\s*(later|after|beyond)", re.I)


@dataclass
class JDCheck:
    readable: bool
    flags: list = field(default_factory=list)       # [(label, matched words)]
    grad_years: list = field(default_factory=list)  # years mentioned near "graduat..." / "class of"
    grad_mismatch: bool = False                     # those years don't include your graduation date

    def summary(self):
        if not self.readable:
            return "could not read the posting; open it yourself"
        parts = [f"⚠ {label}: {words}" for label, words in self.flags] or ["no restriction wording found"]
        if self.grad_years:
            mark = "⚠ " if self.grad_mismatch else ""
            parts.append(f"{mark}graduation years mentioned: {', '.join(map(str, self.grad_years))}")
        return " | ".join(parts)


def plain_text(page):
    page = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))


def graduation_mismatch(segments, years, window):
    """True if the graduation dates a posting names don't include yours.

    window is ((earliest_year, earliest_month), (latest_year, latest_month)) for your possible graduation dates.
    Flags postings whose years all fall outside the window, and postings whose range ends earlier in your
    earliest year than your earliest month ("graduating by June 2028" when you graduate December 2028).
    """
    if not window or not years:
        return False
    (first_year, first_month), (last_year, _) = window
    if not any(first_year <= year <= last_year for year in years):
        return True
    if max(years) == first_year and not any(int(y) == first_year for y, *_ in OR_LATER.findall(segments)):
        months = [MONTHS[m.lower()] for m, y in MONTH_YEAR.findall(segments) if int(y) == first_year]
        if months and max(months) < first_month:
            return True
    return False


def scan(text, window=None, from_api=False):
    """Search a job description for restrictions. Returns a JDCheck.

    from_api means the text came from a job site's posting API, so it is the posting even if it is short;
    text scraped from a page only counts when it reads like a posting (JD_WORDS).
    """
    text = html.unescape(text or "").replace("\xa0", " ")
    if not (JD_WORDS.search(text) or (from_api and len(text.strip()) >= 200)):
        return JDCheck(readable=False)
    result = JDCheck(readable=True)
    for label, pattern, ignore in CHECKS:
        for match in pattern.finditer(text):
            # Skip the match only if an ignore phrase overlaps it, so a real rule next to a form question counts.
            start = max(0, match.start() - 80)
            ignored = ignore and any(start + m.start() < match.end() and start + m.end() > match.start()
                                     for m in ignore.finditer(text[start:match.end() + 40]))
            if not ignored:
                result.flags.append((label, match.group(0)[:60]))
                break
    segments = " ".join(m.group(0) for m in GRAD.finditer(text))
    result.grad_years = sorted({int(year) for year in GRAD_YEAR.findall(segments)})
    result.grad_mismatch = graduation_mismatch(segments, result.grad_years, window)
    return result


# --- Reading the posting text --------------------------------------------------------------------------------

def _workday(match):
    host, site, path = match.groups()
    api = f"https://{host}/wday/cxs/{host.split('.')[0]}/{site}/job/{path}"
    return plain_text(json.loads(fetch(api, TIMEOUT))["jobPostingInfo"]["jobDescription"])


def _ashby(match):
    board = json.loads(fetch(f"https://api.ashbyhq.com/posting-api/job-board/{match.group(1)}", TIMEOUT))
    job = next((j for j in board.get("jobs", []) if j.get("id") == match.group(2)), None)
    return job.get("descriptionPlain", "") if job else ""


def _lever(match):
    data = json.loads(fetch(f"https://api.lever.co/v0/postings/{match.group(1)}/{match.group(2)}", TIMEOUT))
    lists = " ".join(f"{item.get('text', '')} {item.get('content', '')}" for item in data.get("lists", []))
    return plain_text(f"{data.get('descriptionPlain', '')} {lists} {data.get('additionalPlain', '')}")


def _greenhouse(match):
    api = f"https://boards-api.greenhouse.io/v1/boards/{match.group(1)}/jobs/{match.group(2)}"
    return plain_text(html.unescape(json.loads(fetch(api, TIMEOUT)).get("content", "")))


def _smartrecruiters(match):
    api = f"https://api.smartrecruiters.com/v1/companies/{match.group(1)}/postings/{match.group(2)}"
    sections = json.loads(fetch(api, TIMEOUT)).get("jobAd", {}).get("sections", {})
    return plain_text(" ".join(str(part.get("text", "")) for part in sections.values() if isinstance(part, dict)))


def _oracle(match):
    host, site, job_id = match.groups()
    api = (f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
           f"?expand=all&onlyData=true&finder=ById;Id=%22{job_id}%22,siteNumber={site}")
    item = json.loads(fetch(api, TIMEOUT))["items"][0]
    fields = ("ExternalDescriptionStr", "ExternalQualificationsStr", "ExternalResponsibilitiesStr")
    return plain_text(" ".join(str(item.get(name) or "") for name in fields))


def _eightfold(match):
    host, tenant, job_id = match.groups()
    domain = "netflix.com" if "netflix" in host else "qualcomm.com" if "qualcomm" in host else f"{tenant}.com"
    data = json.loads(fetch(f"https://{host}/api/apply/v2/jobs/{job_id}?domain={domain}", TIMEOUT))
    return plain_text(data.get("job_description", ""))


def _ukg(match):
    page = fetch(match.group(0), TIMEOUT)
    start = page.index("CandidateOpportunityDetail(") + len("CandidateOpportunityDetail(")
    data, _ = json.JSONDecoder().raw_decode(page[start:])
    return plain_text(str(data.get("Description") or ""))


def _bamboohr(match):
    data = json.loads(fetch(f"https://{match.group(1)}.bamboohr.com/careers/{match.group(2)}/detail", TIMEOUT))
    return plain_text(str(data.get("result", {}).get("jobOpening", {}).get("description") or ""))


def _icims(match):
    # The normal iCIMS page loads the posting in an iframe; in_iframe=1 serves the posting itself.
    return plain_text(fetch(match.group(1) + "/job?in_iframe=1", TIMEOUT))


READERS = [
    (re.compile(r"https://([^/]+\.myworkdayjobs\.com)/(?:[a-z]{2}-[A-Z]{2}/)?([^/]+)/job/(.+?)(?:\?|$)"), _workday),
    (re.compile(r"https://jobs\.ashbyhq\.com/([^/]+)/([0-9a-f-]{36})"), _ashby),
    (re.compile(r"https://jobs\.lever\.co/([^/]+)/([0-9a-f-]{36})"), _lever),
    (re.compile(r"greenhouse\.io/([^/]+)/jobs/(\d+)"), _greenhouse),
    (re.compile(r"//(?:[a-z]+\.)?(?:weare)?([a-z]+)\.com/.*gh_jid=(\d+)"), _greenhouse),
    (re.compile(r"https://jobs\.smartrecruiters\.com/([^/]+)/(\d+)"), _smartrecruiters),
    (re.compile(r"https://([^/]+\.oraclecloud\.com|enterpriseplatform\.[^/]+)/hcmUI/CandidateExperience/[^/]+/"
                r"sites/([^/]+)/job/(\d+)"), _oracle),
    (re.compile(r"https://(explore\.jobs\.netflix\.net|careers\.qualcomm\.com|([a-z0-9-]+)\.eightfold\.ai)"
                r"/careers(?:/job/|\?.*?\bpid=)(\d+)"), _eightfold),
    (re.compile(r"(https://[^/]+\.icims\.com/jobs/\d+)"), _icims),
    (re.compile(r"https://recruiting\d*\.ultipro\.com/[^/]+/JobBoard/[^/]+/OpportunityDetail\?opportunityId=[0-9a-f-]+",
                re.I), _ukg),
    (re.compile(r"https://([a-z0-9-]+)\.bamboohr\.com/careers/(\d+)"), _bamboohr),
]


def job_description(url):
    """Return (text, from_api) for a job link; text is "" if the posting can't be read."""
    url = final_url(url)
    for pattern, reader in READERS:
        match = pattern.search(url)
        if match:
            try:
                text = reader(match)
                if text.strip():
                    return text, True
            except Exception:  # an API that changed shape or refused us; fall back to the page itself
                pass
            break
    try:
        return plain_text(fetch(url, TIMEOUT)), False
    except Exception:
        return "", False


def check(url, window=None):
    text, from_api = job_description(url)
    return scan(text, window, from_api)
