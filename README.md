# JobScraper

Finds US software jobs **posted today**, scores each against two resumes (Fintech, General SWE) plus
a personal website, and publishes a dashboard with a match score and
a direct **Apply** button via a trycloudflare quick tunnel.

## Run

```powershell
# from Windows (runs everything inside WSL Ubuntu + tmux and attaches)
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
# re-scrape while the server/tunnel stay up (from another terminal)
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Refresh
# only jobs posted in the last 12 hours (works with or without -Refresh)
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Refresh -Hours 12
```

In Claude Code, the `/job-scan` skill (`.claude/skills/job-scan`) does all of this and reports the top
matches in chat: `/job-scan` (last 12 hours) or `/job-scan 24`.

The public URL is printed and saved to `data/tunnel_url.txt`. It changes every time the tunnel restarts
and only works while this PC is on (a trycloudflare limitation). Detach from tmux with `Ctrl-b d`
(the script keeps WSL alive); `tmux kill-session -t jobs` stops everything.

tmux layout (session `jobs`): `fetch` (one pane per source, run in parallel) → `pipeline`
(waits on all fetchers with `tmux wait-for`, then filter/score/build) · `serve` (http.server on :8080) ·
`tunnel` (cloudflared).

Without tmux: `python -m jobscraper.cli all [--hours 12]` then open `site/index.html`;
`python scripts/summary.py` prints the top matches.

## Setup

1. Put resumes at `resumes/resume_fintech.pdf` and `resumes/resume_swe.pdf`.
2. Copy `.env.example` to `.env`. `PROFILE_WEBSITE` (optional) adds your site's text to the profile;
   `TAVILY_API_KEY` enables web search; `FIRECRAWL_API_KEY` enables careers-page scraping.
   Without a key, that source is skipped. Firecrawl's free plan is 1000 credits/month: one run uses ~10
   (1 per careers page) plus 1 per new job detail (max 15), so about one refresh a day fits.
3. One-time WSL setup (already done on this machine): `wsl --install -d Ubuntu --no-launch`, then
   `wsl -d Ubuntu -u root bash scripts/setup_ubuntu.sh` (tmux, python venv, cloudflared).

## Sources

| Source | What | Date field |
|---|---|---|
| greenhouse / lever / ashby / smartrecruiters / workday | Company career pages via public ATS JSON APIs (`config/companies.yaml`, ~300 companies) | first-published / created / "Posted Today" |
| boards | Remotive, RemoteOK, Himalayas, HN "Who is hiring?" | publication time |
| boards (Amazon) | amazon.jobs public search API | posted date (ET) |
| careers | **Firecrawl** scrapes custom career pages with no public API (`config/careers.yaml`): Google, Microsoft, Apple, Goldman Sachs, JPMorgan, Jane Street, Citadel, D. E. Shaw, Bloomberg, Optiver. New relevant jobs get their detail page scraped for a full description | "Posted X ago" when shown, else first day the URL appears (the first run per site only seeds history) |
| websearch | Tavily search limited to the past day on LinkedIn, Indeed, ATS domains (Firecrawl search optional: `firecrawl_search` in profile.yaml) | search-engine recency |

Add companies in `scripts/candidates.yaml` (or from `data/discovered_companies.txt`, which websearch fills
with ATS boards it sees that aren't tracked yet), then `python scripts/verify_companies.py`.

## Filters

`config/profile.yaml`: US locations; backend/SWE titles (whole-word include/exclude lists); required
experience at most `max_years_required` (7), read from the required-qualifications part of the posting
(preferred sections and "BS + 8 or MS + 6" alternatives handled); no US-citizenship, clearance, ITAR or
no-sponsorship roles. Postings that don't state experience or sponsorship are kept.

## Scoring

Per resume, 0–100 = 55% semantic similarity (local `bge-small-en-v1.5` embeddings; resume + website text vs
job title/description) + 30% skill coverage (share of the job's recognized skills you have) + 15% domain
keywords (`boost_keywords` in `config/profile.yaml`), scaled to 85%; the remaining 15% is a preference for
backend titles and a Java/JVM stack (`preferences` in `config/profile.yaml`). The dashboard shows the best-fitting resume and both
scores. Title/seniority filters and search queries are also in `config/profile.yaml`.

## Tests

`python -m pytest -q`
