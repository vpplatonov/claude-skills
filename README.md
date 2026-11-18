# Claude Code skills

Personal Claude Code skills, packaged as a plugin marketplace: PR review
workflows across a GitHub org, git hygiene, CI test conventions, and a set
of default working rules (PII, ticket naming, Python typing, Jira linking).

New to Claude Code? Start with [ONBOARDING.md](ONBOARDING.md) — paste it
into Claude Code for a guided setup walkthrough.

## Install

In Claude Code:

```
/plugin marketplace add vpplatonov/claude-skills
/plugin install personal@vpplatonov-skills
```

Pull updates later with `/plugin marketplace update vpplatonov-skills`.

Skills are namespaced, e.g. `/personal:repo-pr-review`. Claude also picks
them up automatically from natural requests ("check my PRs").

## Configure your project

The skills use placeholders instead of a hard-coded org, repos or branches:

| Placeholder | Default | Meaning |
|---|---|---|
| `your-org` | — | GitHub org (or user) whose repos the PR skills search |
| `~/workspace/<org>/` | — | Local folder with those repos cloned side by side |
| `<release-branch>` | `release` | Shared branch feature PRs merge into; `repo-pull` syncs to it |
| `<main-branch>` | `main` | Production branch; the release branch is promoted into it via a PR |
| `<promotion-repos>` | `api`, `ui` | Repos running the release → main promotion |
| Git hand-off | `on` | `on`: Claude hands you git commands instead of running them. `off`: Claude runs them itself (see below) |
| Model routing | `rewrite` | Subagent routing hook: `rewrite` moves a subagent to the model the routing table picks, `deny` makes Claude retry with it, `off` disables it |
| Slack channel ID | empty | Company-specific channel for automated run summaries; asked per project, never defaulted |
| Org email | empty | Your address at the company: per-folder git commit email and GitHub email routing; asked per project, never defaulted |

Run `/personal:init-personal-skills` once per project. It detects what it
can with `gh`, asks you to confirm each value, and writes them to the
`## repo-* skills` section of your user-level `~/.claude/CLAUDE.md`:

```markdown
## repo-* skills
- GitHub org: my-company
- Local workspace: ~/workspace/my-company/
- Release branch: release
- Main branch: main
- Promotion repos: api, ui
- Git hand-off: on
- Model routing: rewrite
- Slack channel ID: C0123456789
- Org email: you@my-company.com
```

Real values live only in that file, never in this repo.

## Prerequisites

- `gh` CLI authenticated with access to your org (`gh auth login`).
- Optional, for the Jira/Slack steps: Atlassian and Slack connectors enabled
  in claude.ai (Settings → Connectors). Without them, those steps can't run.

## Skills

### PR workflows

| Skill | What it does |
|---|---|
| `repo-pr-review` | Status sweep of your own open PRs org-wide; request reviewers (asked per PR), draft fixes for unaddressed review comments |
| `repo-pr-approve` | Deep review of PRs where you're a requested reviewer, including release → main promotion PRs: check out, run tests, tamper-test guardrails, verify PR-body claims; two-round verdict |
| `repo-code-review` | Self-review loop right after `gh pr create`: Opus review-and-fix loop, then one independent Fable pass |
| `github-email-routing` | Send one org's GitHub notification emails to the org address (GitHub Custom routing, or a Gmail filter + forward as fallback); checks and verifies read-only, never changes settings itself |
| `gh-notifications` | Digest of unread GitHub notifications for the configured org: what needs you, activity on your work, FYI noise as counts; PR state checked, next skill suggested. Read-only unless you approve mark-read/unwatch |
| `repo-pull` | Sync every repo under `~/workspace/<org>/` to `<release-branch>` (or default branch), stashing dirty trees and fast-forwarding submodules |
| `init-personal-skills` | Set up the placeholders above for a new project and write them to `~/.claude/CLAUDE.md` |

### Git and CI

| Skill | What it does |
|---|---|
| `github-branch-hygiene` | Pre/post commit-push checklist (state local and remote targets first) and recovery from a push to the wrong shared branch |
| `git-local-excludes` | Put local-only dirs (`.idea`, `.claude`) in `.git/info/exclude`, not `.gitignore` |
| `ci-test-implementation` | Pytest marker taxonomy (unmarked / integration / long-running), what GitHub Actions may run, local double-run before "CI-ready" |

### Working efficiency

| Skill | What it does |
|---|---|
| `model-routing` | Pick the model and effort for a task from a routing table (Haiku for search/logs, Sonnet for scoped coding, Opus by default, Fable for migrations and deep research), then run it as a subagent with a self-contained brief; escalation ladder: verify → raise effort → move up a model |

### Working rules (applied by default)

| Skill | What it does |
|---|---|
| `no-pii-in-artifacts` | No real person's name in file names, content, docstrings or commits — reference the ticket instead |
| `no-ticket-names-in-filenames` | Name files after what they contain; keep the ticket ID inside the file |
| `python-modern-typing` | Built-in generics, `X \| Y` unions, nudge towards Python 3.12 and current deps |
| `ticket-attachments-step-zero` | Check a ticket's real attachments before planning; downloading them is step 0 |
| `jira-new-ticket-creation` | Link follow-up tickets as "Relates", never "Blocks" without explicit confirmation |

### Reference

| Skill | What it does |
|---|---|
| `torch-apple-silicon-mps` | Verified facts about torch on Apple Silicon: MPS speed-up, Rosetta irrelevance, MPS is not fork-safe |

## Tools (optional)

| Tool | What it does |
|---|---|
| [`tools/git-config`](tools/git-config/README.md) | Global git setup, safe to rerun: identity (asked, never built in), optional SSH signing, aliases, and the safety defaults the skills rely on (`branch.autoSetupMerge=false`, `push.autoSetupRemote=true`). `--org-identity <dir> --email <work-email>` makes repos under `<dir>` commit with a company email |
| [`tools/repo-pr-watcher`](tools/repo-pr-watcher/README.md) | Runs `repo-pr-approve` on a launchd schedule, skipping ticks with no new org review activity (via `gh-notifications`' filter), **fully unattended** — posts approvals/comments with no confirmation. Not part of the plugin; off until you run its `install.sh` |

## Hooks

The plugin ships one hook, active as soon as the plugin is installed:

| Hook | What it does |
|---|---|
| `PreToolUse` on `Agent` → [`hooks/route_agent.py`](plugins/personal/hooks/route_agent.py) | Applies the `model-routing` table to every subagent call by keyword. Raises a model you chose but never lowers it, except for search/log/summary work; no rule match = no change. `[model-override]` in the prompt bypasses it. Logs one line per decision to `~/.claude/model-routing.log` (no prompt text). Any error lets the call through unchanged. Python 3.9+, stdlib only |

Turn it off with `- Model routing: off` in the `## repo-* skills` section
(or `MODEL_ROUTING_MODE=off`, which wins over the file); `deny` blocks
the call and lets Claude retry with the routed model instead of
rewriting it. Tests: `python3 -m unittest plugins/personal/hooks/test_route_agent.py`.

## Ground rules baked into every skill

- **Git hand-off (default `on`):** Claude never commits, pushes or merges
  on its own — it hands you the commands. Set `Git hand-off: off` (via
  `/personal:init-personal-skills`) to let Claude run them itself; it
  still states the target branches first and asks before force-pushes,
  resets, direct pushes to the release/main branches, and merges.
- Anything visible to others (PR comments, approvals, reviewer requests, Jira
  edits, Slack messages) is drafted first and posted only after your OK.

## Contributing

Edit `plugins/personal/skills/<skill>/SKILL.md`, bump `version` in
`plugins/personal/.claude-plugin/plugin.json`, commit. Keep skill content
free of real names, ticket keys and org-, repo- or branch-specific
identifiers — use the placeholders above.
