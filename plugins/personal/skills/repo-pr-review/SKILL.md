---
name: repo-pr-review
description: Check status of every open pull request you authored across all org repos — request a review where none exists yet (with per-PR confirmation), or pull down existing review comments and propose follow-up fixes for ones with feedback. Invoke when the user asks to "check my PRs", "review PR status", "/repo-pr-review", or similar.
---

# PR review status + follow-up (org repos)

Surveys every open PR you authored across all `your-org` repos,
sorts each into one of three buckets (no review requested / awaiting review /
has review feedback), and drives the one next action each bucket needs —
never silently, always with your go-ahead for anything visible to others.

## Scope: GitHub only, for now

Covers every repo under the `your-org` GitHub org via `gh search
prs`. `cost-prediction` is GitLab-hosted (`git.project.example`, not
GitHub) and is **intentionally excluded** from this and every other
`/repo-*` command until a GitLab auth approach (`glab` CLI login vs. a
raw REST PAT) is chosen — don't add GitLab merge-request scanning here
without that decision first.

## Approved-command whitelist (read this before running)

Everything below is read-only **except one command**, which is the only
mutation this skill ever performs, and only after an explicit per-PR
confirmation (see step 3):

- `gh search prs`, `gh pr view`, `gh pr diff`, `gh api` (read-only — status,
  reviews, comments, diff content)
- `gh pr edit --add-reviewer <login>` — **the only side-effecting command**,
  requested review is visible to the reviewer and the rest of the repo's
  watchers. Never batch-approved, never defaulted to a fixed reviewer: ask
  per PR, every time, which login to request (no assumed default even if
  the same person reviewed a prior PR in the same repo).

**Never** run `gh pr edit --add-reviewer` without that PR's own confirmation
in the same run, never merge/close/reopen a PR, never push a fix commit
without separately walking through the normal edit → show diff → user
approves → user commits/pushes flow (this skill proposes fixes, it does not
commit or push them — see step 4).

## Algorithm

1. **Enumerate your open PRs across the org** in one call (covers every
   repo under `your-org`, not just ones cloned locally — a repo
   doesn't need a local checkout for this step):
   ```
   gh search prs --owner your-org --author @me --state open \
     --json repository,title,number,url,isDraft,updatedAt
   ```
   Skip drafts (`isDraft: true`) unless the user asks to include them —
   a draft usually means "not ready for review" by design.

2. **Classify each PR** via its full detail:
   ```
   gh pr view <number> --repo <owner>/<name> --json \
     number,title,url,reviewRequests,reviewDecision,reviews,baseRefName,headRefName
   ```
   - **Staging-bound, no gate needed**: `baseRefName == "staging"` in a repo
     that actually runs a staging→preprod→prod chain (check once per repo:
     `gh api repos/<owner>/<name>/branches/preprod` succeeds — if the repo
     has no `preprod` branch, e.g. `infra`/`worker-api`, this bucket
     doesn't apply and normal classification below still governs). Confirmed
     2026-09-21: a branch→staging merge is ungated by design (developer
     merges it themselves, no reviewer needed) — the review gate for a
     staging-chain repo lives at that repo's staging→preprod promotion PR
     instead — check for an open `head=staging,base=preprod` PR and flag if
     none exists). Report these
     PRs as ready-to-merge, take no reviewer-request action on them, and
     don't route them into step 3 below at all, regardless of whether they
     already carry a review request or not.
   - **No review requested**: not staging-bound per above, and
     `reviewRequests` empty AND `reviews` empty.
   - **Awaiting review**: not staging-bound per above; `reviewRequests`
     non-empty, `reviews` still empty — someone's been asked, nothing
     submitted yet. Report only, no action; nudging a reviewer isn't this
     skill's job.
   - **Has review feedback**: `reviews` non-empty (at least one review was
     actually submitted, regardless of current `reviewDecision`) — covers
     `CHANGES_REQUESTED`, `COMMENTED`, and `APPROVED` (approved still gets
     reported, just with no follow-up needed). This bucket applies
     regardless of target branch -- feedback that already exists gets
     reported and followed up the same way whether the PR is staging-bound
     or not.

3. **No-review-requested bucket — confirm before requesting.**
   For each such PR, show the user: repo, PR title/URL, and that repo's
   collaborator list (`gh api repos/<owner>/<name>/collaborators --jq
   '.[].login'`) so they can pick a reviewer. Ask **every time** — no
   default, no reuse of "who reviewed last time in this repo" — per
   standing preference. Only after the user names someone:
   ```
   gh pr edit <number> --repo <owner>/<name> --add-reviewer <login>
   ```
   A PR the user declines to request a review for is left exactly as-is —
   reported, not nagged about again later in the same run.

4. **Has-review-feedback bucket — pull it down, propose, don't touch code
   yet.**
   For each such PR:
   - Fetch the actual review bodies/comments (`reviews` array from step 2,
     plus `gh api repos/<owner>/<name>/pulls/<number>/comments` for
     line-anchored inline comments) and the current diff
     (`gh pr diff <number> --repo <owner>/<name>`).
   - Check the repo out locally if not already present (or `git fetch` +
     inspect the PR's head ref if it is) and read the actual current state
     of each file/line a comment references — a comment may already be
     addressed by a later commit on the branch; don't assume a review
     comment is still live just because it exists.
   - For each **unaddressed** comment, draft a concrete proposed fix (an
     actual diff, not just a restatement of the comment) and present it —
     same as any other code change: show it, wait for explicit go-ahead,
     never edit files unattended just because a review comment exists.
   - For each **already-addressed** comment, say so explicitly (which
     commit fixed it) rather than silently omitting it — confirms the
     review was actually resolved, not just old news.
   - `APPROVED` PRs with no `CHANGES_REQUESTED`/open comments: report as
     clean, no follow-up section needed.

5. **Report** in this shape, grouped by repo:
   - **Staging-bound, no gate needed**: PR title/URL, noted as ready to
     merge on its own (no reviewer action taken or needed here) — the
     review gate for this one lives at the repo's staging→preprod
     promotion PR instead.
   - **No review requested**: PR title/URL, requested-reviewer confirmation
     result (requested `<login>` / declined by user / skipped).
   - **Awaiting review**: PR title/URL, who it's pending on, how long
     (`updatedAt`/review-requested timestamp) — no action taken.
   - **Has feedback**: PR title/URL, `reviewDecision`, per-comment
     addressed/not-addressed status, proposed fixes for the unaddressed
     ones (pending your approval before anything gets edited).

   **Always qualify a PR number with its repo** (`backend-api#54`, not bare
   `#54`), everywhere this shows up — the report, Slack messages, PR
   comments. PR numbers collide across repos in this org, so a bare number
   is genuinely ambiguous, not just less polished.

## Why ask per-PR for the reviewer, never default

Each org repo has a different natural reviewer depending on who owns
that piece (infra vs. portal vs. backend-api aren't all reviewed by the same
person), and even within one repo the right reviewer for a given PR can
depend on what it touches. Guessing a default and letting the user
rubber-stamp it risks requesting the wrong person on GitHub — a visible,
not-quietly-undoable action (the requested reviewer gets a notification).
Asking every time costs a few seconds and never gets it wrong.

## Why propose fixes but never edit/commit them here

Addressing a review comment is exactly the same kind of judgment call as
any other code change: is the suggested fix actually right, does it need
adapting to something the reviewer didn't see, is now even the right time
to push a follow-up commit on this branch. This skill's job stops at
"here's what's unaddressed and here's a concrete proposed diff for it" —
same handoff point as reviewing any other diff in a normal working session,
not a special fast-path just because the suggestion happens to originate
from a GitHub review comment instead of the user.
