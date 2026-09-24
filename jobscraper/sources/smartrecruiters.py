from __future__ import annotations

from ..config import companies_for, profile
from ..filters import title_ok, window_start
from ..models import Job
from . import gather_limited, html_to_text, parse_dt

API = "https://api.smartrecruiters.com/v1/companies/{t}/postings"


def _location(loc: dict) -> str:
    parts = [loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()]
    s = ", ".join(p for p in parts if p)
    return f"{s} (Remote)" if loc.get("remote") else s


async def _one(client, c) -> list[Job]:
    prof, start = profile(), window_start()
    hits = []
    for offset in range(0, 1000, 100):
        data = await client.get_json(
            API.format(t=c["token"]), params={"limit": 100, "offset": offset, "country": "us"}
        )
        content = (data or {}).get("content") or []
        for p in content:
            posted = parse_dt(p.get("releasedDate"))
            if posted and posted >= start and title_ok(p.get("name", ""), prof):
                hits.append((p, posted))
        if len(content) < 100:
            break

    async def detail(p, posted) -> list[Job]:
        d = await client.get_json(p["ref"]) or {}
        sections = ((d.get("jobAd") or {}).get("sections") or {}).values()
        desc = " ".join(html_to_text(s.get("text")) for s in sections if isinstance(s, dict))
        url = d.get("postingUrl") or f"https://jobs.smartrecruiters.com/{c['token']}/{p['id']}"
        return [Job(
            title=p.get("name", ""),
            company=c["name"],
            location=_location(p.get("location") or {}),
            url=url,
            apply_url=d.get("applyUrl") or url,
            posted_at=posted,
            description=desc[:20000],
            remote=bool((p.get("location") or {}).get("remote")),
            source="smartrecruiters",
        )]

    return await gather_limited([detail(p, t) for p, t in hits], limit=6)


async def fetch(client) -> list[Job]:
    return await gather_limited([_one(client, c) for c in companies_for("smartrecruiters")])
