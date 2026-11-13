"""Tests for the GitHub-only repos key in run_pr_approve.py. Run: uvx pytest tools/repo-pr-watcher"""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("run_pr_approve.py")
spec = importlib.util.spec_from_file_location("run_pr_approve", SCRIPT)
watcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watcher)

SECTION = """# Global

## repo-* skills
- GitHub org: example-org
- Local workspace: ~/workspace/
- Promotion repos:
- Slack channel ID: D000
- GitHub-only repos: {value}
- PR watcher interval: 1h

## Other section
- GitHub-only repos: ignored-repo
"""


@pytest.fixture
def claude_md(tmp_path, monkeypatch):
    def write(value: str) -> Path:
        path = tmp_path / "CLAUDE.md"
        path.write_text(SECTION.format(value=value))
        monkeypatch.setattr(watcher, "CLAUDE_MD", path)
        return path

    monkeypatch.delenv("REPO_WATCHER_GITHUB_ONLY", raising=False)
    return write


def test_key_read_from_repo_skills_section(claude_md):
    claude_md("cto-claude-marketplace, other-repo")
    cfg = watcher.load_config()
    assert watcher.github_only_repos(cfg["GitHub-only repos"]) == ["cto-claude-marketplace", "other-repo"]


def test_env_override_wins(claude_md, monkeypatch):
    claude_md("cto-claude-marketplace")
    monkeypatch.setenv("REPO_WATCHER_GITHUB_ONLY", "env-repo")
    cfg = watcher.load_config()
    assert watcher.github_only_repos(cfg["GitHub-only repos"]) == ["env-repo"]


@pytest.mark.parametrize("value", ["", "<repo>, <repo> or empty"])
def test_empty_or_placeholder_means_no_repos(claude_md, value):
    claude_md(value)
    cfg = watcher.load_config()
    assert watcher.github_only_repos(cfg["GitHub-only repos"]) == []


def test_empty_promotion_repos_is_not_a_placeholder(claude_md):
    claude_md("")
    assert watcher.read_section()["Promotion repos"] == ""


def test_directive_names_github_only_repos():
    text = watcher.automation_directive(Path("/ws"), "D000", ["cto-claude-marketplace"])
    assert "GitHub-only repos (cto-claude-marketplace): send NO DM" in text
    assert "Slack channel ID D000" in text


def test_directive_without_github_only_repos_has_no_exception():
    text = watcher.automation_directive(Path("/ws"), "", [])
    assert "GitHub-only" not in text
    assert "send no summary message anywhere" in text
