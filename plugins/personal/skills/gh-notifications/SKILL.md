---
name: gh-notifications
description: Digest of your unread GitHub notifications for the configured org — sorted into "needs you" (review requests, mentions, assignments, security alerts), "your work" (activity on your PRs/issues, comments, failed CI) and FYI noise (counts only), with each PR's current state checked and the next skill to run suggested. Read-only by default; marking threads read or unwatching repos only after an explicit OK on the exact list. Invoke when the user asks "what's new on GitHub", "check my notifications", "/gh-notifications", or similar, or at the start of a work session.
---

# GitHub notifications digest (configured org)

> **Config:** `your-org` comes from the `## repo-* skills` section of
> `~/.claude/CLAUDE.md`. If that section is missing or still holds
> placeholder values, stop and tell the user to run
> `/personal:init-personal-skills` — never guess the org.

The PR skills ask "which PRs are open and waiting?". This one asks "what
happened since I last looked?" — PRs, issues, mentions, CI, security alerts
— from the GitHub notifications inbox, limited to repos owned by
`your-org`. Personal repos and other orgs are out of scope.

## Approved-command whitelist

Read-only, except the two cleanup actions in step 5, each run only after
the user's OK on the exact list:
- `gh api notifications` (GET) and `gh api <subject.url>` (GET)
- `gh api -X PATCH notifications/threads/<id>` — mark one thread read
- `gh api -X PUT repos/<owner>/<name>/subscription -F ignored=true` —
  stop notifications from a watched repo

Never post, comment, approve, or change anything else.

## Algorithm

1. **Fetch unread threads for the org** — two queries, never a full
   `--paginate` over the whole inbox: watched-repo noise can run to
   thousands of threads and take a minute to page through.
   - **Threads you're involved in** (fast; feeds "Needs you"/"Your work"):
     ```
     gh api notifications --paginate -X GET -f all=false -f participating=true \
       --jq '.[] | select(.repository.owner.login == "your-org")
             | {id, reason, updated_at, type: .subject.type, title: .subject.title,
                url: .subject.url, repo: .repository.name}'
     ```
   - **Latest 100 unread** (one page; feeds the FYI counts, and catches
     `security_alert`/`ci_activity` threads that aren't "participating"):
     ```
     gh api notifications -X GET -f all=false -f per_page=100 \
       --jq '.[] | select(.repository.owner.login == "your-org")
             | {id, reason, updated_at, type: .subject.type, title: .subject.title,
                url: .subject.url, repo: .repository.name}'
     ```
     Merge both by `id`. FYI counts from this page are a floor: if the page
     was full, report them as "N+ (latest 100 checked)", don't paginate.
   If the user asks for "everything since <time>", add `-f all=true -f
   since=<ISO-8601>` to both (includes threads already read on the web).
2. **Sort by `reason`:**

   | Bucket | Reasons | Shown as |
   |---|---|---|
   | Needs you | `review_requested`, `mention`, `team_mention`, `assign`, `security_alert` | full list |
   | Your work | `author`, `comment`, `ci_activity` | full list |
   | FYI | `subscribed`, `state_change`, anything else | count per repo only |

3. **Check current state** for PR threads in the first two buckets (cap at
   30 lookups; say so if more were skipped):
   ```
   gh api <url> --jq '{state, merged, draft, number, html_url,
                       requested: [.requested_reviewers[].login]}'
   ```
   Merged/closed PRs move to a single "resolved since" line — don't send
   the user after finished work. A `review_requested` thread where the
   user is no longer in `requested` is already handled: say so.
4. **Report**, newest first within each bucket, always as `repo#number`
   (numbers collide across repos):
   - **Needs you** — one line each: `repo#n` title, reason, age, link, and
     the next step: review request → `/personal:repo-pr-approve`; mention
     or assignment → open the link.
   - **Your work** — activity on your own PRs → `/personal:repo-pr-review`;
     failed CI → the PR's checks link (`gh pr checks <n> --repo
     your-org/<repo>`).
   - **Resolved** — one line with the merged/closed items.
   - **FYI** — counts per repo, e.g. `api: 12 · ui: 7 (watching)`.
   - If FYI is most of the inbox, say so: watched-repo noise is a
     one-off fix (step 5), not something to read through each time.
5. **Optional cleanup — offer, never do unasked.** Show the exact list
   first and wait for an OK on it:
   - **Mark read**: the FYI threads, the resolved ones, or threads the
     user picks — `gh api -X PATCH notifications/threads/<id>` per thread.
     This changes the user's real inbox on github.com too.
   - **Stop watching** repos that only produce FYI noise — `gh api -X PUT
     repos/your-org/<repo>/subscription -F ignored=true`. Review requests
     and mentions still arrive after this; only "watching" activity stops.

## Rules

- Read-only unless the user approves a specific cleanup list.
- Only repos owned by `your-org`; never widen the scope silently.
- Never quote notification content outside this conversation (no files,
  commits or posts) — titles can carry names and ticket keys.
- `tools/repo-pr-watcher` runs the same org filter as a pre-check before
  each scheduled review, with `ACTIVE_REASONS` = the reasons from step 2
  that can mean a PR needs a review. Change both together.
