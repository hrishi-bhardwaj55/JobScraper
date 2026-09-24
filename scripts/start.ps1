# Windows launcher: runs the tmux pipeline inside WSL Ubuntu and attaches to it.
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Refresh
param([switch]$Refresh)
$arg = if ($Refresh) { "--refresh" } else { "" }
wsl -d Ubuntu -u root --cd /mnt/c/Projects/JobScraper -- bash scripts/run.sh $arg
