"""Tests for route_agent.py: pipe sample hook input in, check the output.

Run: pytest plugins/personal/hooks
Each case runs the script in a subprocess with HOME pointed at a temp
folder, so the real ~/.claude/CLAUDE.md and log are never touched. The
regex tests pin MODEL_ROUTING_CLASSIFIER=regex; the Sonnet tests put a fake
`claude` on PATH, so no test ever calls the real model (all unmarked:
hermetic, no network).
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "route_agent.py"

FAKE_CLAUDE = textwrap.dedent("""\
    #!{python}
    import json, os, subprocess, sys, time
    open(os.environ["FAKE_CALLS"], "a").write(sys.stdin.read() + "\\n")
    if os.environ.get("FAKE_GRANDCHILD"):  # like an npm shim around node
        child = subprocess.Popen(["sleep", "30"])
        open(os.environ["FAKE_GRANDCHILD"], "w").write(str(child.pid))
    if os.environ.get("FAKE_SLEEP"):
        time.sleep(float(os.environ["FAKE_SLEEP"]))
    if os.environ.get("FAKE_BYTES"):
        sys.stdout.buffer.write(bytes.fromhex(os.environ["FAKE_BYTES"]))
    elif os.environ.get("FAKE_RAW"):
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
            read_only: bool = False, effort: str = "medium", why: str = "test") -> str:
    return json.dumps({"task_type": task_type, "model": model, "effort": effort,
                       "read_only": read_only, "confidence": conf, "why": why})


CHEAP_VERDICT = verdict("haiku", "search-read", read_only=True)


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
    ("Independent review of PR a/b#1. Concurrency guard in the worker", None, "opus"),
    ("Security fix in token refresh.\nPlease review the diff fresh", "sonnet", "opus"),
    ("Independent review of PR a/b#2. Copy fix in two templates", None, None),
    ("Concurrency guard in the worker, run the suite", None, None),  # no review word
    ("Review PR a/b#4 and summarize what the author changed", None, None),
    ("Re-review: address review threads on the parser", None, None),
    ("Review the performance section wording in README", None, None),
    ("Review the OAuth token refresh change", None, "opus"),
    ("Review the thread-safe cache rewrite", None, "opus"),
    ("Review: workers now write concurrently to the cache", None, "opus"),
    ("Review the mutex around the session map", None, "opus"),
    ("Review the new encryption of stored tokens", None, "opus"),
    ("Review the SQL injection fix in search", None, "opus"),
    ("Review the lock around the job queue", None, "opus"),
    ("Review the dependency bump in package-lock.json", None, None),
    ("Review the Pipfile.lock and poetry.lock update", None, None),
    ("Review the lock file refresh after the bump", None, None),
    ("Review PR a/b#3: schema migration for orders", None, "fable"),  # large-change first
])
def test_regex_routing(hook: Hook, prompt: str, model: str | None,
                       expected: str | None) -> None:
    _, out = hook(agent(prompt, model))
    assert routed(out) == expected


def test_deny_mode(hook: Hook) -> None:
    _, out = hook(agent("Plan the database migration", "opus"), mode="deny")
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert 'model: "fable"' in hso["permissionDecisionReason"]
    assert "updatedInput" not in hso


def test_deny_mode_never_denies_a_lowering(hook: Hook) -> None:
    assert hook(agent("grep for TODOs", "opus"), mode="deny")[1] is None
    assert hook.last_log()["why"] == "deny-no-lower:search-read"


def test_off_mode_from_env(hook: Hook) -> None:
    assert hook(agent("grep for TODOs", "opus"), mode="off")[1] is None


def test_mode_from_claude_md(hook: Hook) -> None:
    md = "# x\n\n## repo-* skills\n- GitHub org: x\n- Model routing: off\n\n## other\n"
    assert hook(agent("grep for TODOs", "opus"), claude_md=md)[1] is None


def test_env_beats_claude_md(hook: Hook) -> None:
    md = "## repo-* skills\n- Model routing: off\n"
    _, out = hook(agent("Plan the database migration", "opus"), mode="deny", claude_md=md)
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
    verdict("sonnet, not haiku"),  # only an exact tier name counts
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
    # No model requested: haiku still needs the cheap checks.
    (verdict("haiku", "everyday-engineering"), "Fix the race in worker.py", None, None),
    (CHEAP_VERDICT, "Read the CI logs and list failures", None, "haiku"),
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
    (verdict("haiku", "classification", read_only=True),
     "Tag each log line by severity", "opus", "haiku"),
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


@pytest.mark.parametrize("prompt", [
    "Find all TODO comments and delete them",
    "Grep for the old name and rename it everywhere",
    "Search the config and add the missing key",
    "List the stale branches, then commit and push",
    "Find the test that fixes the bug",
    "Locate the parser before fixing it",
    "Find the docs and update them",
    "Scan the files and post a summary to the PR",
    "Read the CI logs and rewrite the summary file",
    "List files that updated the config and overwrite them",
    "Find the stale branches and merge them",
    "Locate the fixtures and move them to tests/",
    "Find the build output and deploy it",
])
def test_edit_wording_blocks_haiku(sonnet: Hook, prompt: str) -> None:
    _, out = sonnet(agent(prompt, "opus"), FAKE_RESULT=CHEAP_VERDICT)
    assert out is None


def test_edit_after_truncation_still_blocks_haiku(sonnet: Hook) -> None:
    prompt = "Read the CI logs. " + "x " * 3000 + "Then delete the old logs."
    _, out = sonnet(agent(prompt, "opus"), FAKE_RESULT=CHEAP_VERDICT)
    assert out is None


def test_deny_mode_never_denies_a_sonnet_lowering(sonnet: Hook) -> None:
    _, out = sonnet(agent("Read the CI logs and list failures", "opus"), mode="deny",
                    FAKE_RESULT=CHEAP_VERDICT)
    assert out is None
    assert sonnet.last_log()["why"] == "deny-no-lower:sonnet:search-read"


def test_unknown_task_type_logged_as_other(sonnet: Hook) -> None:
    _, out = sonnet(agent("Move to the new ORM", "opus"),
                    FAKE_RESULT=verdict("fable", "SECRET-TOKEN-123 echoed"))
    assert routed(out) == "fable"
    line = sonnet.last_log()
    assert line["task_type"] == "other"
    assert "SECRET-TOKEN-123" not in json.dumps(line)


def test_classifier_why_not_relayed(sonnet: Hook) -> None:
    _, out = sonnet(agent("Move to the new ORM", "opus"),
                    FAKE_RESULT=verdict("fable", "large-change", why="INJECTED-TEXT"))
    assert "INJECTED-TEXT" not in json.dumps(out)
    assert "INJECTED-TEXT" not in json.dumps(sonnet.last_log())


def test_timeout_kills_the_whole_process_group(sonnet: Hook, tmp_path: Path) -> None:
    pidfile = tmp_path / "grandchild.pid"
    _, out = sonnet(agent("Fix the bug in date parsing"), FAKE_GRANDCHILD=str(pidfile),
                    FAKE_SLEEP="10", MODEL_ROUTING_CLASSIFIER_TIMEOUT="1")
    assert routed(out) == "sonnet"
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + 5  # give the orphan time to be reaped
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    pytest.fail("grandchild {} still alive after timeout".format(pid))


@pytest.fixture
def route_agent():
    spec = importlib.util.spec_from_file_location("route_agent", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("value, expected", [
    (None, 20.0), ("5", 5.0), ("300", 25.0), ("-1", 0.1), ("abc", 20.0),
    ("nan", 20.0), ("inf", 20.0),
])
def test_classifier_timeout_is_clamped(route_agent, monkeypatch, value, expected) -> None:
    if value is None:
        monkeypatch.delenv("MODEL_ROUTING_CLASSIFIER_TIMEOUT", raising=False)
    else:
        monkeypatch.setenv("MODEL_ROUTING_CLASSIFIER_TIMEOUT", value)
    assert route_agent.classifier_timeout() == expected


@pytest.mark.parametrize("prompt", [
    "find where the email address is parsed",
    "grep the Postgres config",
    "search for additional logging",
    "list the files in the postcode module",
    "find the file that defines the writer class",
])
def test_edit_guard_matches_whole_words_only(hook: Hook, prompt: str) -> None:
    _, out = hook(agent(prompt, "opus"))
    assert routed(out) == "haiku"


def test_undecodable_output_falls_back(sonnet: Hook) -> None:
    _, out = sonnet(agent("Fix the bug in date parsing"), FAKE_BYTES="fffe0081")
    assert routed(out) == "sonnet"
    assert sonnet.last_log()["classifier_status"] == "io-error"


def test_deny_mode_no_model_haiku_not_denied(sonnet: Hook) -> None:
    _, out = sonnet(agent("Read the CI logs and list failures"), mode="deny",
                    FAKE_RESULT=CHEAP_VERDICT)
    assert out is None
    assert sonnet.last_log()["why"] == "deny-no-lower:sonnet:search-read"


@pytest.mark.parametrize("model, expected", [("haiku", "sonnet"), (None, "sonnet")])
def test_contradictory_haiku_verdict_lets_regex_raise(sonnet: Hook, model: str | None,
                                                      expected: str) -> None:
    _, out = sonnet(agent("Search for the parser and fix the bug in parsing", model),
                    FAKE_RESULT=verdict("haiku", "scoped-code", read_only=False))
    assert routed(out) == expected
    line = sonnet.last_log()
    assert (line["classifier"], line["classifier_status"]) == ("regex", "haiku-not-cheap")
    assert "task_type" not in line


# --- UI / design routing (regex) ---------------------------------------------

@pytest.mark.parametrize("prompt, model, stype, expected", [
    # Built from a design: sonnet.
    ("Implement the home page from the mockup in HTML and CSS", None, "general-purpose", "sonnet"),
    # New UI that needs visual judgment: opus.
    ("Build a new landing page with a responsive layout", "sonnet", "general-purpose", "opus"),
    # A bug fix on a page stays scoped.
    ("Fix the bug in the landing page header", "sonnet", "general-purpose", None),
    # Raise-only: never lowers fable.
    ("Redesign the home page", "fable", "general-purpose", None),
    # Architecture still wins over UI.
    ("Plan the architecture for the home page backend", "opus", "general-purpose", "fable"),
    # A design spec alone doesn't mean sonnet: design-system rollout -> opus.
    ("Implement the design system from the Figma handoff across all 40 components",
     None, "general-purpose", "opus"),
    ("Apply the handoff across every screen of the whole app", "sonnet", "general-purpose", "opus"),
    # "redesign" outside UI is not UI work.
    ("Redesign the database schema for orders", "sonnet", "general-purpose", None),
    ("Redesign the checkout page", "sonnet", "general-purpose", "opus"),
    # Searching UI code stays cheap: Explore agents skip the ui-* rules ...
    ("Find the landing page component and list its props", "haiku", "Explore", None),
    ("Find all HTML and CSS files under web/", "haiku", "Explore", None),
    ("Locate the mockup PNGs in the repo", None, "Explore", "haiku"),
    # ... and so does any task without a build/change word.
    ("Find the landing page component and list its props", "opus", "general-purpose", None),
    ("Summarize the page layout docs", "opus", "general-purpose", "haiku"),
    ("Fix the HTML and CSS lint errors", "opus", "general-purpose", None),
])
def test_ui_routing(hook: Hook, prompt: str, model: str | None, stype: str,
                    expected: str | None) -> None:
    _, out = hook(agent(prompt, model, stype))
    assert routed(out) == expected


@pytest.mark.parametrize("task_type, model", [("ui-from-design", "sonnet"), ("ui-visual", "opus")])
def test_sonnet_ui_task_types_accepted(sonnet: Hook, task_type: str, model: str) -> None:
    _, out = sonnet(agent("Build the pricing page", "haiku"),
                    FAKE_RESULT=verdict(model, task_type))
    assert routed(out) == model
    assert sonnet.last_log()["task_type"] == task_type


def test_mode_section_ends_at_level_one_heading(hook: Hook) -> None:
    md = "## repo-* skills\n- GitHub org: x\n\n# Notes\n- Model routing: off\n"
    _, out = hook(agent("Plan the database migration", "sonnet"), mode=None, claude_md=md,
                  MODEL_ROUTING_CLASSIFIER="regex")
    assert out is not None  # "off" is outside the section, so routing still runs


def test_mode_read_through_utf8_bom(hook: Hook) -> None:
    md = "\ufeff## repo-* skills\n- Model routing: off\n"
    assert hook(agent("grep for TODOs", "opus"), claude_md=md)[1] is None
