---
name: repo-code-review
description: Automated, model-escalating self-review of a PR you just authored — invoke right after `gh pr create`. Opus 5.5 reviews and fixes in a loop until clear (or only doc suggestions remain), then Fable 5 does one independent final pass. Hands off a drafted commit message when done; only commits/pushes if the user explicitly approves that specific command. Invoke when the user says "/repo-code-review", "review my new PR", or similar, right after they've opened a PR.
---

# Copilot-style self-review for your own new PR

> **Config:** `your-org`, `~/workspace/<org>/`, `<release-branch>`,
> `<main-branch>` and `<promotion-repos>` come from the `## repo-* skills`
> section of `~/.claude/CLAUDE.md`. If that section is missing or still
> holds placeholder values, stop and tell the user to run
> `/personal:init-personal-skills` — never guess them.

The mirror image of `repo-pr-approve` (reviewing someone else's PR) and
`repo-pr-review` (checking status on your own PRs): this one actually
reviews and fixes a PR you just opened, before you ever request a human
reviewer. Unlike either of those, it edits code and runs tests as part of
the loop; by default it still doesn't commit or push, same as everywhere
else — it only does so with the user's fresh, explicit per-command
approval (see "Committing and pushing" below).

## Scope: only PRs you authored, one at a time

Never run this against a PR authored by someone else. `gh search prs
--author @me` is the only author filter this skill uses.

## Approved-command whitelist (read this before running)

- `gh search prs`, `gh pr view`, `gh pr diff`, `gh api` (read-only)
- `git diff`, `git status`, `git branch --show-current`, `git log`
  (read-only)
- The repo's own test runner (`pytest`, `docker compose ... run`,
  `npm test`/`vitest run`, `ruff`/`eslint`, etc.)
- `Edit` / `Write` on files the review subagents flag — this is the one
  real difference from `repo-pr-approve`: fixes get applied directly to
  the working tree, not just proposed.

`git checkout -b` / `git branch` (branch creation) is allowed — see step
2 below. This was a hard "never" originally (hand off to the user
instead), relaxed 2026-08-26: it's the same throwaway-tracking-branch
pattern `repo-pr-approve` already uses safely (fetch, checkout -b,
delete when done), validated across many runs this session with no
incident.

**Never, without a fresh explicit per-command approval from the user**, in
this skill:
- `git add`, `git commit`, `git push` — see "Committing and pushing" below
  for the exact gate. Default is still: don't. `git stash` stays fully
  out of scope regardless (this skill works entirely in the uncommitted
  working tree, so it's never needed either way).
- `gh pr create`, `gh pr merge`, `gh pr edit --add-reviewer` (this isn't
  the request-a-reviewer step; that's still `repo-pr-review`'s job, run
  separately once this skill reports clean)

## Algorithm

1. **Resolve the target PR.** `/repo-code-review [repo] [pr-number]`.
   If omitted:
   ```
   gh search prs --owner your-org --author @me --state open \
     --json repository,number,title,createdAt
   ```
   pick the most recently created one.

2. **Branch precondition.**
   ```
   gh pr view <number> --repo <owner>/<repo> --json headRefName,baseRefName
   git -C <local-clone-path> status --porcelain
   git -C <local-clone-path> branch --show-current
   ```
   If the current local branch doesn't match `headRefName`, `git status`
   first (session-wide safety protocol) — if there's uncommitted work that
   isn't part of what you're about to review, `git stash push -u` before
   switching, same as `repo-pr-approve` step 5. Then fetch and check out
   the PR's branch yourself:
   ```
   git fetch origin <headRefName>
   git checkout <headRefName>                              # exists locally
   git checkout -b <headRefName> origin/<headRefName>       # first time
   ```
   Since the user just ran `gh pr create` themselves, they're almost always
   already on the right branch — this is the rare path, not the common one.
   At hand-off time (step 6), restore whatever branch was checked out
   before, delete the throwaway tracking branch if one was created, and pop
   any stash — same cleanup discipline as `repo-pr-approve` step 6.

3. **Model selection for the first round.** Prefer Opus 5.5 (`model: "opus"`
   on the `Agent` call — the alias resolves to Opus 5.5, `claude-opus-5-5`). If that call errors out as the model being unavailable in
   this environment, fall back to `model: "fable"` for that round instead.
   This is a technical availability fallback, distinct from step 5's
   deliberate final Fable pass — don't conflate the two triggers when
   reporting back to the user.

4. **The Opus 5.5 loop.** Each round:
   - Get the current diff: `git diff <baseRefName>...HEAD` plus
     `git diff` for uncommitted changes (the working tree already carries
     any fixes from prior rounds — no push needed between rounds).
   - Spawn one review subagent (`Agent`, checking the current
     available-agent-types listing first — use `code-reviewer` if it's
     present in this session, otherwise `general-purpose`) against that diff, with
     `model: "opus"` (Opus 5.5; or the step-3 fallback). Ask it to classify each
     finding as **functional** (real bug, correctness issue, missing test
     coverage, security concern) or **documentation-only** (comment/
     README/docstring wording, no behavior change).
   - **Any functional finding**: apply the fix (`Edit`/`Write`), run the
     smallest test scope that covers it (or the full suite if unsure),
     confirm green, then loop back to another round on the now-updated
     diff.
   - **Zero findings, or all remaining findings are documentation-only**:
     apply the doc fixes if any (cheap, behavior-neutral), then exit the
     loop and move to step 5.
   - **Bound: 5 rounds.** If round 5 still has open functional findings,
     stop and report the unresolved findings to the user rather than
     looping forever.

5. **Final Fable pass.** One independent review subagent, `model: "fable"`,
   against the final diff.
   - Clean (no findings, or doc-only): **stop**. Report success and hand
     off a drafted commit message (see step 6) — done.
   - Finds a real (non-doc) issue: bounce back to step 4 for **exactly one
     more round** (apply fix, verify), then Fable re-checks once more. This
     bounce is capped at one total occurrence: if Fable still isn't clean
     after that single bounce, stop and report the unresolved finding
     rather than ping-ponging further.

6. **Hand off.** Once the loop concludes clean (or hits a bound and needs
   to report out), show:
   - `git diff --stat` for everything the loop touched.
   - A drafted commit message (follow the repo's own commit-message
     convention if one exists).
   - Default: the reminder that the user reviews, commits, and pushes
     themselves to update the actual PR — same as every other workflow in
     this org.

   **Never mention this skill, "self-review", "round", "Opus"/"Fable", or
   any other part of this process in the drafted commit message or PR
   body/comment text itself** — same standing rule as `repo-pr-approve`'s
   two-round protocol, extended here to cover the commit message too, not
   just posted GitHub text. A commit message is a permanent record read by
   people who never see this conversation; it should state what changed
   and why, the same way it would if a human had found and fixed the same
   issues by hand. "Fixed a Dockerfile bug that would have broken the
   container" is fine; "self-review caught a blocker" is not — it exposes
   internal tooling as if it were part of the change's own narrative, and
   reads as noise to a future `git log` reader who has no idea what
   "self-review" refers to. This applies to the *content* of what gets
   handed off, not to your live report to the user in this conversation,
   where round-by-round narration is exactly what they asked for.
   - **With `Git hand-off: on` (the default), only if the user explicitly
     approves committing/pushing this specific diff in this specific turn** (a real go-ahead on the actual
     drafted message shown, not a standing or implied blanket permission —
     see "Committing and pushing" below): `git add` the touched files,
     `git commit` with the approved message, `git push`. Ask again next
     time even if they approved it last time; this is a per-command gate,
     not a session-wide toggle.

## Committing and pushing — gated, not blanket

Everything below describes the default, `Git hand-off: on` (read from the
`## repo-* skills` section of `~/.claude/CLAUDE.md`; missing means `on`).
With `Git hand-off: off`, the per-command approval gate is lifted: once
the loop is clear, commit the touched files with the drafted message and
push to the PR's own branch, stating the local and remote targets first
(see `github-branch-hygiene`). A force-push still needs an explicit OK.

Originally this skill never committed or pushed under any circumstance,
full stop — editing code autonomously across multiple rounds was fine
since it all stayed local and undo-able, but committing to the PR's
branch (visible to everyone watching that PR) was reserved as a
deliberate, human-triggered action, never something that happened
automatically N rounds deep into a loop the user couldn't see live.

Relaxed 2026-08-26 at the user's explicit request: commit/push are now
allowed, but ONLY after a fresh, explicit approval from the user on that
specific command, every single time — not a standing preference, not
inferred from an earlier approval in the same or a prior session. The
underlying reasoning for caution hasn't changed (it's still a visible,
hard-to-reverse action other people watching the PR will see) — what
changed is that the user now wants the option to grant that approval
turn-by-turn rather than the skill refusing categorically. If a fix
genuinely needs to be pushed before the loop can continue (e.g. to
re-trigger CI a local run can't substitute for) and the user hasn't
approved a commit yet, the skill still pauses and hands off the exact
commands by default — approval isn't assumed just because it would be
convenient.

## Why Opus 5.5 first, Fable last, not the reverse

Opus 5.5 is the more capable model and does the actual work: finding real
issues and applying non-trivial fixes across several rounds until the
diff stabilizes. Fable 5's role is different — a fast, independent final
check specifically to catch anything the escalating-fix process itself
might have papered over (a fix that solves the letter of a finding but not
its spirit, a new small issue introduced by an earlier round's fix). Doing
it in this order means the expensive, iterative work happens once, and the
cheap final check runs exactly once at the end — not the other way around,
which would waste the fast model's pass on a diff that's still actively
changing.
