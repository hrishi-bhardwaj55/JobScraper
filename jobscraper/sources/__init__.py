"""Job sources. Each module exposes `async def fetch(client) -> list[Job]`."""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone

from dateutil import parser as dateparser
from selectolax.parser import HTMLParser

log = logging.getLogger(__name__)

SOURCES = ["greenhouse", "lever", "ashby", "smartrecruiters", "workday", "boards", "websearch", "careers"]


def html_to_text(s: str | None, limit: int = 20000) -> str:
    if not s:
        return ""
    s = html.unescape(s)  # greenhouse double-encodes
    text = HTMLParser(s).text(separator=" ") if "<" in s else s
    return re.sub(r"\s+", " ", text).strip()[:limit]


def parse_dt(v) -> datetime | None:
    if v is None or v == "":
        return None
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=timezone.utc)
        d = dateparser.parse(str(v))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, TypeError):
        return None


async def gather_limited(coros, limit: int = 20):
    import asyncio

    sem = asyncio.Semaphore(limit)

    async def run(c):
        async with sem:
            try:
                return await c
            except Exception as e:  # one bad company must not kill the batch
                log.warning("source task failed: %r", e)
                return []

    results = await asyncio.gather(*(run(c) for c in coros))
    return [j for r in results for j in (r or [])]
