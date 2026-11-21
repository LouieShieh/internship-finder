"""Readers for the public internship lists. Each turns one list into Listing records.

The parse_* functions take already-downloaded data so they can be tested without the network; load_source()
downloads and parses one list by name.
"""

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .net import fetch

RAW = "https://raw.githubusercontent.com"
# {year} is the internship summer. The automated list keeps one repository per cycle, so its URL changes yearly.
SOURCE_URLS = {
    "simplify": RAW + "/SimplifyJobs/Summer{year}-Internships/HEAD/.github/scripts/listings.json",
    "vansh": RAW + "/vanshb03/Summer{year}-Internships/HEAD/.github/scripts/listings.json",
    "speedyapply": RAW + "/speedyapply/{year}-SWE-College-Jobs/HEAD/README.md",
    "automated": RAW + "/zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships/HEAD/docs/api/jobs.json",
}
SOURCE_LABELS = {"simplify": "Simplify", "vansh": "vansh", "speedyapply": "Speedy", "automated": "Automated"}

# The sponsorship markers each list uses, mapped to one vocabulary.
SPONSORSHIP = {
    "Offers Sponsorship": "offers",
    "Does Not Offer Sponsorship": "no-sponsorship",
    "U.S. Citizenship is Required": "citizens-only",
    "offers": "offers",
    "no-sponsorship": "no-sponsorship",
    "citizens-only": "citizens-only",
}
BLOCKING = {"no-sponsorship", "citizens-only"}


@dataclass
class Listing:
    company: str
    title: str
    locations: list
    url: str
    posted: date | None
    source: str
    sponsorship: str = ""  # "offers", "no-sponsorship", "citizens-only" or "" (the list doesn't say)
    salary: str = ""


def _epoch_date(value):
    try:
        return date.fromtimestamp(int(value))
    except (TypeError, ValueError, OSError):
        return None


def parse_simplify(items, year):
    """SimplifyJobs listings.json: open roles for Summer <year> that accept bachelor's students."""
    rows = []
    for item in items:
        if not (item.get("active") and item.get("is_visible")):
            continue
        if f"Summer {year}" not in (item.get("terms") or []):
            continue
        degrees = item.get("degrees") or []
        if degrees and "Bachelor's" not in degrees:
            continue
        if item.get("category") in ("Hardware", "Product"):
            continue
        rows.append(Listing(
            company=item["company_name"], title=item["title"], locations=item.get("locations") or [],
            url=item.get("url", ""), posted=_epoch_date(item.get("date_posted")), source="Simplify",
            sponsorship=SPONSORSHIP.get(item.get("sponsorship", ""), ""),
        ))
    return rows


def parse_vansh(items, year):
    """vanshb03 listings.json: the repository is per year, so only the season is checked."""
    rows = []
    for item in items:
        if not (item.get("active") and item.get("is_visible")):
            continue
        if item.get("season") != "Summer":
            continue
        rows.append(Listing(
            company=item["company_name"], title=item["title"], locations=item.get("locations") or [],
            url=item.get("url", ""), posted=_epoch_date(item.get("date_posted")), source="vansh",
            sponsorship=SPONSORSHIP.get(item.get("sponsorship", ""), ""),
        ))
    return rows


def parse_speedyapply(markdown, today):
    """speedyapply README tables: | Company | Position | Location | [Salary] | Posting | Age |"""
    rows = []
    for line in markdown.splitlines():
        if not line.startswith("| <a"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        company = re.sub(r"<[^>]+>", "", cells[0]).strip()
        link = re.search(r'href="([^"]+)"', cells[-2])
        age = re.match(r"(\d+)\s*(d|mo)", cells[-1])
        days = int(age.group(1)) * (30 if age.group(2) == "mo" else 1) if age else 0
        rows.append(Listing(
            company=company, title=re.sub(r"<[^>]+>", "", cells[1]).strip(), locations=[cells[2]],
            url=link.group(1) if link else "", posted=today - timedelta(days=days), source="Speedy",
            salary=cells[3] if len(cells) == 6 else "",
        ))
    return rows


def parse_automated(data, year):
    """zshah101's automated list (docs/api/jobs.json). It reads employer job boards directly and classifies
    sponsorship from the posting text, so it finds roles the hand-curated lists haven't added yet."""
    rows = []
    for item in data.get("jobs", []):
        seasons = item.get("seasons") or [item.get("season")]
        if f"Summer {year}" not in seasons:
            continue
        posted = item.get("posted_at") or item.get("first_seen_at") or ""
        try:
            posted = datetime.fromisoformat(posted.replace("Z", "+00:00")).date()
        except ValueError:
            posted = None
        rows.append(Listing(
            company=item.get("company", ""), title=item.get("title", ""), locations=[item.get("location") or ""],
            url=item.get("url", ""), posted=posted, source="Automated",
            sponsorship=SPONSORSHIP.get(item.get("sponsorship", ""), ""),
            salary=str(item.get("salary") or ""),
        ))
    return rows


def load_source(name, year, today, url=None):
    """Download one list by name ('simplify', 'vansh', 'speedyapply', 'automated') and parse it."""
    url = url or SOURCE_URLS[name].format(year=year)
    if name == "speedyapply":
        return parse_speedyapply(fetch(url), today)
    data = json.loads(fetch(url))
    if name == "simplify":
        return parse_simplify(data, year)
    if name == "vansh":
        return parse_vansh(data, year)
    if name == "automated":
        return parse_automated(data, year)
    raise ValueError(f"unknown source: {name}")
