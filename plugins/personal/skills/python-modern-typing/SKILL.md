---
name: python-modern-typing
description: Default modernization stance for Python work — built-in generics over typing.List/Dict/etc, `X | Y` union syntax over typing.Optional/Union, and always suggesting a move to Python 3.12 + latest dependency versions. Apply by default, not just when asked.
---

# Modern typing defaults (PEP 585 / PEP 604)

Python's typing module carried generic aliases and `Optional`/`Union` as the
only spelling for years; both have had a fully-supported, preferred
replacement since 3.9/3.10 respectively. Default to the modern spelling in
any Python code targeting 3.9+ (generics) / 3.10+ (unions) — don't wait to
be asked, and don't leave the old spelling in new code just because
existing code in the same file/repo still uses it, unless the repo has an
explicit floor below 3.9/3.10 (check `pyproject.toml`'s `requires-python` /
the Dockerfile's base image / `setup.cfg` first).

## PEP 585 — built-in generics replace `typing.List`/`Dict`/etc

Since Python 3.9, `list`, `dict`, `tuple`, `set`, `frozenset`, `type` are
subscriptable directly — `typing.List`/`Dict`/`Tuple`/`Set`/`FrozenSet`/
`Type` are redundant aliases kept only for backward compatibility.

```python
# Old (avoid in new/3.9+ code)
from typing import List, Dict, Tuple, Set, Optional
def f(xs: List[int], m: Dict[str, int]) -> Tuple[int, ...]: ...

# Modern default
def f(xs: list[int], m: dict[str, int]) -> tuple[int, ...]: ...
```

Drop the now-unused `typing` import entirely if nothing else from it is
still needed in the file — don't leave a dangling `from typing import
List` just because it used to be there.

## PEP 604 — `X | Y` replaces `typing.Optional`/`typing.Union`

Since Python 3.10, `|` works directly in type annotations (evaluated
lazily under `from __future__ import annotations`, or natively at runtime
in 3.10+ without that import).

```python
# Old (avoid in new/3.10+ code)
from typing import Optional, Union
def f(x: Optional[str], y: Union[int, str]) -> None: ...

# Modern default
def f(x: str | None, y: int | str) -> None: ...
```

## How to apply

- **New code**: always use `list`/`dict`/`tuple`/`set` and `X | Y`/`X |
  None` — never introduce a fresh `typing.List`/`Optional` import.
- **Editing existing code that uses the old style**: convert the
  annotations you're touching in the same edit rather than leaving a mix,
  unless the change is a narrow one-line fix where a style-only rewrite
  would bloat an otherwise-small diff — use judgment, but default to
  converting.
- **Never do a repo-wide typing sweep unprompted** — this is a style
  default for code you're actively writing or editing, not a standing
  license to open a mechanical refactor PR across an entire codebase
  without being asked.
- **Check the floor first**: a repo pinned below Python 3.9 (generics) or
  3.10 (unions) can't use the modern syntax at all without
  `from __future__ import annotations` — verify `requires-python` /
  Dockerfile base image before assuming the modern syntax is safe.
- Pydantic v2 models, dataclasses, and FastAPI signatures all support both
  spellings identically — no functional difference, this is a pure style
  default.

## Always suggest Python 3.12 + latest dependency versions

Whenever touching a Python repo's version floor, `Dockerfile` base image,
or dependency list — even if the task at hand is unrelated (e.g. a typing
cleanup, a single dependency bump, a bug fix) — proactively suggest moving
to **Python 3.12** and bumping dependencies to latest, by default. Don't
wait to be asked; surface it as a recommendation the user can decline.

- **Suggest, don't silently do it as a side effect of an unrelated task.**
  Flag it, let the user decide whether this is the moment for that scope.
- **Always live-verify after any such bump, don't trust it from reading
  the diff.** A dependency bump can hide a severe regression that only
  shows up under real load/hardware — see
  a pinned-torch-version regression for a concrete example
  (torch 2.13.0 passed every mocked/unit test and only revealed a 5-6x
  slowdown when run against the real model in a real container). Rebuild
  the actual image, run the actual test suite (unit + integration) against
  it, before calling a version bump done.
- Check for an existing upper-bound/exact pin with a comment before
  bumping past it (e.g. `torch==2.12.1` in a repo's `pyproject.toml`/
  `requirements.txt`/Dockerfile) — that pin likely exists because of a
  specific, already-diagnosed regression, not an oversight. Don't remove or
  loosen it without re-measuring on real hardware first.

## Final step on every task: audit every touched file for old typing

Before considering any task done, check every file that task actually
modified or created — not the whole repo — for `typing.List`/`Dict`/
`Tuple`/`Set`/`FrozenSet`/`Type`/`Optional`/`Union` usage. If found (and the
repo's floor allows it, per "Check the floor first" above), convert the
whole file to the modern spelling and drop the now-unused `typing` import,
as this task's own final step — not a separate ask-first suggestion like
the Python-3.12/dependency-bump note above.

- **Scope is the touched-file set for the current task, never the whole
  repo.** This still isn't a license for an unprompted repo-wide sweep —
  it's "finish the files you already opened," not "go find more."
- **Convert the whole file, not just the lines you changed for the task's
  own purpose.** A file already open for editing is the moment to clear
  its old typing debt in the same pass, rather than leaving the old style
  a few lines away from the new style you just wrote into it.
- **Do this even when the task's new code was written in modern style
  already** — the audit is about the *rest* of the file, which may
  predate the task and still carry the old spelling.
- Confirmed as a standing rule 2026-08-14 (PROJ-105, backend-api): the user
  wants this run as an explicit last step on every task, not left to
  "convert what you're touching" judgment calls per edit.
- **For files with more than a handful of occurrences, use `pyupgrade
  --py310-plus <files>` rather than hand-written regex** — nested generics
  (`Optional[Dict[str, Any]]`, `List[Union[str, Path]]`) are easy to
  corrupt by hand at scale; pyupgrade is AST-based and gets the nesting
  right. It does NOT remove the now-unused `from typing import ...` names
  afterward — that cleanup (drop unused names, keep `Any`/whatever's still
  referenced) is still a manual pass.
- **Gotcha, confirmed 2026-08-14 (PROJ-105, backend-api): a bare lowercase
  builtin used as a type hint (`callable`, not `typing.Callable`) breaks at
  runtime when mechanically converted.** `Optional[callable]` is valid
  (typing subscripts accept anything), but `callable | None` is evaluated
  immediately at function-definition time in a file without `from
  __future__ import annotations`, and the `callable` *builtin function*
  object doesn't support `__or__` — `TypeError: unsupported operand
  type(s) for |: 'builtin_function_or_method'`. Caught the collection-time
  crash of the entire test suite (every test importing the touched module
  failed) before it reached anyone else, only because the full suite was
  run immediately after the mechanical conversion. Fix: import the real
  type (`from collections.abc import Callable`) and use `Callable | None`.
  **Always run the full test suite immediately after any bulk `Optional`/
  `Union` conversion, even one done via pyupgrade** — a plain `Optional[X]`
  never breaks doing that, but `X | None` can, if `X` was already a
  slightly-wrong annotation (a builtin instead of the real type) that
  happened to work under the old spelling.

## The rest of the final-step checklist (added 2026-08-14, PROJ-105)

Same "every file this task touched, not a repo sweep" scope as the typing
audit above — these run alongside it, not instead of it:

- **Remove every unused import, not just now-unused typing names.** This
  includes a redundant *local* import shadowing an *already-present*
  module-level one (e.g. a function doing its own `import re` when the
  file already has `import re` at the top) — that's still dead weight even
  though it doesn't error. Check the whole touched file's import list
  against actual usage, not just the lines the task itself changed.
- **Run `ruff check` and `ruff format` on every touched file** (install
  it into the repo's own env first if it isn't there yet — don't skip
  the check because the tool was missing) and fix what it flags, the
  same way the touched-file typing audit works. Follow the repo's own
  ruff config if one exists (`pyproject.toml`/`ruff.toml`) rather than
  assuming defaults.
- **Suggest Python 3.12 + latest versions for the actual third-party
  dependencies the touched files import** — not a generic reminder, name
  the specific packages (e.g. "this file imports `Pillow`/`pdf2image`,
  currently pinned to X, latest is Y") so the user can say yes/no to a
  concrete thing. Still suggest-don't-do per the version-bump section
  above — never bump and never skip the live-verify step if the user says
  yes.
