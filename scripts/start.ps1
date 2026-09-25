# Windows launcher: runs the tmux pipeline inside WSL Ubuntu and attaches to it.
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Refresh
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Refresh -Hours 12
param([switch]$Refresh, [int]$Hours = 0)
$wslArgs = @()
if ($Refresh) { $wslArgs += "--refresh" }
if ($Hours -gt 0) { $wslArgs += @("--hours", "$Hours") }
wsl -d Ubuntu -u root --cd /mnt/c/Projects/JobScraper -- bash scripts/run.sh @wslArgs
