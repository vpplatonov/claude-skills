"""Tests for repo_skills_config.py (SessionStart hook + show/save CLI).

Run: pytest plugins/personal/hooks
Each case runs the script in a subprocess with HOME pointed at a temp folder
and CLAUDE_PLUGIN_ROOT at a fake plugin, so the real ~/.claude is never
touched (unmarked: hermetic, no network).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "repo_skills_config.py"

REAL = """\
## repo-* skills
- GitHub org: acme
- Local workspace: ~/workspace/acme/
- Release branch: release
- Main branch: main
- Promotion repos: api
- Git hand-off: on
- Slack channel ID: C123
- Org email:
"""

TEMPLATE = """\
## repo-* skills
<!-- Run /personal:init-personal-skills to fill in for your project -->
- GitHub org: your-org
- Local workspace: ~/workspace/<org>/
- Release branch: release
- Main branch: main
"""


@pytest.fixture
def env(tmp_path: Path) -> dict:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    plugin = tmp_path / "plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text('{"version": "1.0.0"}')
    return {**os.environ, "HOME": str(home), "CLAUDE_PLUGIN_ROOT": str(plugin)}


def claude_dir(env: dict) -> Path:
    return Path(env["HOME"]) / ".claude"


def run(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], input="{}",
                          capture_output=True, text=True, env=env, timeout=30)


def hook(env: dict) -> dict | None:
    r = run(env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout else None


def set_claude_md(env: dict, text: str) -> None:
    (claude_dir(env) / "CLAUDE.md").write_text(text)


def bump_plugin(env: dict, version: str | None = None, extra: str = "x") -> None:
    root = Path(env["CLAUDE_PLUGIN_ROOT"])
    if version:
        (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": version}))
    (root / "SKILL.md").write_text(extra)


def test_saves_configured_section_and_stays_quiet(env):
    set_claude_md(env, "# Mine\n\n" + REAL + "\n## Other\nkeep\n")
    assert hook(env) is None  # first run, configured: nothing to say
    saved = (claude_dir(env) / "repo-skills-config.saved.md").read_text()
    assert saved == REAL and "## Other" not in saved
    assert hook(env) is None  # unchanged plugin: still quiet


def test_template_is_not_saved_and_first_run_suggests_init(env):
    set_claude_md(env, TEMPLATE)
    out = hook(env)
    assert "init-personal-skills" in out["systemMessage"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert not (claude_dir(env) / "repo-skills-config.saved.md").exists()


def test_update_suggests_init_with_saved_defaults(env):
    set_claude_md(env, REAL)
    hook(env)
    bump_plugin(env, "1.1.0")
    out = hook(env)
    msg = out["systemMessage"]
    assert "updated (1.0.0 -> 1.1.0)" in msg and "acme" in msg
    assert "init-personal-skills" in out["hookSpecificOutput"]["additionalContext"]
    assert hook(env) is None  # only once per update


def test_update_without_version_bump_is_detected(env):
    set_claude_md(env, REAL)
    hook(env)
    bump_plugin(env)
    assert "updated (1.0.0)" in hook(env)["systemMessage"]


def test_reset_section_keeps_saved_copy_and_nags(env):
    set_claude_md(env, REAL)
    hook(env)
    set_claude_md(env, TEMPLATE)  # e.g. overwritten during an update
    out = hook(env)
    assert "saved copy exists" in out["systemMessage"]
    assert (claude_dir(env) / "repo-skills-config.saved.md").read_text() == REAL


def test_show_and_save_cli(env):
    assert run(env, "show").returncode == 1
    set_claude_md(env, TEMPLATE)
    assert run(env, "save").returncode == 1
    set_claude_md(env, REAL)
    assert run(env, "save").returncode == 0
    r = run(env, "show")
    assert r.returncode == 0 and r.stdout == REAL


def test_broken_state_file_never_fails(env):
    set_claude_md(env, REAL)
    (claude_dir(env) / "repo-skills-config.state.json").write_text("{not json")
    r = run(env)
    assert r.returncode == 0
