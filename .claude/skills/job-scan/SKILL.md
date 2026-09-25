---
name: job-scan
description: Scan the web for US backend/software jobs posted in the last N hours (default 12), score them against the fintech and general resumes, refresh the dashboard, and report the top matches with apply links. Use when asked to find, scan, refresh or check new jobs / job matches, e.g. "/job-scan", "/job-scan 24", "any new jobs in the last 6 hours?".
---

# Job scan

Runs the JobScraper pipeline in this repo for a rolling window and reports the best matches.

## Arguments

`$ARGUMENTS` is an optional number of hours (default **12**). Accept forms like `12`, `24h`, `last 6 hours`;
extract the integer. Anything else in the arguments is a note from the user (e.g. "only Java") to apply when
summarizing.

## Steps

1. **Pick the hours** `H` from the arguments (default 12).

2. **Check the tmux session** (runs in WSL Ubuntu):

   ```bash
   wsl -d Ubuntu -u root -- tmux has-session -t jobs && echo running || echo stopped
   ```

3. **Run the scan.**
   - If `running`: refresh in place. This blocks until scoring finishes (usually 3–5 minutes); use a
     timeout of at least 600000 ms.

     ```bash
     powershell -ExecutionPolicy Bypass -File scripts/start.ps1 -Refresh -Hours H
     ```

   - If `stopped`: start the full stack (parallel fetch panes, pipeline, web server, trycloudflare tunnel).
     It stays in the foreground to keep WSL alive, so run it **in the background**, then wait until
     `data/logs/pipeline.log` contains `dashboard built` (poll with an until-loop, don't sleep blindly):

     ```bash
     powershell -ExecutionPolicy Bypass -File scripts/start.ps1 -Hours H
     ```

   - If WSL/tmux is unavailable, fall back to a plain sequential run (no tunnel):

     ```bash
     python -m jobscraper.cli all --hours H
     ```

4. **Check for failures**: `grep -h "WARNING\|Traceback" data/logs/*.log`. A source that failed only
   shrinks coverage; mention it, don't abort. Firecrawl "credits low" or "slots busy" warnings mean the
   careers source was skipped this run.

5. **Report**: run `python scripts/summary.py --top 15` and relay its output: the window, how many jobs
   were scanned / kept / hidden and why, the dashboard URL, and the table of top matches with apply links.
   Apply any user note (e.g. only show rows mentioning Java) when presenting the table. Point out standout
   rows briefly (strong score, sponsorship mentioned, fintech fit) — don't pad.

## Notes

- Filters (in `config/profile.yaml`): US locations, backend/SWE titles, ≤ `max_years_required` (7) years
  of required experience, and no citizenship/clearance/no-sponsorship roles. Postings that say nothing
  about experience or sponsorship are kept.
- The dashboard URL (`data/tunnel_url.txt`) changes whenever the tunnel restarts and works only while the
  PC is on.
- Firecrawl's free plan is ~1000 credits/month; each run uses ~10–25. Avoid running more than a few times
  a day.
- Never print or commit `.env` or anything under `resumes/`.
