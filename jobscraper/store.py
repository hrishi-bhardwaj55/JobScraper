"""SQLite store so reruns within a day don't duplicate and history is kept."""
from __future__ import annotations

import json
import sqlite3
from datetime import date

from .config import DATA
from .models import Job

DB = DATA / "jobs.db"


def connect() -> sqlite3.Connection:
    DATA.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute(
        """CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, first_seen TEXT, last_seen TEXT, score REAL, data TEXT)"""
    )
    con.execute("CREATE TABLE IF NOT EXISTS seen (url TEXT PRIMARY KEY, site TEXT, first_seen TEXT)")
    return con


def mark_seen(site: str, urls: list[str]) -> tuple[set[str], bool]:
    """Record URLs for a careers page. Returns (urls not seen before, whether this is the site's first run)."""
    today = date.today().isoformat()
    with connect() as con:
        first_run = con.execute("SELECT 1 FROM seen WHERE site = ? LIMIT 1", (site,)).fetchone() is None
        known = {u for (u,) in con.execute("SELECT url FROM seen WHERE site = ?", (site,))}
        new = set(urls) - known
        con.executemany("INSERT OR IGNORE INTO seen VALUES (?, ?, ?)", [(u, site, today) for u in new])
    return new, first_run


def upsert(jobs: list[Job]) -> None:
    today = date.today().isoformat()
    with connect() as con:
        for j in jobs:
            con.execute(
                """INSERT INTO jobs (id, first_seen, last_seen, score, data) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen, score=excluded.score,
                   data=excluded.data""",
                (j.id, today, today, j.score, json.dumps(j.to_dict())),
            )


def first_seen_map(ids: list[str]) -> dict[str, str]:
    with connect() as con:
        q = f"SELECT id, first_seen FROM jobs WHERE id IN ({','.join('?' * len(ids))})"
        return dict(con.execute(q, ids).fetchall()) if ids else {}
