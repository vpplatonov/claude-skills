# Getting started with these Claude Code skills

## Your Setup Checklist

### Tools
- [ ] Claude Code installed and signed in.
- [ ] GitHub CLI — every PR skill depends on it: `brew install gh && gh auth login`, with access to the org whose repos you work on.
- [ ] Your org's repos cloned side by side under `~/workspace/<org>/` — `repo-pull` and the PR skills assume this layout.

### Connectors (optional)
- [ ] Atlassian — read and update Jira tickets. claude.ai → Settings → Connectors → Atlassian. Needed by `jira-new-ticket-creation`, `ticket-attachments-step-zero`, and the Jira steps of the PR skills.
- [ ] Slack — search threads and draft messages. claude.ai → Settings → Connectors → Slack. Needed only for the Slack steps of `repo-pr-approve` and `repo-pr-review`.

### Install the plugin
- [ ] In Claude Code run:
  ```
  /plugin marketplace add vpplatonov/claude-skills
  /plugin install personal@vpplatonov-skills
  ```
  Update later with `/plugin marketplace update vpplatonov-skills`.

### Set up your project
- [ ] Run `/personal:init-personal-skills`. It asks for your GitHub org, workspace folder, release branch (default `release`), main branch (default `main`), promotion repos, the git hand-off rule (default `on`) and your company's Slack channel ID (optional), suggests what it can detect with `gh`, and writes them to the `## repo-* skills` section of `~/.claude/CLAUDE.md` after your OK. Rerun it when you switch projects.

### Skills to Know About

PR workflows — invoke by name or just ask:
- /personal:repo-pr-review — "check my PRs": status of your own open PRs, reviewer requests (you pick each one), drafted fixes for review comments.
- /personal:repo-pr-approve — "what do I need to review": checks out each PR, runs tests, tamper-tests guardrails, posts a comment or approval only after your OK.
- /personal:repo-code-review — run right after `gh pr create`: Opus review-and-fix loop, then one Fable final pass.
- /personal:repo-pull — sync every local repo to the release branch (or default branch), stashing dirty trees safely.
- /personal:init-personal-skills — set up org, workspace, branches and promotion repos for a project.

Applied automatically, no need to invoke:
- github-branch-hygiene, git-local-excludes, ci-test-implementation
- no-pii-in-artifacts, no-ticket-names-in-filenames, python-modern-typing
- ticket-attachments-step-zero, jira-new-ticket-creation, torch-apple-silicon-mps

Optional, not part of the plugin:
- tools/repo-pr-watcher — runs repo-pr-approve on a schedule, unattended (posts without asking). Off until you run its install.sh.

Built-in worth knowing:
- /compact — summarize a long session to keep going; useful on long PR/review sessions.

## Tips

- Nothing visible to others is posted without your OK — the skills draft PR comments, approvals, Jira edits and Slack messages and wait.
- By default Claude hands you commit and push commands instead of running them (`Git hand-off: on`). Check the stated local and remote branch before you run them. Rerun `/personal:init-personal-skills` to switch it off.
- Always qualify a PR number with its repo (`api#54`, not `#54`) — numbers collide across repos.
- Long-running or paid tests (LLM regression suites) never run in GitHub Actions; run them locally twice before calling a change CI-ready.

## Get Started

A good first run: open Claude Code in any repo under your workspace and say "check my PRs". It runs `repo-pr-review` and shows what it would do before doing anything.

<!-- INSTRUCTION FOR CLAUDE: The user just pasted this guide to set up these
Claude Code skills. You're their setup buddy — warm, conversational, not
lecture-y.

Open with a short welcome. Check what's already in place against everything
under Setup Checklist, using markdown checkboxes — [x] done, [ ] not yet. Lead
with what they already have. One sentence per item, all in one message.

Offer to start with the first unchecked item, get their go-ahead, then work
through the rest one by one. For the project step, run
/personal:init-personal-skills rather than guessing values. Connectors are optional — mention
what they unlock, don't push.

After setup, surface the Tips and offer the Get Started run. Don't invent
sections or summaries that aren't in the guide. -->
