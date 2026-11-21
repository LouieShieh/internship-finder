"""Command line: python -m internship_finder [options]. Run with --help for the options."""

import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from . import jd
from .applied import AppliedIndex, read_applied
from .config import build_settings, parse_window
from .filters import load_exclusions
from .h1b import load_index
from .links import resolve_short_links
from .pipeline import add_h1b, compare_with_applied, keep, merge, sort_key
from .sources import SOURCE_LABELS, SOURCE_URLS, load_source

COLUMNS = ["underclass", "company", "title", "locations", "posted", "salary", "h1b_approvals", "h1b_employer",
           "list_sponsorship", "applied_at_company", "jd_check", "sources", "url"]


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="internship_finder",
        description="Merge public internship lists into a shortlist for F-1 students, minus roles you applied to.")
    parser.add_argument("--config", type=Path, help="settings file (default: ./config.toml if it exists)")
    parser.add_argument("--year", type=int, help="internship summer (default 2027)")
    parser.add_argument("--days", type=int, help="only roles posted in the last N days (default 14)")
    parser.add_argument("--applied", type=Path, help="CSV/XLSX of roles you applied to (read-only)")
    parser.add_argument("--sheet", dest="applied_sheet", help="part of the sheet name to read in an XLSX file")
    parser.add_argument("--max-per-company", type=int, help="hide companies where you already have N roles (2)")
    parser.add_argument("--check-jd", type=int, metavar="N", help="read the top N job descriptions and flag wording")
    parser.add_argument("--grad-window", nargs=2, metavar=("EARLIEST", "LATEST"),
                        help="your possible graduation dates, e.g. 2028-12 2030-05; flags postings that exclude them")
    parser.add_argument("--sources", nargs="+", choices=list(SOURCE_URLS), help="lists to read (default: all)")
    parser.add_argument("--h1b-csv", nargs="+", type=Path, help="H-1B Employer Data Hub exports you downloaded")
    parser.add_argument("--min-h1b", type=int, help="hide companies with fewer H-1B approvals than this")
    parser.add_argument("--no-h1b", action="store_true", help="skip the H-1B lookup")
    parser.add_argument("--no-default-exclusions", action="store_true",
                        help="don't use the bundled list of companies that bar F-1 students")
    parser.add_argument("--output-dir", type=Path, help="where to write the CSV (default ./output)")
    return parser.parse_args(argv)


def settings_from(args):
    config = args.config or (Path("config.toml") if Path("config.toml").exists() else None)
    if args.config and not args.config.exists():
        sys.exit(f"config file not found: {args.config}")
    overrides = {
        "year": args.year, "days": args.days, "applied": args.applied, "applied_sheet": args.applied_sheet,
        "max_per_company": args.max_per_company, "check_jd": args.check_jd, "sources": args.sources,
        "h1b_csv": args.h1b_csv, "min_h1b": args.min_h1b, "output_dir": args.output_dir,
        "grad_window": parse_window(args.grad_window) if args.grad_window else None,
        "h1b": False if args.no_h1b else None,
        "default_exclusions": False if args.no_default_exclusions else None,
    }
    return build_settings(config, overrides)


def warn(message):
    print(f"warning: {message}", file=sys.stderr)


def load_all(settings, today):
    """Download every enabled list in parallel. A list that fails is reported and skipped."""
    listings, counts = [], {}
    with ThreadPoolExecutor(max_workers=len(settings.sources) or 1) as pool:
        jobs = {name: pool.submit(load_source, name, settings.year, today, settings.source_urls.get(name))
                for name in settings.sources}
    for name, job in jobs.items():
        try:
            rows = job.result()
        except Exception as error:
            warn(f"could not load {name}: {error}")
            continue
        counts[SOURCE_LABELS[name]] = len(rows)
        listings.extend(rows)
    return listings, counts


def write_csv(path, roles):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:  # BOM so Excel reads UTF-8
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for role in roles:
            writer.writerow({
                "underclass": "yes" if role.underclass else "",
                "company": role.company,
                "title": role.title,
                "locations": "; ".join(sorted(role.locations))[:80],
                "posted": role.posted.isoformat() if role.posted else "",
                "salary": role.salary,
                "h1b_approvals": "" if role.h1b is None else role.h1b,
                "h1b_employer": role.h1b_employer,
                "list_sponsorship": ", ".join(sorted(role.sponsorship)),
                "applied_at_company": role.applied_at_company,
                "jd_check": role.jd,
                "sources": ",".join(sorted(role.sources)),
                "url": role.url,
            })


def main(argv=None):
    args = parse_args(argv)
    settings = settings_from(args)
    today = date.today()

    listings, counts = load_all(settings, today)
    if not listings:
        sys.exit("no list could be loaded; check your connection")

    excluded = load_exclusions(settings.exclusion_paths())
    dropped = {}
    kept = []
    for item in listings:
        reason = keep(item, today, settings.days, excluded)
        if reason:
            dropped[reason] = dropped.get(reason, 0) + 1
        else:
            kept.append(item)

    applied_rows = []
    if settings.applied:
        try:
            applied_rows = read_applied(settings.applied, settings.applied_sheet, settings.applied_header_row,
                                        settings.applied_first_data_row, settings.applied_columns)
        except (OSError, ValueError) as error:
            sys.exit(f"could not read {settings.applied}: {error}")

    links = resolve_short_links([url for _, _, url in applied_rows] + [item.url for item in kept],
                                settings.cache_dir / "url_cache.json")
    roles = merge(kept, links)
    shortlist, hidden = compare_with_applied(roles, AppliedIndex(applied_rows, links), settings.max_per_company)

    h1b_index = None
    if settings.h1b:
        try:
            h1b_index = load_index(settings.h1b_csv, settings.h1b_archive_years, settings.cache_dir)
        except Exception as error:
            warn(f"H-1B data unavailable ({error}); continuing without it")
    before = len(shortlist)
    shortlist = add_h1b(shortlist, h1b_index, settings.min_h1b if h1b_index else 0)
    if before != len(shortlist):
        hidden[f"fewer than {settings.min_h1b} H-1B approvals"] = before - len(shortlist)

    shortlist.sort(key=sort_key)
    top = shortlist[: settings.check_jd]
    if top:
        print(f"reading {len(top)} job descriptions...", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=8) as pool:
            for role, result in zip(top, pool.map(lambda r: jd.check(r.url, settings.grad_window), top)):
                role.jd = result.summary()

    out = Path(settings.output_dir) / f"shortlist_{today.isoformat()}.csv"
    write_csv(out, shortlist)

    print("lists: " + ", ".join(f"{name} {n}" for name, n in counts.items()))
    print(f"kept {len(kept)} rows -> {len(roles)} distinct roles -> {len(shortlist)} on the shortlist")
    for reason, n in sorted(dropped.items(), key=lambda kv: -kv[1]):
        print(f"  dropped {n:5}: {reason}")
    if settings.applied:
        print(f"applications read: {len(applied_rows)}")
    for reason, n in hidden.items():
        print(f"  hidden  {n:5}: {reason}")
    if h1b_index is not None:
        print(f"H-1B data: {h1b_index.describe()} ({len(h1b_index)} employers)")
    print(f"saved: {out}")
    for role in shortlist[: settings.console_rows]:
        star = "★" if role.underclass else " "
        h1b = "" if role.h1b is None else f"H1B {role.h1b}"
        extra = f" | {role.jd}" if role.jd else ""
        posted = role.posted.isoformat() if role.posted else "          "
        print(f"{star} {posted} | {role.company[:24]:24} | {role.title[:58]:58} | {h1b:>9}{extra}")


if __name__ == "__main__":
    main()
