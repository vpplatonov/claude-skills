---
name: repo-pr-approve
description: Deep-verify and review open PRs across org repos where you're a requested reviewer (not the author) — checks out each branch, actually runs the test/lint suite, tamper-tests any claimed guardrails, cross-checks PR-body claims against measured reality. A finding in that first pass gets posted as a PR comment and stops there; a clean first pass gets exactly one more independent check forced onto Opus 5.5 before either approving (clean) or commenting and stopping (finding) — always with your go-ahead before anything posts. Invoke when the user asks to "review the PRs waiting on me", "check what I need to review", "/repo-pr-approve", or similar.
---

# Reviewing other people's PRs (org repos)

> **Config:** `your-org`, `~/workspace/<org>/`, `<release-branch>`,
> `<main-branch>` and `<promotion-repos>` come from the `## repo-* skills`
> section of `~/.claude/CLAUDE.md`. If that section is missing or still
> holds placeholder values, stop and tell the user to run
> `/personal:init-personal-skills` — never guess them.

The mirror image of `repo-pr-review`: that skill checks status on PRs *you*
authored. This one is you acting as *reviewer* on someone else's PR — the
exact workflow used against a teammate's stacked PR series, a pair of
soft-delete PRs, a conventions ADR, and backend/frontend PRs in the same
sitting. The distinguishing trait of that session
wasn't reading diffs — it was refusing to trust anything (a description, a
claimed test count, a claimed guardrail) without independently reproducing
it, and it caught real, otherwise-invisible bugs that a read-only review
would have missed entirely.

## Scope: any org repo, GitHub only

Same exclusion as `repo-pr-review`: repos hosted outside GitHub (e.g.
GitLab) stay excluded from every `/repo-*` command until a GitLab auth
approach is chosen.

Confirmed 2026-09-21: in a repo running a <release-branch> → <main-branch> chain, a
branch → <release-branch> merge is ungated by design and doesn't need a review before
merge (`repo-pr-review` won't request one). If you're queued as a
reviewer on one anyway, that's an explicit ask — review it the same as any
other PR here, this skill's own job doesn't change based on target branch.

Extended 2026-09-23: the real code review for that chain now happens on
the <release-branch> → <main-branch> promotion PR itself (`<promotion-repos>`) — step 1's
enumeration always checks for it, not just when GitHub's review-requested
marker happens to be live on it (see step 1's third source). Release-level
readiness (Jira ticket sweep, merge-conflict/integration-test
check, status transitions) is out of scope — this skill's job on
that PR is just the code-review pass itself, same Round 1/Round 2
discipline as any other PR here.

## Approved-command whitelist

Read-only for everything except:
- The final review-posting step, always confirmed per PR first:
  `gh pr review <n> --approve --body-file ...` (Round 2 clean only) or
  `gh pr comment <n> --body-file ...` (any finding, either round — see the
  two-round decision protocol below). No `--request-changes`: a finding
  always ends in a comment, never a formal request-changes review.
  Standing allowance (confirmed 2026-10-02): `gh pr review <n> --approve
  --body-file ...` and `gh pr comment <n> --body-file ...` against
  `your-org/*` are explicitly permitted commands for this skill
  once the user has given the per-PR go-ahead. The skill text alone does not
  clear the permission classifier: a matching Bash allow rule must also
  exist in settings (`Bash(gh pr review:*)`, `Bash(gh pr comment:*)`). If
  the post is still denied, stop and tell the user; don't work around it.
- A short Slack notification to the PR's author, sent in the same
  confirmation as the GitHub post it accompanies (`slack_send_message`,
  channel_id = the author's Slack user ID from `slack_search_users`) — see
  "Notify the requester in Slack" below.
- Local git operations needed to set up and clean up an **isolated
  worktree** for the review — see step 6, this skill always reviews in a
  worktree, never by checking the PR's branch out in the user's main
  working copy: `git fetch`, `git worktree add <repo>/.review-worktrees/
  pr-<n> origin/<branch>`, `git worktree remove` and `git branch -D` on
  the throwaway branch when done — never force-pushing or touching the
  PR's actual remote branch, never touching the user's main checkout or
  another open branch's state.
- Test/build tooling native to the repo (`npm install`, `pytest`,
  `docker compose ... run`, `ruff check`, `tsc --noEmit`, etc.) and, when a
  fix requires it, a scratch `_tamper*` file inside the review
  worktree — always deleted before moving on, never committed.

**Never** merge, close, or reopen a PR. Never push a fix commit — this
skill verifies and reports, the author or the user pushes fixes. Never post
a review verdict without the user's explicit go-ahead on that specific PR,
every time — a batch "approve all" is not a substitute for a decision on
each one.

## Concurrency lock — required before step 1, and after every exit path

This skill can run both manually (you, interactively) and on an optional
unattended schedule (`tools/repo-pr-watcher` in this plugin's repo, a
launchd job running `claude -p /personal:repo-pr-approve`). Both paths share one lock so
they never run the review protocol at the same time:

- Before step 1, try to create the lock directory:
  `mkdir ~/.claude/repo-pr-approve.lock.d`
- If that fails because the directory already exists: check its age first
  (`stat -f %m ~/.claude/repo-pr-approve.lock.d` on macOS). If
  it's older than 65 minutes, treat it as stale (a previous run crashed
  without cleaning up) — remove it, create it fresh, note the stale-lock
  recovery in your final report, and proceed. Otherwise, a review is
  genuinely in progress elsewhere right now: stop immediately, do not
  enumerate PRs, do not touch any repo, and tell the user a review
  (automated or manual) is already running.
- If you acquired the lock, remove it
  (`rmdir ~/.claude/repo-pr-approve.lock.d`) before you finish
  — on normal completion, a Round 1 stop, a Round 2 stop, or any error.
  Never leave it behind.

## Algorithm

Step 2 is a dedup/inclusion gate that runs per PR before anything else.
Steps 3-8 constitute **Round 1**. Step 9 is the two-round decision protocol
that replaces any free-form verdict choice — see there for how Round 1's
outcome determines whether a Round 2 (forced Opus 5.5) pass happens at all.

1. **Enumerate PRs where review is requested from you, plus PRs where
   you've previously commented, plus every open PR into `<main-branch>` (the
   <release-branch> → <main-branch> promotion and per-ticket promotions) for repos running
   that chain**, across every repo under the org:
   ```
   gh search prs --owner your-org --review-requested=@me --state open \
     --json repository,title,number,url,isDraft,updatedAt,author
   gh search prs --owner your-org --commenter=@me --state open \
     --json repository,title,number,url,isDraft,updatedAt,author
   ```
   The second query exists because the review-request marker can go away
   (repo settings, or the author manually clearing it) even though the
   author still wants your eyes after landing a fix — a live request isn't
   the only signal that you're expected back on a PR.

   **Third source, added 2026-09-23**: for the repos that run a
   <release-branch> → <main-branch> chain (`<promotion-repos>`), the real code review for that chain now
   happens on the <release-branch> → <main-branch> promotion PR itself, not just on the
   ungated branch → <release-branch> PRs. Always check for one, whether or not either
   query above happened to catch it.

   Extended 2026-10-01: list **every** open PR into `<main-branch>`, not just
   `head=<release-branch>`. Releases also promote per ticket from a feature or
   promotion branch, and those carry no review request or prior comment
   from you, so the two searches above miss them (one such PR went
   unseen this way).
   Skip PRs you authored yourself — those belong to `repo-pr-review`:
   ```
   for r in <promotion-repos>; do
     gh pr list --repo your-org/$r --base <main-branch> \
       --state open --json number,title,url,isDraft,updatedAt,author,headRefName
   done
   ```
   Tag any PR found this way the same as a review-requested match for step
   2's gate — it's a recurring, mandatory review point, not an opt-in "you
   commented once" PR, so it always gets the plain dedup-by-self-
   touchpoint check (skip only if nothing changed since your last comment
   or review on it), never the stricter three-condition inclusion gate.

   Merge all three lists, deduplicating by repo + PR number, and tag each
   PR with which source(s) matched — step 2 treats a comment-only match
   (from the second query alone) differently from every other case. Unlike
   `repo-pr-review`, do **not** blanket-skip drafts — a draft with an
   explicit review request means the author wants eyes now regardless of
   status. Group results by repo and, within a repo, note if several PRs
   form a **stacked chain** (each PR's base is the prior PR's branch) —
   review those bottom-up, since later ones only make sense once earlier
   ones are understood, and diff against the *actual* base branch, not
   always `<release-branch>`.

2. **Dedup/inclusion gate — decide whether each PR from step 1 gets a
   Round 1 pass at all.** Handle the tags from step 1 differently:

   - **PR matched the review-requested query, or the <release-branch> → <main-branch>
     promotion-PR check** — dedup check, skip if nothing changed. `gh pr comment` (this skill's only way to post a
     finding) is a plain issue-style comment, not a submitted GitHub
     review — unlike `gh pr review --approve`, it never clears the pending
     review request. So a PR that stopped at a Round 1 or Round 2 finding
     keeps resurfacing in step 1's search on every later run, manual or via
     an unattended schedule, even though nothing
     about it has changed. Confirmed 2026-09-10: the
     watcher re-ran the full protocol on an unchanged PR and posted the
     same finding a second time under your name, because nothing checked
     for the first one first.
     ```
     gh pr view <n> --repo <owner>/<name> --json headRefOid,comments,reviews,author
     ```
     Find your own most recent **self-touchpoint** on this PR — whichever
     is later of: the most recent comment authored by your own GitHub login
     (`comments[].createdAt`), or the most recent review you submitted in
     any state (`reviews[].submittedAt` where `reviews[].author.login` is
     you) — an **approval counts exactly like a comment** for this dedup
     check, since re-running Round 1/2 on a PR you already formally
     approved, with nothing changed since, is the same wasted,
     under-your-own-name duplication this gate exists to prevent. If
     neither a comment nor a review from you exists, there is nothing to
     dedup against — proceed to step 3 normally. If one exists, fetch the
     head commit's own timestamp and compare it to that self-touchpoint's
     timestamp:
     ```
     gh api repos/<owner>/<name>/commits/<headRefOid> --jq .commit.committer.date
     ```
     - **Head commit's date is at or before your last self-touchpoint**:
       nothing has changed since you last reviewed (or approved) this PR.
       Skip it entirely — no worktree, no re-running tests, no new comment,
       no Round 2. Note it in the final report as "already approved at this
       head (`<sha>`), no action" or "already reviewed (commented) at this
       head (`<sha>`), no action" — whichever touchpoint was actually later
       — and move to the next PR.
     - **Head commit's date is after your last self-touchpoint**: new
       commits landed since you last posted or approved. Proceed to Round
       1, but do it as the re-verify pass described in step 10 (check what
       actually changed relative to your prior finding or approval) rather
       than a from-scratch review.

   - **PR matched only the commenter query** (no live request, but you've
     commented or reviewed there before) — inclusion check, opt in only on
     an explicit ask. Having commented or reviewed once is not by itself a
     reason to look again; most such PRs are simply done with you. Include
     one in this run's working set only if all three hold:
     1. You have at least one prior comment or submitted review on it
        (`gh pr view <n> --repo <owner>/<name> --json
        comments,reviews,commits,headRefOid` — find your own login's most
        recent comment or review, same combined self-touchpoint as the
        review-requested dedup check above).
     2. At least one commit landed after that self-touchpoint's
        timestamp — a genuine code follow-up, not just more conversation.
     3. At least one comment posted after that follow-up commit — from the
        author or anyone else — that explicitly asks you for another look
        (e.g. "re-review", "PTAL again", "can you take another pass",
        "ready for you to check again", a direct ask aimed at you). Read it
        for actual intent, not a fixed keyword match: a reply that just
        says "thanks" or moves on to something unrelated does not count.

     If all three hold, include the PR and proceed to Round 1 as the
     re-verify pass described in step 10. If any is missing, leave the PR
     alone entirely — no worktree, no comment, and no report entry beyond
     an optional one-line "commented/reviewed before, no active re-review
     ask, skipped" if you want a record.

3. **Read the description and diff, but treat every claim in the
   description as unverified until checked.** This is the core discipline
   this skill exists to enforce:
   - **Numbers** (test counts, file counts, bundle sizes, coverage) — rerun
     and measure, don't trust as stated. PR descriptions drift stale after
     follow-up commits; this session found several 2x-off test-count claims
     and a ~10 KB stale bundle-size figure this way, none of them bugs, all
     worth flagging so the next reader isn't misled.
   - **Claimed guardrails, security mechanisms, or "fixed" bugs** — tamper
     test them. Inject the exact violation the guard exists to catch, run
     the guard's actual command/script verbatim (copy it out of the CI
     workflow file, don't paraphrase it), and confirm it fails closed. Do
     not stop at reading the regex/logic and reasoning that it looks right —
     a missing `-E` flag on a `git grep` call silently defeated two content
     guardrails across an entire PR stack, and reading the code alone would
     not have caught it (git grep defaults to POSIX basic regex, where `|`
     and `(...)` are literal characters, not metacharacters — the pattern
     was matching against one long literal string that could never appear in
     real code). Only running it with a real violation present exposed it.
   - **Concurrency/race fixes** — hand-trace the exact scenario the PR
     describes through the actual code before trusting the fix, and check
     whether the test proves the mechanism (e.g. explicitly asserts two
     concurrent operations are *still blocked* mid-flight before releasing
     a lock) rather than just asserting a correct end state, which can pass
     by luck on a single run even with a subtly broken implementation.
   - **Migrations** — read `upgrade`/`downgrade` for correctness (additive,
     nullable, correct drop order), but see the test-DB contamination
     pitfall below before concluding a schema-related test failure means
     the PR is broken.

4. **Actually run the test/lint suite**, using the repo's own documented
   convention — don't invent a different one:
   - Python repos: conda env named after the repo folder (per standing
     convention), `pytest`; for a repo whose `CLAUDE.md` documents a Docker
     Compose test profile, use that
     (`docker compose ... --profile test run --rm <api-test-service> pytest ...`)
     — never bare `pytest`
     against the host, integration tests there need the compose network.
   - JS/TS repos: `npm install`, `npx vitest run` / repo's own test script,
     `npx tsc --noEmit` or the repo's `typecheck` script, the repo's own
     lint script if one exists (not every repo has one — check before
     assuming `ruff`/`eslint` applies).
   - Compare full-suite results against the PR's claimed pass/fail counts;
     when a failure appears that the PR body doesn't mention, trace it via
     `git log`/`git blame`/ancestry checks to find out whether it predates
     this PR's own commits (inherited debt — say so explicitly, don't
     misattribute) or is genuinely introduced by this diff.

5. **Repo/environment gotchas that produce false findings** — rule these
   out before reporting anything as a real problem:
   - **Shared test-DB contamination (any repo with a Docker Compose
     Postgres setup).** The test profile (`<api-test-service>`) and the
     persistent dev container often point at the *same* Postgres
     database. Two branches that each define a same-numbered Alembic
     revision (a documented, expected collision during a stacked-PR
     rollout — e.g. two sibling PRs both adding their own "0005") will
     silently corrupt each other's schema state if tested back-to-back:
     alembic sees itself "already at head" by revision number and skips
     applying the branch's actual migration content. Signature errors:
     `column X does not exist`, `Can't locate revision identified by 'N'`.
     Fix: `docker compose exec -T <db-service> psql -U <user> -d <db> -c "DROP SCHEMA
     public CASCADE; CREATE SCHEMA public;"`, then rerun — don't conclude
     the PR is broken until this is ruled out.
   - **Local Node version newer than CI's pinned version** can break the
     jsdom/`localStorage` interaction (Node's own native experimental
     `localStorage` global collides with jsdom's shim) — an entire test
     file can appear to fail for reasons that have nothing to do with the
     PR. Confirm with `NODE_OPTIONS="--localstorage-file=/tmp/scratch.db"`
     before concluding a real regression; compare against what CI's own
     logs actually show for the same commit.
   - **Stale local npm/package caches** can produce a false `ERESOLVE` on
     `npm install` that a clean-cache reinstall resolves instantly (`rm -rf
     node_modules package-lock.json && npm cache clean --force && npm
     install`, repeat 2-3x to confirm it's not a fluke). Don't report this
     as a PR problem without ruling out your own environment first.
   - **Lockfile-commit conventions differ per repo** — some repos don't
     commit `package-lock.json` (gitignored, CI uses `npm install`),
     others do. Check with `git ls-files <lockfile>`
     before a blanket `rm -rf node_modules package-lock.json` cleanup, or
     you will delete and need to restore a tracked file.
   - **Leftover untracked files from your own earlier work in the same
     repo** (e.g. a scratch test file from a previous, unrelated review in
     the same session) can get picked up by a Docker build's `COPY` and
     cause unrelated import errors in a completely different branch's test
     run. `mv` it aside before testing, restore it after.

6. **Always review in an isolated git worktree — never check the PR's
   branch out in the user's main working copy.**
   ```
   git fetch origin <pr-branch>
   git worktree add <repo>/.review-worktrees/pr-<n> origin/<pr-branch>
   ```
   Run every subsequent step (installing deps, running tests/lint, tamper
   tests) inside that worktree directory, not the main checkout. This is
   why no `git status`/`git stash` dance is needed here the way
   `repo-pull`/`repo-code-review` need it elsewhere: the user's
   current branch and any of their own uncommitted work in the main
   checkout are never touched at all, by construction — see "Why always a
   worktree" below.

7. **Clean up the worktree when done, every time.**
   ```
   git worktree remove --force <repo>/.review-worktrees/pr-<n>
   git branch -D <local-tracking-branch-if-one-was-created>
   ```
   Also remove any scratch files/directories the review itself created
   inside the worktree before removing it if you want them inspectable
   first (`node_modules`, generated `package-lock.json` if the repo
   doesn't commit one, `build/`, `storybook-static/`, tamper-test scratch
   files) — though removing the whole worktree directory takes all of
   that with it either way. Confirm with `git worktree list` that only
   pre-existing worktrees remain, and `git status --porcelain` in the main
   checkout that nothing there changed either.

8. **Compose findings**, separating:
   - **Real, currently-reproducible problems** — state exactly how you
     reproduced it (the command, the injected input, the exact output),
     not just a description of the theoretical concern.
   - **Pre-existing/unrelated debt** the PR happens to touch or inherit —
     say explicitly that it predates this PR and name the commit that
     actually introduced it if you traced it.
   - **PR-body claims that don't match measured reality** — call these out
     even when they aren't bugs; a reviewer or future reader relying on a
     stated number deserves to know it's stale.
   - **Open questions worth asking rather than asserting** — if you can
     construct a plausible failure scenario but can't cheaply prove it
     happens (e.g. a narrow concurrency window), say so as a question, not
     a claim, and note what would be needed to confirm it either way.

9. **Two-round decision protocol.** Steps 3-8 are Round 1, done directly by
   whichever model is running this skill. **Every time a comment or
   approval actually goes up on GitHub** (Round 1 finding, Round 2 finding,
   or Round 2 approval), draft the matching short Slack version in the same
   turn and get one combined go-ahead for both — see "Notify the requester
   in Slack" below; don't ask twice.
   - **Round 1 finds a real, reproducible problem** (step 8's first
     category): post it as a PR comment (`gh pr comment <n> --body-file`,
     confirmed with the user first — see "Why never auto-post" below) and
     **stop**. Do not proceed to Round 2, do not approve, do not post a
     formal `--request-changes` review — a comment is enough to hand the
     finding back to the author. Pre-existing debt and open questions
     (step 8's other categories) aren't "findings" for this gate on their
     own; note them in the same comment, but they don't by themselves
     block Round 2.
   - **Round 1 is clear**: proceed to **Round 2** — exactly one more
     independent pass, forced onto Opus 5.5 (`model: "opus"`) regardless of what
     model ran Round 1 (spawn via `Agent` if the current session isn't
     already Opus 5.5). Re-examine the diff at its current head fresh, not
     just Round 1's notes — the point is a genuinely independent second
     look before a formal approval goes out.
     - **Round 2 is also clear**: post the formal approval
       (`gh pr review <n> --approve --body-file`, confirmed with the user
       first).
     - **Round 2 finds something**: post it as a PR comment (confirmed
       with the user first) and **stop** — never auto-approve after a
       Round 2 finding, and never loop back to a third round or back into
       Round 1. Two rounds, total, always.
   - If the same root cause affects another PR already merged or under
     separate review, flag it there too (a comment, not a new review)
     rather than letting it go unnoticed.
   - **Never mention "Round 1"/"Round 2" or this skill's two-round process
     in the text that actually gets posted to GitHub or Slack.** That's
     internal bookkeeping for deciding whether to approve — nobody reading
     the PR uses this skill or knows what a "round" refers to here, so it
     reads as unexplained jargon, not information. State the verdict and
     the evidence directly ("Reviewed and verified...", "Found the
     following issue...") instead of describing the process that produced
     it. Round terminology stays fine in the report to the user (this
     conversation) and the skill's own internal reasoning — it just never
     belongs in the posted comment/review body itself.

10. **When a PR changes after your review — a fix lands, or the author
   pushes back on a finding — re-verify against the actual current head
   commit before changing your review.** Don't defensively re-assert your
   original finding, and don't take the author's word for it either;
   check out the new head, rerun the exact same reproduction, and report
   what you actually find. If the author disputes something and turns out
   to be right, say so plainly and flip your review — that's the same
   discipline this skill applies to the PR itself, applied to your own
   prior conclusion.

11. **If the PR's own thread already has another reviewer's findings, read
    those before your own pass.** Sometimes the real blocking issue is
    already sitting there and unresolved (e.g. "the deliverable file was
    described in the commit message but never actually `git add`ed") —
    verify and echo it clearly rather than only hunting for something new.

## Notify the requester in Slack

Whenever a comment or approval actually gets posted to GitHub (any point in
step 9), also draft a short Slack DM to the PR author pointing them at it —
don't make them notice the GitHub notification on their own.

- **Find the author's Slack account**: `slack_search_users` with the PR
  author's display name (from `gh pr view`'s `author` field — GitHub
  logins and Slack display names don't always match, so search by name,
  not login). If nothing matches, say so and skip the Slack step for that
  PR rather than guessing a channel.
- **Draft it short** — a pointer, not a duplicate of the full comment: repo
  `#n`, one line on the verdict (approved / found an issue, briefly what
  kind), and the PR URL. The full detail lives in the GitHub comment
  itself; this is just the "go look" nudge.
  - Finding: `"<repo>#<n> — reviewed, found <one-line issue summary>. <url>"`
  - Approval: `"<repo>#<n> — reviewed and approved. <url>"`
- **Show the draft directly, don't use `AskUserQuestion` to pick a
  recipient** — the recipient is already determined (the PR author), so
  there's no multiple-choice decision to make here; just show the drafted
  text as part of the same confirmation as the GitHub post.
- Send with `slack_send_message` (channel_id = the author's Slack user ID)
  only after that combined go-ahead — same "never auto-post" standard as
  the GitHub action itself, not a lesser bar just because it's "only" a
  heads-up.
- **Sequence it: GitHub first, Slack only after it succeeds.** Never send
  the Slack DM in the same parallel batch as the `gh` post. Confirm the `gh`
  command exited 0 (the comment/review URL printed) before sending; if the
  post was denied or failed, send no Slack message. (2026-10-02: a denied
  `gh pr review --approve` ran in parallel with the DMs, so "reviewed and
  approved" reached the author with no approval on GitHub.)

## Report shape

Per PR: repo, number, title, current head SHA you actually tested against,
what you ran and what it showed (pass/fail counts, tamper-test results),
findings grouped per step 8's categories, which round the review concluded
at (Round 1 finding / Round 2 clean → approve / Round 2 finding), and the
exact action taken pending the user's go-ahead. A PR skipped by step 2's
dedup check needs only its one-line "already reviewed at this head, no
action" note, not the full shape.

**Always qualify a PR number with its repo** (`api#54`, not bare
`#54`), everywhere — reports to the user, Slack messages, PR comments, doc
notes. PR numbers collide across repos in this org (e.g. `api#54`
and `ui#54` were two entirely different PRs in the same review
batch), so a bare number is genuinely ambiguous, not just less polished.

## Live-verify against the real dependency when one is feasibly available

For concurrency, timeout, health-check, or external-service-integration changes, mocked unit tests can't fully prove the behavior — they prove the code does what the mock lets it do. Before settling for mocked-only coverage, check whether the real dependency is actually reachable (a cached model, a container you can start, a reachable service) and run a live check: start the real service, fire genuinely concurrent requests, hit the real endpoint under real load. Confirmed 2026-08-12 (PROJ-103/PROJ-106, an inference service's single-flight guard + api outcome signals): the model was already cached locally from an earlier session, so a live run (real concurrent HTTP requests, real 503 busy responses, real Prometheus counter deltas) was one `curl` loop away and caught nothing new — but it turned "the unit tests pass" into concrete, reviewer-grade evidence ("fired two real concurrent requests, the second got a real 503 with this exact body"). Don't wait for a reviewer to ask for this — treat it as the default bar for this class of change.

## Why tamper-test instead of just reading the guard code

A regex, a lock, an allowlist check — these are exactly the kind of code
that *looks* obviously correct on inspection and is exactly where a subtle,
invisible bug survives review after review, because nobody actually feeds
it the input it exists to catch. The whole point of a guardrail is the
behavior at the boundary; reading the implementation checks the shape of
the code, not whether the boundary actually holds. It costs one throwaway
file and thirty seconds to find out for certain instead of assuming.

## Why always a worktree, never a checkout in the main copy

Checking the PR's branch out directly in the user's main working copy
means every step in this skill that follows — installing deps, running
tests, tamper-testing a guardrail — happens on top of whatever the user
was doing before the review started, and requires a stash-before/
restore-after dance (see `repo-pull` and `repo-code-review`, which
both need exactly that dance because they don't have this option) to put
things back correctly. A worktree checks the PR's branch out into its own
directory sharing the same `.git`, so the main checkout's branch and any
uncommitted work there are never touched at all — there's no state to
protect and no state to restore, by construction, not by discipline. It
also means a review can run in parallel with the user actively working in
the main checkout without either interfering with the other.

## Why exactly two rounds, forced Opus 5.5 for the second

A single pass risks a false-clear: whoever ran Round 1 — tests, tamper
tests, live-verification and all — can still miss something a second,
independent read would catch. But re-reviewing indefinitely trades a
bounded cost for diminishing returns without much real signal past the
second pass. Two rounds is the balance: Round 1 does the expensive,
evidence-gathering work; if it already found something, a second pass adds
nothing — hand the finding back immediately rather than spending another
full pass to double-confirm a bug that's already confirmed. If Round 1
came back clean, exactly one more independent pass — deliberately forced
onto Opus 5.5, the more capable model, regardless of what ran Round 1 — is the
one check worth paying for before an approval goes out under your name.
Confirmed with the user (2026-08-20): no third round either way, and a
Round 2 finding never gets auto-approved or bounced back to fix anything —
this skill never edits code, so a finding always ends in a comment, never
a fix.

## Why never auto-post

Same reasoning as `repo-pr-review`: approving, requesting changes, or even
commenting on someone else's PR is visible to them and everyone watching
that repo, and — unlike your own PR's status check — it's a judgment call
about someone else's work that they will read as your considered opinion.
Getting it wrong (approving something broken, or blocking something fine
over a misunderstanding) costs more than the few seconds it takes to show
the draft and wait for a go-ahead. The Slack notification carries the same
weight even though it's shorter — it's still a message landing in someone
else's DMs under your name — so it rides on the exact same go-ahead as the
GitHub post, never a separate, lower bar.
