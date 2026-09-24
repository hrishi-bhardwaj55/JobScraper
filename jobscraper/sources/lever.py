from __future__ import annotations

from ..config import companies_for
from ..models import Job
from . import gather_limited, html_to_text, parse_dt

API = "https://api.lever.co/v0/postings/{t}?mode=json"


def parse(data: list, company: str) -> list[Job]:
    jobs = []
    for p in data or []:
        cats = p.get("categories") or {}
        locs = cats.get("allLocations") or [cats.get("location", "")]
        desc = " ".join(filter(None, [
            p.get("descriptionPlain"),
            " ".join(html_to_text(l.get("content")) for l in p.get("lists", [])),
            p.get("additionalPlain"),
        ]))
        jobs.append(Job(
            title=p.get("text", ""),
            company=company,
            location=" / ".join(l for l in locs if l),
            url=p.get("hostedUrl", ""),
            apply_url=p.get("applyUrl") or p.get("hostedUrl", ""),
            posted_at=parse_dt(p.get("createdAt")),
            description=desc[:20000],
            remote=p.get("workplaceType") == "remote",
            source="lever",
        ))
    return jobs


async def _one(client, c):
    return parse(await client.get_json(API.format(t=c["token"])), c["name"])


async def fetch(client) -> list[Job]:
    return await gather_limited([_one(client, c) for c in companies_for("lever")])
