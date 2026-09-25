"""Web search for jobs posted in the last day (LinkedIn, Indeed, ATS pages) via Tavily / Firecrawl.

Uses search-engine results only (no direct LinkedIn scraping). ATS URLs found here that aren't in
companies.yaml are logged to data/discovered_companies.txt so they can be added as first-class sources.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from ..config import DATA, env, profile
from ..models import Job

log = logging.getLogger(__name__)

JOB_DOMAINS = [
    "linkedin.com/jobs", "indeed.com", "boards.greenhouse.io", "job-boards.greenhouse.io",
    "jobs.lever.co", "jobs.ashbyhq.com", "myworkdayjobs.com", "wellfound.com", "builtin.com",
]

ATS_TOKEN = [
    (re.compile(r"greenhouse\.io/([\w-]+)/jobs"), "greenhouse"),
    (re.compile(r"jobs\.lever\.co/([\w-]+)/"), "lever"),
    (re.compile(r"jobs\.ashbyhq\.com/([\w.-]+)/"), "ashby"),
]
LINKEDIN_TITLE = re.compile(r"^(?P<company>.+?) hiring (?P<title>.+?) in (?P<loc>.+?)(?: \| LinkedIn)?$")
# aggregate/listing pages rather than a single posting
LISTING = re.compile(r"^\d[\d,+]*\s.*\bjobs?\b|\bjobs? (in|near)\b|\bjobs? & (work|careers)\b|^jobs at\b", re.I)
INDEED_TITLE = re.compile(r"^(?P<title>.+?) - (?P<company>.+?) - (?P<loc>.+?)(?: - Indeed.*)?$")


def _queries() -> list[str]:
    p = profile()
    return [f'"{q}" job United States' for q in p["search_queries"]]


def to_job(url: str, title: str, content: str) -> Job | None:
    host = urlparse(url).netloc
    title = (title or "").strip()
    if LISTING.search(title):
        return None
    company, loc, role = "", "", title
    if "linkedin.com" in host:
        if "/jobs/view/" not in url:
            return None  # search/listing pages, not a posting
        m = LINKEDIN_TITLE.match(title)
        if m:
            company, role, loc = m["company"], m["title"], m["loc"]
        elif m := re.match(r"^(?P<title>.+?) at (?P<company>[^|]+?)(?: \| LinkedIn)?$", title):
            company, role = m["company"], m["title"]
    elif "indeed.com" in host:
        if "viewjob" not in url and "jk=" not in url:
            return None
        m = INDEED_TITLE.match(title)
        if m:
            company, role, loc = m["company"], m["title"], m["loc"]
    else:
        for rx, _ in ATS_TOKEN:
            if m := rx.search(url):
                company = m.group(1).replace("-", " ").title()
        role = re.sub(r"^(Job Application for|Jobs? at)\s+", "", title)
        role = re.split(r"\s+[@|–-]\s+|\s+at\s+", role)[0]
        if loc_m := re.search(r"\b([A-Z][a-zA-Z .]+, [A-Z]{2})\b|\bRemote\b", content or ""):
            loc = loc_m.group(0)
    if not role:
        return None
    return Job(
        title=role.strip(), company=company.strip() or host, location=loc or "United States",
        url=url, apply_url=url, description=(content or "")[:4000], source="websearch",
        # results are restricted to the past day by the search API
        posted_at=datetime.now(timezone.utc), tags=[host.replace("www.", "")],
    )


async def tavily(client, key: str) -> list[tuple[str, str, str]]:
    async def one(q):
        d = await client.post_json(
            "https://api.tavily.com/search",
            json={"query": q, "time_range": "day", "max_results": 20, "search_depth": "basic",
                  "include_domains": JOB_DOMAINS, "country": "united states"},
            headers={"Authorization": f"Bearer {key}"},
        )
        return [(r["url"], r.get("title", ""), r.get("content", "")) for r in (d or {}).get("results", [])]

    rs = await asyncio.gather(*(one(q) for q in _queries()))
    return [x for r in rs for x in r]


async def firecrawl(client, key: str) -> list[tuple[str, str, str]]:
    sites = " OR ".join(f"site:{d}" for d in JOB_DOMAINS[:6])

    async def one(q):
        d = await client.post_json(
            "https://api.firecrawl.dev/v2/search",
            json={"query": f"{q} ({sites})", "limit": 20, "tbs": "qdr:d", "location": "United States"},
            headers={"Authorization": f"Bearer {key}"},
        )
        web = ((d or {}).get("data") or {}).get("web") or []
        return [(r["url"], r.get("title", ""), r.get("description", "")) for r in web]

    rs = await asyncio.gather(*(one(q) for q in _queries()))
    return [x for r in rs for x in r]


def _log_discovered(urls: list[str]) -> None:
    from ..config import companies

    known = {(c["ats"], c["token"].lower()) for c in companies()}
    found = set()
    for u in urls:
        for rx, ats in ATS_TOKEN:
            if (m := rx.search(u)) and (ats, m.group(1).lower()) not in known:
                found.add(f"{ats}\t{m.group(1)}")
    if found:
        path = DATA / "discovered_companies.txt"
        prev = set(path.read_text().splitlines()) if path.exists() else set()
        path.write_text("\n".join(sorted(prev | found)) + "\n")


async def fetch(client) -> list[Job]:
    tasks = []
    if k := env("TAVILY_API_KEY"):
        tasks.append(tavily(client, k))
    # Firecrawl search costs ~2 credits/10 results; off by default so credits go to careers scraping
    if (k := env("FIRECRAWL_API_KEY")) and profile().get("firecrawl_search"):
        tasks.append(firecrawl(client, k))
    if not tasks:
        log.info("no search API keys set; skipping websearch")
        return []
    results = await asyncio.gather(*tasks, return_exceptions=True)
    hits = [h for r in results if isinstance(r, list) for h in r]
    _log_discovered([u for u, _, _ in hits])
    seen, jobs = set(), []
    for url, title, content in hits:
        if url in seen:
            continue
        seen.add(url)
        if j := to_job(url, title, content):
            jobs.append(j)
    return jobs
