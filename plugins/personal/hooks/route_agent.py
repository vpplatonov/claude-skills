#!/usr/bin/env python3
"""PreToolUse hook for the Agent (Task) tool: route subagents to a model.

Reads the hook input on stdin, classifies the subagent task with the
keyword rules below, and when a rule picks a different model than the one
requested it either rewrites the call (``rewrite``) or denies it with a
"retry with model X" reason (``deny``). Mode comes from ``MODEL_ROUTING_MODE``
or ``- Model routing: <mode>`` in the ``## repo-* skills`` section of
``~/.claude/CLAUDE.md``; default ``rewrite``. ``off`` disables it.

Runs on Python 3.9, stdlib only. Any error -> exit 0 with no output, so
the tool call always goes ahead unchanged.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

OVERRIDE = "[model-override]"
MODES = ("rewrite", "deny", "off")
TIER = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3}
CLAUDE_MD = os.path.expanduser("~/.claude/CLAUDE.md")
LOG = os.path.expanduser("~/.claude/model-routing.log")

# First match wins. "cheap" rules may lower an explicitly requested model;
# every other rule only raises it (or fills it in when none was given).
RULES = [
    {
        "name": "large-change",
        "model": "fable",
        "cheap": False,
        "pattern": r"\b(migrat(e|ion|ing)|architect(ure|ural)?|re-?architect|"
                   r"major refactor|large refactor|codebase-wide|deep research|"
                   r"quantitative analysis|scientific)\b",
    },
    {
        "name": "scoped-code",
        "model": "sonnet",
        "cheap": False,
        "pattern": r"\b(fix (the |a |this )?bug|bug ?fix|implement (the |this )?spec|"
                   r"per the spec|add (a )?unit tests?|write (the )?tests?)\b",
    },
    {
        "name": "search-read",
        "model": "haiku",
        "cheap": True,
        "types": ("explore",),
        "pattern": r"\b(search (the |for )|grep|find (all |the )?(files?|usages?|"
                   r"references|where)|locate|list (all |the )?files|read (the )?logs?|"
                   r"scan (the )?logs?|summari[sz]e|run (the )?tests?|classif(y|ication)|"
                   r"tag(ging)?|extract)\b",
    },
]
# A cheap rule never applies when the task also edits code or needs judgment.
NOT_CHEAP = re.compile(
    r"\b(fix|edit|modify|implement|refactor|write (the )?code|change the code|"
    r"review|decide|design|debug|patch|update the code)\b", re.I)


def norm_model(value: object) -> str | None:
    """Map 'sonnet', 'claude-sonnet-5-5', ... to a tier name; None if unknown."""
    if not isinstance(value, str):
        return None
    v = value.lower()
    for name in TIER:
        if name in v:
            return name
    return None


def mode_from_claude_md() -> str | None:
    try:
        with open(CLAUDE_MD, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    m = re.search(r"^## repo-\* skills\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return None
    k = re.search(r"^\s*-\s*Model routing:\s*(\S+)", m.group(1), re.M | re.I)
    return k.group(1).lower() if k else None


def get_mode() -> str:
    mode = (os.environ.get("MODEL_ROUTING_MODE") or mode_from_claude_md() or "rewrite").lower()
    return mode if mode in MODES else "rewrite"


def classify(ti: dict) -> dict | None:
    text = " ".join(str(ti.get(k) or "") for k in ("description", "prompt"))
    stype = str(ti.get("subagent_type") or "").lower()
    for rule in RULES:
        hit = stype in rule.get("types", ()) or re.search(rule["pattern"], text, re.I)
        if not hit:
            continue
        if rule["cheap"] and NOT_CHEAP.search(text):
            continue
        return rule
    return None


def decide(ti: dict) -> tuple[str | None, str]:
    """Return (target model or None for no change, reason)."""
    if OVERRIDE in str(ti.get("prompt") or ""):
        return None, "override"
    rule = classify(ti)
    if rule is None:
        return None, "no-rule"
    want = rule["model"]
    have = norm_model(ti.get("model"))
    if have == want:
        return None, "already:" + rule["name"]
    if have is not None and TIER[want] < TIER[have] and not rule["cheap"]:
        return None, "keep-explicit:" + rule["name"]
    return want, rule["name"]


def log(entry: dict) -> None:
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def main() -> None:
    data = json.load(sys.stdin)
    if not isinstance(data, dict) or data.get("tool_name") not in ("Agent", "Task"):
        return
    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        return
    mode = get_mode()
    if mode == "off":
        return
    target, why = decide(ti)
    log({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": mode,
        "subagent_type": ti.get("subagent_type"),
        "requested": ti.get("model"),
        "routed": target,
        "why": why,
        "description": str(ti.get("description") or "")[:80],
    })
    if target is None:
        return
    if mode == "deny":
        out = {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "Model routing ({}): retry the same Agent call unchanged except "
                "model: \"{}\". To keep your choice, add [model-override] to the "
                "prompt.".format(why, target)),
        }}
    else:
        new = dict(ti)  # updatedInput replaces the whole input: copy everything
        new["model"] = target
        out = {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "Model routing: {} -> {}".format(why, target),
            "updatedInput": new,
            "additionalContext": (
                "Model routing: this subagent was sent to {} instead of {} (rule: {}). "
                "Its result is valid; don't retry on another model. To force a model, "
                "put [model-override] in the prompt.".format(
                    target, ti.get("model") or "the default", why)),
        }}
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # never break the tool call
        pass
    sys.exit(0)
