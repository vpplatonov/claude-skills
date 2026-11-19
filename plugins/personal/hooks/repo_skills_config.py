#!/usr/bin/env python3
"""Keep a copy of the ``## repo-* skills`` config and flag plugin updates.

SessionStart hook (no argument, hook JSON on stdin):
  * if ``~/.claude/CLAUDE.md`` holds a filled-in ``## repo-* skills``
    section (up to the next ``#`` or ``##`` heading), save it to ``SAVED``
    (only when it changed);
  * fingerprint the installed plugin's file contents (plugin.json
    included; an update can keep the same version) and tell the user to
    run ``/personal:init-personal-skills``, which offers the saved values
    as defaults: once per new fingerprint, once on a first run with no
    config, and every session while the section is missing/placeholder
    but a saved copy exists.

The fingerprint skips dot-entries other than ``.claude-plugin`` (Claude
Code writes per-session ``.in_use/<pid>`` markers into the plugin root) and
Python caches. State is keyed per plugin install (root minus its version
folder), so a dev checkout and the marketplace copy don't overwrite each
other, while a version bump still counts as an update of the same install.
The state file is read-modify-written without a lock; two sessions starting
in the same instant may both show the update notice, which is harmless.

CLI, for the init skill:
  ``show``  print the saved section (exit 1 if there is none usable)
  ``save``  save the current section now (exit 1 if it isn't filled in,
            exit 2 if writing failed)

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
SECTION_RE = re.compile(r"^## repo-\* skills[ \t]*\n.*?(?=^#{1,2} |\Z)", re.M | re.S)
PLACEHOLDER_ORGS = {"", "your-org", "<org>"}
VERSION_DIR = re.compile(r"^v?\d+\.\d+(\.\d+)?([-+.][\w.-]*)?$")


def read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8-sig") as fh:  # -sig: tolerate a BOM
            return fh.read()
    except (OSError, ValueError):  # ValueError: not valid UTF-8
        return None


def write(path: str, text: str) -> None:
    tmp = f"{path}.{os.getpid()}.tmp"  # unique: two sessions may start at once
    try:
        # 0600: the section can hold an org email and Slack channel ID
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with open(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def section(text: str | None) -> str | None:
    m = SECTION_RE.search(text or "")
    return m.group(0).rstrip() + "\n" if m else None


def value(sec: str, key: str) -> str:
    m = re.search(rf"^\s*-\s*{re.escape(key)}:[ \t]*(.*)$", sec, re.M | re.I)
    return re.sub(r"<!--.*?-->", "", m.group(1)).strip() if m else ""


def placeholder(text: str) -> bool:
    return bool(re.search(r"<[^<>]+>", text))


def configured(sec: str | None) -> bool:
    """True when the section holds real values, not the template."""
    if not sec:
        return False
    org = value(sec, "GitHub org")
    return org.lower() not in PLACEHOLDER_ORGS and not placeholder(org) \
        and not placeholder(value(sec, "Local workspace"))


def fingerprint(root: str) -> str:
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__"
                             and (not d.startswith(".") or d == ".claude-plugin"))
        for name in sorted(filenames):
            if name.startswith(".") or name.endswith(".pyc"):
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


def install_key(root: str, version: str) -> str:
    """The plugin root without its trailing version folder, if it has one.

    Matches the folder against plugin.json's version, or, if that is
    missing, against a version-like name (``1.2``, ``1.2.3-beta``).
    """
    root = os.path.realpath(root)
    base = os.path.basename(root)
    if base == version or VERSION_DIR.match(base):
        return os.path.dirname(root)
    return root


def save_current() -> bool:
    """Save a filled-in section; True if one exists. Raises OSError on write failure."""
    sec = section(read(CLAUDE_MD))
    if not configured(sec):
        return False
    if read(SAVED) != sec:
        write(SAVED, sec)
    return True


def session_start() -> dict | None:
    try:
        has_config = save_current()
    except OSError:  # still report, even if the copy can't be written
        has_config = configured(section(read(CLAUDE_MD)))
    saved = read(SAVED)

    try:
        states = json.loads(read(STATE) or "{}")
    except ValueError:
        states = {}
    if not isinstance(states, dict):
        states = {}
    fp, version = fingerprint(PLUGIN_ROOT), plugin_version(PLUGIN_ROOT)
    key = install_key(PLUGIN_ROOT, version)
    state = states.get(key) if isinstance(states.get(key), dict) else {}
    first_run = "fingerprint" not in state
    updated = not first_run and state.get("fingerprint") != fp
    if state.get("fingerprint") != fp:
        try:
            latest = json.loads(read(STATE) or "{}")  # re-read: merge only our key
        except ValueError:
            latest = {}
        latest = latest if isinstance(latest, dict) else {}
        latest[key] = {"fingerprint": fp, "version": version}
        try:
            write(STATE, json.dumps(latest, indent=1) + "\n")
        except OSError:
            pass

    if updated:
        old = state.get("version") or "?"
        what = (f"The personal plugin was updated ({old} -> {version})"
                if old != version else f"The personal plugin was updated ({version})")
        reason = f"{what}. Run {INIT} to review the repo-* skills config"
    elif not has_config and configured(saved):
        reason = ("The ## repo-* skills section of ~/.claude/CLAUDE.md is missing or "
                  f"still has placeholders, but a saved copy exists (delete {SAVED} if you "
                  f"removed it on purpose). Run {INIT}")
    elif first_run and not has_config:
        reason = f"The repo-* skills are not set up yet. Run {INIT}"
    else:
        return None

    if configured(saved):
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
    cmd = argv[1] if len(argv) > 1 else None
    if cmd == "show":
        saved = read(SAVED)
        if not configured(saved):
            return 1
        sys.stdout.write(saved)
        return 0
    if cmd == "save":
        try:
            return 0 if save_current() else 1
        except OSError as exc:
            sys.stderr.write(f"could not save {SAVED}: {exc}\n")
            return 2
    if cmd is not None:
        sys.stderr.write("usage: repo_skills_config.py [show|save]  (no argument = SessionStart hook)\n")
        return 2
    try:
        sys.stdin.buffer.read()
        out = session_start()
    except Exception:  # never break session start
        return 0
    if out:
        sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
