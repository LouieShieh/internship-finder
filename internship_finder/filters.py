"""Which roles to keep: tech titles, programs for first- and second-year students, and company exclusion lists."""

import re
from pathlib import Path

from .normalize import company_key

TECH = re.compile(
    r"software|developer|engineer|swe\b|machine learning|\bml\b|\bai\b|data|backend|back-end|frontend|front-end|"
    r"full.?stack|infrastructure|platform|security|cyber|devops|sre\b|reliability|cloud|mobile|ios|android|web|"
    r"quant(itative)? dev|systems|compiler|research",
    re.I,
)
NOT_TECH = re.compile(
    # Engineering fields and business roles that share words with tech titles.
    r"mechanical|electrical|hardware|civil|chemical|manufacturing|process engineer|quality engineer|sales|marketing|"
    r"account(ing|ant)|finance|audit|legal|recruit|\bhr\b|human resources|product manag|program manag|business|"
    r"design(er)?\b|ux\b|supply chain|operations|field|construction|biomedical|aerospace|structural|"
    r"test technician|technician|material|"
    # Roles for graduate students, co-ops, and programs that name an upper class year in the title.
    r"phd|master'?s|mba|graduate student|postdoc|co-?op|"
    r"junior intern|senior intern|rising (junior|senior)|penultimate|final.year",
    re.I,
)
UNDERCLASS = re.compile(
    r"explore|first play|ignite|discovery|freshm|sophomore|first.year|1st.year|underclass|\bstep\b|exploratory|"
    r"early insight|insight program|launch program|emerging talent",
    re.I,
)


def is_tech(title):
    return bool(TECH.search(title)) and not NOT_TECH.search(title)


def is_underclass_program(title):
    """Programs aimed at first- and second-year students (Google STEP, Microsoft Explore, ...)."""
    return bool(UNDERCLASS.search(title))


def load_exclusions(paths):
    """Company keys from one or more text files: one company per line, '#' starts a comment."""
    names = set()
    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            name = line.split("#", 1)[0].strip()
            if name:
                names.add(company_key(name))
    return names
