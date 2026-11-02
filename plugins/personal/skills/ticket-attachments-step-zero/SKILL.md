---
name: ticket-attachments-step-zero
description: When planning any new task sourced from a Jira ticket (or similar tracker), check the ticket body/description for attachment wording first, and confirm whether real attachments exist — if so, the plan's first step is always downloading them to the right place, before step 1. Apply by default, not just when asked.
---

# Check for ticket attachments before planning step 1

Tickets often say "see attached", "See Attachments for test images", or
similar, describing real evidence (screenshots, sample files, test
images) that the actual fix work depends on. It's easy to plan straight
into the code-diagnosis work and only notice the real attachments exist
much later — by which point the plan has already been built and partly
executed around synthetic recreations instead of the real thing.

## How to apply

- **Before writing any plan for a ticket-sourced task**, read the
  ticket's own description/body text for attachment-indicating wording
  ("attach", "attachment", "screenshot", "see attached", "sample file",
  "test image(s)", etc.) — not just the summary line.
- **Separately, always check the ticket's actual `attachment` field**
  (e.g. `getJiraIssue` with `fields: ["attachment"]`) regardless of
  whether the body text mentions attachments explicitly — a ticket can
  have real attachments without the description text calling them out by
  name, and the reverse (text says "see attached" with nothing actually
  attached, e.g. an inline image reference in the description itself
  rather than a tracked attachment).
- **If real attachments exist, make downloading them Step 0 of the
  plan — before step 1, not folded into a later step.** Name the exact
  files, their real filenames, and a concrete target path in the relevant
  repo (e.g. `tests/fixtures/<descriptive-name>/`) where they should
  land. See [[no-ticket-names-in-filenames]] for how to name that path —
  descriptive of content, not the ticket ID.
- **No authenticated attachment-download tool is available** — Jira
  attachment content URLs require auth that isn't accessible
  programmatically from a plain fetch. Step 0 in practice means asking
  the user to download the files and confirm the drop location, then
  verifying the files landed with the expected sizes (cross-check against
  the ticket's own attachment metadata — filename, byte size — before
  trusting they're genuine, complete downloads).
- **Why this matters, learned from a real incident:** the
  ticket's own description said "See Attachments for test images" and
  the ticket actually had the 6 real repro images attached (uploaded by
  the reporter) the whole time. The investigation instead spent real
  effort reconstructing synthetic recreations and querying the database
  for indirect evidence before anyone thought to check the ticket's own
  attachments directly — all of which would have been unnecessary if
  Step 0 had been "download the real attachments" from the start.
