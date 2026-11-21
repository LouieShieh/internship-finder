"""Recognize job links: which posting a URL names, and which company account on the job site it belongs to."""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .net import final_url

# Short links used by the lists; they are followed once and the answer is cached.
SHORT_LINK = re.compile(r"//(go\.vansh\.nyc|simplify\.jobs/p)/", re.I)

# (site, pattern) where group 1 is the company's account on that site and group 2 is the job ID. The account
# identifies the employer even when two lists (or your own tracker) spell the company name differently.
ATS_LINKS = [
    ("workday", re.compile(r"//([a-z0-9-]+)\.wd\d+\.myworkdayjobs\.com/[^?#]*_([a-z0-9-]+)", re.I)),
    ("workday", re.compile(r"myworkdaysite\.com/(?:[a-z]{2}-[a-z]{2}/)?recruiting/([^/?#]+)/[^?#]*_([a-z0-9-]+)", re.I)),
    ("greenhouse", re.compile(r"greenhouse\.io/([^/?#]+)/jobs/(\d+)", re.I)),
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_app\?for=([^&#]+)&token=(\d+)", re.I)),
    ("greenhouse", re.compile(r"//(?:www\.|careers\.|jobs\.)?([^/.]+)\.[^/]+/[^#]*[?&]gh_jid=(\d+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f-]{36})", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/([^/?#]+)/([0-9a-f-]{36})", re.I)),
    ("icims", re.compile(r"//([a-z0-9-]+)\.icims\.com/jobs/(\d+)", re.I)),
    ("oracle", re.compile(r"//([^/]+)\.oraclecloud\.com/hcmUI/CandidateExperience/[^?#]*/job/(\d+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/([^/?#]+)/j/([0-9a-f]+)", re.I)),
    ("smartrecruiters", re.compile(r"jobs\.smartrecruiters\.com/([^/?#]+)/(\d+)", re.I)),
    ("successfactors", re.compile(r"(?=.*[?&]company=([^&#]+))(?=.*[?&]career_job_req_id=(\d+))", re.I)),
    ("amazon", re.compile(r"(amazon)\.jobs/(?:[a-z]{2}/)?jobs/(\d+)", re.I)),
]
GLOBAL_JOB_IDS = {"greenhouse", "ashby", "lever"}  # these sites' job IDs are unique across all companies


def posting_keys(url):
    """Return (posting, employer) for a job link.

    posting names one job ("workday:nvidia:jr2029119"); employer names the company's account on the job site
    ("workday:nvidia"). Unknown sites give employer None and fall back to the cleaned-up URL as the posting, but
    only when the URL contains something that looks like a job ID, because a careers home page is shared by many
    roles.
    """
    url = (url or "").strip()
    if not url.lower().startswith("http"):
        return None, None
    for site, pattern in ATS_LINKS:
        match = pattern.search(url)
        if match:
            employer, job = match.group(1).lower(), match.group(2).lower()
            if site == "workday":
                job = re.sub(r"-\d{1,2}$", "", job)  # reposted copies of one requisition end in -1, -2
            posting = f"{site}:{job}" if site in GLOBAL_JOB_IDS else f"{site}:{employer}:{job}"
            return posting, f"{site}:{employer}"
    cleaned = re.sub(r"^https?://(www\.)?", "", url.split("#")[0].lower())
    cleaned = re.sub(r"[?&](utm_[a-z]+|source|src|ref)=[^&]*", "", cleaned)
    cleaned = re.sub(r"/(apply|application)?/?$", "", cleaned)
    return (cleaned if re.search(r"\d{4,}|[0-9a-f]{8}-[0-9a-f]{4}", cleaned) else None), None


def resolve_short_links(urls, cache_path, workers=16, resolver=final_url):
    """Map list short links to the real posting URL. Answers are cached in a JSON file between runs."""
    cache_path = Path(cache_path)
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    todo = sorted({url for url in urls if url and SHORT_LINK.search(url) and url not in cache})
    if todo:
        print(f"resolving {len(todo)} short links (cached afterwards)...", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for url, target in zip(todo, pool.map(resolver, todo)):
                if target != url and target.startswith("http"):
                    cache[url] = target
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=0, sort_keys=True), encoding="utf-8")
    return cache
