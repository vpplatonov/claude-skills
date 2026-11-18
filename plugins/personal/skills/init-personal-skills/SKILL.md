---
name: init-personal-skills
description: Set up the repo-* skills for a new project — ask for (and auto-detect via gh) the GitHub org, local workspace folder, release branch, main branch, promotion repos, the git hand-off rule (default on), the subagent model-routing mode (default rewrite), the company's Slack channel ID, the optional unattended PR watcher, and git safety defaults plus the org email (per-folder commit email), then write them to the `## repo-* skills` section of the user-level ~/.claude/CLAUDE.md after confirmation. Invoke when the user says "/init-personal-skills", "set up the skills for a new project", "switch the repo skills to another org", or when another skill reports placeholder config values.
---

# Initialize the repo-* skills for a project

The `repo-*` skills (and `github-branch-hygiene`, `ci-test-implementation`)
are written against placeholders — `your-org`, `~/workspace/<org>/`,
`<release-branch>`, `<main-branch>`, `<promotion-repos>` — so the plugin
itself never carries a real org, repo or branch name. This skill fills in
the real values for the current project, in one place on the user's own
machine: the `## repo-* skills` section of `~/.claude/CLAUDE.md`. Rerun it
whenever the user moves to a different project.

## What gets written

```markdown
## repo-* skills
- GitHub org: <org>
- Local workspace: ~/workspace/<folder>/
- Release branch: <release-branch>
- Main branch: <main-branch>
- Promotion repos: <repo>, <repo>
- Git hand-off: on
- Model routing: rewrite
- Slack channel ID: <channel-id or empty>
- GitHub-only repos: <repo>, <repo> or empty
- Org email: <company email or empty>
```

Only if the user opts into the unattended PR watcher (step 7), also:

```markdown
- PR watcher window: 15:00-02:00
- PR watcher timezone: Europe/Berlin
- PR watcher interval: 30m
- PR watcher precheck: on
- PR watcher max skip: 6h
```

| Key | Used by | Default suggestion |
|---|---|---|
| GitHub org | `repo-pr-review`, `repo-pr-approve`, `repo-code-review` (`gh search prs --owner`) | detected, see step 1 |
| Local workspace | `repo-pull`, `git-local-excludes` | `~/workspace/<org, lowercased>/` |
| Release branch | shared integration branch feature PRs merge into; `repo-pull` syncs to it | `release` |
| Main branch | production branch; `<release-branch>` is promoted into it via a PR | `main` |
| Promotion repos | repos running the release → main promotion; `repo-pr-approve` lists their open PRs into the main branch. Empty = no promotion sweep (only review requests and PRs you commented on) | detected, see step 4 |
| Git hand-off | `on`: Claude never commits, pushes, creates branches/PRs or merges — it hands you the commands. `off`: Claude runs them itself, still asking before force-pushes, resets, direct pushes to shared branches and merges (`github-branch-hygiene`, `repo-code-review`, `repo-pr-review`) | `on` |
| Model routing | the plugin's PreToolUse hook on the Agent tool (`model-routing` skill): `rewrite` changes a subagent's model per the routing table, `deny` makes Claude retry with that model, `off` disables the hook | `rewrite` |
| Slack channel ID | `tools/repo-pr-watcher` run summary; company-specific | none — always asked, empty allowed (= no summary) |
| GitHub-only repos | repos where review results go to GitHub only: `repo-pr-approve` and `tools/repo-pr-watcher` send the PR author no Slack DM | empty (= author DMs everywhere) |
| Org email | per-folder git commit email (step 8), `github-email-routing`; company-specific | none — always asked, empty allowed |
| PR watcher window / timezone / interval / precheck / max skip | `tools/repo-pr-watcher` only | any time / system local / `30m` / `on` / `6h` |

## Steps

1. **Read current state.** `cat ~/.claude/CLAUDE.md` (may not exist). If a
   `## repo-* skills` section is there, show its current values — they are
   the defaults for every question below, unless they're still the
   placeholders (`your-org`, `<org>`, `api`, `ui`).
   Then read the saved copy:
   `python3 "<this skill's base directory>/../../hooks/repo_skills_config.py" show`
   (the plugin's SessionStart hook copies the filled-in section to
   `~/.claude/repo-skills-config.saved.md` whenever a fresh session starts
   and the section has changed, so it survives a plugin update or a
   CLAUDE.md that got reset). Exit 1 means there is no usable copy. If the current section is missing or still placeholders
   and a saved copy exists, show it and use its values as the defaults
   instead. If both exist and differ, show both and use the current one.
   Saved company-specific values (Slack channel ID, GitHub-only repos, Org
   email) are defaults only while the org the user confirms in step 2 is
   the saved copy's org.
2. **GitHub org.** Suggest candidates, don't pick one:
   - the owner of the current directory's `origin` remote, if any
     (`git remote get-url origin`);
   - `gh api user/orgs --jq '.[].login'` plus the user's own login
     (`gh api user --jq .login`).
   Ask the user to confirm or type the org. Verify it resolves:
   `gh api orgs/<org> --jq .login` (or `users/<org>` for a personal account).
3. **Local workspace.** Suggest `~/workspace/<org, lowercased>/`. Check it
   exists (`ls -d`). If it doesn't, say so — don't create it or clone
   anything; that's the user's call.
4. **Branches and promotion repos.** Ask for the release branch (default
   `release`) and main branch (default `main`). Then detect which repos
   actually run the promotion chain:
   ```
   gh repo list <org> --no-archived --limit 200 --json name --jq '.[].name' |
   while read r; do
     gh api "repos/<org>/$r/branches/<release-branch>" --silent 2>/dev/null && echo "$r"
   done
   ```
   Show the matches as the suggested promotion repos and let the user add or
   remove entries. If nothing matches, ask whether the branch name is right
   before accepting an empty list.
5. **Git hand-off.** Ask whether Claude should keep handing off git
   commands (`on`, the default — Claude never commits, pushes or merges on
   its own) or run them itself (`off`). Explain what `off` still guards
   (force-pushes, resets, direct pushes to the release/main branches and
   merges each need an OK). Keep `on` unless the user clearly chooses `off`.
   Then ask for **Model routing**: `rewrite` (default — the plugin's hook
   moves a subagent to the model the routing table picks and tells Claude
   it did), `deny` (the hook blocks the call and Claude retries with that
   model) or `off`. Point to `/personal:model-routing` for the table.
6. **Slack channel ID.** Ask for the Slack channel (or DM) ID that should
   get automated run summaries in *this* company's workspace, e.g.
   `C0123456789`. It is company-specific: never suggest one from memory,
   another project or the previous section's value when the org changed.
   Empty is a valid answer and means "post no summaries".
   Then ask for **GitHub-only repos**: repos where the team talks only
   through PR comments, change requests and approvals, so review results
   get no Slack DM to the author. Empty (the default) means DMs everywhere.
7. **Unattended PR watcher (optional, default no).** Ask whether the user
   wants `tools/repo-pr-watcher` (scheduled, fully unattended
   `repo-pr-approve` that posts approvals and comments with no
   confirmation). If no, write none of the `PR watcher` keys (remove them
   if the section has them). If yes, ask for the active window (e.g.
   `15:00-02:00`, empty = any time), its IANA timezone (empty = system
   local), the interval (`10m`/`30m`/`1h`, default `30m`), and whether to
   skip ticks with no new org notifications (`PR watcher precheck`, default
   `on`; a full run still happens at least every `PR watcher max skip`,
   default `6h`). Never run
   its `install.sh` yourself — tell the user to run it after step 10, and
   to rerun it whenever the interval changes.
8. **Git safety defaults and org identity.** Read-only check first:
   ```
   git config --global --get branch.autoSetupMerge   # want: false
   git config --global --get push.autoSetupRemote    # want: true
   git config --global --get user.email
   git config --global --get-regexp '^includeif\.'
   ```
   - If either default is off, say why it matters (`autoSetupMerge=false`
     stops `git checkout -b x origin/<release-branch>` from tracking the
     shared branch — the root cause in `github-branch-hygiene`) and offer
     to set it (`git config --global branch.autoSetupMerge false`,
     `git config --global push.autoSetupRemote true`).
   - If the global email looks like a company address, point out that
     every repo outside an org folder commits with it, and suggest a
     personal or GitHub noreply address as the global default.
   - Ask for the **Org email** — the user's address at this company, or
     empty if there is none (company-specific: never suggest one; when the
     org changed, don't reuse the previous section's value). It's written
     as `- Org email:` in step 9 and also used by `github-email-routing`.
   - If it's set, ask whether repos under the local workspace should commit
     with it. If yes, offer, with `<slug>` = the workspace folder name:
     ```
     git config --file ~/.gitconfig-<slug> user.email <Org email>
     git config --global includeIf.gitdir:<workspace, absolute, ending in />.path ~/.gitconfig-<slug>
     ```
     Verify with `git -C <a repo in the workspace> config user.email`.
   Show each `git config` command and run it only after the user's OK.
   `tools/git-config/setup.sh` in this plugin's repo does the full global
   setup (identity, signing, aliases) if the user wants all of it.
   If `Org email` is set and the org isn't the user's own account, mention
   `/personal:github-email-routing` to send this org's GitHub notification
   emails there instead of the personal inbox.
9. **Confirm, then write.** Show the complete section exactly as it will be
   written and wait for the user's OK. Then:
   - file missing → create `~/.claude/CLAUDE.md` with just this section;
   - section present → replace it in place (from the `## repo-* skills`
     heading up to the next `# ` or `## ` heading or end of file);
   - section absent → append it at the end, separated by a blank line.
   Never touch any other part of the file. Show the resulting section
   (`sed -n '/^## repo-\* skills/,/^##\{0,1\} /p' ~/.claude/CLAUDE.md`) as proof.
   Then refresh the saved copy right away, not at the next session start:
   `python3 "<this skill's base directory>/../../hooks/repo_skills_config.py" save`.
   Exit 1 means the written section isn't readable as filled in (or
   CLAUDE.md couldn't be read as UTF-8, or the heading isn't exactly
   `## repo-* skills`): recheck
   that GitHub org is a real org (not empty or `your-org`) and that neither
   it nor Local workspace holds a `<…>` placeholder. Exit 2 means the backup
   copy couldn't be written, so tell the user (CLAUDE.md itself was still
   written).
10. **Report** the values written and remind the user that a new Claude Code
   session picks them up (the current one already has the old CLAUDE.md
   loaded).

## Rules

- Write only to `~/.claude/CLAUDE.md` (and its saved copy via the script's
  `save`), plus the `git config` commands of
  step 8 (global git config and `~/.gitconfig-<slug>`), each run only after
  the user's OK. Never write real org, repo or branch names into the plugin
  repo itself — that's the point of the placeholders.
- Every value is confirmed by the user; auto-detection only suggests.
- Company-specific identifiers (org, Slack channel ID, company email) are asked fresh for
  each project — never defaulted, never carried over from another project.
  The one exception is the saved copy of the *same* org's section (step 1),
  restoring that project's own values after an update or reset.
- Read-only `gh` calls only (`api` GETs, `repo list`); no repo, branch or
  settings changes.
