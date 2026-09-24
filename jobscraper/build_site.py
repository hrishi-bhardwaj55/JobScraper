from __future__ import annotations

import json
from datetime import datetime

from jinja2 import Template

from .config import SITE, profile
from .filters import ET
from .models import Job


def build(jobs: list[Job], stats: dict) -> None:
    SITE.mkdir(exist_ok=True)
    rows = [j.to_dict() for j in jobs]
    for r in rows:
        r["description"] = r["description"][:600]  # keep payload small
    payload = {
        "generated_at": datetime.now(ET).strftime("%b %d, %Y %I:%M %p ET"),
        "min_score": profile().get("min_score", 0),
        "strong_score": profile().get("strong_score", 80),
        "resumes": [r["label"] for r in profile()["resumes"].values()],
        "stats": stats,
        "jobs": rows,
    }
    (SITE / "jobs.json").write_text(json.dumps(payload), encoding="utf-8")
    tpl = Template((SITE / "template.html").read_text(encoding="utf-8"))
    # inline the data so the page works as a single file too
    (SITE / "index.html").write_text(
        tpl.render(data=json.dumps(payload).replace("</", "<\\/")), encoding="utf-8"
    )
