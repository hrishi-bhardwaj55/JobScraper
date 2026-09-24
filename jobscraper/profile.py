"""Build candidate profile texts from resumes + personal website."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from pypdf import PdfReader
from selectolax.parser import HTMLParser

from .config import DATA, ROOT, env, profile

log = logging.getLogger(__name__)
CACHE = DATA / "profile_cache.json"


def pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return re.sub(r"\s+", " ", " ".join(p.extract_text() or "" for p in reader.pages)).strip()


def website_text(base: str, max_pages: int = 10) -> str:
    """Text of the site's home page plus same-site pages it links to (breadth-first, capped)."""
    if not base:
        return ""
    host = urlparse(base).netloc
    queue, seen, out = [base], set(), []
    with httpx.Client(timeout=20, follow_redirects=True) as c:
        while queue and len(seen) < max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            try:
                r = c.get(url)
                r.raise_for_status()
            except httpx.HTTPError as e:
                log.warning("website page %s failed: %s", url, e)
                continue
            h = HTMLParser(r.text)
            for a in h.css("a[href]"):
                link = urljoin(url, a.attributes.get("href") or "").split("#")[0]
                if urlparse(link).netloc == host and not re.search(r"\.(pdf|png|jpe?g|svg|zip)$", link, re.I):
                    queue.append(link)
            for s in h.css("script,style,nav,footer"):
                s.decompose()
            if h.body:
                out.append(h.body.text(separator=" "))
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def resolve_resume(path: str) -> Path | None:
    """A configured resume path may be a PDF or a folder; for a folder use its newest PDF."""
    p = ROOT / path
    if p.is_dir():
        pdfs = sorted(p.glob("*.pdf"), key=lambda f: f.stat().st_mtime, reverse=True)
        return pdfs[0] if pdfs else None
    return p if p.exists() else None


def load_profiles(refresh: bool = False) -> dict[str, dict]:
    """Returns {resume_key: {label, text, boost_keywords}}; website text is appended to each resume."""
    prof = profile()
    files = {k: resolve_resume(v["path"]) for k, v in prof["resumes"].items()}
    sig = {k: f"{f}:{f.stat().st_mtime}" if f else "" for k, f in files.items()}
    if CACHE.exists() and not refresh:
        cached = json.loads(CACHE.read_text(encoding="utf-8"))
        if cached.get("sig") == sig:
            return cached["profiles"]

    site = website_text(env("PROFILE_WEBSITE") or prof.get("website", ""))
    profiles = {}
    for key, r in prof["resumes"].items():
        path = files[key]
        if path is None:
            log.warning("resume %s missing at %s; using website text only", key, ROOT / r["path"])
            text = ""
        else:
            text = pdf_text(path)
            log.info("resume %s: %s (%d chars)", key, path.relative_to(ROOT), len(text))
        profiles[key] = {
            "label": r["label"],
            "resume_text": text,
            "text": f"{text} {site}".strip(),
            "boost_keywords": r.get("boost_keywords", []),
            "domain": r.get("domain", "general"),
        }
    DATA.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps({"sig": sig, "profiles": profiles}), encoding="utf-8")
    return profiles
