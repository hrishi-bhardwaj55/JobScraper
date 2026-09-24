"""Free public job boards and APIs: Remotive, RemoteOK, Himalayas, HN 'Who is hiring?', Amazon."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

from ..filters import ET, window_start
from ..models import Job
from . import html_to_text, parse_dt


async def remotive(client) -> list[Job]:
    data = await client.get_json("https://remotive.com/api/remote-jobs?category=software-dev&limit=500")
    return [Job(
        title=p.get("title", ""),
        company=p.get("company_name", ""),
        location="Remote - " + (p.get("candidate_required_location") or "Anywhere"),
        url=p.get("url", ""),
        posted_at=parse_dt(p.get("publication_date")),
        description=html_to_text(p.get("description")),
        remote=True,
        source="boards",
        tags=p.get("tags") or [],
    ) for p in (data or {}).get("jobs", [])]


async def remoteok(client) -> list[Job]:
    data = await client.get_json("https://remoteok.com/api")
    return [Job(
        title=p.get("position", ""),
        company=p.get("company", ""),
        location="Remote - " + (p.get("location") or "Anywhere"),
        url=p.get("url", ""),
        apply_url=p.get("apply_url") or p.get("url", ""),
        posted_at=parse_dt(p.get("epoch") or p.get("date")),
        description=html_to_text(p.get("description")),
        remote=True,
        source="boards",
        tags=p.get("tags") or [],
    ) for p in (data or [])[1:] if isinstance(p, dict)]  # [0] is a legal notice


async def himalayas(client) -> list[Job]:
    jobs = []
    for offset in range(0, 1200, 20):
        data = await client.get_json(f"https://himalayas.app/jobs/api?limit=20&offset={offset}")
        rows = (data or {}).get("jobs") or []
        for p in rows:
            locs = p.get("locationRestrictions") or []
            jobs.append(Job(
                title=p.get("title", ""),
                company=p.get("companyName", ""),
                location="Remote - " + (", ".join(locs) if locs else "Anywhere"),
                url=p.get("applicationLink") or p.get("guid", ""),
                posted_at=parse_dt(p.get("pubDate")),
                description=html_to_text(p.get("description")),
                remote=True,
                source="boards",
            ))
        if not rows or (jobs and jobs[-1].posted_at and jobs[-1].posted_at < window_start()):
            break  # sorted newest-first
    return jobs


async def amazon(client) -> list[Job]:
    """amazon.jobs public search JSON; posted_date is a bare date, interpreted in US Eastern."""
    jobs = []
    for q in ("software engineer", "software development engineer"):
        for offset in range(0, 500, 100):
            d = await client.get_json("https://www.amazon.jobs/en/search.json", params={
                "base_query": q, "country": "USA", "sort": "recent", "result_limit": 100, "offset": offset})
            rows = (d or {}).get("jobs") or []
            for p in rows:
                posted = parse_dt(p.get("posted_date"))
                if posted:
                    posted = posted.replace(tzinfo=ET)
                jobs.append(Job(
                    title=p.get("title", ""), company="Amazon",
                    location=p.get("normalized_location") or p.get("location", ""),
                    url="https://www.amazon.jobs" + p.get("job_path", ""),
                    apply_url=p.get("url_next_step") or "https://www.amazon.jobs" + p.get("job_path", ""),
                    posted_at=posted,
                    description=html_to_text(" ".join(filter(None, [
                        p.get("description"), p.get("basic_qualifications"), p.get("preferred_qualifications")]))),
                    source="boards", tags=["amazon"],
                ))
            if len(rows) < 100 or (jobs[-1].posted_at and jobs[-1].posted_at < window_start()):
                break
    return jobs


HN_URL = re.compile(r'href="([^"]+)"')


async def hn_whos_hiring(client) -> list[Job]:
    """Top-level comments posted today on the latest 'Ask HN: Who is hiring?' thread."""
    s = await client.get_json(
        "https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&query=who%20is%20hiring"
    )
    story = next((h for h in (s or {}).get("hits", []) if "who is hiring" in h.get("title", "").lower()), None)
    if not story:
        return []
    since = int(window_start().timestamp())
    c = await client.get_json(
        "https://hn.algolia.com/api/v1/search_by_date",
        params={"tags": f"comment,story_{story['objectID']}", "numericFilters": f"created_at_i>{since}",
                "hitsPerPage": 1000},
    )
    jobs = []
    for h in (c or {}).get("hits", []):
        if str(h.get("parent_id")) != str(story["objectID"]):
            continue  # replies, not postings
        raw = h.get("comment_text") or ""
        text = html_to_text(raw)
        head = [x.strip() for x in text.split("|")]
        if len(head) < 3:
            continue
        link = next((u for u in HN_URL.findall(raw) if "ycombinator" not in u), None)
        hn = f"https://news.ycombinator.com/item?id={h['objectID']}"
        loc = next((x for x in head[1:5] if re.search(r"remote|onsite|hybrid|,\s*[A-Z]{2}\b|NYC|SF", x, re.I)), "")
        role = next((x for x in head[1:5] if re.search(r"engineer|developer|swe|software", x, re.I)), head[1])
        jobs.append(Job(
            title=role[:120], company=head[0][:80], location=loc[:120], url=hn, apply_url=link or hn,
            posted_at=datetime.fromtimestamp(h["created_at_i"], tz=timezone.utc),
            description=text[:20000], source="boards", tags=["hn"],
        ))
    return jobs


async def fetch(client) -> list[Job]:
    results = await asyncio.gather(
        remotive(client), remoteok(client), himalayas(client), hn_whos_hiring(client), amazon(client),
        return_exceptions=True,
    )
    return [j for r in results if isinstance(r, list) for j in r]
