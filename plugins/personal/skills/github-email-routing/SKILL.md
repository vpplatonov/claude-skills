---
name: github-email-routing
description: Route GitHub notification emails for one org to that org's email address while your own repos keep using your personal email — via GitHub's Custom routing (preferred) or a Gmail filter + forward (fallback). Checks what's verified on the account, gives the exact settings to click and the exact Gmail query, then verifies read-only that org mails stopped arriving in the personal inbox. Never changes GitHub or mail settings itself. Invoke when the user says "route org GitHub emails to my work address", "GitHub notifications go to the wrong inbox", "/github-email-routing", or similar.
---

# Route an org's GitHub emails to the org address

> **Config:** `GitHub org` and `Org email` come from the `## repo-* skills`
> section of `~/.claude/CLAUDE.md`. If `GitHub org` is missing or a
> placeholder, stop and tell the user to run `/personal:init-personal-skills`.
> If `Org email` is missing, ask for it — it's company-specific, so never
> suggest one — and offer to save it as `- Org email: <address>` in that
> section (show the line, write it only after an OK, touch nothing else).

The setup this is for: one personal GitHub account used for both personal
and org work. GitHub sends every notification email to the account's
primary (personal) address. Org notifications should land in the org
mailbox instead, personal ones stay where they are.

## What Claude can and can't do here

| Step | Who |
|---|---|
| Add/verify an email on GitHub, set Custom routing | User, in the browser — no API exists |
| Create a Gmail filter or forwarding | User, in Gmail settings |
| Check which emails are verified on the account | Claude, `gh api user/emails` (read-only) |
| Check where org mails are arriving | Claude, Gmail connector search (read-only) |

Never create mail filters, forwarding, auto-reply rules or labels, and
never change GitHub settings — explain, check, and give exact values only.

## Steps

1. **Check the account's emails** (read-only):
   ```
   gh api user/emails --jq '.[] | {email, verified, primary}'
   ```
   A `404` here means the token lacks the scope. `gh` suggests the broad
   `user` scope; `user:email` is enough for this read-only call, so offer
   only that: `gh auth refresh -h github.com -s user:email` (it opens a
   browser login). Run it only after the user's OK, or skip the check and
   ask the user what Settings → Emails shows.
   - `Org email` listed and `verified: true` → go to step 3.
   - Listed but unverified → step 2, part 2 only.
   - Not listed → step 2.
2. **Add and verify the org email** — the user does this:
   1. https://github.com/settings/emails → "Add email address" → `Org email`.
   2. Open GitHub's verification mail in the org mailbox and click the
      link. It's added as a secondary address; the primary email and the
      commit email (noreply, if "Keep my email addresses private" is on)
      don't change.
   Then rerun step 1.
3. **Custom routing** — the user does this, at
   https://github.com/settings/notifications/custom_routing:
   "Add new route" → org `GitHub org` → email `Org email` → Save.
   The dropdown only lists verified emails, and the org list only orgs the
   user is a *member* of.
4. **If it doesn't work**, match the symptom:

   | Symptom | Cause / fix |
   |---|---|
   | "Email is already in use" when adding | Attached to another GitHub account (e.g. an old work account) — remove it there, or use the Gmail fallback |
   | No verification mail | Org mail server may filter `noreply@github.com` — check spam/quarantine, or ask the org's IT |
   | Verified, but not in the route's email list | Org restricts notifications to its verified domain(s); the email must be on one (org settings → "Restrict email notifications to verified domains") |
   | Org not in the route's org list | User is an outside collaborator, not a member — routing is per membership; use the Gmail fallback |

5. **Fallback: Gmail filter + forward** — only if custom routing isn't
   possible. Give the user exact values; they create it themselves:
   - Query (GitHub's `List-Id` is `<repo>.<org>.github.com`):
     ```
     from:notifications@github.com list:<GitHub org>.github.com
     ```
     Suggest pasting it into Gmail search first to confirm it matches only
     org mails.
   - Gmail → Settings → Forwarding: add `Org email` and confirm Gmail's
     verification code (it arrives in the org mailbox).
   - Search → "Create filter" → Forward to `Org email`, plus "Skip the
     Inbox" if they don't want copies.
6. **Verify** with the Gmail connector, read-only, after some org activity
   (a comment or review on an org PR):
   ```
   from:notifications@github.com list:<GitHub org>.github.com newer_than:2d
   ```
   - Custom routing: new org mails should **stop** appearing in Gmail. Only
     mails from before the route was saved should match.
   - Gmail fallback: they still appear in Gmail (forwarded copies leave
     from there); confirm with the user they arrive in the org mailbox.
   Report counts and dates only — not subjects (they can carry names and
   ticket keys).
7. **Clean up the old filter.** Once custom routing is confirmed, tell the
   user they can delete their Gmail filter (and the forwarding address, if
   nothing else uses it) — Gmail → Settings → Filters / Forwarding. Their
   call; never suggest deleting before step 6 confirms the route works.

## Rules

- Never write `Org email` or any real address into the plugin repo or a
  commit — only into `~/.claude/CLAUDE.md`, after the user's OK.
- Read-only `gh api` GETs and read-only Gmail searches only.
- The `user:email` scope refresh, saving the config line, and every
  settings change are the user's decision, asked each time.
