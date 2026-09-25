from datetime import datetime, timedelta, timezone

import pytest

from jobscraper.filters import apply_filters, is_us, required_years, title_ok, window_start, work_auth
from jobscraper.models import Job

PROF = {
    "title_include": ["software engineer", "backend", "developer"],
    "title_exclude": ["staff", "principal", "manager", "intern"],
}


@pytest.mark.parametrize("loc", [
    "New York, NY", "San Francisco, California", "Remote - US", "United States", "Remote (USA)",
    "Seattle, WA / Dublin", "Pittsburgh", "US-Remote",
])
def test_us_locations(loc):
    assert is_us(loc)


@pytest.mark.parametrize("loc", ["London, UK", "Toronto, Canada", "Bengaluru", "Remote - EMEA", ""])
def test_non_us_locations(loc):
    assert not is_us(loc)


def test_titles():
    assert title_ok("Software Engineer II, Payments", PROF)
    assert title_ok("Senior Backend Engineer", PROF)
    assert not title_ok("Staff Software Engineer", PROF)
    assert not title_ok("Engineering Manager", PROF)
    assert not title_ok("Account Executive", PROF)


def test_window_start_is_et_midnight():
    now = datetime(2026, 9, 24, 3, 0, tzinfo=timezone.utc)  # 23:00 ET on the 23rd
    assert window_start(now) == datetime(2026, 9, 23, 4, 0, tzinfo=timezone.utc)


def test_apply_filters_and_dedupe():
    now = datetime.now(timezone.utc)
    mk = lambda **kw: Job(**{"title": "Software Engineer", "company": "Acme", "location": "New York, NY",
                             "url": "u", "source": "greenhouse", "posted_at": now, **kw})
    jobs = [
        mk(),
        mk(source="websearch"),                          # duplicate, lower priority
        mk(company="Old", posted_at=now - timedelta(days=3)),
        mk(company="UK", location="London, UK"),
        mk(company="Mgr", title="Engineering Manager"),
    ]
    out = apply_filters(jobs, PROF, window_start(hours=24))
    assert len(out) == 1 and out[0].source == "greenhouse"


def test_title_keywords_are_whole_words():
    prof = {"title_include": ["sde", "swe", "software engineer"], "title_exclude": []}
    assert not title_ok("Psychiatric Nurse Practitioner - Gadsden", prof)
    assert title_ok("SDE II, Payments", prof)


EEO = ("We are an equal opportunity employer and do not discriminate on the basis of race, religion, "
       "national origin, citizenship status, age, disability or veteran status.")


@pytest.mark.parametrize("text,reason", [
    ("Applicants must be U.S. citizens due to contract requirements.", "citizenship"),
    ("US citizenship is required for this role.", "citizenship"),
    ("This position requires U.S. citizenship.", "citizenship"),
    ("Candidates must be a lawful permanent resident or citizen.", "citizenship"),
    ("Must hold an active TS/SCI clearance with polygraph.", "clearance"),
    ("Ability to obtain and maintain a security clearance.", "clearance"),
    ("Access to ITAR-controlled data; must be a U.S. person.", "export control"),
    ("We are unable to sponsor visas for this position.", "no sponsorship"),
    ("This role is not eligible for visa sponsorship.", "no sponsorship"),
    ("Must be authorized to work in the US without the need for current or future visa sponsorship.",
     "no sponsorship"),
    ("Sponsorship is not available for this role.", "no sponsorship"),
    ("The company will not sponsor employment visas.", "no sponsorship"),
    ("What You'll Need: US Citizen or Green Card holder. Strong Linux skills.", "citizenship"),
    ("Required Qualifications US Citizen Bachelor's degree in computer science", "citizenship"),
])
def test_work_auth_blocks(text, reason):
    assert work_auth(f"Build distributed systems. {text} {EEO}") == ("blocked", reason)


@pytest.mark.parametrize("text", [
    "",
    EEO,
    "No security clearance required. " + EEO,
    "Knowledge of FIX protocol and trading systems.",
    "Complete Form I-9 via E-Verify with the U.S. Citizenship and Immigration Services.",
    "Authorized to work in the United States and a resident in a US time zone.",
])
def test_work_auth_unknown_passes(text):
    assert work_auth(text) == ("unknown", "")


@pytest.mark.parametrize("text", [
    "Capital One will consider sponsoring a new qualified applicant for employment authorization.",
    "Visa sponsorship is available for this position.",
    "We sponsor H-1B visas. Sponsorship available.",
])
def test_work_auth_sponsors(text):
    assert work_auth(text + " " + EEO)[0] == "sponsors"


@pytest.mark.parametrize("text,years", [
    ("Basic Qualifications: At least 4 years of experience in software engineering.", 4),
    ("Requirements: 8+ years of professional software development experience.", 8),
    ("You have 5-8 years of backend engineering experience.", 5),
    ("Minimum of ten years experience building distributed systems.", 10),
    ("Experience: 3+ years", 3),
    ("BS with 8+ years of experience, or MS with 6+ years of experience.", 6),
    ("3+ years of Java experience. 6+ years of professional software engineering experience.", 6),
    ("Required: 4+ years of software experience. Preferred Qualifications: 10+ years of experience leading teams.", 4),
    ("5+ years of experience with Kafka preferred. 2+ years of professional experience.", 2),
    ("We have been in business for 25 years old company. Build great APIs.", None),
    ("Join our team and build scalable backend services in Java.", None),
])
def test_required_years(text, years):
    assert required_years(text) == years


def test_experience_filter_drops_over_limit():
    now = datetime.now(timezone.utc)
    prof = {**PROF, "max_years_required": 7}
    mk = lambda d: Job(title="Software Engineer", company=d[:5], location="New York, NY", url="u",
                       source="greenhouse", posted_at=now, description=d)
    out = apply_filters([mk("8+ years of experience required."), mk("7+ years of experience."), mk("")],
                        prof, window_start(hours=24))
    assert sorted(j.years_required or 0 for j in out) == [0, 7]


def test_required_years_ignores_preferred_prose():
    d = ("Even if you do not meet all of the preferred qualifications and skills listed, we encourage you to apply. "
         "Basic qualifications - 3+ years of non-internship professional software development experience "
         "- 2+ years of non-internship design or architecture experience")
    assert required_years(d) == 3
