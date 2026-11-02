---
name: no-pii-in-artifacts
description: Never put a real person's name (or other PII) in file names, file content, docstrings, commit messages, or any other artifact — reference the ticket/case number instead. Apply by default, not just when asked.
---

# No PII in file names, file content, or anywhere else

Any deliverable that gets built — a zip, a test file, a fixture, a
docstring, a README, a commit message — must not carry a real person's name
(reporter, customer contact, colleague) anywhere in it, including the
container's own name (a zip file named after who reported the bug is still
a PII leak, even if every file *inside* it was scrubbed).

## Why this matters

Learned from a real incident (a regression-fixture zip):
first pass scrubbed a reporter's name out of an internal test filename per
instruction, but the outer zip's own filename
(`proj123-<reporter-name>-regression-fixtures.zip`) still carried it — caught
only because the user checked twice. A first pass that stops at "the file
the user pointed at" misses every other place the same name snuck in:
docstrings, README prose, JSON fixture `"description"` fields, even the
archive's own name.

## How to apply

- **Use ticket/case identifiers, never a person's name**, for: file names,
  archive/zip names, test names, fixture `description` fields, docstrings,
  README prose, commit messages, Jira comments, Slack messages about the
  artifact — anywhere the artifact or its description gets written down.
  `PROJ-123`, `TC0001` identify the work precisely without naming
  anyone.
- **Scrub exhaustively, not just where told.** When asked to fix one
  instance (e.g. "rename this file"), `grep -rl` the *entire* deliverable
  for the name (and check the outer container's own name too — a zip/tar/
  directory name is content, not just a wrapper) before considering it
  done. A single missed occurrence anywhere defeats the whole point.
- **Synthetic fixture data needs the same treatment even earlier.** When
  building a synthetic reproduction of a real bug report, don't carry the
  real reporter's name into the synthetic data or its documentation at
  all — reference the ticket number from the first draft, not as a
  find-and-replace afterward.
- **Generic placeholder names in synthetic test data are fine** (e.g.
  "Jane Doe", a fictional company name) — this rule is about real
  identifiable people, not about avoiding *any* name-shaped string in test
  fixtures.
- **This is a default stance, not a per-request check-box** — apply it to
  every future artifact (zips, fixtures, docs, commits) without being
  asked each time, the same way secret-masking and terse-response
  preferences apply by default.
