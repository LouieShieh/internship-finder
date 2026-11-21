"""The steps from raw list rows to a shortlist. Pure functions over in-memory data, so they can be tested offline."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from .filters import is_tech, is_underclass_program
from .links import SHORT_LINK, posting_keys
from .normalize import company_key, is_us, title_tokens
from .sources import BLOCKING


@dataclass
class Role:
    """One job after merging the lists that carry it."""
    company: str
    title: str
    locations: set = field(default_factory=set)
    urls: set = field(default_factory=set)
    posted: date | None = None
    sources: set = field(default_factory=set)
    sponsorship: set = field(default_factory=set)
    salary: str = ""
    applied_at_company: int = 0
    underclass: bool = False
    h1b: int | None = None
    h1b_employer: str = ""
    jd: str = ""

    @property
    def url(self):
        """The link to show: a direct job-site link if any list has one, else a short link."""
        direct = sorted(u for u in self.urls if u and not SHORT_LINK.search(u))
        return direct[0] if direct else min(self.urls, default="")


def keep(listing, today, days, excluded):
    """Return the reason a listing is dropped, or None to keep it."""
    if listing.sponsorship in BLOCKING:
        return "list says no sponsorship / citizens only"
    if company_key(listing.company) in excluded:
        return "company in exclusion list"
    if not is_us(listing.locations):
        return "not in the US"
    if not is_tech(listing.title):
        return "not a tech role for undergrads"
    if listing.posted and (today - listing.posted).days > days:
        return f"posted more than {days} days ago"
    return None


def merge(listings, links):
    """Combine rows that describe the same job: same company and title words, or the same posting link."""
    roles, by_name, by_posting = [], {}, {}
    for item in listings:
        url = links.get(item.url, item.url)
        name_key = (company_key(item.company), " ".join(sorted(title_tokens(item.title, item.locations))))
        posting, _ = posting_keys(url)
        role = by_name.get(name_key) or (by_posting.get(posting) if posting else None)
        if role is None:
            role = Role(company=item.company, title=item.title, posted=item.posted)
            roles.append(role)
        role.locations.update(loc for loc in item.locations if loc)
        role.urls.add(url)
        role.sources.add(item.source)
        if item.sponsorship:
            role.sponsorship.add(item.sponsorship)
        role.salary = role.salary or item.salary
        if item.posted and (role.posted is None or item.posted < role.posted):
            role.posted = item.posted
        by_name.setdefault(name_key, role)
        if posting:
            by_posting.setdefault(posting, role)
    return roles


def compare_with_applied(roles, index, max_per_company):
    """Split roles into (shortlist, hidden reasons). Sets applied_at_company and underclass on each role."""
    shortlist, hidden = [], Counter()
    for role in roles:
        count, status = index.check(role.company, role.title, role.urls)
        role.applied_at_company = count
        role.underclass = is_underclass_program(role.title)
        if not status and count < max_per_company:
            shortlist.append(role)
            continue
        hidden[f"already applied ({status})" if status else f"already {max_per_company}+ applications there"] += 1
        # Would the company name alone have caught it? If not, the job-site link did.
        name_count, name_status = index.check(role.company, role.title, ())
        if not name_status and name_count < max_per_company:
            hidden["  of which caught only by the job link"] += 1
    return shortlist, hidden


def add_h1b(roles, index, minimum=0):
    """Attach H-1B approval counts; with minimum > 0, drop roles below it (unmatched names count as 0).
    Without an index (data unavailable) nothing is attached or dropped."""
    if index is None:
        return list(roles)
    kept = []
    for role in roles:
        match = index.lookup(role.company)
        if match:
            role.h1b, name, others = match
            role.h1b_employer = name + (f" (+{others - 1} more)" if others > 1 else "")
        if minimum <= 0 or (role.h1b or 0) >= minimum:
            kept.append(role)
    return kept


def sort_key(role):
    """Underclass programs first, then companies you haven't applied to yet, then newest."""
    return (not role.underclass, role.applied_at_company > 0, -(role.posted or date.min).toordinal())
