---
name: repo-pull
description: Sync every repo under ~/workspace/<org>/ to the latest origin/<release-branch> (or, for repos with no `<release-branch>` branch, their own remote default branch), safely handling dirty working trees via stash, plus fast-forwarding any git submodules (e.g. a shared schema repo pulled in as a submodule) to their own remote's latest — invoke when the user asks to "pull whole project", "sync all org repos", "/repo-pull", or similar.
---

# Pull all org repos (sync all repos to <release-branch>, or default branch)

> **Config:** `your-org`, `~/workspace/<org>/`, `<release-branch>`,
> `<main-branch>` and `<promotion-repos>` come from the `## repo-* skills`
> section of `~/.claude/CLAUDE.md`. If that section is missing or still
> holds placeholder values, stop and tell the user to run
> `/personal:init-personal-skills` — never guess them.

Brings every git repo under `~/workspace/<org>/` up to date on
`origin/<release-branch>` — or, for a repo with no `<release-branch>` branch (its PRs merge
straight to `main`), up to date on its own remote default branch instead —
without losing local work-in-progress or leaving any repo on a different
branch than it started on.

## Approved-command whitelist (read this before running)

This is the **only** skill allowed to run these git commands directly,
without asking the user to run them instead:

- `git stash push` / `git stash apply`
- `git pull`
- `git checkout` / `git switch` (branch navigation only — never `-B`/force
  against a shared branch, never used to discard changes)
- `git status`, `git branch`, `git ls-remote` (read-only)
- `git submodule update --init --remote <path>` (submodule fast-forward only
  — never `git add`/`git commit` the resulting pointer bump, see step 7)

**Never** run `git add`, `git commit`, `git push`, `git stash pop`, `git
stash drop`, or `git reset --hard` as part of this skill — those stay
strictly off-limits — this skill only syncs, whatever `Git hand-off` is
set to in `~/.claude/CLAUDE.md`. This whitelist is
deliberately narrow specifically so there's no commit path to gate at all —
dirty repos only ever get stashed, never committed, by this skill.

## Algorithm

1. **Enumerate repos**: every immediate subdirectory of `~/workspace/<org>/`
   containing a `.git` directory whose `origin` is on GitHub. Skip (and
   report) any repo hosted elsewhere, e.g. GitLab — same GitHub-only scope
   as `repo-pr-review`.
   ```
   for d in ~/workspace/<org>/*/; do
     [ -d "$d/.git" ] && git -C "$d" remote get-url origin 2>/dev/null | grep -q 'github\.com' && echo "$d"
   done
   ```
2. **Determine each repo's sync branch**: `git ls-remote --heads origin
   <release-branch>` — non-empty output means `SYNC_BRANCH=<release-branch>`. Empty output means the repo has no `<release-branch>` branch (its PRs
   merge straight to `main`) — resolve its actual remote default branch
   instead of guessing `main`:
   ```
   git ls-remote --symref origin HEAD | awk '/^ref:/ {sub("refs/heads/", "", $2); print $2}'
   ```
   `SYNC_BRANCH` = that result (typically `main`, but stays correct for a
   repo defaulting to `master` or anything else). Every repo now gets
   synced against one branch or the other — the old "no `<release-branch>` branch,
   skip entirely" outcome only still applies if this resolution itself
   fails (malformed/unreachable remote): skip pull/switch for that one
   repo, report it untouched, and continue with the rest of the run.
3. **Record current branch** per remaining repo: `git branch --show-current`.
   This is what gets restored at the end — never assume it's `main` or
   `<release-branch>`.
4. **Status check**: `git status --porcelain` per repo. Collect every dirty
   repo (non-empty output) into one batch and ask the user once, listing
   each dirty repo with its file count — confirm which (if any) should be
   stashed before proceeding. A repo the user declines to stash is skipped
   entirely: not switched, not pulled, left exactly as-is.
5. **Stash approved repos**:
   ```
   git stash push -u -m "auto-stash before repo-pull ($(basename repo), <original-branch>)"
   ```
   `-u` included so untracked files can't block the branch switch either.
6. **Switch to `$SYNC_BRANCH` and pull**:
   ```
   git rev-parse --verify $SYNC_BRANCH >/dev/null 2>&1 \
     && git checkout $SYNC_BRANCH \
     || git checkout -b $SYNC_BRANCH origin/$SYNC_BRANCH
   git pull
   ```
   If `git pull` fails (diverged history / conflict), run `git merge
   --abort` immediately to leave `$SYNC_BRANCH` clean, record the failure
   for that repo, and continue to step 7 anyway — never leave a repo
   mid-merge.
7. **Submodule handling** — runs for every enumerated repo regardless of
   which branch it synced to in step 2 (submodule state is orthogonal to
   the parent's own branch sync; e.g. a repo with no
   `<release-branch>` branch syncs against `main` per step 2, but its
   submodule update is independent of that choice):
   ```
   [ -f "$d/.gitmodules" ] && git -C "$d" config --file .gitmodules \
     --get-regexp path | awk '{print $2}'
   ```
   For each submodule path found, record the current pinned commit
   (`git -C "$d/$path" rev-parse HEAD`), then:
   ```
   git -C "$d" submodule update --init --remote "$path"
   ```
   This fast-forwards the submodule's local checkout to the tip of its own
   remote's default branch (per its own `.gitmodules` entry — no `branch =`
   key means "the submodule's default branch," typically `main`). Record
   the resulting commit and report old-sha → new-sha.

   **This deliberately leaves the submodule "modified" in the parent repo's
   working tree** — the submodule now points at a newer commit than what's
   committed in the parent (the parent's index still references
   the old submodule SHA). That's expected and reported explicitly,
   never silently resolved: whether to commit that pointer bump in the
   parent repo is the user's call, same as any other change this skill
   surfaces but doesn't stage. Never run `git add`/`git commit` on the
   submodule pointer as part of this skill.
8. **Restore the original branch** recorded in step 3:
   `git checkout <branch>` (no-op for repos that started on `$SYNC_BRANCH`).
9. **Re-apply the stash** for repos stashed in step 5:
   ```
   git stash apply
   ```
   Deliberately `apply`, never `pop` — the stash entry stays in `git stash
   list` even after a successful apply, so nothing is lost if something
   looks wrong afterward. If apply reports conflicts, stop for that repo and
   report it; don't attempt automatic resolution. The user drops the stash
   themselves once they've confirmed it applied cleanly.
10. **Report** in this shape:
    - **Pull result** per repo: pulled `<SYNC_BRANCH>` (old-sha → new-sha)
      / already up to date / could not resolve remote default branch —
      skipped / failed, merge aborted. Always name which branch
      (`<release-branch>` or the resolved default) each repo actually synced to.
    - **Submodule result** per submodule found: old-sha → new-sha / already
      up to date, plus the "now shows modified in parent" note whenever the
      SHA moved.
    - **What was stashed / applied** per repo, with the stash message, and
      whether apply was clean or conflicted.
    - **Current branch** for every git-controlled repo under `~/workspace/<org>/`,
      including any left untouched because its default branch couldn't be
      resolved.

## Why `apply` and not `pop`, and why stash-only (no commit option)

A dirty repo here almost always means uncommitted exploratory/local-only
changes (scratch scripts, `.env` edits, docs-in-progress) rather than
something ready to commit — offering to commit it on the user's behalf
would require picking a commit message and message content without full
context, which is exactly the judgment call the user reserves for
themselves. Stashing is fully reversible and requires no such judgment call,
which is why it's the only mutation this skill is trusted to perform
unattended (after the one batch confirmation in step 4).

## Why fast-forward the submodule pointer but never commit it

A submodule is pinned to a specific commit by design — that pin is itself
committed state in the parent repo. Moving the pointer to the submodule
remote's latest is exactly analogous to `git pull` on the parent (fetch the
newest upstream state), so it's safe to do unattended the same way pulling
`<release-branch>` is. But *committing* that pointer bump in the parent repo is a
judgment call indistinguishable from any other "should this change land"
decision (does the parent's code still work against the newer submodule
commit? is this the right moment to bump it?) — exactly the kind of call
this skill never makes on the user's behalf for ordinary file changes
either. So the submodule checkout moves, the parent repo's tracked pointer
reference does not get staged or committed; the user decides separately
whether/when to commit that bump.
