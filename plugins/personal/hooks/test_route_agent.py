"""Tests for route_agent.py: pipe sample hook input in, check the output.

Run: python3 -m unittest plugins/personal/hooks/test_route_agent.py
Each case runs the script in a subprocess with HOME pointed at a temp
folder, so the real ~/.claude/CLAUDE.md and log are never touched.
RouteAgentTest pins the regex classifier; SonnetClassifierTest puts a fake
`claude` on PATH, so no test ever calls the real model.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "route_agent.py")


def agent(prompt: str, model: str | None = None, stype: str = "general-purpose",
          desc: str = "task") -> dict:
    ti = {"description": desc, "prompt": prompt, "subagent_type": stype}
    if model:
        ti["model"] = model
    return {"hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": ti}


class HookCase(unittest.TestCase):
    """Runs the hook in a subprocess with a throwaway HOME."""
    classifier = "regex"
    extra_env: dict = {}

    def setUp(self) -> None:
        self.home = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.home.name, ".claude"))

    def tearDown(self) -> None:
        self.home.cleanup()

    def run_hook(self, payload: object, mode: str | None = None,
                 claude_md: str | None = None) -> tuple[int, dict | None]:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("MODEL_ROUTING_")}
        env["HOME"] = self.home.name
        env["MODEL_ROUTING_CLASSIFIER"] = self.classifier
        env.update(self.extra_env)
        if mode:
            env["MODEL_ROUTING_MODE"] = mode
        if claude_md is not None:
            with open(os.path.join(self.home.name, ".claude", "CLAUDE.md"), "w") as fh:
                fh.write(claude_md)
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        p = subprocess.run([sys.executable, SCRIPT], input=raw, env=env,
                           capture_output=True, text=True, timeout=10)
        return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None)

    def routed(self, out: dict | None) -> str | None:
        return out["hookSpecificOutput"]["updatedInput"]["model"] if out else None


class RouteAgentTest(HookCase):
    """Keyword (regex) classifier."""

    def test_explore_goes_to_haiku_even_from_opus(self) -> None:
        code, out = self.run_hook(agent("Look around the auth module", "opus", "Explore"))
        self.assertEqual(code, 0)
        self.assertEqual(self.routed(out), "haiku")
        self.assertIn("additionalContext", out["hookSpecificOutput"])

    def test_rewrite_keeps_every_other_field(self) -> None:
        payload = agent("grep the logs for timeouts and summarize", "sonnet")
        payload["tool_input"]["run_in_background"] = True
        _, out = self.run_hook(payload)
        new = out["hookSpecificOutput"]["updatedInput"]
        self.assertEqual(new["model"], "haiku")
        self.assertTrue(new["run_in_background"])
        self.assertEqual(new["prompt"], payload["tool_input"]["prompt"])

    def test_cheap_rule_skipped_when_task_edits_code(self) -> None:
        _, out = self.run_hook(agent("Search for the parser and fix the crash", "opus"))
        self.assertIsNone(out)

    def test_migration_upgrades_to_fable(self) -> None:
        _, out = self.run_hook(agent("Plan the database migration to the new schema", "sonnet"))
        self.assertEqual(self.routed(out), "fable")

    def test_bug_fix_never_lowers_explicit_opus(self) -> None:
        _, out = self.run_hook(agent("Fix the bug in date parsing", "opus"))
        self.assertIsNone(out)

    def test_bug_fix_fills_missing_model(self) -> None:
        _, out = self.run_hook(agent("Fix the bug in date parsing"))
        self.assertEqual(self.routed(out), "sonnet")

    def test_bug_fix_raises_haiku(self) -> None:
        _, out = self.run_hook(agent("Fix a bug in date parsing", "haiku"))
        self.assertEqual(self.routed(out), "sonnet")

    def test_no_rule_no_change(self) -> None:
        _, out = self.run_hook(agent("Write a haiku about autumn", "opus"))
        self.assertIsNone(out)

    def test_already_on_target(self) -> None:
        _, out = self.run_hook(agent("grep for TODOs", "haiku"))
        self.assertIsNone(out)

    def test_override(self) -> None:
        _, out = self.run_hook(agent("[model-override] grep for TODOs", "opus"))
        self.assertIsNone(out)

    def test_deny_mode(self) -> None:
        _, out = self.run_hook(agent("grep for TODOs", "opus"), mode="deny")
        hso = out["hookSpecificOutput"]
        self.assertEqual(hso["permissionDecision"], "deny")
        self.assertIn('model: "haiku"', hso["permissionDecisionReason"])
        self.assertNotIn("updatedInput", hso)

    def test_off_mode_from_env(self) -> None:
        _, out = self.run_hook(agent("grep for TODOs", "opus"), mode="off")
        self.assertIsNone(out)

    def test_mode_from_claude_md(self) -> None:
        md = "# x\n\n## repo-* skills\n- GitHub org: x\n- Model routing: off\n\n## other\n"
        _, out = self.run_hook(agent("grep for TODOs", "opus"), claude_md=md)
        self.assertIsNone(out)

    def test_env_beats_claude_md(self) -> None:
        md = "## repo-* skills\n- Model routing: off\n"
        _, out = self.run_hook(agent("grep for TODOs", "opus"), mode="deny", claude_md=md)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_full_model_id_normalised(self) -> None:
        _, out = self.run_hook(agent("grep for TODOs", "claude-opus-5-5"))
        self.assertEqual(self.routed(out), "haiku")

    def test_other_tool_ignored(self) -> None:
        _, out = self.run_hook({"tool_name": "Bash", "tool_input": {"command": "grep x"}})
        self.assertIsNone(out)

    def test_malformed_input_never_breaks(self) -> None:
        for raw in ("", "not json", "[]", '{"tool_name": "Agent", "tool_input": "x"}', "{"):
            code, out = self.run_hook(raw)
            self.assertEqual((code, out), (0, None), raw)

    def test_log_has_no_prompt(self) -> None:
        self.run_hook(agent("grep for SECRET-TOKEN-123", "opus", desc="d" * 200))
        with open(os.path.join(self.home.name, ".claude", "model-routing.log")) as fh:
            line = json.loads(fh.read().splitlines()[-1])
        self.assertNotIn("SECRET-TOKEN-123", json.dumps(line))
        self.assertEqual(len(line["description"]), 80)


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


def verdict(model: str, task_type: str = "scoped-code", conf: float = 0.9,
            read_only: bool = False, effort: str = "medium") -> str:
    return json.dumps({"task_type": task_type, "model": model, "effort": effort,
                       "read_only": read_only, "confidence": conf, "why": "test"})


class SonnetClassifierTest(HookCase):
    """Same hook, Sonnet classifier on, with a fake `claude` CLI."""
    classifier = "sonnet"

    def setUp(self) -> None:
        super().setUp()
        bindir = os.path.join(self.home.name, "bin")
        os.makedirs(bindir)
        exe = os.path.join(bindir, "claude")
        with open(exe, "w") as fh:
            fh.write(FAKE_CLAUDE.format(python=sys.executable))
        os.chmod(exe, 0o755)
        self.calls = os.path.join(self.home.name, "calls.txt")
        self.extra_env = {"PATH": bindir + os.pathsep + os.environ.get("PATH", ""),
                          "FAKE_CALLS": self.calls, "FAKE_RESULT": verdict("opus")}

    def fake(self, **env: str) -> None:
        self.extra_env = dict(self.extra_env, **env)

    def last_log(self) -> dict:
        with open(os.path.join(self.home.name, ".claude", "model-routing.log")) as fh:
            return json.loads(fh.read().splitlines()[-1])

    def n_calls(self) -> int:
        if not os.path.exists(self.calls):
            return 0
        with open(self.calls) as fh:
            return sum(1 for line in fh if line.strip())

    def test_valid_verdict_routes_and_logs(self) -> None:
        self.fake(FAKE_RESULT=verdict("fable", "large-change", effort="high"))
        _, out = self.run_hook(agent("Move the whole app to the new ORM", "sonnet"))
        self.assertEqual(self.routed(out), "fable")
        self.assertIn("sonnet:large-change", out["hookSpecificOutput"]["additionalContext"])
        line = self.last_log()
        self.assertEqual((line["classifier"], line["effort"], line["task_type"]),
                         ("sonnet", "high", "large-change"))
        self.assertIn("classifier_ms", line)

    def test_prompt_sent_is_truncated_and_never_logged(self) -> None:
        self.run_hook(agent("SECRET-TOKEN-123 " + "x" * 9000, "opus"))
        with open(self.calls) as fh:
            sent = json.loads(fh.read().splitlines()[0])
        self.assertEqual(len(sent["prompt"]), 4000)
        self.assertEqual(sent["requested_model"], "opus")
        self.assertNotIn("SECRET-TOKEN-123", json.dumps(self.last_log()))

    def test_fenced_json_accepted(self) -> None:
        self.fake(FAKE_RESULT="```json\n" + verdict("fable", "large-change") + "\n```")
        _, out = self.run_hook(agent("Re-architect it", "opus"))
        self.assertEqual(self.routed(out), "fable")

    def test_invalid_json_falls_back_to_regex(self) -> None:
        self.fake(FAKE_RESULT="I think opus would be best.")
        _, out = self.run_hook(agent("grep for TODOs", "opus"))
        self.assertEqual(self.routed(out), "haiku")  # regex search-read rule
        line = self.last_log()
        self.assertEqual((line["classifier"], line["classifier_status"]), ("regex", "bad-json"))

    def test_bad_fields_fall_back(self) -> None:
        for bad in (verdict("gpt-4"), verdict("opus", effort="max"),
                    verdict("opus", conf=1.5), '{"model": "opus"}', "[]"):
            self.fake(FAKE_RESULT=bad)
            _, out = self.run_hook(agent("Fix the bug in date parsing"))
            self.assertEqual(self.routed(out), "sonnet", bad)  # regex scoped-code
            self.assertEqual(self.last_log()["classifier"], "regex")

    def test_garbage_envelope_and_nonzero_exit_fall_back(self) -> None:
        for env in ({"FAKE_RAW": "not json"}, {"FAKE_EXIT": "1"},
                    {"FAKE_RAW": json.dumps({"is_error": True, "result": verdict("opus")})}):
            self.fake(**env)
            _, out = self.run_hook(agent("Fix the bug in date parsing"))
            self.assertEqual(self.routed(out), "sonnet", env)
            self.extra_env = {k: v for k, v in self.extra_env.items() if k not in env}

    def test_timeout_falls_back(self) -> None:
        self.fake(FAKE_SLEEP="3", MODEL_ROUTING_CLASSIFIER_TIMEOUT="0.5")
        _, out = self.run_hook(agent("Fix the bug in date parsing"))
        self.assertEqual(self.routed(out), "sonnet")
        self.assertEqual(self.last_log()["classifier_status"], "timeout")

    def test_low_confidence_falls_back(self) -> None:
        self.fake(FAKE_RESULT=verdict("fable", "large-change", conf=0.4))
        _, out = self.run_hook(agent("Write a haiku about autumn", "opus"))
        self.assertIsNone(out)  # regex: no rule
        self.assertEqual(self.last_log()["classifier_status"], "low-confidence")

    def test_missing_cli_falls_back(self) -> None:
        self.fake(PATH="/nonexistent")
        _, out = self.run_hook(agent("Fix the bug in date parsing"))
        self.assertEqual(self.routed(out), "sonnet")
        self.assertEqual(self.last_log()["classifier_status"], "no-cli")

    def test_regex_opt_out_skips_cli(self) -> None:
        self.classifier = "regex"
        _, out = self.run_hook(agent("Fix the bug in date parsing"))
        self.assertEqual(self.routed(out), "sonnet")
        self.assertEqual(self.n_calls(), 0)

    def test_recursion_guard(self) -> None:
        self.fake(MODEL_ROUTING_CLASSIFYING="1")
        code, out = self.run_hook(agent("grep for TODOs", "opus"))
        self.assertEqual((code, out), (0, None))
        self.assertEqual(self.n_calls(), 0)

    def test_override_skips_cli(self) -> None:
        _, out = self.run_hook(agent("[model-override] Migrate everything", "haiku"))
        self.assertIsNone(out)
        self.assertEqual(self.n_calls(), 0)

    def test_never_lowers_for_edit_work(self) -> None:
        self.fake(FAKE_RESULT=verdict("sonnet", "scoped-code"))
        _, out = self.run_hook(agent("Fix the off-by-one in pager.py", "opus"))
        self.assertIsNone(out)
        self.assertTrue(self.last_log()["why"].startswith("keep-explicit:"))

    def test_haiku_lowering_needs_read_only(self) -> None:
        self.fake(FAKE_RESULT=verdict("haiku", "search-read", read_only=False))
        _, out = self.run_hook(agent("Read the CI logs and list failures", "opus"))
        self.assertIsNone(out)

    def test_haiku_lowering_needs_cheap_task_type(self) -> None:
        self.fake(FAKE_RESULT=verdict("haiku", "scoped-code", read_only=True))
        _, out = self.run_hook(agent("Read the CI logs and list failures", "opus"))
        self.assertIsNone(out)

    def test_haiku_lowering_blocked_by_keyword_guard(self) -> None:
        self.fake(FAKE_RESULT=verdict("haiku", "search-read", read_only=True))
        _, out = self.run_hook(agent("Find the parser and fix the crash", "opus"))
        self.assertIsNone(out)

    def test_haiku_lowering_for_read_only_search(self) -> None:
        self.fake(FAKE_RESULT=verdict("haiku", "search-read", read_only=True))
        _, out = self.run_hook(agent("Read the CI logs and list failures", "opus"))
        self.assertEqual(self.routed(out), "haiku")

    def test_raises_haiku_request(self) -> None:
        self.fake(FAKE_RESULT=verdict("opus", "everyday-engineering"))
        _, out = self.run_hook(agent("Debug why checkout hangs", "haiku"))
        self.assertEqual(self.routed(out), "opus")

    def test_deny_mode_uses_sonnet_verdict(self) -> None:
        self.fake(FAKE_RESULT=verdict("fable", "large-change"))
        _, out = self.run_hook(agent("Move to the new ORM", "opus"), mode="deny")
        self.assertIn('model: "fable"', out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_off_mode_skips_cli(self) -> None:
        _, out = self.run_hook(agent("Migrate everything", "haiku"), mode="off")
        self.assertIsNone(out)
        self.assertEqual(self.n_calls(), 0)


if __name__ == "__main__":
    unittest.main()
