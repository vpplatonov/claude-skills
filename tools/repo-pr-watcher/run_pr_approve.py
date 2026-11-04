#!/usr/bin/env python3
"""Run /personal:repo-pr-approve unattended on a schedule (macOS launchd).

Config comes from the `## repo-* skills` section of ~/.claude/CLAUDE.md
(written by /personal:init-personal-skills); REPO_WATCHER_* environment
variables override it. See README.md.

    run_pr_approve.py                     run once, if inside the window and the lock is free
    run_pr_approve.py --dry-run           print resolved config, window and lock state; never runs claude
    run_pr_approve.py --interval-seconds  print the configured interval (used by install.sh)
"""
from __future__ import annotations  # `X | None` on macOS's system python3 (3.9)

import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"
# Same lock directory the skill's own "Concurrency lock" step uses, so a
# manual run and a scheduled run never overlap.
LOCK_DIR = Path.home() / ".claude" / "repo-pr-approve.lock.d"
LOG_DIR = Path.home() / "Library" / "Logs" / "repo-pr-watcher"
STALE_LOCK_SECONDS = 65 * 60
RUN_TIMEOUT_SECONDS = 55 * 60
SKILL = "/personal:repo-pr-approve"

# CLAUDE.md key -> (environment override, default)
KEYS = {
    "Local workspace": ("REPO_WATCHER_WORKSPACE", ""),
    "Slack channel ID": ("REPO_WATCHER_SLACK_CHANNEL", ""),  # empty: no run summary
    "PR watcher window": ("REPO_WATCHER_WINDOW", ""),        # empty: any time
    "PR watcher timezone": ("REPO_WATCHER_TZ", ""),          # empty: system local time
    "PR watcher interval": ("REPO_WATCHER_INTERVAL", "30m"),
}


def read_section() -> dict[str, str]:
    """Key/value lines of the `## repo-* skills` section, or {} if absent."""
    try:
        text = CLAUDE_MD.read_text()
    except FileNotFoundError:
        return {}
    m = re.search(r"^## repo-\* skills[ \t]*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return {}
    return {
        kv[1].strip(): kv[2].strip()
        for line in m[1].splitlines()
        if (kv := re.match(r"\s*-\s*([^:]+):\s*(.*)$", line))
    }


def is_placeholder(value: str) -> bool:
    return "<" in value or "your-org" in value


def load_config() -> dict[str, str]:
    section = read_section()
    cfg = {}
    for key, (env, default) in KEYS.items():
        value = os.environ.get(env) or section.get(key, "") or default
        cfg[key] = "" if is_placeholder(value) else value
    if not cfg["Local workspace"]:
        sys.exit(f"'Local workspace' is missing or a placeholder in {CLAUDE_MD} "
                 "(or set REPO_WATCHER_WORKSPACE) — run /personal:init-personal-skills first")
    return cfg


def parse_window(value: str) -> tuple[dtime, dtime] | None:
    if not value:
        return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", value)
    if not m:
        sys.exit(f"PR watcher window must look like 15:00-02:00, got {value!r}")
    h1, m1, h2, m2 = map(int, m.groups())
    return dtime(h1, m1), dtime(h2, m2)


def parse_interval(value: str) -> int:
    m = re.fullmatch(r"(\d+)\s*([smh]?)", value.strip())
    if not m:
        sys.exit(f"PR watcher interval must look like 30m, 1h or 600s, got {value!r}")
    return int(m[1]) * {"": 1, "s": 1, "m": 60, "h": 3600}[m[2]]


def in_window(now: datetime, window: tuple[dtime, dtime] | None) -> bool:
    if window is None:
        return True
    start, end, t = *window, now.time()
    if start <= end:
        return start <= t <= end
    # Window wraps past midnight (e.g. 15:00-02:00).
    return t >= start or t <= end


def lock_status() -> str:
    """'free', 'held', or 'stale'."""
    if not LOCK_DIR.exists():
        return "free"
    age = time.time() - LOCK_DIR.stat().st_mtime
    return "stale" if age > STALE_LOCK_SECONDS else "held"


def automation_directive(workspace: Path, slack_channel: str) -> str:
    if slack_channel:
        summary = (
            f"  2. Run summary: only if at least one PR got an action (approved and/or commented) this run, "
            f"ALSO send one summary message to Slack channel ID {slack_channel} listing each such PR "
            f"(repo#number), the verdict and a one-line reason. If nothing got an action, send nothing there. "
            f"This rollup is on top of each PR's own author DM from item 1, never a substitute for it."
        )
    else:
        summary = "  2. No run-summary channel is configured: send no summary message anywhere."
    return f"""AUTOMATED UNATTENDED RUN — nobody is watching this session; do not wait for any confirmation.

- Skip every "wait for the user's go-ahead" pause in the skill's instructions. Once the review protocol reaches a verdict for a PR (Round 1 finding, or Round 2 clean/finding), post it immediately (comment or approve) without asking.
- Isolation: never check out a PR branch in the existing working directory at {workspace}/<repo>. Use `git worktree add {workspace}/<repo>/.review-worktrees/pr-<number> <branch-or-sha>` and do all checkout/testing/tamper-testing inside that worktree; remove it when done (`git worktree remove --force <path>`, plus any throwaway tracking branch). Never run `git checkout` or `git stash` in the primary working directory.
- Slack, two independent sends:
  1. Per-PR author DM (the skill's "Notify the requester in Slack" step): whenever a comment or approval actually posts to GitHub, send that PR's author their short DM as the skill describes, without confirmation. Skip it if the Slack connector is unavailable.
{summary}

The skill's own "Concurrency lock" step (mkdir/rmdir on {LOCK_DIR}) is the real mutex against a manual run or another tick — follow it exactly, first thing, before step 1.
"""


def main(argv: list[str]) -> None:
    cfg = load_config()
    if "--interval-seconds" in argv:
        print(parse_interval(cfg["PR watcher interval"]))
        return

    workspace = Path(cfg["Local workspace"]).expanduser()
    window = parse_window(cfg["PR watcher window"])
    tz = ZoneInfo(cfg["PR watcher timezone"]) if cfg["PR watcher timezone"] else None
    now = datetime.now(tz).astimezone(tz)
    status = lock_status()

    if "--dry-run" in argv:
        for key, value in cfg.items():
            print(f"{key}: {value or '(empty)'}")
        print(f"now={now.isoformat()} in_window={in_window(now, window)} lock={status} "
              f"workspace_exists={workspace.is_dir()} claude={shutil.which('claude')}")
        print("(dry run — claude was NOT invoked)")
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=LOG_DIR / f"{now:%Y-%m-%d}.log", level=logging.INFO,
                        format="%(asctime)s %(message)s")

    if not in_window(now, window):
        logging.info("Outside window %s (now=%s) — skipping", cfg["PR watcher window"], now.isoformat())
        return
    if not workspace.is_dir():
        logging.error("Workspace %s does not exist — skipping", workspace)
        return
    claude = shutil.which("claude")
    if not claude:
        logging.error("claude not found on PATH — skipping")
        return
    if status == "held":
        logging.info("Lock held (manual run or another tick in progress) — skipping")
        return
    if status == "stale":
        logging.warning("Lock is stale (>%ds old) — removing; a previous run likely crashed", STALE_LOCK_SECONDS)
        LOCK_DIR.rmdir()

    logging.info("Starting %s run at %s", SKILL, now.isoformat())
    try:
        result = subprocess.run(
            [claude, "-p", "--dangerously-skip-permissions",
             "--append-system-prompt", automation_directive(workspace, cfg["Slack channel ID"]),
             SKILL],
            cwd=workspace, capture_output=True, text=True, timeout=RUN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logging.error("Run timed out after %d minutes", RUN_TIMEOUT_SECONDS // 60)
        return
    logging.info("Exit code: %s", result.returncode)
    logging.info("STDOUT:\n%s", result.stdout)
    if result.stderr:
        logging.info("STDERR:\n%s", result.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
