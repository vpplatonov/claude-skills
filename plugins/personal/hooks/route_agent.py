#!/usr/bin/env python3
"""PreToolUse hook for the Agent (Task) tool: route subagents to a model.

Reads the hook input on stdin and classifies the subagent task: first with
Sonnet (``claude -p --model sonnet``, prompt in ``classify_prompt.md``),
then, on timeout, error, bad JSON or low confidence, with the keyword rules
below. ``MODEL_ROUTING_CLASSIFIER=regex`` skips Sonnet.

Policy: raise-only (fill in a missing model, raise a weaker one), except
that haiku may replace a stronger model for cheap, read-only work; haiku
is never picked for anything else. ``rewrite`` changes ``model`` in place;
``deny`` blocks only raises, with a "retry with model X" reason (a lowering
passes unchanged, so retries can't oscillate). Mode comes from
``MODEL_ROUTING_MODE``
or ``- Model routing: <mode>`` in the ``## repo-* skills`` section of
``~/.claude/CLAUDE.md``; default ``rewrite``. ``off`` disables it.

Runs on Python 3.9, stdlib only. Any error -> exit 0 with no output, so
the tool call always goes ahead unchanged.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

OVERRIDE = "[model-override]"
MODES = ("rewrite", "deny", "off")
TIER = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3}
CLAUDE_MD = os.path.expanduser("~/.claude/CLAUDE.md")
LOG = os.path.expanduser("~/.claude/model-routing.log")
HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT_FILE = os.path.join(HERE, "classify_prompt.md")
# Set in the nested `claude -p` run so its own hooks (if any) exit at once.
GUARD = "MODEL_ROUTING_CLASSIFYING"
EFFORTS = ("low", "medium", "high")
MIN_CONFIDENCE = 0.6
PROMPT_CHARS = 4000
# Keep below the hooks.json timeout (30 s) so the regex fallback still runs.
DEFAULT_TIMEOUT = 20.0
# Task types the classifier may use to lower an explicitly requested model.
CHEAP_TYPES = ("search-read", "classification")
# Rows of the table in classify_prompt.md; anything else is logged as "other".
TASK_TYPES = ("everyday-engineering", "scoped-code", "classification", "search-read",
              "chat", "docs", "complex-docs", "repeated-agent", "computer-use",
              "large-change", "deep-research", "ui-from-design", "ui-visual", "unsure")
MAX_TIMEOUT = 25.0  # hooks.json allows 30 s; leave room for the fallback

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
    # A review of a risky change stays on opus when the classifier fails
    # (both a review word and a risk area must appear, in any order).
    {
        "name": "risky-review",
        "model": "opus",
        "cheap": False,
        # Whole words only: "author", "review threads" and a README's
        # "performance" section must not count as risk areas.
        # "lock" not after "-"/"." and not before ".json"/"file(s)", so a
        # package-lock.json or "lock file" bump doesn't count.
        # Global rule, raise-only: any Agent call naming a review and a risk
        # area (even negated, "no auth changes") goes to opus when the
        # classifier fails. Accepted cost.
        "pattern": r"^(?=[\s\S]*\breview\w*)(?=[\s\S]*\b(concurren\w*|race conditions?|"
                   r"races?|racy|(?<![-.])locks?(?!\.json|\s?files?)|locking|deadlocks?|mutex\w*|"
                   r"thread[- ]safe\w*|threading|multi-?thread\w*|async|asyncio|"
                   r"security|auth|authn|authz|authenticat\w*|authori[sz]\w*|oauth|jwt|"
                   r"permissions?|credentials?|crypto\w*|(en|de)crypt\w*|injection|xss|csrf|"
                   r"secrets?|schema|database|transactions?|cross-cutting|"
                   r"performance[- ]critical|hot path)\b)",
    },
    # The ui-* rules need a build/change word and skip Explore agents (see
    # BUILDS), so searching UI code still reaches search-read.
    {
        "name": "ui-system",
        "model": "opus",
        "cheap": False,
        "builds": True,
        "pattern": r"\b(design system|component library|(across|for) (all|every) (the |\d+ )?"
                   r"(components|pages|screens|views)|(whole|entire) (app|site|website|ui|"
                   r"front-?end))\b",
    },
    {
        "name": "ui-from-design",
        "model": "sonnet",
        "cheap": False,
        "builds": True,
        "pattern": r"\b(implement (the |this |a )?(design|mock-?up)|from (the |a |this )?"
                   r"(mock-?up|design|figma|wireframe|handoff)|match(es|ing)? the "
                   r"(design|mock-?up)|pixel[- ]perfect)\b",
    },
    {
        "name": "scoped-code",
        "model": "sonnet",
        "cheap": False,
        "pattern": r"\b(fix (the |a |this )?bug|bug ?fix|implement (the |this )?spec|"
                   r"per the spec|add (a )?unit tests?|write (the )?tests?)\b",
    },
    {
        "name": "ui-visual",
        "model": "opus",
        "cheap": False,
        "builds": True,
        "pattern": r"\b(home ?page|landing page|mock-?ups?|wireframes?|ui design|ux design|"
                   r"visual design|page layout|responsive layout|redesign(ing)? (the |a |this |"
                   r"our )?(\w+ )?(page|ui|ux|screen|site|website|layout|dashboard|"
                   r"component|header|footer|nav\w*)s?)\b",
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
# A cheap rule never applies when the task also edits, publishes or needs
# judgment. Deliberately broad: a false hit only costs a stronger model.
NOT_CHEAP = re.compile(
    r"\b(fix\w*|edit\w*|modif\w*|implement\w*|refactor\w*|patch\w*|debug\w*|"
    r"review\w*|decid\w*|design\w*|delet\w*|remov\w*|renam\w*|creat\w*|"
    r"add|adds|added|adding|(re|over)?writ(e|es|ing|ten)|(re|over)?wrote|"
    r"commit\w*|push\w*|merg\w*|mov(e|es|ed|ing)|install\w*|deploy\w*|"
    r"post|posts|posted|posting|appl(y|ies|ied|ying)|replac\w*|"
    r"(change|update|changes|updates|changed|updated|changing|updating) "
    r"(the|it|them|this|that|all))\b",
    re.I)


# A "builds" rule only applies when the task also makes or changes something.
BUILDS = re.compile(
    r"\b(implement\w*|build\w*|creat\w*|add|adds|added|adding|writ(e|es|ing)|"
    r"make|makes|making|convert\w*|appl(y|ies|ied|ying)|redesign\w*|lay out|laying out|"
    r"design (a|an|the|new|our|this)|styl(e|es|ed|ing) (the|a|it|this)|restyl\w*|"
    r"updat\w*|chang\w*|edit\w*|refactor\w*|rebuild\w*|code|coding|prototyp\w*|"
    r"roll ?out)\b", re.I)


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


def regex_classify(ti: dict) -> dict | None:
    text = " ".join(str(ti.get(k) or "") for k in ("description", "prompt"))
    stype = str(ti.get("subagent_type") or "").lower()
    for rule in RULES:
        hit = stype in rule.get("types", ()) or re.search(rule["pattern"], text, re.I)
        if not hit:
            continue
        if rule.get("builds") and (stype == "explore" or not BUILDS.search(text)):
            continue
        if rule["cheap"] and NOT_CHEAP.search(text):
            continue
        return rule
    return None


def classifier_timeout() -> float:
    try:
        t = float(os.environ.get("MODEL_ROUTING_CLASSIFIER_TIMEOUT") or DEFAULT_TIMEOUT)
    except ValueError:
        return DEFAULT_TIMEOUT
    if not math.isfinite(t):
        return DEFAULT_TIMEOUT
    return min(max(t, 0.1), MAX_TIMEOUT)


def parse_verdict(raw: str) -> dict | None:
    """Validate the classifier's JSON reply; None if anything is off."""
    raw = raw.strip()
    if raw.startswith("```"):  # tolerate a stray code fence
        raw = raw.strip("`")
        raw = raw[raw.find("{"):]
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        v = json.loads(raw[start:end + 1])
    except ValueError:
        return None
    if not isinstance(v, dict):
        return None
    model = str(v.get("model") or "").strip().lower()
    effort = str(v.get("effort") or "medium").lower()
    conf = v.get("confidence")
    if model not in TIER or effort not in EFFORTS or isinstance(conf, bool) \
            or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
        return None
    return {
        "task_type": v["task_type"] if v.get("task_type") in TASK_TYPES else "other",
        "model": model,
        "effort": effort,
        "read_only": v.get("read_only") is True,
        "confidence": float(conf),
    }


def llm_classify(ti: dict) -> tuple[dict | None, str]:
    """Ask Sonnet for a verdict. Returns (verdict or None, status)."""
    exe = shutil.which("claude")
    if exe is None:
        return None, "no-cli"
    try:
        with open(PROMPT_FILE, encoding="utf-8") as fh:
            system = fh.read()
    except OSError:
        return None, "no-prompt"
    task = json.dumps({
        "subagent_type": ti.get("subagent_type"),
        "description": str(ti.get("description") or "")[:200],
        "requested_model": ti.get("model"),
        "prompt": str(ti.get("prompt") or "")[:PROMPT_CHARS],
    })
    env = dict(os.environ)
    env[GUARD] = "1"
    cmd = [exe, "-p", "--model", "sonnet", "--effort", "low",
           "--output-format", "json", "--tools", "", "--strict-mcp-config",
           "--setting-sources", "", "--no-session-persistence",
           "--system-prompt", system]
    try:
        # Own process group, so a timeout also kills whatever `claude` spawned
        # (it may be a shell or npm shim around node).
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, env=env, text=True,
                             cwd=tempfile.gettempdir(), start_new_session=True)
    except OSError:
        return None, "exec-error"
    try:
        stdout, _ = p.communicate(task, timeout=classifier_timeout())
    except Exception as exc:  # timeout, undecodable output, ...: kill and fall back
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.wait()
        return None, "timeout" if isinstance(exc, subprocess.TimeoutExpired) else "io-error"
    if p.returncode != 0:
        return None, "exit-{}".format(p.returncode)
    try:
        envelope = json.loads(stdout)
    except ValueError:
        return None, "bad-envelope"
    if not isinstance(envelope, dict) or envelope.get("is_error"):
        return None, "cli-error"
    verdict = parse_verdict(str(envelope.get("result") or ""))
    if verdict is None:
        return None, "bad-json"
    if verdict["confidence"] < MIN_CONFIDENCE:
        return None, "low-confidence"
    return verdict, "ok"


def task_text(ti: dict) -> str:
    return " ".join(str(ti.get(k) or "") for k in ("description", "prompt"))


def decide(ti: dict, info: dict | None = None) -> tuple[str | None, str]:
    """Return (target model or None for no change, reason).

    ``info`` (if given) is filled with classifier details for the log.
    """
    info = {} if info is None else info
    if OVERRIDE in str(ti.get("prompt") or ""):
        return None, "override"
    want = name = None
    cheap = False
    if (os.environ.get("MODEL_ROUTING_CLASSIFIER") or "sonnet").lower() != "regex":
        t0 = time.monotonic()
        verdict, status = llm_classify(ti)
        info["classifier_ms"] = int((time.monotonic() - t0) * 1000)
        info["classifier_status"] = status
        if verdict is not None:
            info.update(classifier="sonnet", effort=verdict["effort"],
                        confidence=verdict["confidence"], task_type=verdict["task_type"])
            want, name = verdict["model"], "sonnet:" + verdict["task_type"]
            # Lowering a chosen model is allowed only for cheap, read-only
            # work, double-checked by the keyword guard.
            cheap = (want == "haiku" and verdict["read_only"]
                     and verdict["task_type"] in CHEAP_TYPES
                     and not NOT_CHEAP.search(task_text(ti)))
            if want == "haiku" and not cheap:
                # Self-contradictory verdict (haiku for non-cheap work): treat
                # it as unusable, so the keyword rules can still raise.
                for key in ("effort", "confidence", "task_type"):
                    info.pop(key, None)
                info["classifier_status"] = "haiku-not-cheap"
                want = name = None
    if want is None:
        info["classifier"] = "regex"
        rule = regex_classify(ti)
        if rule is None:
            return None, "no-rule"
        want, name, cheap = rule["model"], rule["name"], rule["cheap"]
    have = norm_model(ti.get("model"))
    if have == want:
        return None, "already:" + name
    # Haiku only ever for cheap work, also when no model was requested (the
    # subagent would otherwise inherit the parent's, usually stronger, model).
    if want == "haiku" and not cheap:
        return None, "not-cheap:" + name
    if have is not None and TIER[want] < TIER[have] and not cheap:
        return None, "keep-explicit:" + name
    return want, name


def log(entry: dict) -> None:
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def main() -> None:
    if os.environ.get(GUARD):  # nested classifier run: never recurse
        return
    data = json.load(sys.stdin)
    if not isinstance(data, dict) or data.get("tool_name") not in ("Agent", "Task"):
        return
    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        return
    mode = get_mode()
    if mode == "off":
        return
    info: dict = {}
    target, why = decide(ti, info)
    have = norm_model(ti.get("model"))
    lowers = target is not None and (
        TIER[target] < TIER[have] if have is not None else target == "haiku")
    if mode == "deny" and lowers:
        # A retry is classified again and, with a non-deterministic or flaky
        # classifier, could flip back up: deny mode only ever denies raises.
        target, why = None, "deny-no-lower:" + why
    log({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": mode,
        "subagent_type": ti.get("subagent_type"),
        "requested": ti.get("model"),
        "routed": target,
        "why": why,
        **info,
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
