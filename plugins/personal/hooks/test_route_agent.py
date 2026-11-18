"""Tests for route_agent.py: pipe sample hook input in, check the output.

Run: pytest plugins/personal/hooks
Each case runs the script in a subprocess with HOME pointed at a temp
folder, so the real ~/.claude/CLAUDE.md and log are never touched. The
regex tests pin MODEL_ROUTING_CLASSIFIER=regex; the Sonnet tests put a fake
`claude` on PATH, so no test ever calls the real model (all unmarked:
hermetic, no network).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "route_agent.py"

FAKE_CLAUDE = textwrap.dedent("""\
    #!{python}
    import json, os, sys, time
    open(os.environ["FAKE_CALLS"], "a").write(sys.stdin.read() + "\\n")
    if os.environ.get("FAKE_SLEEP"):
        time.sleep(float(os.environ["FAKE_SLEEP"]))
    if os.environ.get("FAKE_RAW"):
        sys.stdout.write(os.environ["FAKE_RAW"])
    else:
        sys.stdout.write(json.dumps({{"type": "result", "is_error": False,
                                     "result": os.environ["FAKE_RESULT"]}}))
    sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
    """)


def agent(prompt: str, model: str | None = None, stype: str = "general-purpose",
          desc: str = "task") -> dict:
    ti = {"description": desc, "prompt": prompt, "subagent_type": stype}
    if model:
        ti["model"] = model
    return {"hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": ti}


def verdict(model: str, task_type: str = "scoped-code", conf: float = 0.9,
            read_only: bool = False, effort: str = "medium") -> str:
    return json.dumps({"task_type": task_type, "model": model, "effort": effort,
                       "read_only": read_only, "confidence": conf, "why": "test"})


def routed(out: dict | None) -> str | None:
    return out["hookSpecificOutput"]["updatedInput"]["model"] if out else None


class Hook:
    """Runs route_agent.py in a subprocess with a throwaway HOME."""

    def __init__(self, home: Path, classifier: str) -> None:
        self.home = home
        (home / ".claude").mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("MODEL_ROUTING_")}
        self.env.update(HOME=str(home), MODEL_ROUTING_CLASSIFIER=classifier)
        self.calls = home / "calls.txt"

    def install_fake_claude(self) -> None:
        bindir = self.home / "bin"
        bindir.mkdir()
        exe = bindir / "claude"
        exe.write_text(FAKE_CLAUDE.format(python=sys.executable))
        exe.chmod(0o755)
        self.env.update(PATH=str(bindir) + os.pathsep + os.environ.get("PATH", ""),
                        FAKE_CALLS=str(self.calls), FAKE_RESULT=verdict("opus"))

    def __call__(self, payload: object, mode: str | None = None,
                 claude_md: str | None = None, **env: str) -> tuple[int, dict | None]:
        run_env = dict(self.env, **env)
        if mode:
            run_env["MODEL_ROUTING_MODE"] = mode
        if claude_md is not None:
            (self.home / ".claude" / "CLAUDE.md").write_text(claude_md)
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        p = subprocess.run([sys.executable, str(SCRIPT)], input=raw, env=run_env,
                           capture_output=True, text=True, timeout=15)
        return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None)

    def last_log(self) -> dict:
        lines = (self.home / ".claude" / "model-routing.log").read_text().splitlines()
        return json.loads(lines[-1])

    def n_calls(self) -> int:
        if not self.calls.exists():
            return 0
        return sum(1 for line in self.calls.read_text().splitlines() if line.strip())


@pytest.fixture
def hook(tmp_path: Path) -> Hook:
    """Keyword (regex) classifier only."""
    return Hook(tmp_path, "regex")


@pytest.fixture
def sonnet(tmp_path: Path) -> Hook:
    """Sonnet classifier on, backed by a fake `claude` CLI answering opus."""
    h = Hook(tmp_path, "sonnet")
    h.install_fake_claude()
    return h


# --- regex classifier -------------------------------------------------------

def test_explore_goes_to_haiku_even_from_opus(hook: Hook) -> None:
    code, out = hook(agent("Look around the auth module", "opus", "Explore"))
    assert code == 0
    assert routed(out) == "haiku"
    assert "additionalContext" in out["hookSpecificOutput"]


def test_rewrite_keeps_every_other_field(hook: Hook) -> None:
    payload = agent("grep the logs for timeouts and summarize", "sonnet")
    payload["tool_input"]["run_in_background"] = True
    _, out = hook(payload)
    new = out["hookSpecificOutput"]["updatedInput"]
    assert new["model"] == "haiku"
    assert new["run_in_background"] is True
    assert new["prompt"] == payload["tool_input"]["prompt"]


@pytest.mark.parametrize("prompt, model, expected", [
    ("Search for the parser and fix the crash", "opus", None),   # cheap rule skipped on edits
    ("Plan the database migration to the new schema", "sonnet", "fable"),
    ("Fix the bug in date parsing", "opus", None),               # never lowers explicit opus
    ("Fix the bug in date parsing", None, "sonnet"),             # fills missing model
    ("Fix a bug in date parsing", "haiku", "sonnet"),            # raises haiku
    ("Write a haiku about autumn", "opus", None),                # no rule
    ("grep for TODOs", "haiku", None),                           # already on target
    ("[model-override] grep for TODOs", "opus", None),
    ("grep for TODOs", "claude-opus-5-5", "haiku"),              # full id normalised
])
def test_regex_routing(hook: Hook, prompt: str, model: str | None,
                       expected: str | None) -> None:
    _, out = hook(agent(prompt, model))
    assert routed(out) == expected


def test_deny_mode(hook: Hook) -> None:
    _, out = hook(agent("grep for TODOs", "opus"), mode="deny")
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert 'model: "haiku"' in hso["permissionDecisionReason"]
    assert "updatedInput" not in hso


def test_off_mode_from_env(hook: Hook) -> None:
    assert hook(agent("grep for TODOs", "opus"), mode="off")[1] is None


def test_mode_from_claude_md(hook: Hook) -> None:
    md = "# x\n\n## repo-* skills\n- GitHub org: x\n- Model routing: off\n\n## other\n"
    assert hook(agent("grep for TODOs", "opus"), claude_md=md)[1] is None


def test_env_beats_claude_md(hook: Hook) -> None:
    md = "## repo-* skills\n- Model routing: off\n"
    _, out = hook(agent("grep for TODOs", "opus"), mode="deny", claude_md=md)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_other_tool_ignored(hook: Hook) -> None:
    assert hook({"tool_name": "Bash", "tool_input": {"command": "grep x"}})[1] is None


@pytest.mark.parametrize("raw", [
    "", "not json", "[]", '{"tool_name": "Agent", "tool_input": "x"}', "{",
])
def test_malformed_input_never_breaks(hook: Hook, raw: str) -> None:
    assert hook(raw) == (0, None)


def test_log_has_no_prompt(hook: Hook) -> None:
    hook(agent("grep for SECRET-TOKEN-123", "opus", desc="d" * 200))
    line = hook.last_log()
    assert "SECRET-TOKEN-123" not in json.dumps(line)
    assert len(line["description"]) == 80
    assert line["classifier"] == "regex"


# --- Sonnet classifier (fake CLI) ---------------------------------------------

def test_valid_verdict_routes_and_logs(sonnet: Hook) -> None:
    _, out = sonnet(agent("Move the whole app to the new ORM", "sonnet"),
                    FAKE_RESULT=verdict("fable", "large-change", effort="high"))
    assert routed(out) == "fable"
    assert "sonnet:large-change" in out["hookSpecificOutput"]["additionalContext"]
    line = sonnet.last_log()
    assert (line["classifier"], line["effort"], line["task_type"]) == \
        ("sonnet", "high", "large-change")
    assert "classifier_ms" in line
    assert "classifier_why" not in line


def test_prompt_sent_is_truncated_and_never_logged(sonnet: Hook) -> None:
    sonnet(agent("SECRET-TOKEN-123 " + "x" * 9000, "opus"))
    sent = json.loads(sonnet.calls.read_text().splitlines()[0])
    assert len(sent["prompt"]) == 4000
    assert sent["requested_model"] == "opus"
    assert "SECRET-TOKEN-123" not in json.dumps(sonnet.last_log())


def test_fenced_json_accepted(sonnet: Hook) -> None:
    fenced = "```json\n" + verdict("fable", "large-change") + "\n```"
    _, out = sonnet(agent("Re-architect it", "opus"), FAKE_RESULT=fenced)
    assert routed(out) == "fable"


def test_invalid_json_falls_back_to_regex(sonnet: Hook) -> None:
    _, out = sonnet(agent("grep for TODOs", "opus"), FAKE_RESULT="I think opus would be best.")
    assert routed(out) == "haiku"  # regex search-read rule
    line = sonnet.last_log()
    assert (line["classifier"], line["classifier_status"]) == ("regex", "bad-json")


@pytest.mark.parametrize("bad", [
    verdict("gpt-4"), verdict("opus", effort="max"), verdict("opus", conf=1.5),
    '{"model": "opus"}', "[]",
])
def test_bad_fields_fall_back(sonnet: Hook, bad: str) -> None:
    _, out = sonnet(agent("Fix the bug in date parsing"), FAKE_RESULT=bad)
    assert routed(out) == "sonnet"  # regex scoped-code
    assert sonnet.last_log()["classifier"] == "regex"


@pytest.mark.parametrize("env, status", [
    ({"FAKE_RAW": "not json"}, "bad-envelope"),
    ({"FAKE_EXIT": "1"}, "exit-1"),
    ({"FAKE_RAW": json.dumps({"is_error": True, "result": verdict("opus")})}, "cli-error"),
    ({"FAKE_SLEEP": "3", "MODEL_ROUTING_CLASSIFIER_TIMEOUT": "0.5"}, "timeout"),
    ({"PATH": "/nonexistent"}, "no-cli"),
])
def test_cli_failures_fall_back(sonnet: Hook, env: dict, status: str) -> None:
    _, out = sonnet(agent("Fix the bug in date parsing"), **env)
    assert routed(out) == "sonnet"
    assert sonnet.last_log()["classifier_status"] == status


def test_low_confidence_falls_back(sonnet: Hook) -> None:
    _, out = sonnet(agent("Write a haiku about autumn", "opus"),
                    FAKE_RESULT=verdict("fable", "large-change", conf=0.4))
    assert out is None  # regex: no rule
    assert sonnet.last_log()["classifier_status"] == "low-confidence"


@pytest.mark.parametrize("prompt, env", [
    ("Fix the bug in date parsing", {"MODEL_ROUTING_CLASSIFIER": "regex"}),  # opt-out
    ("grep for TODOs", {"MODEL_ROUTING_CLASSIFYING": "1"}),                  # recursion guard
    ("[model-override] Migrate everything", {}),
    ("Migrate everything", {"MODEL_ROUTING_MODE": "off"}),
])
def test_cli_not_called(sonnet: Hook, prompt: str, env: dict) -> None:
    code, _ = sonnet(agent(prompt, "opus"), **env)
    assert code == 0
    assert sonnet.n_calls() == 0


def test_recursion_guard_outputs_nothing(sonnet: Hook) -> None:
    assert sonnet(agent("grep for TODOs", "opus"), MODEL_ROUTING_CLASSIFYING="1") == (0, None)


@pytest.mark.parametrize("result, prompt, model, expected", [
    # Edit work is never lowered from an explicit model.
    (verdict("sonnet", "scoped-code"), "Fix the off-by-one in pager.py", "opus", None),
    # Haiku lowering needs read_only ...
    (verdict("haiku", "search-read", read_only=False),
     "Read the CI logs and list failures", "opus", None),
    # ... a cheap task type ...
    (verdict("haiku", "scoped-code", read_only=True),
     "Read the CI logs and list failures", "opus", None),
    # ... and no edit keyword in the task.
    (verdict("haiku", "search-read", read_only=True),
     "Find the parser and fix the crash", "opus", None),
    (verdict("haiku", "search-read", read_only=True),
     "Read the CI logs and list failures", "opus", "haiku"),
    (verdict("opus", "everyday-engineering"), "Debug why checkout hangs", "haiku", "opus"),
])
def test_sonnet_policy(sonnet: Hook, result: str, prompt: str, model: str,
                       expected: str | None) -> None:
    _, out = sonnet(agent(prompt, model), FAKE_RESULT=result)
    assert routed(out) == expected


def test_never_lowers_logs_keep_explicit(sonnet: Hook) -> None:
    sonnet(agent("Fix the off-by-one in pager.py", "opus"),
           FAKE_RESULT=verdict("sonnet", "scoped-code"))
    assert sonnet.last_log()["why"] == "keep-explicit:sonnet:scoped-code"


def test_deny_mode_uses_sonnet_verdict(sonnet: Hook) -> None:
    _, out = sonnet(agent("Move to the new ORM", "opus"), mode="deny",
                    FAKE_RESULT=verdict("fable", "large-change"))
    assert 'model: "fable"' in out["hookSpecificOutput"]["permissionDecisionReason"]
