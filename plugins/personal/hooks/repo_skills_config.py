#!/usr/bin/env python3
"""Keep a copy of the ``## repo-* skills`` config and flag plugin updates.

SessionStart hook (no argument, hook JSON on stdin):
  * if ``~/.claude/CLAUDE.md`` holds a filled-in ``## repo-* skills``
    section, save it to ``SAVED`` (only when it changed);
  * fingerprint the installed plugin (version + file contents, since an
    update can keep the same version); on a new fingerprint, or when the
    section is missing/placeholder but a saved copy exists, tell the user
    to run ``/personal:init-personal-skills``, which offers the saved
    values as defaults.

CLI, for the init skill:
  ``show``  print the saved section (exit 1 if there is none)
  ``save``  save the current section now (exit 1 if it isn't filled in)

Python 3.9, stdlib only. The hook never fails a session: any error exits 0
with no output.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

HOME_CLAUDE = os.path.expanduser("~/.claude")
CLAUDE_MD = os.path.join(HOME_CLAUDE, "CLAUDE.md")
SAVED = os.path.join(HOME_CLAUDE, "repo-skills-config.saved.md")
STATE = os.path.join(HOME_CLAUDE, "repo-skills-config.state.json")
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
INIT = "/personal:init-personal-skills"
SECTION_RE = re.compile(r"^## repo-\* skills[ \t]*\n.*?(?=^## |\Z)", re.M | re.S)
PLACEHOLDER_ORGS = {"", "your-org", "<org>"}


def read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def write(path: str, text: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def section(text: str | None) -> str | None:
    m = SECTION_RE.search(text or "")
    return m.group(0).rstrip() + "\n" if m else None


def value(sec: str, key: str) -> str:
    m = re.search(rf"^\s*-\s*{re.escape(key)}:[ \t]*(.*)$", sec, re.M | re.I)
    return m.group(1).strip() if m else ""


def configured(sec: str | None) -> bool:
    """True when the section holds real values, not the template."""
    if not sec:
        return False
    org = value(sec, "GitHub org")
    return org.lower() not in PLACEHOLDER_ORGS and "<" not in org \
        and "<org>" not in value(sec, "Local workspace")


def fingerprint(root: str) -> str:
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in ("__pycache__", ".pytest_cache"))
        for name in sorted(filenames):
            if name.endswith(".pyc"):
                continue
            path = os.path.join(dirpath, name)
            h.update(os.path.relpath(path, root).encode())
            try:
                with open(path, "rb") as fh:
                    h.update(hashlib.sha256(fh.read()).digest())
            except OSError:
                pass
    return h.hexdigest()


def plugin_version(root: str) -> str:
    try:
        meta = json.loads(read(os.path.join(root, ".claude-plugin", "plugin.json")) or "{}")
        return str(meta.get("version") or "?")
    except ValueError:
        return "?"


def save_current() -> bool:
    sec = section(read(CLAUDE_MD))
    if not configured(sec):
        return False
    if read(SAVED) != sec:
        write(SAVED, sec)
    return True


def session_start() -> dict | None:
    has_config = save_current()
    saved = read(SAVED)

    try:
        state = json.loads(read(STATE) or "{}")
    except ValueError:
        state = {}
    fp, version = fingerprint(PLUGIN_ROOT), plugin_version(PLUGIN_ROOT)
    first_run = "fingerprint" not in state
    updated = not first_run and state.get("fingerprint") != fp
    if state.get("fingerprint") != fp:
        write(STATE, json.dumps({"fingerprint": fp, "version": version}) + "\n")

    if updated:
        old = state.get("version") or "?"
        what = (f"The personal plugin was updated ({old} -> {version})"
                if old != version else f"The personal plugin was updated ({version})")
        reason = f"{what}. Run {INIT} to review the repo-* skills config"
    elif not has_config and saved:
        reason = ("The ## repo-* skills section of ~/.claude/CLAUDE.md is missing or "
                  f"still has placeholders, but a saved copy exists. Run {INIT}")
    elif first_run and not has_config:
        reason = f"The repo-* skills are not set up yet. Run {INIT}"
    else:
        return None

    if saved and configured(saved):
        reason += (f" — it will offer your saved values (GitHub org "
                   f"{value(saved, 'GitHub org')}) as defaults.")
    else:
        reason += "."
    return {
        "systemMessage": reason,
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                f"{reason} Mention this to the user once, early in your first reply, "
                f"and offer to run {INIT}; don't run it without their OK."),
        },
    }


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "session-start"
    if cmd == "show":
        saved = read(SAVED)
        if not saved:
            return 1
        sys.stdout.write(saved)
        return 0
    if cmd == "save":
        return 0 if save_current() else 1
    try:
        sys.stdin.read()
    except OSError:
        pass
    try:
        out = session_start()
    except Exception:  # never break session start
        return 0
    if out:
        sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
