import json
from pathlib import Path

from jobscraper.sources import ashby, greenhouse, lever, parse_dt
from jobscraper.sources.websearch import to_job

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def test_greenhouse_uses_first_published():
    data = load("greenhouse")
    jobs = greenhouse.parse(data, "Stripe")
    assert len(jobs) == len(data["jobs"])
    j, raw = jobs[0], data["jobs"][0]
    assert j.posted_at == parse_dt(raw["first_published"])
    assert j.apply_url == raw["absolute_url"]
    assert j.description and "<" not in j.description[:200]


def test_lever_fields():
    jobs = lever.parse(load("lever"), "Palantir")
    assert jobs and all(j.posted_at and j.apply_url.startswith("https://jobs.lever.co") for j in jobs)


def test_ashby_fields():
    jobs = ashby.parse(load("ashby"), "Ramp")
    assert jobs and jobs[0].posted_at is not None
    assert jobs[0].apply_url.startswith("https://jobs.ashbyhq.com")


def test_parse_dt_epoch_ms_and_iso():
    assert parse_dt(1786469891368).year == 2026
    assert parse_dt("2026-09-24T20:14:46.889Z").tzinfo is not None
    assert parse_dt("garbage") is None


def test_websearch_linkedin_title():
    j = to_job("https://www.linkedin.com/jobs/view/software-engineer-at-acme-123",
               "Acme hiring Software Engineer in New York, NY | LinkedIn", "")
    assert (j.company, j.title, j.location) == ("Acme", "Software Engineer", "New York, NY")
    assert to_job("https://www.linkedin.com/jobs/search?keywords=x", "Jobs", "") is None
