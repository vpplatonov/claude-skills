---
name: ci-test-implementation
description: Pytest marker taxonomy and verification protocol for org repos — unmarked/integration/long-running (e.g. backend-api's llm_regression), what GitHub Actions is allowed to run, the required local double-run before calling anything "CI-ready", and the rule that any GitHub-admin dependency (branch protection, environment secrets, Secrets Manager seeding) gets its own linked Jira follow-up ticket rather than a buried note. Apply whenever adding or changing tests in a repo with this pytest.ini shape, or wiring a new GitHub Actions workflow.
---

# CI/test implementation pattern (org repos)

Confirmed 2026-09-18 while building PROJ-101 (backend-api's three evaluation
surfaces): a real bug was caught by this pattern before it shipped — a new
test that hit a real local Postgres was left unmarked, which would have
made a bare `pytest` fail on every PR (no Postgres exists on a GitHub
runner) instead of being cleanly skipped. This skill exists so that class
of mistake gets caught by convention, not by accident.

## Marker taxonomy

Every Python repo in the org with tests follows the same three-tier shape
(confirmed in `backend-api/pytest.ini`; conda/env-per-repo mechanics
are out of scope here):

```ini
[pytest]
markers =
    integration: requires live external service credentials (e.g. SendGrid) - excluded by default, run with -m integration
    llm_regression: exercises the real pipeline via a live DeepInfra-backed doc-processor-local - excluded by default (real LLM cost/latency), run with -m llm_regression
addopts = -m "not integration and not llm_regression"
```

`llm_regression` here is backend-api's own name for its **long-running
tier** — the concept is general (any test that takes real
minutes/real money to run, regardless of which repo or what it's actually
testing), the marker *name* is repo-specific. Don't assume `llm_regression`
is the name to reuse elsewhere.

- **Unmarked** — fast, hermetic, no network, no live credentials (mocks/
  stubs only). This is what a bare `pytest` invocation runs, and therefore
  what every GitHub Actions PR/push test job actually exercises.
- **`integration`** — needs a live external service or real credentials to
  do anything meaningful, **including a local-only dependency** (a local
  Postgres container, a local Langfuse stack) — locality doesn't exempt a
  test from this marker, only whether the dependency is real/live does.
  Excluded by default; opted into via `pytest -m integration`.
- **Long-running tier** (backend-api names its `llm_regression`; a
  different repo may have no such marker yet) — real model calls, a slow
  live pipeline, or otherwise minutes-not-seconds wall-clock, regardless
  of cost. Excluded by default same as `integration`, but with one
  further, absolute rule below.

**If a repo doesn't yet have a marker for this tier and a new test needs
one, introduce a new marker for it** (register it in that repo's
`pytest.ini` `markers =` block and fold it into `addopts`'s exclusion,
matching the `llm_regression` pattern above) rather than either leaving
the test unmarked or force-fitting it under `integration` — `integration`
is for "needs a live dependency," not "takes a long time"; a test can be
both, in which case it can carry both markers.

**A new test that touches a live/local-container dependency must get the
`integration` marker before it's considered done — not "it happens to
self-skip when unreachable."** A `skipif(not reachable())` guard is fine
as defense-in-depth (see `test_feedback_correction_dedup.py`,
`test_feedback_scorer.py`), but it is not a substitute for the marker: the
marker is what makes `-m "not integration"` a correct, honest description
of "this run touched nothing external," rather than something that
happens to be true by luck of what's reachable on this machine right now.

## Long-running tests never run on an automatic GitHub Actions trigger

Confirmed 2026-09-18, generalized the same day from an initial (too
narrow) framing of "llm_regression never runs on GitHub" — the rule is
about the **tier** (long-running, whatever it's called in a given repo),
not about that one marker name. Refined again the same day once a
pre-existing counter-example turned up (`backend-api`'s `llm-regression.yml`
is `workflow_dispatch`-only and does run `pytest -m llm_regression`
directly): the actual rule is **no automatic trigger** — `pull_request`,
`push`, `schedule` — **may ever invoke a test carrying a long-running
marker, in any repo.** A deploy-triggered workflow that seems like a
legitimate exception (e.g. a pre-deploy regression check firing on push
to `preprod`) is not one: automate everything that can safely run on a
GitHub-hosted runner (liveness/readiness polling, waiting for a candidate
image to actually be serving, posting the result), then hand off the
actual long-running test invocation to a human running it locally — print
or Slack the exact command, don't run it yourself on the runner. PROJ-101's
`preprod-regression.yml` was originally built running `pytest -m
llm_regression` directly on push-to-preprod and had to be reworked once
this was made explicit; don't repeat that mistake for any push/pull_request/
schedule trigger, in this repo or any other.

**A manual `workflow_dispatch`-only workflow is the one narrow exception**,
since a human explicitly clicking "run" is the same act as running it
locally, just on a shared runner instead of a laptop — that's what
`llm-regression.yml` already is, and it's fine as-is. The line is: would
this test ever run *without* a person deciding, right then, to run it?
If yes (any push/PR/cron trigger), it's not allowed. If a human has to
show up and press the button every time, it's allowed.

## Local double-run protocol — required before calling a change "CI-ready"

Two separate local runs, both must be green, before saying a PR's tests
will pass in CI:

1. **`pytest`** (bare, default `addopts`) — this is the literal command
   (or as close as the target CI workflow's own `run:` step gets to it;
   check the actual workflow file, don't assume) that a GitHub PR/push job
   will execute. If this doesn't pass locally, the PR check will be red.
2. **`pytest -m integration`** — proves the deeper, live-dependency
   coverage also passes (real local Postgres, real local service). Start
   the local dependency first if it isn't already running (e.g. `docker
   compose --profile db up -d docproc-db` for backend-api).

Long-running-tier tests (`llm_regression` in backend-api, or whatever a
given repo calls it) are run as a **third, separate, manual** invocation
(`pytest -m <that marker> ...`) when actually needed (e.g. verifying a
model-behavior change) — never folded into either of the two runs above,
and never used as a stand-in for "did I break CI."

## Any GitHub-admin dependency gets its own linked Jira follow-up ticket

If completing a piece of work depends on an action only a human with the
right access can take — adding a required branch-protection check, adding
a GitHub Environment secret, seeding a value into AWS Secrets Manager,
granting a GitHub App new permissions/repos, admin-merging past a broken
required check — that dependency is never left as a sentence in a PR
description or a code comment alone. File a separate Jira ticket:

- **Description**: exactly what admin action is needed, why (what breaks
  or stays incomplete without it), and who plausibly has the access
  (infra/secrets-write precedent in this org: check who sought/granted
  access on the most recent similar case rather than guessing).
- **Link**: "relates to" (or "is blocked by", if the action is a hard
  prerequisite) the ticket the work item came from.
- **Comment on the originating ticket**: a short pointer to the new
  ticket, so anyone reading the original ticket later sees the dependency
  immediately rather than having to reconstruct it from a PR thread.

This mirrors why a follow-up ticket got filed during PR review work earlier the same
day (a worker-api follow-up, linked back to its origin ticket) — the same
discipline, just now also covering infra/ops actions discovered while
*building* something, not only while *reviewing* someone else's PR.

## Why this exists as a skill

The environment/tooling half (conda-only, `pytest.ini` shape, no venv) is
conventional. This skill covers the *decision* half: which marker a new
test gets, the absolute no-GitHub rule for long-running/billed tests, the
two-run verification protocol, and the admin-follow-up-ticket obligation —
all of which are judgment calls made while writing code, not standing
tooling facts, so they belong in a skill that loads when relevant rather
than a memory note read once.
