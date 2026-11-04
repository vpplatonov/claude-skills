# git-config

`setup.sh` sets up global git on a new machine: your identity, optional SSH
commit signing, the safety defaults the `repo-*` skills rely on, and a set of
short aliases. It's safe to rerun — it prints only the values it changes.

## Run it

```bash
# Global identity (asks for anything you leave out, defaulting to current values)
./setup.sh --name "Your Name" --email 12345678+you@users.noreply.github.com

# ...plus SSH commit signing and a default branch for `git init`
./setup.sh --name "Your Name" --email you@example.com \
  --signing-key ~/.ssh/id_ed25519.pub --default-branch main

# Company email only for repos under one folder (everything else keeps the global one)
./setup.sh --org-identity ~/workspace/acme/ --email you@acme.com
```

| Option | Effect |
|---|---|
| `--name`, `--email` | Global `user.name` / `user.email`. A GitHub noreply address keeps your real email out of public commits |
| `--signing-key <file.pub>` | SSH commit signing: `gpg.format=ssh`, `user.signingkey`, `commit.gpgsign=true`, and adds `<email> <key>` to `~/.ssh/allowed_signers` (older lines are kept, so earlier commits still verify) |
| `--default-branch <name>` | `init.defaultBranch`; without it the current value is kept, or `main` if unset |
| `--org-identity <dir> --email <e>` | Writes `~/.gitconfig-<dir name>` with that email and adds `includeIf "gitdir:<dir>/"` to the global config. Does nothing else |

Check which email a repo will commit with: `git -C <repo> config user.email`.

## Safety defaults (always set)

| Setting | Why |
|---|---|
| `branch.autoSetupMerge=false` | `git checkout -b x origin/release` no longer makes `x` track `release`, so a later plain `git push` can't land on the shared branch (the incident in `github-branch-hygiene`) |
| `push.autoSetupRemote=true` | The first plain `git push` of a new branch creates a same-named remote branch and tracks it — no `-u origin <branch>` needed |
| `core.autocrlf=input` | Commits LF line endings even if a tool writes CRLF |

## Aliases

An alias is a shortcut for a git subcommand: you type `git <alias>`, and
anything after it is passed through, so `git co -b feature/x` runs
`git checkout -b feature/x`.

| Alias | Runs | What it's for | Example |
|---|---|---|---|
| `co` | `checkout` | Switch branches or restore files | `git co feature/login`, `git co -b feature/new` |
| `br` | `branch` | List, create or delete branches | `git br -a`, `git br -d old-branch` |
| `ci` | `commit` | Commit | `git ci -m "Fix login redirect"` |
| `st` | `status` | Working-tree status | `git st`, `git st -sb` (short, with branch) |
| `nmerge` | `merge --no-ff` | Merge that always creates a merge commit, so the branch stays visible in history | `git nmerge feature/login` |
| `unstage` | `reset HEAD --` | Take files out of the staging area, keeping your edits (same as `git restore --staged`) | `git unstage app.py`, `git unstage .` |
| `last` | `log -1 HEAD` | Show the latest commit | `git last`, `git last --stat` |
| `lg` | `log --graph --pretty=format:'…' --abbrev-commit --date=relative` | Compact colour graph: short hash, branches/tags, subject, relative date, author | `git lg -20`, `git lg --all`, `git lg main..HEAD` |
| `hist` | `log --pretty=format:'%h %ad \| %s%d [%an]' --graph --date=short` | Same graph with plain `YYYY-MM-DD` dates — easier to copy or paste into notes | `git hist -10`, `git hist --since=2.weeks` |
| `release` | shell function (below) | Create an annotated tag `release-<n>-<branch>-<full sha>` on the current commit, where `<n>` = number of existing `release-*` tags | `git release -m "Sprint 12"` |

`release` is a shell alias (it starts with `!`), so its tag name is
computed each time you run it:

```
!f() { b=$(git symbolic-ref --short HEAD) || return 1; n=$(git tag -l "release-*" | wc -l | tr -d " "); git tag -a "release-$n-$b-$(git rev-parse HEAD)" "$@"; }; f
```

- Without `-m "…"` it opens your editor for the tag message (annotated tags need one).
- Tags stay local until you push them: `git push origin <tag>` (or `git push origin --tags`).
- It needs a branch checked out — on a detached HEAD it stops with
  `fatal: ref HEAD is not a symbolic ref` and creates no tag.

### Managing aliases

| Task | Command |
|---|---|
| List all aliases | `git config --get-regexp '^alias\.'` |
| See what one alias runs | `git config --global alias.lg` |
| Add or change one | `git config --global alias.sw switch` |
| Remove one | `git config --global --unset alias.sw` |
| Restore this set | rerun `./setup.sh` |
