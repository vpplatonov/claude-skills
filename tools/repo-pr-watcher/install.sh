#!/usr/bin/env bash
# Install (or reinstall after a config change) the repo-pr-watcher launchd job
# for the current user. macOS only. Config: see README.md.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
label="local.repo-pr-watcher"
plist="$HOME/Library/LaunchAgents/$label.plist"
logs="$HOME/Library/Logs/repo-pr-watcher"

command -v claude >/dev/null || { echo "claude not found on PATH" >&2; exit 1; }
command -v gh >/dev/null || { echo "gh not found on PATH" >&2; exit 1; }

# Fails with a clear message if the config is missing or still placeholders.
"$here/run_pr_approve.py" --dry-run
interval="$("$here/run_pr_approve.py" --interval-seconds)"

mkdir -p "$logs" "$HOME/Library/LaunchAgents"
sed -e "s|@HOME@|$HOME|g" \
    -e "s|@PATH@|$PATH|g" \
    -e "s|@LABEL@|$label|g" \
    -e "s|@SCRIPT@|$here/run_pr_approve.py|g" \
    -e "s|@LOGS@|$logs|g" \
    -e "s|@INTERVAL@|$interval|g" \
    "$here/launchd.plist.template" > "$plist"
plutil -lint "$plist" >/dev/null

launchctl unload "$plist" 2>/dev/null || true
launchctl load "$plist"
echo "Loaded $label: every ${interval}s, logs in $logs"
