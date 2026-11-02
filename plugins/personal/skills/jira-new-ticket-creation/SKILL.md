---
name: jira-new-ticket-creation
description: Link-type discipline when filing a new Jira ticket that derives from existing work (a follow-up, an admin/ops dependency, a discovered gap) — default to a non-blocking link ("Relates"), never "Blocks", unless a genuine blocking dependency exists and the user has explicitly confirmed it should be modeled that way. Apply whenever creating a Jira issue that will be linked back to another ticket.
---

# Jira new-ticket link-type discipline

Learned from a real incident: three GitHub-admin follow-up
tickets were filed while implementing a feature ticket, and one of them
(seeding observability credentials) was linked as **"Blocks"**
("feature is blocked by follow-up") on the reasoning that the feedback-scorer
CronJob can't do anything useful without those credentials. The user
corrected this: the follow-up tickets are **next steps to enable the work
in CI/production, not blockers on the ticket's own completion** — the
codebase implementation was done, tests were correctly marked, and the
admin actions are separate enablement work, not a gate on the feature ticket itself.

## Default: non-blocking link, always

When filing a new ticket that derives from existing work, default to a
**"Relates"** (or equivalently non-directional/non-blocking) link back to
the originating ticket. This is the default even when the new ticket
genuinely describes something the originating ticket's fuller value
depends on (e.g. "seed these credentials so this CronJob is actually
useful once deployed") — depending on something for full *value* is not
the same as being *blocked* from *completion*. A code-complete,
correctly-tested ticket is done; a follow-up admin/ops ticket enabling it
in a live environment is separate, sequenced work, not a precondition.

## Before ever using "Blocks"

1. **Check whether the relationship can be expressed as "Relates" instead.**
   Ask: does the originating ticket's own definition of done actually
   require the new ticket to complete first, or does the new ticket just
   make the originating work fully effective/live? The latter is
   "Relates," not "Blocks" — this is true far more often than it first
   seems, especially for infra/ops/admin follow-ups discovered while
   building something (secrets, branch protection, environment config).
2. **If a genuine blocking dependency exists** (the originating ticket
   literally cannot be marked done, or its own next step cannot start,
   until the new ticket resolves) — **ask the user before creating the
   "Blocks" link**, rather than deciding unilaterally. State plainly which
   ticket you believe blocks which, and why, and let the user confirm or
   correct it. Don't default to "Blocks" and let the user catch it after
   the fact — reverse of the incident this skill exists to
   prevent.

## Link direction, once "Blocks" is actually confirmed appropriate

Per Jira's actual (not the tool docstring's paraphrased) semantics,
confirmed empirically via `linkedIssues(<key>, "is blocked by")`/
`linkedIssues(<key>, "blocks")` JQL after creating a test link — don't
trust the docstring's direction claim blindly, verify with a JQL check
before reporting the link as correct:
```
createIssueLink(inwardIssue=<the blocker>, outwardIssue=<the blocked ticket>, type="Blocks")
```
produces "`<blocked ticket>` is blocked by `<the blocker>`" as the visible
relationship on the blocked ticket's own page.

## No delete-issue-link tool exists in this MCP connector

Confirmed 2026-09-18: there is no reachable `deleteIssueLink`-style tool.
A wrong link (wrong type, wrong direction) cannot be removed
programmatically — it can only be added-to/superseded by a second,
correct link, and the wrong one must be flagged to the user for manual
removal in the Jira UI (Issue → Links → remove). Say this explicitly
rather than silently leaving a stray incorrect link with no mention of it.
