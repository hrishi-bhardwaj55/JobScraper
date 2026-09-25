#!/usr/bin/env bash
# Parallel scrape in tmux, then score/build, serve, and publish via a trycloudflare quick tunnel.
#
#   scripts/run.sh            full start: fetch (parallel panes) -> pipeline -> serve -> tunnel
#   scripts/run.sh --refresh  re-run fetch + pipeline only (server/tunnel keep running)
#   add --hours N to either   jobs posted in the last N hours instead of "today (ET)"
#   tmux attach -t jobs       watch it
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
SESSION=jobs
PORT=${PORT:-8080}
SOURCES=(greenhouse lever ashby smartrecruiters workday boards websearch careers)
PY="$ROOT/.venv/bin/python"

REFRESH=0
HOURS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --refresh) REFRESH=1 ;;
    --hours) HOURS="$2"; shift ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac
  shift
done
# tmux panes inherit nothing from this shell, so pass the window on each command line
ENVP=""
[[ -n "$HOURS" ]] && ENVP="JOBSCRAPER_HOURS=$HOURS "

if [[ ! -x "$PY" ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
mkdir -p data/raw data/logs

launch_fetch() {
  # one pane per source; each signals completion with `tmux wait-for`
  tmux kill-window -t "$SESSION:fetch" 2>/dev/null || true
  tmux new-window -d -t "$SESSION" -n fetch -c "$ROOT"
  for i in "${!SOURCES[@]}"; do
    s=${SOURCES[$i]}
    [[ $i -gt 0 ]] && tmux split-window -d -t "$SESSION:fetch" -c "$ROOT" && tmux select-layout -t "$SESSION:fetch" tiled >/dev/null
    tmux send-keys -t "$SESSION:fetch.$i" \
      "$ENVP$PY -m jobscraper.cli fetch --source $s 2>&1 | tee data/logs/$s.log; tmux wait-for -S done-$s" Enter
  done

  local waits=""
  for s in "${SOURCES[@]}"; do waits+="tmux wait-for done-$s; "; done
  tmux kill-window -t "$SESSION:pipeline" 2>/dev/null || true
  tmux new-window -d -t "$SESSION" -n pipeline -c "$ROOT"
  tmux send-keys -t "$SESSION:pipeline" \
    "echo 'waiting for ${#SOURCES[@]} fetchers…'; $waits $ENVP$PY -m jobscraper.cli pipeline 2>&1 | tee data/logs/pipeline.log; tmux wait-for -S pipeline-done" Enter
}

if [[ $REFRESH == 1 ]]; then
  tmux has-session -t "$SESSION" 2>/dev/null || { echo "session not running; run without --refresh"; exit 1; }
  launch_fetch
  tmux wait-for pipeline-done
  echo "refreshed. $(cat data/tunnel_url.txt 2>/dev/null)"
  exit 0
fi

tmux kill-session -t "$SESSION" 2>/dev/null || true
tmux new-session -d -s "$SESSION" -n main -c "$ROOT"
tmux send-keys -t "$SESSION:main" "echo 'JobScraper control window. Refresh: scripts/run.sh --refresh'" Enter

launch_fetch

# placeholder page so the tunnel works while the first run finishes
[[ -f site/index.html ]] || echo '<meta http-equiv="refresh" content="20"><p style="font:16px system-ui;padding:40px">Scraping today&#39;s jobs… this page refreshes automatically.</p>' > site/index.html

tmux new-window -d -t "$SESSION" -n serve -c "$ROOT"
tmux send-keys -t "$SESSION:serve" "$PY -m http.server $PORT --bind 127.0.0.1 -d site" Enter

rm -f data/tunnel_url.txt data/logs/tunnel.log
tmux new-window -d -t "$SESSION" -n tunnel -c "$ROOT"
tmux send-keys -t "$SESSION:tunnel" "cloudflared tunnel --no-autoupdate --url http://127.0.0.1:$PORT 2>&1 | tee data/logs/tunnel.log" Enter

for _ in $(seq 1 60); do
  url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' data/logs/tunnel.log 2>/dev/null | head -1 || true)
  [[ -n "$url" ]] && break
  sleep 1
done
if [[ -n "${url:-}" ]]; then
  echo "$url" > data/tunnel_url.txt
  echo "Public dashboard: $url"
else
  echo "Tunnel URL not found yet; check: tmux attach -t $SESSION (window 'tunnel')"
fi

tmux wait-for pipeline-done
echo "Pipeline finished. Dashboard: ${url:-http://localhost:$PORT}"

# WSL stops the distro (and the tunnel) once no wsl.exe session is attached, so stay in the foreground.
if [[ -t 1 ]]; then
  exec tmux attach -t "$SESSION"
else
  while tmux has-session -t "$SESSION" 2>/dev/null; do sleep 30; done
fi
