import pytest

from jobscraper.models import Job
from jobscraper.scoring import domain_score, skill_score, skills_in


def test_skills_whole_word():
    s = skills_in("We use Go and Java; experience with Kafka, k8s and C++ preferred. Let's go!")
    assert {"java", "kafka", "kubernetes", "c++"} <= s
    assert "golang" not in s  # bare "go" is too ambiguous


def test_skill_score_coverage():
    score, matched = skill_score({"java", "kafka", "aws"}, {"java", "kafka", "rust", "gcp"})
    assert score == 3.5 / 7 and matched == ["java", "kafka"]


def test_domain_score():
    assert domain_score("low latency trading and FX settlement", ["trading", "fx", "settlement"]) == 0.75
    assert domain_score("marketing website", ["trading"]) == 0.0


@pytest.mark.slow
def test_fintech_job_prefers_fintech_resume():
    from jobscraper.scoring import score_jobs

    profiles = {
        "fintech": {"label": "Fintech", "text": "Built FX execution and post-trade settlement systems in Java "
                    "with low latency market data and FIX engine at a capital markets firm.",
                    "boost_keywords": ["trading", "fx", "post-trade", "market data"], "domain": "fintech"},
        "swe": {"label": "SWE", "text": "Built React web apps and Kubernetes microservices on AWS; "
                "LLM applications with FastAPI and vector databases.",
                "boost_keywords": ["kubernetes", "llm", "cloud"]},
    }
    job = Job(title="Software Engineer, Trading Systems", company="HRT", location="New York, NY",
              url="u", source="greenhouse",
              description="Build low latency trading and market data systems in Java; FX and post-trade.")
    [scored] = score_jobs([job], profiles)
    assert scored.best_resume == "Fintech"
    assert scored.scores["Fintech"] > scored.scores["SWE"]
