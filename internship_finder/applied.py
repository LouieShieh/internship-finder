"""Read the list of roles you already applied to (CSV or Excel) and answer "have I applied to this already?".

The file is only read, never written. Columns are found from the header text (company / organization /
employer, title / position / role, url / link) unless you name them in the config.
"""

import csv
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree

from .links import posting_keys
from .normalize import company_key, similarity, title_tokens

HEADERS = {
    # Tried in order: "Position Format" must not win over "Job Title".
    "company": [re.compile(r"company|organi[sz]ation|employer", re.I)],
    "title": [re.compile(r"title", re.I), re.compile(r"position|role", re.I)],
    "url": [re.compile(r"url|link", re.I)],
}
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def column_index(letters):
    """'A' -> 0, 'D' -> 3, 'AA' -> 26."""
    index = 0
    for char in letters.upper():
        index = index * 26 + ord(char) - 64
    return index - 1


def read_xlsx(path, sheet=None):
    """Rows of one worksheet as [(row_number, {column_index: text})], using only the standard library.

    sheet is part of the sheet name (case-insensitive); the first sheet is used when it's None.
    """
    with zipfile.ZipFile(path) as book:
        shared = []
        if "xl/sharedStrings.xml" in book.namelist():
            for item in ElementTree.fromstring(book.read("xl/sharedStrings.xml")).findall("m:si", NS):
                shared.append("".join(t.text or "" for t in item.iter(f"{{{NS['m']}}}t")))
        sheets = list(ElementTree.fromstring(book.read("xl/workbook.xml")).find("m:sheets", NS))
        chosen = next((s for s in sheets if sheet and sheet.lower() in s.get("name", "").lower()), None)
        if chosen is None:
            if sheet:
                names = ", ".join(s.get("name", "") for s in sheets)
                raise ValueError(f"no sheet named like {sheet!r} in {path} (sheets: {names})")
            chosen = sheets[0]
        rel_id = chosen.get(f"{{{NS['r']}}}id")
        rels = ElementTree.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in rels if r.get("Id") == rel_id)
        data = ElementTree.fromstring(book.read("xl/" + target.lstrip("/").removeprefix("xl/")))

    def text(cell):
        value = cell.find("m:v", NS)
        if cell.get("t") == "s" and value is not None:
            return shared[int(value.text)]
        if cell.get("t") == "inlineStr":
            return "".join(t.text or "" for t in cell.iter(f"{{{NS['m']}}}t"))
        return value.text if value is not None and value.text else ""

    rows = []
    for row in data.iter(f"{{{NS['m']}}}row"):
        cells = {}
        for cell in row.findall("m:c", NS):
            cells[column_index(re.sub(r"\d", "", cell.get("r")))] = text(cell).strip()
        rows.append((int(row.get("r")), cells))
    return rows


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return [(number, {i: value.strip() for i, value in enumerate(row)})
                for number, row in enumerate(csv.reader(handle), start=1)]


def find_columns(rows, header_row=None, scan=30):
    """Return (header_row_number, {"company": i, "title": i, "url": i or None}) from the header text."""
    candidates = [r for r in rows if r[0] == header_row] if header_row else rows[:scan]
    for number, cells in candidates:
        found = {}
        for key, patterns in HEADERS.items():
            for pattern in patterns:
                index = next((i for i, value in sorted(cells.items()) if pattern.search(value)), None)
                if index is not None:
                    found[key] = index
                    break
        if "company" in found and "title" in found:
            found.setdefault("url", None)
            return number, found
    where = f"row {header_row}" if header_row else f"the first {scan} rows"
    raise ValueError(f"could not find company and title columns in {where}; set them in the config")


def read_applied(path, sheet=None, header_row=None, first_data_row=None, columns=None):
    """Return [(company, title, url)] for every filled row of your applications file."""
    path = Path(path).expanduser()
    rows = read_xlsx(path, sheet) if path.suffix.lower() in (".xlsx", ".xlsm") else read_csv(path)
    if columns:
        cols = {key: column_index(value) if isinstance(value, str) else int(value) for key, value in columns.items()}
        cols.setdefault("url", None)
        header = header_row or 0
    else:
        header, cols = find_columns(rows, header_row)
    start = first_data_row or header + 1
    applied = []
    for number, cells in rows:
        if number < start:
            continue
        company, title = cells.get(cols["company"], ""), cells.get(cols["title"], "")
        url = cells.get(cols["url"], "") if cols.get("url") is not None else ""
        if company or title:
            applied.append((company, title, url))
    return applied


class AppliedIndex:
    """Answers: how many roles have I applied to at this company, and is this role one of them?"""

    def __init__(self, rows, links=None):
        links = links or {}
        self.titles = defaultdict(list)       # company key -> title token sets
        self.postings = set()                 # posting keys of applied links
        self.employer_names = defaultdict(set)  # job-site account -> company keys seen under it
        for company, title, url in rows:
            key = company_key(company)
            self.titles[key].append(title_tokens(title))
            posting, employer = posting_keys(links.get(url, url))
            if posting:
                self.postings.add(posting)
            if employer:
                self.employer_names[employer].add(key)

    def previous_titles(self, company, employers=()):
        """Title token sets of applied rows at this company: matched by name, or by the same job-site account
        (so "ModMed" and "Modernizing Medicine" count as one company when both link to the same Workday site)."""
        key = company_key(company)
        matched = set()
        if key:
            # Exact name, or one name containing the other when both are long enough not to collide by chance.
            matched = {other for other in self.titles if key == other or (
                min(len(key), len(other)) >= 5 and (key in other or other in key))}
        for employer in employers:
            matched |= self.employer_names.get(employer, set())
        return [tokens for other in matched for tokens in self.titles[other]]

    def check(self, company, title, urls, threshold=0.6):
        """Return (applied_at_company, status) where status is "same posting", "similar title" or ""."""
        keys = [posting_keys(url) for url in urls]
        previous = self.previous_titles(company, [employer for _, employer in keys if employer])
        if any(posting in self.postings for posting, _ in keys if posting):
            return len(previous), "same posting"
        tokens = title_tokens(title)
        if any(similarity(tokens, other) >= threshold for other in previous):
            return len(previous), "similar title"
        return len(previous), ""
