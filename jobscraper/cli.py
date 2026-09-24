"""CLI: fetch one source to data/raw, then score + build the dashboard.

  python -m jobscraper.cli fetch --source greenhouse
  python -m jobscraper.cli pipeline          # filter + score + build from data/raw/*.jsonl
  python -m jobscraper.cli all               # everything sequentially (no tmux)
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import time
from collections import Counter

from .config import RAW, profile
from .filters import apply_filters, window_start
from .http import Client
from .models import Job
from .sources import SOURCES

log = logging.getLogger("jobscraper")


async def fetch_source(name: str) -> int:
    mod = importlib.import_module(f"jobscraper.sources.{name}")
    t0 = time.time()
    async with Client() as client:
        jobs = await mod.fetch(client)
    RAW.mkdir(parents=True, exist_ok=True)
    tmp = RAW / f"{name}.jsonl.tmp"
    with tmp.open("w", encoding="utf-8") as f:
        for j in jobs:
            f.write(json.dumps(j.to_dict()) + "\n")
    tmp.replace(RAW / f"{name}.jsonl")
    start = window_start()
    today = sum(1 for j in jobs if j.posted_at and j.posted_at >= start)
    log.info("[%s] %d postings fetched, %d posted today (%.0fs)", name, len(jobs), today, time.time() - t0)
    return len(jobs)


def load_raw() -> list[Job]:
    jobs = []
    for p in sorted(RAW.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                jobs.append(Job.from_dict(json.loads(line)))
    return jobs


def fintech_companies() -> set[str]:
    """Lowercased names of companies tagged fintech in companies.yaml / careers.yaml."""
    import yaml

    from .config import ROOT, companies

    names = {c["name"].lower() for c in companies() if c.get("tag") == "fintech"}
    careers = yaml.safe_load((ROOT / "config" / "careers.yaml").read_text(encoding="utf-8"))["sites"]
    return names | {s["name"].lower() for s in careers if s.get("tag") == "fintech"}


def pipeline(hours: int | None = None) -> None:
    from . import store
    from .build_site import build
    from .profile import load_profiles
    from .scoring import score_jobs

    raw = load_raw()
    blocked = Counter()
    jobs = apply_filters(raw, profile(), window_start(hours=hours), blocked)
    log.info("%d raw postings -> %d relevant US jobs posted today", len(raw), len(jobs))
    log.info("dropped for work authorization: %s", dict(blocked) or "none")
    jobs = score_jobs(jobs, load_profiles(), fintech_companies())
    store.upsert(jobs)
    stats = {
        "raw": len(raw),
        "matched": len(jobs),
        "by_source": dict(Counter(j.source for j in jobs)),
        "companies": len({j.company for j in jobs}),
        "blocked": dict(blocked),
        "sponsors": sum("sponsors" in j.tags for j in jobs),
    }
    build(jobs, stats)
    log.info("dashboard built: site/index.html (%d jobs)", len(jobs))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--source", required=True, choices=SOURCES)
    for name in ("pipeline", "all"):
        p = sub.add_parser(name)
        p.add_argument("--hours", type=int, help="rolling window instead of 'today (ET)'")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S",
    )
    for noisy in ("httpx", "httpcore", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if args.cmd == "fetch":
        asyncio.run(fetch_source(args.source))
    elif args.cmd == "pipeline":
        pipeline(args.hours)
    else:
        async def run_all():
            await asyncio.gather(*(fetch_source(s) for s in SOURCES))
        asyncio.run(run_all())
        pipeline(args.hours)


if __name__ == "__main__":
    main()
