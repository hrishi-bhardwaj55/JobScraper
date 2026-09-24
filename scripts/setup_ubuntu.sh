#!/usr/bin/env bash
# One-time system setup inside WSL Ubuntu (run as root: wsl -d Ubuntu -u root bash scripts/setup_ubuntu.sh)
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y -qq tmux python3-venv python3-pip curl ca-certificates gnupg

if ! command -v cloudflared >/dev/null; then
  # official Cloudflare apt repo
  mkdir -p --mode=0755 /usr/share/keyrings
  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
  echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
    > /etc/apt/sources.list.d/cloudflared.list
  apt-get update -qq
  apt-get install -y -qq cloudflared
fi

tmux -V
cloudflared --version
python3 --version
