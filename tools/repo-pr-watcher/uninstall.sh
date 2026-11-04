#!/usr/bin/env bash
# Stop and remove the repo-pr-watcher launchd job. Logs are kept.
set -euo pipefail

plist="$HOME/Library/LaunchAgents/local.repo-pr-watcher.plist"
if [ -f "$plist" ]; then
  launchctl unload "$plist" 2>/dev/null || true
  rm "$plist"
  echo "Unloaded and removed $plist"
else
  echo "Not installed ($plist not found)"
fi
