---
name: no-ticket-names-in-filenames
description: Never put a ticket ID (PROJ-105, TC0001, etc.) in a file or folder name — name files/folders after what they contain or test, and put the ticket reference inside the file (docstring, header comment, or a leading comment on the specific test function it relates to). Apply by default, not just when asked.
---

# No ticket names in file/folder names

A file or folder named after a ticket (`test_proj105_...py`,
`fixtures/proj105_real_images/`) reads as permanently tied to that ticket,
even once the ticket closes and the code/fixture outlives it — the next
person to touch that code has no idea whether it's still relevant just
from the name, and the name stops describing what the thing actually is.

## How to apply

- **Name files and folders after what they contain or test**, not the
  ticket that motivated them: `test_real_attachment_regression.py`, not
  `test_proj105_real_attachment_regression.py`;
  `fixtures/real_email_attachment_images/`, not
  `fixtures/proj105_real_images/`.
- **The ticket reference still belongs in the file** — just inside its
  content, not its name:
  - A module-level docstring/header comment when everything in the file
    relates to one ticket (e.g. `"""Regression test for PROJ-105 ..."""`).
  - A comment on the specific test function/case when only that one part
    relates to a ticket, in a file that otherwise covers broader ground.
- **This applies to both test files and their fixtures/data folders** —
  same reasoning, same fix, applied together (e.g. renamed `tests/test_proj105_real_attachment_regression.py`
  → `tests/test_real_attachment_regression.py` and
  `tests/fixtures/proj105_real_images/` → `tests/fixtures/real_email_attachment_images/`
  in the same pass, updating every internal path reference and rerunning
  the full suite to confirm nothing broke).
- **Not a license to rename unrelated pre-existing files unprompted** —
  apply this to files/folders you're creating or already touching for the
  current task, the same "touched-file scope" discipline as
  [[python-modern-typing]]'s final-step audits, not a standing invitation
  to go rename things elsewhere in the repo.
- Zip/deliverable archive names sent externally (e.g.
  `proj123-proj456-regression-fixtures.zip`) are a different
  case — an archive's name is itself documentation of what tickets it
  covers for whoever receives it, not a repo file/folder name. Don't
  over-apply this rule there.
