# repo-pr-watcher

Runs `/personal:repo-pr-approve` on a schedule (macOS launchd), **fully
unattended**: it posts real GitHub approvals and comments, and Slack DMs to
PR authors, with no human confirmation. That's the point of it — install it
only if that's what you want. It is not part of the plugin and does nothing
until you run `install.sh`.

Each run reviews PRs in an isolated `git worktree` per repo, never in your
own checkouts, and shares the skill's concurrency lock
(`~/.claude/repo-pr-approve.lock.d`): a manual `/personal:repo-pr-approve`
in progress blocks the next scheduled tick, and vice versa.

## Configure

Run `/personal:init-personal-skills` and say yes to the PR watcher step, or
edit the `## repo-* skills` section of `~/.claude/CLAUDE.md` yourself:

| Key | Default | Meaning |
|---|---|---|
| `Local workspace` | — (required) | Folder the run starts in; repos are cloned under it |
| `Slack channel ID` | empty | Company-specific channel for the run summary; empty = no summary |
| `PR watcher window` | empty = any time | Active hours, e.g. `15:00-02:00` (may wrap past midnight) |
| `PR watcher timezone` | system local | IANA name for the window, e.g. `Europe/Berlin` |
| `PR watcher interval` | `30m` | How often launchd fires: `10m`, `30m`, `1h`, `600s` |

Environment variables override the file: `REPO_WATCHER_WORKSPACE`,
`REPO_WATCHER_SLACK_CHANNEL`, `REPO_WATCHER_WINDOW`, `REPO_WATCHER_TZ`,
`REPO_WATCHER_INTERVAL`.

Window, timezone, workspace and Slack channel are read fresh on every run.
The interval is baked into the launchd job: rerun `install.sh` after
changing it.

## Install / uninstall

```bash
./install.sh      # validates config (dry run), renders the plist, loads it
./uninstall.sh    # unloads and removes it; logs are kept
```

Check it's loaded: `launchctl list | grep local.repo-pr-watcher`

## Try it safely

```bash
./run_pr_approve.py --dry-run
```

Prints the resolved config, whether now is inside the window, the lock
state, and whether the workspace and `claude` are found — without invoking
`claude`. Running the script with no arguments does a real run.

## Logs

`~/Library/Logs/repo-pr-watcher/`: one `YYYY-MM-DD.log` per day (window
checks, skips, full `claude` output) plus `launchd.out.log` /
`launchd.err.log`. They contain PR titles and review text from your org —
they live outside this repo on purpose; never commit them.

## What a run does

```
claude -p --dangerously-skip-permissions --append-system-prompt "<directive>" /personal:repo-pr-approve
```

started in `Local workspace`. The appended directive, for this run only:

1. Posts each verdict (comment or approval) without waiting for a go-ahead.
2. Uses an isolated worktree per PR; never touches your checkouts.
3. Sends each PR author their Slack DM when something posts, and — only if
   `Slack channel ID` is set and at least one PR got an action — one run
   summary to that channel.

On Linux, run the same script from cron instead of launchd.
