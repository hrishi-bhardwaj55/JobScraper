from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    source: str
    posted_at: datetime | None = None
    apply_url: str = ""
    description: str = ""
    remote: bool = False
    tags: list[str] = field(default_factory=list)
    # filled by scoring
    scores: dict[str, float] = field(default_factory=dict)
    best_resume: str = ""
    score: float = 0.0
    matched_skills: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        key = f"{norm(self.company)}|{norm(self.title)}|{norm(self.location)}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        d["posted_at"] = self.posted_at.isoformat() if self.posted_at else None
        d["apply_url"] = self.apply_url or self.url
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        d = dict(d)
        d.pop("id", None)
        if d.get("posted_at"):
            d["posted_at"] = datetime.fromisoformat(d["posted_at"])
        return cls(**d)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
