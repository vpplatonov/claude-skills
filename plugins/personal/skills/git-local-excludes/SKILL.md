---
name: git-local-excludes
description: Add local-only, untracked-editor/tool directories (.idea, .claude) to a repo's .git/info/exclude instead of .gitignore.
---

# Git local excludes

When setting up or noticing untracked local-only directories in a git repo (IDE state, local tool config), add them to that repo's `.git/info/exclude` rather than `.gitignore` — `.git/info/exclude` is local to the clone and never committed, so it doesn't affect other contributors or get pushed.

## Rule

Ensure these two entries exist in `<repo>/.git/info/exclude`:

```
.idea
.claude
```

Append after the existing commented boilerplate lines (`# git ls-files...` etc.) — don't remove or alter that boilerplate.

## When to apply

- When starting work in a new repo under `~/workspace/<org>/` (or any repo) that doesn't have these entries yet
- When the user asks to replicate a `.git/info/exclude` change from one repo to another (sibling projects)
- When `git status` shows `.idea/` or `.claude/` as untracked and the repo's exclude file doesn't already cover them

Check the file first (`cat <repo>/.git/info/exclude`) before editing — don't duplicate entries that already exist.
