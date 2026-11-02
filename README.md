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

## Configure your org

The `repo-*` skills use two placeholders instead of a hard-coded org:

| Placeholder | Meaning |
|---|---|
| `your-org` | GitHub org (or user) whose repos the PR skills search |
| `~/workspace/<org>/` | Local folder with those repos cloned side by side |

Tell Claude the real values once, in your user-level `~/.claude/CLAUDE.md`:

```markdown
## repo-* skills
- GitHub org: my-company
- Local workspace: ~/workspace/my-company/
```

## Prerequisites

- `gh` CLI authenticated with access to your org (`gh auth login`).
- Optional, for the Jira/Slack steps: Atlassian and Slack connectors enabled
  in claude.ai (Settings → Connectors). Without them, those steps can't run.

## Skills

### PR workflows

| Skill | What it does |
|---|---|
| `repo-pr-review` | Status sweep of your own open PRs org-wide; request reviewers (asked per PR), draft fixes for unaddressed review comments |
| `repo-pr-approve` | Deep review of PRs where you're a requested reviewer: check out, run tests, tamper-test guardrails, verify PR-body claims; two-round verdict |
| `repo-code-review` | Self-review loop right after `gh pr create`: Opus review-and-fix loop, then one independent Fable pass |
| `repo-pull` | Sync every repo under `~/workspace/<org>/` to `staging` (or default branch), stashing dirty trees and fast-forwarding submodules |

### Git and CI

| Skill | What it does |
|---|---|
| `github-branch-hygiene` | Pre/post commit-push checklist (state local and remote targets first) and recovery from a push to the wrong shared branch |
| `git-local-excludes` | Put local-only dirs (`.idea`, `.claude`) in `.git/info/exclude`, not `.gitignore` |
| `ci-test-implementation` | Pytest marker taxonomy (unmarked / integration / long-running), what GitHub Actions may run, local double-run before "CI-ready" |

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

## Ground rules baked into every skill

- Claude never commits, pushes or merges on its own — it hands you the
  commands.
- Anything visible to others (PR comments, approvals, reviewer requests, Jira
  edits, Slack messages) is drafted first and posted only after your OK.

## Contributing

Edit `plugins/personal/skills/<skill>/SKILL.md`, bump `version` in
`plugins/personal/.claude-plugin/plugin.json`, commit. Keep skill content
free of real names, ticket keys and org-specific identifiers — use the
placeholders above.
