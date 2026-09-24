"""Filtering: posted today, US location, relevant title, seniority, dedupe."""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .models import Job

ET = ZoneInfo("America/New_York")

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}
US_CITIES = [
    "new york", "nyc", "san francisco", "sf bay", "bay area", "seattle", "austin", "boston",
    "chicago", "los angeles", "denver", "atlanta", "pittsburgh", "palo alto", "mountain view",
    "menlo park", "sunnyvale", "san jose", "san mateo", "redwood city", "cambridge", "brooklyn",
    "jersey city", "miami", "dallas", "houston", "philadelphia", "washington, d", "arlington",
    "salt lake", "portland", "san diego", "raleigh", "charlotte", "phoenix", "minneapolis",
]
_state_names = "|".join(re.escape(n.lower()) for n in STATES.values())
_state_abbr = "|".join(STATES)
US_RE = re.compile(
    rf"\b(united states|u\.s\.a?\.?|usa|us-remote|remote[\s,\-–(]*us\b|us[\s,\-–]*remote|americas?|north america|{_state_names})\b",
    re.I,
)
ABBR_RE = re.compile(rf"(?:,|\s-|\()\s*({_state_abbr})\b(?!\w)")
NON_US_RE = re.compile(
    r"\b(canada|toronto|vancouver|montreal|london|uk|united kingdom|ireland|dublin|germany|berlin|"
    r"munich|france|paris|india|bangalore|bengaluru|hyderabad|pune|singapore|australia|sydney|"
    r"japan|tokyo|brazil|mexico|poland|warsaw|spain|madrid|netherlands|amsterdam|israel|tel aviv|"
    r"emea|apac|latam|europe|philippines|argentina|colombia|romania|portugal|lisbon)\b",
    re.I,
)


def is_us(location: str) -> bool:
    loc = location or ""
    if not loc.strip():
        return False
    low = loc.lower()
    if US_RE.search(loc) or ABBR_RE.search(loc) or any(c in low for c in US_CITIES):
        return True
    if NON_US_RE.search(loc):
        return False
    # bare "Remote" with no country: keep (most US boards default to US)
    return low.strip() in {"remote", "remote - anywhere", "anywhere", "hybrid"}


def is_remote(job: Job) -> bool:
    return bool(re.search(r"\bremote\b", f"{job.location} {job.title}", re.I))


def window_start(now: datetime | None = None, hours: int | None = None) -> datetime:
    """Start of 'today' in US Eastern; if hours given, a rolling window instead."""
    now = now or datetime.now(timezone.utc)
    if hours:
        return now - timedelta(hours=hours)
    et = now.astimezone(ET)
    return et.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def posted_today(job: Job, start: datetime) -> bool:
    if job.posted_at is None:
        return False
    p = job.posted_at if job.posted_at.tzinfo else job.posted_at.replace(tzinfo=timezone.utc)
    return p >= start


def title_ok(title: str, prof: dict) -> bool:
    t = (title or "").lower()
    # whole words, so e.g. "sde" can't match inside "Gadsden"
    if not any(re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", t) for k in prof["title_include"]):
        return False
    if any(re.search(rf"\b{re.escape(k)}\b", t) for k in prof["title_exclude"]):
        return False
    return True


# Work authorization. Postings nearly always carry EEO boilerplate ("...without regard to citizenship
# status"), so patterns target explicit requirements, not the word "citizenship".
_US = r"(?:u\.?\s?s\.?|united states|american)"
BLOCKERS = [
    ("citizenship", rf"{_US} citizen(?:ship)?\s+(?:is\s+|are\s+)?(?:required|only|mandatory)"),
    ("citizenship", rf"must\s+(?:be|hold)\s+(?:an?\s+)?{_US}\s+citizen"),
    ("citizenship", rf"requires?\s+{_US}\s+citizenship"),
    ("citizenship", rf"(?:only|solely|exclusively)\s+(?:open|available)\s+to\s+{_US}\s+citizens"),
    ("citizenship", rf"{_US} citizens?\s+(?:or|and/or|and)\s+(?:lawful\s+)?(?:permanent residents?|green card holders?)"
                    rf"\s+(?:only|are required|is required)"),
    ("citizenship", r"(?:must|required to)\s+be\s+(?:a\s+)?(?:u\.?\s?s\.?\s+)?(?:lawful\s+)?permanent resident"),
    ("citizenship", r"green card holders?\s+only"),
    ("citizenship", rf"{_US} citizens?\s+or\s+(?:lawful\s+)?(?:permanent residents?|green card holders?)"),
    ("citizenship", rf"(?:required|requirements|qualifications|must have)\b[^.\n]{{0,40}}\b{_US} citizen\b(?!ship)"),
    ("export control", rf"(?:must|required to)\s+be\s+an?\s+{_US}\s+person"),
    ("export control", r"\bitar\b"),
    ("clearance", r"\b(?:ts\s*/\s*sci|top secret|secret clearance|public trust|polygraph)\b"),
    ("clearance", r"(?:active|current|obtain|maintain|eligib\w*|ability to (?:obtain|get))\b[^.\n]{0,40}\bsecurity clearance"),
    ("clearance", r"security clearance\s+(?:is\s+)?(?:required|needed|mandatory)"),
    ("no sponsorship", r"\b(?:not|unable to|cannot|can't|will not|won't|does not|doesn't|do not|don't|no)\b"
                       r"[^.\n]{0,40}\bsponsor"),
    ("no sponsorship", r"sponsorship\s+(?:is\s+|will\s+)?(?:not|un)(?:\s+be)?\s*available"),
    ("no sponsorship", r"without\s+(?:the\s+)?(?:need\s+for\s+|requiring\s+)?(?:current\s+or\s+future\s+|any\s+)?"
                       r"(?:visa\s+|employer\s+|employment\s+)?sponsorship"),
    ("no sponsorship", r"not\s+(?:eligible|able)\s+(?:for|to\s+(?:provide|offer))\s+(?:visa\s+)?sponsorship"),
]
BLOCKERS = [(reason, re.compile(p, re.I)) for reason, p in BLOCKERS]
SPONSORS = re.compile(
    r"(?:visa|h-?1b|immigration)\s+sponsorship\s+(?:is\s+)?(?:available|provided|offered)"
    r"|(?:will|may|can|does|is able to)\s+(?:consider\s+)?sponsor(?:ing)?\b"
    r"|sponsorship\s+(?:is\s+)?(?:available|offered|provided)|open to sponsor",
    re.I,
)


NEGATED = re.compile(r"\b(?:no|not|without|isn't|n't need|never)\b[^.\n]{0,20}$", re.I)


def work_auth(text: str) -> tuple[str, str]:
    """('blocked', reason) | ('sponsors', '') | ('unknown', ''). Unknown passes: most postings don't say."""
    text = text or ""
    for reason, rx in BLOCKERS:
        for m in rx.finditer(text):
            # "no security clearance required" / "not a U.S. citizen requirement" don't block
            if reason != "no sponsorship" and NEGATED.search(text[max(0, m.start() - 30):m.start()]):
                continue
            return "blocked", reason
    return ("sponsors", "") if SPONSORS.search(text or "") else ("unknown", "")


def dedupe(jobs: list[Job]) -> list[Job]:
    seen: dict[str, Job] = {}
    for j in jobs:
        prev = seen.get(j.id)
        # prefer ATS-sourced (direct apply links) over aggregator/search hits
        if prev is None or (prev.source in ("websearch", "boards") and j.source not in ("websearch", "boards")):
            seen[j.id] = j
    return list(seen.values())


def apply_filters(jobs: list[Job], prof: dict, start: datetime, blocked: Counter | None = None) -> list[Job]:
    """`blocked`, if given, collects counts of jobs dropped for work-authorization reasons."""
    out = []
    for j in jobs:
        if not posted_today(j, start):
            continue
        if not is_us(j.location):
            continue
        if not title_ok(j.title, prof):
            continue
        status, reason = work_auth(f"{j.title}\n{j.description}")
        if status == "blocked":
            if blocked is not None:
                blocked[reason] += 1
            continue
        if status == "sponsors" and "sponsors" not in j.tags:
            j.tags.append("sponsors")
        j.remote = j.remote or is_remote(j)
        out.append(j)
    return dedupe(out)
