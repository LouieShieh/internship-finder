"""H-1B sponsorship history from USCIS's public H-1B Employer Data Hub.

A JD tells you what a posting says; this tells you what the company has done: how many H-1B petitions USCIS
approved for it. Companies that have never sponsored are more likely to turn away F-1 interns, because they
don't plan to convert them. The match is by company name, so treat the number as a hint and check the
matched legal name in the output.

Data:
  - By default the archived per-year exports (FY2009-FY2023) are downloaded once and cached. FY2023 is a
    partial year.
  - Newer years (through FY2026) are only in the interactive hub: Crosstab view -> Download -> CSV. Pass the
    downloaded files with --h1b-csv. The parser looks for an "Employer" column and sums every "Approval" column,
    so both the archived format and the hub's crosstab export should work.
"""

import csv
import io
import re
import sys
from collections import defaultdict
from pathlib import Path

from .net import fetch_bytes

ARCHIVE_URL = "https://www.uscis.gov/sites/default/files/document/data/h1b_datahubexport-{year}.csv"
LEGAL_SUFFIX = {"inc", "incorporated", "llc", "llp", "lp", "ltd", "limited", "corp", "corporation", "co", "company",
                "plc", "pc", "pllc", "na", "us", "usa", "and"}
# List names whose legal name doesn't start with them.
ALIASES = {"ibm": "international business machines", "meta": "meta platforms", "aws": "amazon web services",
           "jpmorgan": "jpmorgan chase", "jp morgan": "jpmorgan chase", "jpmorgan chase": "jpmorgan chase",
           "google deepmind": "google", "deepmind": "google"}
MIN_PREFIX_LENGTH = 4  # shorter names ("EY", "CAI") only match exactly


def normalize(name):
    """'AMAZON.COM SERVICES, L.L.C.' -> 'amazon com services'; 'The Goldman Sachs & Co. LLC' -> 'goldman sachs'."""
    name = re.sub(r"\(.*?\)", " ", (name or "").lower()).replace("&", " and ")
    name = re.sub(r"[^a-z0-9]+", " ", name)
    # Join spelled-out abbreviations: "l l c" -> "llc", "u s" -> "us".
    name = re.sub(r"\b([a-z])\s(?=[a-z]\b)", r"\1", name)
    words = name.split()
    while words and words[-1] in LEGAL_SUFFIX:
        words.pop()
    if words and words[0] == "the":
        words.pop(0)
    return " ".join(words)


def read_export(data):
    """[(fiscal_year, employer, approvals)] from one Data Hub CSV export (bytes)."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = data.decode("utf-16")  # Tableau crosstab downloads are UTF-16 and tab-separated
    else:
        text = data.decode("utf-8-sig", errors="replace")
    first = text.split("\n", 1)[0]
    reader = csv.reader(io.StringIO(text), delimiter="\t" if first.count("\t") > first.count(",") else ",")
    header = [h.strip().lower() for h in next(reader, [])]
    employer = next((i for i, h in enumerate(header) if "employer" in h and "name" in h), None)
    if employer is None:
        employer = next((i for i, h in enumerate(header) if "employer" in h or "petitioner" in h), None)
    approvals = [i for i, h in enumerate(header) if "approv" in h]
    year = next((i for i, h in enumerate(header) if "fiscal" in h), None)
    if employer is None or not approvals:
        raise ValueError("not an H-1B Employer Data Hub export (no Employer / Approval columns)")
    rows = []
    for row in reader:
        if len(row) <= max(approvals + [employer]):
            continue
        count = 0
        for i in approvals:
            value = row[i].replace(",", "").strip()
            count += int(float(value)) if value else 0
        fiscal_year = row[year].strip() if year is not None else ""
        rows.append((int(fiscal_year) if fiscal_year.isdigit() else None, row[employer], count))
    return rows


class H1BIndex:
    def __init__(self, rows=()):
        self.approvals = defaultdict(int)    # normalized employer name -> approvals
        self.display = {}                    # normalized name -> a legal name as USCIS spells it
        self.by_first_word = defaultdict(set)
        self.years = set()
        for fiscal_year, employer, count in rows:
            names = [employer] + re.split(r"\bd\s?b\s?a\b", employer, flags=re.I)[1:]  # "X DBA Y" counts for both
            for raw in names:
                key = normalize(raw)
                if not key:
                    continue
                self.approvals[key] += count
                self.display.setdefault(key, raw.strip())
                self.by_first_word[key.split()[0]].add(key)
            if fiscal_year:
                self.years.add(fiscal_year)

    def __len__(self):
        return len(self.approvals)

    def describe(self):
        if not self.years:
            return "USCIS H-1B Employer Data Hub"
        low, high = min(self.years), max(self.years)
        return f"USCIS H-1B approvals FY{low}" + (f"-FY{high}" if high != low else "")

    def lookup(self, company):
        """Return (approvals, matched legal name, number of legal names summed), or None if no match.

        Exact normalized name first; otherwise every employer whose name starts with the company's full name
        on a word boundary ("amazon" -> "amazon com services", "amazon web services", ...).
        """
        key = normalize(company)
        key = ALIASES.get(key, key)
        if not key:
            return None
        if key in self.approvals and len(key) < MIN_PREFIX_LENGTH:
            return self.approvals[key], self.display[key], 1
        if len(key) < MIN_PREFIX_LENGTH:
            return None
        matches = [name for name in self.by_first_word.get(key.split()[0], ())
                   if name == key or name.startswith(key + " ")]
        if not matches:
            return None
        top = max(matches, key=lambda name: self.approvals[name])
        return sum(self.approvals[name] for name in matches), self.display[top], len(matches)


def load_index(csv_paths=(), archive_years=(), cache_dir=None):
    """Build an index from your downloaded exports plus archived years (downloaded once into cache_dir)."""
    rows = []
    for path in csv_paths:
        rows.extend(read_export(Path(path).expanduser().read_bytes()))
    for year in archive_years:
        cached = Path(cache_dir) / f"h1b_datahubexport-{year}.csv"
        if not cached.exists():
            print(f"downloading USCIS H-1B data for FY{year} (once)...", file=sys.stderr)
            data = fetch_bytes(ARCHIVE_URL.format(year=year), timeout=120)
            read_export(data)  # make sure it is a real export before caching it
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
        rows.extend(read_export(cached.read_bytes()))
    return H1BIndex(rows)
