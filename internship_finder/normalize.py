"""Name, title and location normalization shared by every step."""

import re

US_STATE = re.compile(r",\s*[A-Z]{2}\b|\bUSA\b|United States|Remote in US|\bUS\b")
NON_US = re.compile(r"\b(ON|BC|QC|AB|MB|NS|NB|SK|NL|PE|UK)\b|canada|united kingdom|england|india|germany|ireland|"
                    r"poland", re.I)
LEGAL_WORDS = re.compile(r"\b(inc|llc|llp|ltd|corp|corporation|co|company|the|group|technologies|holdings)\b")
# Words that say nothing about which job a title is, so they are ignored when comparing titles.
NOISE = {"intern", "internship", "summer", "the", "and", "of", "for", "us", "usa", "-", "–", "program", "university",
         "students", "student", "opportunities", "undergraduate", "undergrad"}
YEAR = re.compile(r"^20\d\d$")


def company_key(name):
    """'The Walt Disney Company (Parks)' -> 'waltdisney'. Used to compare company names across lists."""
    name = re.sub(r"\(.*?\)", " ", (name or "").lower())
    return re.sub(r"[^a-z0-9]+", "", LEGAL_WORDS.sub(" ", name))


def title_tokens(title, locations=()):
    """The words that identify a job title, minus filler words, years and the role's own place names."""
    place_words = set(re.findall(r"[a-z0-9]+", " ".join(locations).lower()))
    words = re.findall(r"[a-z0-9+#]+", (title or "").lower())
    return {w for w in words if w not in NOISE and w not in place_words and not YEAR.match(w)}


def similarity(a, b):
    """Jaccard similarity of two token sets (0 to 1)."""
    return len(a & b) / max(1, len(a | b))


def is_us(locations):
    """True if any location looks like a US place (state abbreviation, 'USA', 'Remote in US')."""
    return any(US_STATE.search(loc) and not NON_US.search(loc) for loc in locations)
