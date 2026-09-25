"""Print the latest run's top matches (used by the job-scan skill).

  python scripts/summary.py [--top 15]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    data = json.loads((ROOT / "site" / "jobs.json").read_text(encoding="utf-8"))
    stats, jobs = data["stats"], data["jobs"]
    url_file = ROOT / "data" / "tunnel_url.txt"
    window = f"last {stats['window_hours']} hours" if stats.get("window_hours") else "today (ET)"

    print(f"Window: {window} · generated {data['generated_at']}")
    print(f"Scanned {stats['raw']:,} postings -> {len(jobs)} relevant jobs at {stats['companies']} companies")
    if stats.get("blocked"):
        print("Hidden: " + ", ".join(f"{v} {k}" for k, v in sorted(stats["blocked"].items(), key=lambda x: -x[1])))
    print(f"Dashboard: {url_file.read_text().strip() if url_file.exists() else 'site/index.html (tunnel not running)'}")
    print()
    print("| Score | Resume | Role | Company | Location | Exp | Apply |")
    print("|---|---|---|---|---|---|---|")
    for j in jobs[: args.top]:
        exp = f"{j['years_required']}+ yrs" if j.get("years_required") is not None else "–"
        loc = j["location"].replace("|", "/")[:40]
        title = j["title"].replace("|", "/")[:70]
        flag = " · sponsors" if "sponsors" in j.get("tags", []) else ""
        print(f"| {round(j['score'])} | {j['best_resume']} | {title}{flag} | {j['company']} | {loc} | {exp} | "
              f"[apply]({j['apply_url']}) |")


if __name__ == "__main__":
    main()
