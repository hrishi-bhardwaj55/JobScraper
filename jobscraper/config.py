from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
SITE = ROOT / "site"

load_dotenv(ROOT / ".env")


@lru_cache
def profile() -> dict:
    return yaml.safe_load((ROOT / "config" / "profile.yaml").read_text(encoding="utf-8"))


@lru_cache
def companies() -> list[dict]:
    return yaml.safe_load((ROOT / "config" / "companies.yaml").read_text(encoding="utf-8"))["companies"]


def companies_for(ats: str) -> list[dict]:
    return [c for c in companies() if c["ats"] == ats]


def env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    return "" if v.startswith("your-") else v  # unfilled .env placeholder
