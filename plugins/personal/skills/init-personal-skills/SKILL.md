---
name: init-personal-skills
description: Set up the repo-* skills for a new project — ask for (and auto-detect via gh) the GitHub org, local workspace folder, release branch, main branch, promotion repos and the git hand-off rule (default on), then write them to the `## repo-* skills` section of the user-level ~/.claude/CLAUDE.md after confirmation. Invoke when the user says "/init-personal-skills", "set up the skills for a new project", "switch the repo skills to another org", or when another skill reports placeholder config values.
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
```

| Key | Used by | Default suggestion |
|---|---|---|
| GitHub org | `repo-pr-review`, `repo-pr-approve`, `repo-code-review` (`gh search prs --owner`) | detected, see step 1 |
| Local workspace | `repo-pull`, `git-local-excludes` | `~/workspace/<org, lowercased>/` |
| Release branch | shared integration branch feature PRs merge into; `repo-pull` syncs to it | `release` |
| Main branch | production branch; `<release-branch>` is promoted into it via a PR | `main` |
| Promotion repos | repos running the release → main promotion; `repo-pr-approve` lists their open PRs into the main branch | detected, see step 4 |
| Git hand-off | `on`: Claude never commits, pushes, creates branches/PRs or merges — it hands you the commands. `off`: Claude runs them itself, still asking before force-pushes, resets, direct pushes to shared branches and merges (`github-branch-hygiene`, `repo-code-review`, `repo-pr-review`) | `on` |

## Steps

1. **Read current state.** `cat ~/.claude/CLAUDE.md` (may not exist). If a
   `## repo-* skills` section is there, show its current values — they are
   the defaults for every question below, unless they're still the
   placeholders (`your-org`, `<org>`, `api`, `ui`).
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
6. **Confirm, then write.** Show the complete section exactly as it will be
   written and wait for the user's OK. Then:
   - file missing → create `~/.claude/CLAUDE.md` with just this section;
   - section present → replace it in place (from the `## repo-* skills`
     heading up to the next `## ` heading or end of file);
   - section absent → append it at the end, separated by a blank line.
   Never touch any other part of the file. Show the resulting section
   (`sed -n '/^## repo-\* skills/,/^## /p' ~/.claude/CLAUDE.md`) as proof.
7. **Report** the values written and remind the user that a new Claude Code
   session picks them up (the current one already has the old CLAUDE.md
   loaded).

## Rules

- Write only to `~/.claude/CLAUDE.md`. Never write real org, repo or branch
  names into the plugin repo itself — that's the point of the placeholders.
- Every value is confirmed by the user; auto-detection only suggests.
- Read-only `gh` calls only (`api` GETs, `repo list`); no repo, branch or
  settings changes.
