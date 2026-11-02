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

### Tell Claude your org
- [ ] Add to `~/.claude/CLAUDE.md` (replace with your real values):
  ```markdown
  ## repo-* skills
  - GitHub org: my-company
  - Local workspace: ~/workspace/my-company/
  ```

### Skills to Know About

PR workflows — invoke by name or just ask:
- /personal:repo-pr-review — "check my PRs": status of your own open PRs, reviewer requests (you pick each one), drafted fixes for review comments.
- /personal:repo-pr-approve — "what do I need to review": checks out each PR, runs tests, tamper-tests guardrails, posts a comment or approval only after your OK.
- /personal:repo-code-review — run right after `gh pr create`: Opus review-and-fix loop, then one Fable final pass.
- /personal:repo-pull — sync every local repo to `staging` (or default branch), stashing dirty trees safely.

Applied automatically, no need to invoke:
- github-branch-hygiene, git-local-excludes, ci-test-implementation
- no-pii-in-artifacts, no-ticket-names-in-filenames, python-modern-typing
- ticket-attachments-step-zero, jira-new-ticket-creation, torch-apple-silicon-mps

Built-in worth knowing:
- /compact — summarize a long session to keep going; useful on long PR/review sessions.

## Tips

- Nothing visible to others is posted without your OK — the skills draft PR comments, approvals, Jira edits and Slack messages and wait.
- Claude hands you commit and push commands instead of running them. Check the stated local and remote branch before you run them.
- Always qualify a PR number with its repo (`backend-api#54`, not `#54`) — numbers collide across repos.
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
through the rest one by one. For the CLAUDE.md step, ask for their real org
and workspace path rather than guessing. Connectors are optional — mention
what they unlock, don't push.

After setup, surface the Tips and offer the Get Started run. Don't invent
sections or summaries that aren't in the guide. -->
