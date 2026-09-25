"""Match scoring: semantic similarity + skill coverage + domain keywords, per resume."""
from __future__ import annotations

import re

import numpy as np

from .models import Job

# Skill vocabulary; matched as whole words (case-insensitive). Aliases map to a canonical name.
SKILLS = {
    "python": [], "java": [], "golang": [], "c++": ["cpp"], "c#": [], "rust": [], "scala": [],
    "kotlin": [], "typescript": [], "javascript": [], "sql": [], "bash": [],
    "spring": ["spring boot"], "fastapi": [], "django": [], "flask": [], "node.js": ["nodejs"],
    "react": [], "grpc": [], "rest api": ["restful", "rest apis"], "graphql": [],
    "kafka": [], "samza": [], "spark": [], "flink": [], "hadoop": [], "airflow": [],
    "redis": [], "postgresql": ["postgres"], "mysql": [], "mongodb": [], "cassandra": [],
    "dynamodb": [], "elasticsearch": [], "chromadb": [], "snowflake": [],
    "aws": ["amazon web services"], "gcp": ["google cloud"], "azure": [], "kubernetes": ["k8s"],
    "docker": [], "helm": [], "terraform": [], "ci/cd": ["cicd"], "linux": [], "microservices": [],
    "distributed systems": [], "multithreading": ["concurrency"], "low latency": ["low-latency"],
    "high throughput": ["high-throughput"], "system design": [], "observability": [],
    "machine learning": ["ml"], "llm": ["llms", "large language models"], "rag": [], "pytorch": [],
    "fix protocol": ["fix engine"], "trading": [], "fx": ["foreign exchange"], "payments": [],
    "post-trade": ["post trade"], "market data": [], "risk": [], "order management": ["oms"],
}
_PATTERNS = {
    canon: re.compile(r"(?<![\w+#])(" + "|".join(re.escape(a) for a in [canon, *alts]) + r")(?![\w+#])", re.I)
    for canon, alts in SKILLS.items()
}

W_EMBED, W_SKILL, W_DOMAIN = 0.55, 0.30, 0.15
_model = None


def skills_in(text: str) -> set[str]:
    return {k for k, rx in _PATTERNS.items() if rx.search(text or "")}


def _embedder():
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        _model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _model


def _chunks(text: str, words: int = 250) -> list[str]:
    w = text.split()
    return [" ".join(w[i:i + words]) for i in range(0, max(len(w), 1), words)] or [""]


def embed(texts: list[str]) -> np.ndarray:
    v = np.array(list(_embedder().embed(texts)))
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def profile_vector(text: str) -> np.ndarray:
    v = embed(_chunks(text)).mean(axis=0)
    return v / np.linalg.norm(v)


def job_text(j: Job) -> str:
    return f"{j.title}. {j.company}. {j.description[:2500]}"


def rescale(cos: float, lo: float = 0.64, hi: float = 0.80) -> float:
    """bge-small cosine between filtered SWE postings and a resume sits ~0.65–0.78 (measured); map to 0–1."""
    return float(np.clip((cos - lo) / (hi - lo), 0, 1))


def skill_score(profile_skills: set[str], job_skills: set[str]) -> tuple[float, list[str]]:
    if not job_skills:
        return 0.5, []  # no signal
    matched = sorted(profile_skills & job_skills)
    # smoothed toward 0.5 so a job listing one skill you have isn't a "perfect" skill match
    return (len(matched) + 1.5) / (len(job_skills) + 3), matched


def domain_score(text: str, keywords: list[str]) -> float:
    hits = sum(1 for k in keywords if re.search(rf"(?<!\w){re.escape(k)}(?!\w)", text, re.I))
    return min(hits / 4, 1.0)


def fintech_ness(text: str, keywords: list[str], fintech_company: bool) -> float:
    """0–1: how finance-flavored a job is (keywords, plus a floor for companies tagged fintech)."""
    return max(domain_score(text, keywords), 0.6 if fintech_company else 0.0)


def _has(words: list[str], text: str) -> int:
    return sum(1 for w in words if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", text, re.I))


def preference_score(job: Job, prefs: dict) -> float:
    """0–1: backend-flavored title (half) and Java-family stack (half; strongest when in the title)."""
    if not prefs:
        return 0.0
    title_hit = 1.0 if _has(prefs.get("backend_title", []), job.title) else 0.0
    stack = prefs.get("stack", [])
    if _has(stack, job.title):
        stack_hit = 1.0
    else:
        n = _has(stack, job.description[:6000])
        stack_hit = 0.7 if n >= 2 else 0.4 if n == 1 else 0.0
    return 0.5 * title_hit + 0.5 * stack_hit


def score_jobs(jobs: list[Job], profiles: dict[str, dict], fintech_companies: set[str] = frozenset(),
               prefs: dict | None = None) -> list[Job]:
    """Domain component is symmetric: the fintech resume earns a job's fintech-ness, the general resume
    its complement, so generic words ("cloud", "api") can't hand one resume a bonus on every job.
    `prefs` (profile.yaml `preferences`) takes `weight` of the score; the rest keeps its proportions."""
    if not jobs:
        return jobs
    prefs = prefs or {}
    w_pref = float(prefs.get("weight", 0.0))
    scale = 1.0 - w_pref
    pref = [preference_score(j, prefs) for j in jobs]
    texts = [job_text(j) for j in jobs]
    jv = embed(texts)
    fin_kw = next((p["boost_keywords"] for p in profiles.values() if p.get("domain") == "fintech"), [])
    fin = [fintech_ness(t, fin_kw, j.company.lower() in fintech_companies) for j, t in zip(jobs, texts)]
    for key, p in profiles.items():
        pv = profile_vector(p["text"])
        if p.get("resume_text"):
            # resume dominates; website adds shared context that would otherwise blur the two resumes
            pv = 0.7 * profile_vector(p["resume_text"]) + 0.3 * pv
            pv /= np.linalg.norm(pv)
        pskills = skills_in(p["text"])
        cos = jv @ pv
        for j, t, c, f, pr in zip(jobs, texts, cos, fin, pref):
            s_sk, matched = skill_score(pskills, skills_in(t))
            dom = f if p.get("domain") == "fintech" else 1 - f
            base = W_EMBED * rescale(c) + W_SKILL * s_sk + W_DOMAIN * dom
            s = 100 * (scale * base + w_pref * pr)
            j.scores[p["label"]] = round(s, 1)
            if s > j.score:
                j.score, j.best_resume, j.matched_skills = round(s, 1), p["label"], matched
    return sorted(jobs, key=lambda j: j.score, reverse=True)
