"""Settings: built-in defaults, then config.toml, then command-line flags (each overrides the one before)."""

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from .sources import SOURCE_URLS

PACKAGE_DATA = Path(__file__).resolve().parent / "data"


@dataclass
class Settings:
    year: int = 2027
    days: int = 14
    max_per_company: int = 2
    check_jd: int = 0
    sources: list = field(default_factory=lambda: list(SOURCE_URLS))
    source_urls: dict = field(default_factory=dict)  # override a list's URL, e.g. for another cycle
    # Your applications file (CSV or XLSX). Read-only.
    applied: Path | None = None
    applied_sheet: str | None = None
    applied_header_row: int | None = None
    applied_first_data_row: int | None = None
    applied_columns: dict | None = None
    # Filters
    exclude_files: list = field(default_factory=list)
    default_exclusions: bool = True
    grad_window: tuple | None = None  # ((year, month), (year, month))
    min_h1b: int = 0
    # H-1B data
    h1b: bool = True
    h1b_csv: list = field(default_factory=list)
    h1b_archive_years: list = field(default_factory=lambda: [2022, 2023])
    # Output
    output_dir: Path = Path("output")
    cache_dir: Path = Path(".cache")
    console_rows: int = 25

    def exclusion_paths(self):
        built_in = [PACKAGE_DATA / "excluded_companies.txt"] if self.default_exclusions else []
        return built_in + list(self.exclude_files)


def parse_month(text):
    """'2028-12' -> (2028, 12)."""
    year, _, month = str(text).partition("-")
    return int(year), int(month or 12)


def parse_window(values):
    if not values:
        return None
    first, last = values
    return parse_month(first), parse_month(last)


# config.toml layout: section -> {key in the file: Settings field}
CONFIG_KEYS = {
    "search": {"year": "year", "days": "days", "max_per_company": "max_per_company", "check_jd": "check_jd",
               "sources": "sources", "source_urls": "source_urls"},
    "applied": {"path": "applied", "sheet": "applied_sheet", "header_row": "applied_header_row",
                "first_data_row": "applied_first_data_row", "columns": "applied_columns"},
    "filters": {"exclude_files": "exclude_files", "default_exclusions": "default_exclusions",
                "graduation_window": "grad_window", "min_h1b_approvals": "min_h1b"},
    "h1b": {"enabled": "h1b", "csv": "h1b_csv", "archive_years": "h1b_archive_years"},
    "output": {"dir": "output_dir", "cache_dir": "cache_dir", "console_rows": "console_rows"},
}
PATH_FIELDS = {"applied", "output_dir", "cache_dir"}
PATH_LIST_FIELDS = {"exclude_files", "h1b_csv"}


def load_config(path):
    """Read config.toml into a {Settings field: value} dict. Relative paths are relative to the file."""
    path = Path(path).expanduser()
    base = path.resolve().parent
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    known = {name for name in (f.name for f in fields(Settings))}
    values = {}
    for section, keys in CONFIG_KEYS.items():
        table = data.get(section, {})
        unknown = set(table) - set(keys)
        if unknown:
            raise ValueError(f"{path}: unknown key(s) in [{section}]: {', '.join(sorted(unknown))}")
        for key, name in keys.items():
            if key in table:
                values[name] = table[key]
    for name in PATH_FIELDS & set(values):
        values[name] = base / Path(values[name]).expanduser()
    for name in PATH_LIST_FIELDS & set(values):
        values[name] = [base / Path(p).expanduser() for p in values[name]]
    if "grad_window" in values:
        values["grad_window"] = parse_window(values["grad_window"])
    assert set(values) <= known
    return values


def build_settings(config_path=None, overrides=None):
    settings = Settings()
    if config_path:
        for name, value in load_config(config_path).items():
            setattr(settings, name, value)
    for name, value in (overrides or {}).items():
        if value is not None:
            setattr(settings, name, value)
    return settings
