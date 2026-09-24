"""Workday career sites via the public CXS JSON API used by *.myworkdayjobs.com.

companies.yaml token format: "<tenant>|<wdN>|<site>", e.g. "capitalone|wd12|Capital_One".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..config import companies_for, profile
from ..filters import ET, title_ok
from ..models import Job
from . import gather_limited, html_to_text

QUERIES = ["software engineer", "developer"]
PAGE = 20
MAX_PAGES = 10


def posted_on_to_dt(text: str) -> datetime | None:
    t = (text or "").lower()
    now = datetime.now(ET)
    if "today" in t:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if "yesterday" in t:
        return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return None


async def _one(client, c) -> list[Job]:
    tenant, wd, site = c["token"].split("|")
    base = f"https://{tenant}.{wd}.myworkdayjobs.com"
    api = f"{base}/wday/cxs/{tenant}/{site}"
    prof = profile()
    paths: dict[str, dict] = {}
    for q in QUERIES:
        for page in range(MAX_PAGES):
            data = await client.post_json(
                f"{api}/jobs",
                json={"appliedFacets": {}, "limit": PAGE, "offset": page * PAGE, "searchText": q},
            )
            posts = (data or {}).get("jobPostings") or []
            for p in posts:
                if "today" in (p.get("postedOn") or "").lower() and title_ok(p.get("title", ""), prof):
                    paths[p["externalPath"]] = p
            if len(posts) < PAGE:
                break

    async def detail(path: str, p: dict) -> list[Job]:
        d = ((await client.get_json(f"{api}{path}")) or {}).get("jobPostingInfo") or {}
        locs = [d.get("location") or p.get("locationsText", "")] + (d.get("additionalLocations") or [])
        country = (d.get("country") or {}).get("descriptor", "")
        url = d.get("externalUrl") or f"{base}/{site}{path}"
        start = d.get("startDate")
        posted = (
            datetime.fromisoformat(start).replace(tzinfo=ET) if start else posted_on_to_dt(p.get("postedOn"))
        )
        return [Job(
            title=d.get("title") or p.get("title", ""),
            company=c["name"],
            location=" / ".join(filter(None, locs + [country])),
            url=url,
            apply_url=url,
            posted_at=posted.astimezone(timezone.utc) if posted else None,
            description=html_to_text(d.get("jobDescription")),
            source="workday",
        )]

    return await gather_limited([detail(k, v) for k, v in paths.items()], limit=6)


async def fetch(client) -> list[Job]:
    return await gather_limited([_one(client, c) for c in companies_for("workday")], limit=8)
