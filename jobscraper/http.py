"""Shared async HTTP client with retries, backoff and per-host concurrency limits."""
from __future__ import annotations

import asyncio
import logging
import random
from collections import defaultdict
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 JobScraper/1.0"


class Client:
    def __init__(self, per_host: int = 8, timeout: float = 30.0, retries: int = 3):
        self._client = httpx.AsyncClient(
            headers={"User-Agent": UA, "Accept": "application/json, text/html;q=0.9"},
            timeout=timeout,
            follow_redirects=True,
            http2=False,
        )
        self._sems: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(per_host))
        self.retries = retries

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self._client.aclose()

    async def request(self, method: str, url: str, **kw) -> httpx.Response | None:
        host = urlparse(url).netloc
        async with self._sems[host]:
            for attempt in range(self.retries + 1):
                try:
                    r = await self._client.request(method, url, **kw)
                except (httpx.TransportError, httpx.TimeoutException) as e:
                    log.debug("%s %s failed: %s", method, url, e)
                    r = None
                if r is not None and r.status_code < 400:
                    return r
                if r is not None and r.status_code in (400, 401, 403, 404, 410, 422):
                    log.debug("%s %s -> %s", method, url, r.status_code)
                    return None
                if attempt < self.retries:
                    await asyncio.sleep((2**attempt) + random.random())
            log.warning("giving up on %s %s", method, url)
            return None

    async def get_json(self, url: str, **kw):
        r = await self.request("GET", url, **kw)
        try:
            return r.json() if r is not None else None
        except ValueError:
            return None

    async def post_json(self, url: str, json=None, **kw):
        r = await self.request("POST", url, json=json, **kw)
        try:
            return r.json() if r is not None else None
        except ValueError:
            return None

    async def get_text(self, url: str, **kw) -> str | None:
        r = await self.request("GET", url, **kw)
        return r.text if r is not None else None
