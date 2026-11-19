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


def test_saved_copy_is_private(env):
    set_claude_md(env, REAL)
    assert hook(env) is None
    mode = (claude_dir(env) / "repo-skills-config.saved.md").stat().st_mode & 0o777
    assert mode == 0o600

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
    for _ in range(2):  # every session, not just once
        assert "saved copy exists" in hook(env)["systemMessage"]
    assert (claude_dir(env) / "repo-skills-config.saved.md").read_text() == REAL


def test_show_and_save_cli(env):
    assert run(env, "show").returncode == 1
    set_claude_md(env, TEMPLATE)
    assert run(env, "save").returncode == 1
    set_claude_md(env, REAL)
    assert run(env, "save").returncode == 0
    r = run(env, "show")
    assert r.returncode == 0 and r.stdout == REAL


def test_session_markers_and_caches_do_not_look_like_an_update(env):
    """Claude Code writes .in_use/<pid> into the plugin root every session."""
    set_claude_md(env, REAL)
    assert hook(env) is None
    root = Path(env["CLAUDE_PLUGIN_ROOT"])
    (root / ".in_use").mkdir()
    (root / ".in_use" / "12345").write_text("pid")
    (root / ".orphaned_at").write_text("now")
    (root / ".DS_Store").write_text("x")
    (root / "hooks" / "__pycache__").mkdir(parents=True)
    (root / "hooks" / "__pycache__" / "m.cpython-39.pyc").write_text("x")
    (root / "hooks" / "stray.pyc").write_text("x")
    assert hook(env) is None


def test_versioned_install_folder_update_is_detected(env, tmp_path):
    """A marketplace update moves the root from .../personal/1.0.0 to .../1.1.0."""
    set_claude_md(env, REAL)
    for v in ("1.0.0", "1.1.0"):
        meta = tmp_path / "cache" / "personal" / v / ".claude-plugin"
        meta.mkdir(parents=True)
        (meta / "plugin.json").write_text(json.dumps({"version": v}))
    old = {**env, "CLAUDE_PLUGIN_ROOT": str(tmp_path / "cache" / "personal" / "1.0.0")}
    new = {**env, "CLAUDE_PLUGIN_ROOT": str(tmp_path / "cache" / "personal" / "1.1.0")}
    assert hook(old) is None
    assert "updated (1.0.0 -> 1.1.0)" in hook(new)["systemMessage"]
    assert hook(new) is None


def test_two_installs_do_not_flip_each_other(env, tmp_path):
    set_claude_md(env, REAL)
    dev = tmp_path / "dev-plugin"
    (dev / ".claude-plugin").mkdir(parents=True)
    (dev / ".claude-plugin" / "plugin.json").write_text('{"version": "9.9.9"}')
    other = {**env, "CLAUDE_PLUGIN_ROOT": str(dev)}
    assert hook(env) is None and hook(other) is None
    assert hook(env) is None and hook(other) is None


def test_unconfigured_first_run_message_shows_once(env):
    set_claude_md(env, TEMPLATE)
    assert "not set up" in hook(env)["systemMessage"]
    assert hook(env) is None


def test_missing_claude_md_with_saved_copy_nags(env):
    set_claude_md(env, REAL)
    hook(env)
    (claude_dir(env) / "CLAUDE.md").unlink()
    assert "saved copy exists" in hook(env)["systemMessage"]


def test_section_at_eof_without_newline_is_saved(env):
    set_claude_md(env, "# Top\n\n" + REAL.rstrip("\n"))
    assert run(env, "save").returncode == 0
    assert run(env, "show").stdout == REAL


def test_broken_state_is_a_first_run_and_gets_rewritten(env):
    set_claude_md(env, REAL)
    state = claude_dir(env) / "repo-skills-config.state.json"
    state.write_text("{not json")
    assert hook(env) is None  # first run, configured: no false "updated"
    assert isinstance(json.loads(state.read_text()), dict)


def test_non_utf8_stdin_never_fails(env):
    r = subprocess.run([sys.executable, str(SCRIPT)], input=b"\xff\xfe",
                       capture_output=True, env=env, timeout=30)
    assert r.returncode == 0 and r.stderr == b""


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_unwritable_claude_dir(env):
    set_claude_md(env, REAL)
    hook(env)
    bump_plugin(env, "1.1.0")
    set_claude_md(env, REAL.replace("C123", "C456"))  # forces a failing save
    d = claude_dir(env)
    d.chmod(0o500)
    try:
        assert "updated" in hook(env)["systemMessage"]  # message survives
        r = run(env, "save")
    finally:
        d.chmod(0o700)
    assert r.returncode == 2  # saved copy is stale and can't be refreshed
    set_claude_md(env, REAL.replace("acme", "acme2"))
    d.chmod(0o500)
    try:
        r = run(env, "save")
    finally:
        d.chmod(0o700)
    assert r.returncode == 2 and "could not save" in r.stderr


def test_non_utf8_files_are_treated_as_missing(env):
    (claude_dir(env) / "CLAUDE.md").write_bytes(b"## repo-* skills\n- GitHub org: \xe9\n")
    out = hook(env)  # unreadable config = not set up; the user is told
    assert "not set up" in out["systemMessage"]
    assert run(env, "save").returncode == 1
    (claude_dir(env) / "repo-skills-config.saved.md").write_bytes(b"\xe9")
    assert run(env, "show").returncode == 1


def test_symlinked_root_keeps_its_key_across_updates(env, tmp_path):
    set_claude_md(env, REAL)
    for v in ("1.0.0", "1.1.0"):
        meta = tmp_path / "store" / v / ".claude-plugin"
        meta.mkdir(parents=True)
        (meta / "plugin.json").write_text(json.dumps({"version": v}))
    link = tmp_path / "current"
    link.symlink_to(tmp_path / "store" / "1.0.0")
    linked = {**env, "CLAUDE_PLUGIN_ROOT": str(link)}
    assert hook(linked) is None
    link.unlink()
    link.symlink_to(tmp_path / "store" / "1.1.0")
    assert "updated (1.0.0 -> 1.1.0)" in hook(linked)["systemMessage"]


def test_version_folder_without_plugin_version(env, tmp_path):
    set_claude_md(env, REAL)
    roots = []
    for v in ("2.0.0", "2.1.0"):
        root = tmp_path / "cache" / "personal" / v
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin" / "plugin.json").write_text("{}")
        (root / "SKILL.md").write_text(v)
        roots.append({**env, "CLAUDE_PLUGIN_ROOT": str(root)})
    assert hook(roots[0]) is None
    assert "updated" in hook(roots[1])["systemMessage"]


@pytest.mark.parametrize("content", ["[1, 2]", '{"KEY": "not a dict"}'])
def test_odd_state_shapes_are_a_first_run(env, content):
    set_claude_md(env, REAL)
    key = os.path.realpath(env["CLAUDE_PLUGIN_ROOT"])
    state = claude_dir(env) / "repo-skills-config.state.json"
    state.write_text(content.replace("KEY", key))
    assert hook(env) is None
    assert json.loads(state.read_text())[key]["version"] == "1.0.0"


def test_state_write_keeps_other_installs_keys(env):
    set_claude_md(env, REAL)
    state = claude_dir(env) / "repo-skills-config.state.json"
    state.write_text(json.dumps({"/elsewhere": {"fingerprint": "x", "version": "0"}}))
    hook(env)
    assert "/elsewhere" in json.loads(state.read_text())


def test_update_while_unconfigured_without_saved_copy(env):
    set_claude_md(env, TEMPLATE)
    hook(env)
    bump_plugin(env, "1.1.0")
    msg = hook(env)["systemMessage"]
    assert "updated (1.0.0 -> 1.1.0)" in msg and msg.endswith("config.")


@pytest.mark.parametrize("junk", ["junk", TEMPLATE])
def test_unusable_saved_copy_does_not_nag(env, junk):
    (claude_dir(env) / "repo-skills-config.saved.md").write_text(junk)
    set_claude_md(env, REAL)
    hook(env)  # first run, configured: saves REAL over the junk
    (claude_dir(env) / "repo-skills-config.saved.md").write_text(junk)
    (claude_dir(env) / "CLAUDE.md").unlink()
    assert hook(env) is None
    assert run(env, "show").returncode == 1


def test_org_with_trailing_comment_is_configured(env):
    set_claude_md(env, REAL.replace("GitHub org: acme", "GitHub org: acme <!-- work -->"))
    assert run(env, "save").returncode == 0


@pytest.mark.parametrize("ws", ["~/workspace/<org>/", "~/workspace/<folder>/"])
def test_placeholder_workspace_is_not_configured(env, ws):
    set_claude_md(env, REAL.replace("~/workspace/acme/", ws))
    assert run(env, "save").returncode == 1


def test_unknown_cli_command_is_rejected_without_side_effects(env):
    set_claude_md(env, REAL)
    r = run(env, "Show")
    assert r.returncode == 2 and "usage" in r.stderr
    assert not (claude_dir(env) / "repo-skills-config.state.json").exists()


def test_internal_error_exits_zero_silently(monkeypatch, capsys):
    import io
    mod = load_module()

    def boom():
        raise RuntimeError("unexpected")
    monkeypatch.setattr(mod, "session_start", boom)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"{}")))
    assert mod.main(["repo_skills_config.py"]) == 0
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def load_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("repo_skills_config_t", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_state_write_rereads_to_keep_a_concurrent_installs_key(env, monkeypatch):
    """Another session writes its key between our read and our write."""
    set_claude_md(env, REAL)
    monkeypatch.setenv("HOME", env["HOME"])
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", env["CLAUDE_PLUGIN_ROOT"])
    mod = load_module()
    real_fp = mod.fingerprint

    def racing_fingerprint(root):
        Path(mod.STATE).write_text(json.dumps({"/other": {"fingerprint": "y", "version": "1"}}))
        return real_fp(root)
    monkeypatch.setattr(mod, "fingerprint", racing_fingerprint)
    mod.session_start()
    state = json.loads(Path(mod.STATE).read_text())
    assert "/other" in state and len(state) == 2


def test_mixed_case_placeholder_org_and_non_semver_version_folder(env, tmp_path):
    set_claude_md(env, REAL.replace("GitHub org: acme", "GitHub org: Your-Org"))
    assert run(env, "save").returncode == 1
    mod = load_module()
    assert mod.install_key(str(tmp_path / "personal" / "nightly"), "nightly") == \
        os.path.realpath(tmp_path / "personal")


def test_level_one_heading_ends_the_section(env):
    set_claude_md(env, REAL + "\n# Private notes\nsecret stuff\n")
    assert run(env, "save").returncode == 0
    saved = run(env, "show").stdout
    assert saved == REAL and "secret" not in saved


def test_utf8_bom_is_tolerated(env):
    (claude_dir(env) / "CLAUDE.md").write_bytes(b"\xef\xbb\xbf" + REAL.encode())
    assert run(env, "save").returncode == 0
    assert run(env, "show").stdout == REAL


def test_missing_section_message_says_how_to_silence_it(env):
    set_claude_md(env, REAL)
    hook(env)
    set_claude_md(env, TEMPLATE)
    assert "delete" in hook(env)["systemMessage"]
