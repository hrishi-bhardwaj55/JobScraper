from datetime import datetime, timedelta, timezone

from jobscraper.sources.careers import parse_listing, title_from_slug

SITE = {"name": "Microsoft", "link": r"apply\.careers\.microsoft\.com/careers/job/\d+"}

MD = (
    "[Software Engineer II - Azure\\\\\n\\\\\nUnited States, Washington, Redmond\\\\\n\\\\\nPosted 20 minutes ago]"
    "(https://apply.careers.microsoft.com/careers/job/111?src=x)\n"
    "[Apply](https://apply.careers.microsoft.com/careers/job/111)\n"
    "[Principal PM\\\\\n\\\\\nUnited States, Texas\\\\\n\\\\\nPosted 3 days ago](https://apply.careers.microsoft.com/careers/job/222)\n"
    "[Privacy](https://www.microsoft.com/privacy)\n"
)


def test_parse_listing_titles_locations_dates():
    got = parse_listing({"markdown": MD, "links": ["https://apply.careers.microsoft.com/careers/job/333"]}, SITE)
    a = got["https://apply.careers.microsoft.com/careers/job/111"]
    assert a["title"] == "Software Engineer II - Azure"
    assert "Redmond" in a["location"]
    assert datetime.now(timezone.utc) - a["posted_at"] < timedelta(minutes=25)
    assert got["https://apply.careers.microsoft.com/careers/job/222"]["posted_at"] < datetime.now(timezone.utc) - timedelta(days=2)
    assert "https://apply.careers.microsoft.com/careers/job/333" in got  # link-only fallback
    assert not any("privacy" in u for u in got)


def test_title_from_slug():
    assert title_from_slug("https://www.deshaw.com/careers/infrastructure-software-engineer-5829") == \
        "Infrastructure Software Engineer"
