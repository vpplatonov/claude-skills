"""Tests for route_agent.py: pipe sample hook input in, check the output.

Run: python3 -m unittest plugins/personal/hooks/test_route_agent.py
Each case runs the script in a subprocess with HOME pointed at a temp
folder, so the real ~/.claude/CLAUDE.md and log are never touched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "route_agent.py")


def agent(prompt: str, model: str | None = None, stype: str = "general-purpose",
          desc: str = "task") -> dict:
    ti = {"description": desc, "prompt": prompt, "subagent_type": stype}
    if model:
        ti["model"] = model
    return {"hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": ti}


class RouteAgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.home.name, ".claude"))

    def tearDown(self) -> None:
        self.home.cleanup()

    def run_hook(self, payload: object, mode: str | None = None,
                 claude_md: str | None = None) -> tuple[int, dict | None]:
        env = {k: v for k, v in os.environ.items() if k != "MODEL_ROUTING_MODE"}
        env["HOME"] = self.home.name
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


if __name__ == "__main__":
    unittest.main()
