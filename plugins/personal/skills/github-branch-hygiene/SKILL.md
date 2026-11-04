---
name: github-branch-hygiene
description: Pre/post commit-push verification checklist, always stating the local/remote branch targets before recommending a commit or push, and recovering from an accidental push to the wrong shared branch (<release-branch>/<main-branch>) — reset --hard + force-push, not revert, to keep GitHub history clean.
---

# GitHub branch hygiene

> **Config:** `<release-branch>` and `<main-branch>` come from the
> `## repo-* skills` section of `~/.claude/CLAUDE.md`. If they're unset,
> ask the user which branches are shared (and suggest
> `/personal:init-personal-skills`) — never guess them.

**Git hand-off — default `on`.** Read `Git hand-off` from the `## repo-* skills` section of `~/.claude/CLAUDE.md`; missing or unset means `on`.

- **`on` (default): every command below is for the user to run, unconditionally.** `git commit`, `git add`, `git push` (including `--force`/`--force-with-lease`), `git reset --hard`, `git checkout -B` against a shared branch, `git branch`, `git checkout -b`, `gh pr create`, `gh pr merge` — none of these get executed by the agent itself, no matter how routine, low-risk, or clearly-the-right-move a step looks (including every step in the "Remediation" checklist below). The agent's role is always: diagnose, explain, and hand off the exact commands (or, for a PR, the drafted title/body) — never run them. This holds even mid-incident-cleanup, when moving fast feels justified. The two sections below ("Never create a PR", "Branch creation") apply in this mode.
- **`off`: the agent may run these commands itself** — commits, pushes, branch creation, `gh pr create` — but every check in this skill still applies: state the local and remote targets first, check the upstream before the first push, verify after, and create branches off a shared branch with `--no-track` per the rule below. Still ask for an explicit OK, per action, before anything destructive or shared: any force-push, `git reset --hard`, a direct push to `<release-branch>` or `<main-branch>`, or merging a PR.

## Never create a PR — `gh pr create` is always the user's (hand-off `on`)

Confirmed 2026-08-20, generalized from a session where the agent had previously opened several PRs on explicit per-instance requests ("yep - open PR") earlier in the same work: those one-off asks do not establish a standing default. **The default, always and without being asked again, is: draft the title/body, hand them off, and stop** — `gh pr create` itself is never run by the agent, the same way `git commit`/`git push` never are.

**How to apply:** when work is ready for a PR, produce the title and body text (following each repo's commit-message conventions) and present them for the user to use with `gh pr create` themselves, or via their IDE/GitHub UI. Do not run `gh pr create` even when the user has approved everything else about the PR (commit message, body content) — approving the *content* is not the same as authorizing the *action*.

**Exception:** a narrow, explicitly-named exception may exist for a dedicated "code review loop" workflow the user is introducing separately — that exception applies only within that specific, explicitly-invoked workflow once defined, never as a general loosening here.

## Branch creation is the user's privilege (hand-off `on`) — confirmed twice now

Confirmed 2026-08-05, right after the exact incident this skill exists to prevent happened again: the agent ran `git checkout -b feat/proj104-<short-desc> origin/<release-branch>` itself, which set the new branch's upstream to `origin/<release-branch>` (see "Root cause" below) — and a later plain `git push` (also run by the user, but on a footgun the agent had already set) landed a commit directly on shared `<release-branch>`. Explaining the footgun after the fact wasn't enough; the fix is to never be the one who creates the branch in the first place.

**Recurred 2026-08-20 (ui): the agent did it again** — `git checkout -b PROJ-102-<short-desc> origin/<release-branch>`, same shape, same missing `--no-track`, same outcome: the user's later plain `git push` landed on `<release-branch>` and auto-deployed before anyone caught it. Two occurrences of the identical mistake, months apart, means "explain the footgun and move on" doesn't work — the rule has to be followed reflexively every time, not re-derived in the moment a branch feels obviously needed.

**How to apply:** whenever a new branch is needed, give the user the exact `git checkout -b <name> <base>` command (with `--no-track` per the footgun note below, when applicable) and ask them to run it. Never type `git checkout -b` or `git branch` into a tool call myself, under any framing — no exceptions, not even "just this once to save a round-trip." This closes the loophole regardless of how careful the agent tries to be about tracking/upstream afterward — no branch creation by the agent, no chance of silently inheriting the wrong upstream.

**Strict rule (confirmed 2026-08-07, corrected 2026-08-12): `--no-track` applies only when `<name>` differs from `<shared-branch>` — i.e. starting genuinely new work off a shared integration branch.** In that case, don't hand off `git checkout -b <name> origin/<shared-branch>` bare and rely on remembering `git push -u origin <name>` correctly later — that's exactly the two-step sequence that produced the incident twice. Always write it as:
```
git fetch origin <shared-branch>
git checkout -b <name> origin/<shared-branch> --no-track
```
`--no-track` means the new branch is based on that commit but has **no** upstream configured at all — a bare `git push` on it fails loudly (no configured push destination) instead of silently landing on the shared branch. The first real push then requires `git push -u origin <name>` explicitly, which is the point: the safety now lives in the branch's own config, not in remembering a follow-up step.

**Do NOT use `--no-track` when checking out a same-named remote branch to continue existing work on it** (e.g. `git checkout -b PROJ-103 origin/PROJ-103` — the branch already exists remotely under that exact name because someone already pushed a commit to it). There, tracking is exactly what's wanted: `git push`/`git pull` should go to that same branch, since that IS the ticket's branch, not a shared one. Caught 2026-08-12: handed off `--no-track` for exactly this case, the user had to `git branch --set-upstream-to` manually to undo it. The footgun this rule guards against is a new branch inheriting a *different, shared* branch's identity as its upstream — it does not apply when `<name>` and `<shared-branch>` are the same name, because there's no different branch to accidentally push to.

## Always state the branch targets before recommending a commit/push

Whenever suggesting or handing off a `git commit` / `git push` (including the commands themselves, not just doing it), explicitly say both:
- **Local branch** the commit will be made on (`git branch --show-current` if unsure).
- **Remote branch** the push will actually target — the branch's configured upstream (`git rev-parse --abbrev-ref --symbolic-full-name @{u}` if unsure), not just an assumption from how the branch was named or created.

State this even when it seems obvious — the upstream-tracking footgun in "Root cause" below (`checkout -b <name> origin/<other-branch>` silently tracks `<other-branch>`) is exactly the kind of mismatch that's invisible unless someone says the target out loud before pushing.

## Pre/post commit-push verification checklist

Run this around every commit — it catches wrong-file commits and wrong-branch pushes (the root cause below) before they need remediation.

**Before `git commit` — confirm exactly what's about to be included:**
1. `git status` — full picture: staged, unstaged, untracked.
2. `git diff --cached --name-only` — the exact file list the commit WILL contain. Cross-check against what you actually intended to change: nothing extra (stray debug output, unrelated edits, anything that looks like a secret), nothing missing.
3. Fix mismatches before committing: `git add <file>` to include something missing, `git restore --staged <file>` to drop something that shouldn't be there.

**Before the FIRST `git push` on this branch — always check the upstream, no exceptions:**

Confirmed 2026-08-20, right after the second occurrence of the wrong-branch-push incident: a check that only happens "if unsure" doesn't happen, because the mistracked branch never *feels* unsure — it looks completely normal until the push lands somewhere unexpected. This step is now unconditional, every time, on every branch's first push:

3a. `git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || echo "no upstream configured"` — run this and read the actual output before pushing, not just when something seems off.
3b. If it names a shared branch (`<release-branch>`, `<main-branch>`) that isn't the branch you intend to push to: **stop**, do not push — this is exactly the footgun in "Root cause" below. Fix the tracking first (`git branch --unset-upstream`, then push with `-u` to the correct remote branch name).
3c. If it says "no upstream configured" (expected right after a `--no-track` checkout): the push must be `git push -u origin <branch-name>` explicitly — a bare `git push` will simply fail here, which is correct and safe.

**After `git commit` && `git push` — confirm it landed completely, cleanly, and on the right branch:**
4. `git status` — must read both **"nothing to commit, working tree clean"** and **"Your branch is up to date with 'origin/&lt;branch&gt;'"**. The first confirms no local leftovers; the second confirms the push actually reached that remote branch.
5. `git fetch origin && git log --oneline -1 HEAD` compared with `git log --oneline -1 origin/<branch>` — the SHAs must match. This is the check that catches a wrong-branch push early (see root cause below): if you meant to push a feature branch but it landed on `<release-branch>`, this comparison surfaces the mismatch immediately.
6. `git diff HEAD origin/<branch>` — expect no output. Any output means local and remote have diverged unexpectedly.

## Recovering a wrong-branch push

When a commit lands directly on a shared branch (`<release-branch>`, `<main-branch>`) instead of the intended feature branch, fix it with **reset + force-push**, not a revert. Goal: the shared branch's history reads exactly as if the mistake never happened — no revert commit, no "revert the revert" commit, no permanent noise.

## Root cause this guards against

`git checkout -b <new-branch> origin/<other-branch>` sets `<new-branch>`'s upstream to `origin/<other-branch>`, **not** a same-named remote branch. A later plain `git push` then lands on `<other-branch>` directly — e.g. creating a branch from `origin/<release-branch>` this way, then pushing, pushes straight to `<release-branch>`.

Git can block this footgun itself: with `git config --global branch.autoSetupMerge false` a branch created from `origin/<other-branch>` gets no upstream at all, and `push.autoSetupRemote true` makes the first plain `git push` create a same-named remote branch. `/personal:init-personal-skills` checks both; `tools/git-config/setup.sh` sets them. Still follow the checklist above — the setting may be off on another machine.

**Prevention:** always push a brand-new branch explicitly the first time — `git push -u origin <branch-name>` — regardless of how it was created. This sets correct tracking in one step and avoids the accident entirely. Stronger still, per the strict rule above: hand off the branch-creation command itself with `--no-track` so there's no upstream to silently inherit in the first place, rather than depending on the explicit-push step happening correctly later.

## Remediation: reset --hard + force-push (not revert)

1. **Identify exactly** which commit(s) shouldn't be on the shared branch, and the SHA of the last-good commit before them (`git log --oneline origin/<branch>`).
2. **Safety check before forcing anything** — confirm nobody else has already fetched/based work on the bad commit (check recent activity, ask in the team channel if there's any doubt). Force-push rewrites public history; it's safe specifically because you're catching it immediately, before anyone else's clone depends on it. If real time has passed or others may have pulled, coordinate before proceeding.
3. `git fetch origin`
4. `git checkout -B <branch> origin/<branch>` (recreate the local branch pointing at the current, still-bad remote tip)
5. `git reset --hard <last-good-sha>`
6. `git push --force origin <branch>` (or `--force-with-lease` for an extra guard against someone else having pushed in the meantime)
7. **Verify**: `git log --oneline origin/<branch> -5` shows the shared branch back at exactly the last-good commit, with zero trace of the accident.
8. Recreate/rebase the intended feature branch on the now-clean shared-branch tip, and push it explicitly with `-u origin <branch-name>` per the prevention note above.

## Why not `git revert`

A revert is the right tool when a bad commit has already been *built on* (by other branches, deploys, or teammates) and removing it outright would break things — reverting preserves a clean historical record of "this happened, then was undone" without rewriting anything. But for a same-session, caught-immediately wrong-branch push, revert (or worse, revert-the-revert once a follow-up fix needs to actually land) leaves permanent clutter in a shared branch's history for an event that should never have been visible there at all. Reset + force-push restores a clean, linear history — the correct choice specifically for this "caught it fast, nobody else has it yet" scenario.
