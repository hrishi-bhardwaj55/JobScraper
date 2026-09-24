from __future__ import annotations

from ..config import companies_for
from ..models import Job
from . import gather_limited, html_to_text, parse_dt

API = "https://boards-api.greenhouse.io/v1/boards/{t}/jobs?content=true"


def parse(data: dict, company: str) -> list[Job]:
    jobs = []
    for p in (data or {}).get("jobs", []):
        jobs.append(Job(
            title=p.get("title", ""),
            company=company,
            location=(p.get("location") or {}).get("name", ""),
            url=p.get("absolute_url", ""),
            apply_url=p.get("absolute_url", ""),
            # first_published is the real post date; updated_at changes on any edit
            posted_at=parse_dt(p.get("first_published") or p.get("updated_at")),
            description=html_to_text(p.get("content")),
            source="greenhouse",
        ))
    return jobs


async def _one(client, c):
    return parse(await client.get_json(API.format(t=c["token"])), c["name"])


async def fetch(client) -> list[Job]:
    return await gather_limited([_one(client, c) for c in companies_for("greenhouse")])
