from __future__ import annotations

from ..config import companies_for
from ..models import Job
from . import gather_limited, html_to_text, parse_dt

API = "https://api.ashbyhq.com/posting-api/job-board/{t}?includeCompensation=true"


def parse(data: dict, company: str) -> list[Job]:
    jobs = []
    for p in (data or {}).get("jobs", []):
        if p.get("isListed") is False:
            continue
        locs = [p.get("location", "")] + [
            s.get("location", "") for s in p.get("secondaryLocations") or []
        ]
        addr = ((p.get("address") or {}).get("postalAddress") or {}).get("addressCountry", "")
        jobs.append(Job(
            title=p.get("title", ""),
            company=company,
            location=" / ".join(filter(None, locs + [addr])),
            url=p.get("jobUrl", ""),
            apply_url=p.get("applyUrl") or p.get("jobUrl", ""),
            posted_at=parse_dt(p.get("publishedAt")),
            description=p.get("descriptionPlain") or html_to_text(p.get("descriptionHtml")),
            remote=bool(p.get("isRemote")),
            source="ashby",
        ))
    return jobs


async def _one(client, c):
    return parse(await client.get_json(API.format(t=c["token"])), c["name"])


async def fetch(client) -> list[Job]:
    return await gather_limited([_one(client, c) for c in companies_for("ashby")])
