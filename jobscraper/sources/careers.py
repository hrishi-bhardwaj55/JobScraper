"""Custom company career pages scraped with Firecrawl (config/careers.yaml).

Listing pages are scraped as markdown + links (1 credit each); job links are found by a per-site regex.
New jobs with a relevant title get their detail page scraped for a full description (1 credit each).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone

import httpx
import yaml

from ..config import ROOT, env, profile
from ..filters import title_ok
from ..models import Job
from .. import store

log = logging.getLogger(__name__)
API = "https://api.firecrawl.dev/v2"
MD_LINK = re.compile(r"\[((?:[^\[\]]|\\\[|\\\])+?)\]\((https?://[^)\s]+)")
AGO = re.compile(r"posted\s+(?:an?|\d+)\s+(minute|hour|day)s?\s+ago|posted\s+(today|just now)", re.I)
US_LOC = re.compile(r"\b[A-Z][a-zA-Z .]+,\s*(?:[A-Z]{2}|New York|California|Texas|Illinois|Washington)\b"
                    r"|United States|\bUSA\b|Remote", re.M)


class Firecrawl:
    """Free plan: 2 concurrent jobs, ~10 scrapes/min. Run one at a time (leaves a slot for other
    tools) and pace requests; each scrape carries a server-side timeout so it can't hog a slot."""

    SCRAPE_TIMEOUT_MS = 45000

    def __init__(self, client, key: str, concurrency: int = 1, interval: float = 6.5):
        self.client, self.h = client, {"Authorization": f"Bearer {key}"}
        self.sem, self.interval, self._next, self._lock = asyncio.Semaphore(concurrency), interval, 0.0, asyncio.Lock()

    async def credits(self) -> int:
        d = await self.client.get_json(f"{API}/team/credit-usage", headers=self.h)
        return int(((d or {}).get("data") or {}).get("remainingCredits", 0))

    async def wait_for_slot(self, max_wait: float = 180) -> bool:
        """Jobs from an interrupted earlier run can hold every slot for a while; wait them out."""
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            q = await self.client.get_json(f"{API}/team/queue-status", headers=self.h) or {}
            if q.get("activeJobsInQueue", 0) < q.get("maxConcurrency", 2):
                return True
            log.info("firecrawl: all %s slots busy, waiting", q.get("maxConcurrency"))
            await asyncio.sleep(15)
        return False

    async def scrape(self, url: str, formats=("markdown", "links")) -> dict:
        async with self.sem:
            for attempt in range(4):
                async with self._lock:
                    wait = self._next - time.monotonic()
                    self._next = max(self._next, time.monotonic()) + self.interval
                if wait > 0:
                    await asyncio.sleep(wait)
                try:
                    # raw client: the shared retry policy gives up on 429 too quickly for Firecrawl's limits
                    r = await self.client._client.post(
                        f"{API}/scrape", headers=self.h, timeout=self.SCRAPE_TIMEOUT_MS / 1000 + 30,
                        json={"url": url, "formats": list(formats), "onlyMainContent": False,
                              "waitFor": 2000, "timeout": self.SCRAPE_TIMEOUT_MS},
                    )
                except httpx.HTTPError as e:
                    log.warning("firecrawl %s failed: %r", url, e)
                    continue
                if r.status_code == 429 or (r.status_code == 408 and "CONCURRENCY" in r.text):
                    await asyncio.sleep(15 * (attempt + 1))
                    continue
                if r.status_code >= 400:
                    log.warning("firecrawl %s -> %s %s", url, r.status_code, r.text[:200])
                    return {}
                return (r.json() or {}).get("data") or {}
        return {}


def clean(s: str) -> list[str]:
    """Split markdown link text into non-empty lines, stripping formatting."""
    s = s.replace("\\\\", "\n").replace("\\n", "\n")
    parts = [re.sub(r"[*_#`]|!\[.*?\]\(.*?\)", "", p).strip(" \\") for p in s.split("\n")]
    return [p for p in parts if p]


def title_from_slug(url: str) -> str:
    slug = re.sub(r"[?#].*", "", url.rstrip("/")).split("/")[-1]
    slug = re.sub(r"^\d+-|-\d+$|^\d+$", "", slug)
    return slug.replace("-", " ").strip().title()


def parse_listing(data: dict, site: dict) -> dict[str, dict]:
    """Returns {canonical_url: {title, location, posted_at}} for links matching the site's pattern."""
    rx = re.compile(site["link"])
    canon = lambda u: re.sub(r"[?#].*", "", u)
    found: dict[str, dict] = {}
    for text, url in MD_LINK.findall(data.get("markdown", "")):
        if not rx.search(url):
            continue
        lines = clean(text)
        if not lines or lines[0].lower() in {"apply", "apply now", "see full role description", "learn more"}:
            continue
        title = re.sub(r"^Learn more about\s+", "", lines[0])
        rest = " | ".join(lines[1:])
        loc = next((l for l in lines[1:] if US_LOC.search(l) or "·" in l), "")
        posted = None
        if m := AGO.search(rest):
            unit = (m.group(1) or "").lower()
            n = re.search(r"(\d+)", m.group(0))
            n = int(n.group(1)) if n else 1
            posted = datetime.now(timezone.utc) - {"minute": timedelta(minutes=n), "hour": timedelta(hours=n),
                                                   "day": timedelta(days=n)}.get(unit, timedelta())
        found.setdefault(canon(url), {"title": title, "location": loc.replace("·", ", "), "posted_at": posted})
    for url in data.get("links", []):  # pages whose links carry no text (e.g. card layouts)
        if rx.search(url):
            found.setdefault(canon(url), {"title": title_from_slug(url), "location": "", "posted_at": None})
    if "loc" in rx.groupindex:
        for url, info in found.items():
            if not info["location"] and (m := rx.search(url)):
                info["location"] = m.group("loc").replace("-", " ").title()
    return found


async def _site(fc: Firecrawl, site: dict, prof: dict) -> list[tuple[dict, str, dict]]:
    data = await fc.scrape(site["url"])
    listing = parse_listing(data, site)
    new, first_run = store.mark_seen(site["name"], list(listing))
    today = datetime.now(timezone.utc) - timedelta(hours=24)
    out = []
    for url, info in listing.items():
        explicit_today = info["posted_at"] is not None and info["posted_at"] >= today
        # first run only seeds history, unless the page itself says the job is fresh
        if (url in new and not first_run) or explicit_today:
            if title_ok(info["title"], prof):
                out.append((site, url, info))
    log.info("[careers] %s: %d listed, %d new%s, %d relevant", site["name"], len(listing), len(new),
             " (first run: seeded)" if first_run else "", len(out))
    return out


def _detail_location(md: str) -> str:
    head = md[:3000]
    m = US_LOC.search(head)
    return m.group(0) if m else ""


async def fetch(client) -> list[Job]:
    key = env("FIRECRAWL_API_KEY")
    if not key:
        log.info("FIRECRAWL_API_KEY not set; skipping careers")
        return []
    cfg = yaml.safe_load((ROOT / "config" / "careers.yaml").read_text(encoding="utf-8"))
    sites, max_details, reserve = cfg["sites"], cfg.get("max_detail_scrapes", 15), cfg.get("credit_reserve", 50)
    fc = Firecrawl(client, key)
    credits = await fc.credits()
    if credits - len(sites) < reserve:
        log.warning("firecrawl credits low (%d); skipping careers", credits)
        return []
    if not await fc.wait_for_slot():
        log.warning("firecrawl concurrency slots still busy; skipping careers this run")
        return []
    prof = profile()
    hits = [h for r in await asyncio.gather(*(_site(fc, s, prof) for s in sites), return_exceptions=True)
            if isinstance(r, list) for h in r]
    budget = min(max_details, max(0, credits - len(sites) - reserve))

    async def build(i, site, url, info) -> Job:
        desc, loc = "", info["location"]
        if i < budget:
            d = await fc.scrape(url, formats=("markdown",))
            md = d.get("markdown", "")
            desc = re.sub(r"\s+", " ", re.sub(r"!\[.*?\]\(.*?\)|\[([^\]]*)\]\([^)]*\)", r"\1", md))[:20000]
            loc = loc or _detail_location(md)
        return Job(
            title=info["title"], company=site["name"], location=loc or site.get("location", ""),
            url=url, apply_url=url, source="careers", description=desc,
            posted_at=info["posted_at"] or datetime.now(timezone.utc), tags=[site.get("tag", "")],
        )

    return list(await asyncio.gather(*(build(i, *h) for i, h in enumerate(hits))))
