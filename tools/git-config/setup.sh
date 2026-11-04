#!/usr/bin/env bash
# Configure global git: identity, aliases, and the safety defaults the repo-*
# skills rely on. Safe to rerun — prints every value it changes.
#
#   setup.sh [--name "Full Name"] [--email you@example.com]
#            [--signing-key ~/.ssh/id_ed25519.pub] [--default-branch main]
#   setup.sh --org-identity ~/workspace/acme/ --email you@acme.com [--name "Full Name"]
#
# Without --org-identity it sets the global identity (missing values are
# asked for, defaulting to the current ones). With it, it only adds a
# per-folder identity: commits in repos under that folder use that email.
set -euo pipefail

name="" email="" signing_key="" default_branch="" org_dir=""
while [ $# -gt 0 ]; do
  case "$1" in
    --name) name="$2"; shift 2 ;;
    --email) email="$2"; shift 2 ;;
    --signing-key) signing_key="$2"; shift 2 ;;
    --default-branch) default_branch="$2"; shift 2 ;;
    --org-identity) org_dir="$2"; shift 2 ;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

# set_cfg <file-flag> <key> <value>: set and report only if it changes.
set_cfg() {
  local where="$1" key="$2" value="$3" old
  old="$(git config $where --get "$key" 2>/dev/null || true)"
  if [ "$old" != "$value" ]; then
    git config $where "$key" "$value"
    echo "  $key: ${old:-(unset)} -> $value"
  fi
}

ask() {  # ask <prompt> <default>
  local reply
  read -r -p "$1 [${2}]: " reply
  echo "${reply:-$2}"
}

if [ -n "$org_dir" ]; then
  [ -n "$email" ] || { echo "--org-identity needs --email" >&2; exit 2; }
  org_dir="${org_dir/#\~/$HOME}"
  org_dir="${org_dir%/}/"
  slug="$(basename "$org_dir")"
  file="$HOME/.gitconfig-$slug"
  echo "Org identity for $org_dir ($file):"
  set_cfg "--file $file" user.email "$email"
  [ -z "$name" ] || set_cfg "--file $file" user.name "$name"
  set_cfg --global "includeIf.gitdir:$org_dir.path" "$file"
  exit 0
fi

echo "Identity:"
[ -n "$name" ] || name="$(ask "Name" "$(git config --global user.name || true)")"
[ -n "$email" ] || email="$(ask "Email (a GitHub noreply address keeps it private)" "$(git config --global user.email || true)")"
[ -n "$name" ] && [ -n "$email" ] || { echo "name and email are required" >&2; exit 2; }
set_cfg --global user.name "$name"
set_cfg --global user.email "$email"

if [ -n "$signing_key" ]; then
  signing_key="${signing_key/#\~/$HOME}"
  [ -f "$signing_key" ] || { echo "signing key not found: $signing_key" >&2; exit 2; }
  echo "SSH commit signing:"
  signers="$HOME/.ssh/allowed_signers"
  set_cfg --global gpg.format ssh
  set_cfg --global user.signingkey "$signing_key"
  set_cfg --global commit.gpgsign true
  set_cfg --global gpg.ssh.allowedSignersFile "$signers"
  # Add the email -> key line for local verification; keep older lines so
  # commits signed under a previous email still verify.
  line="$email $(awk '{print $1, $2}' "$signing_key")"
  if ! grep -qxF "$line" "$signers" 2>/dev/null; then
    echo "$line" >> "$signers"
    echo "  $signers: added $email"
  fi
fi

echo "Defaults:"
# Never let `git checkout -b x origin/<shared-branch>` track the shared
# branch — the root cause in github-branch-hygiene. New branches push to a
# same-named remote branch instead.
set_cfg --global branch.autoSetupMerge false
set_cfg --global push.autoSetupRemote true
set_cfg --global core.autocrlf input
current_default="$(git config --global init.defaultBranch || true)"
set_cfg --global init.defaultBranch "${default_branch:-${current_default:-main}}"

echo "Aliases:"
set_cfg --global alias.co checkout
set_cfg --global alias.br branch
set_cfg --global alias.ci commit
set_cfg --global alias.st status
set_cfg --global alias.nmerge "merge --no-ff"
set_cfg --global alias.unstage "reset HEAD --"
set_cfg --global alias.last "log -1 HEAD"
set_cfg --global alias.lg "log --graph --pretty=format:'%Cred%h%Creset %C(yellow)%d%Creset %s %Cgreen(%cr) %C(bold blue)<%an>%Creset' --abbrev-commit --date=relative"
set_cfg --global alias.hist "log --pretty=format:'%h %ad | %s%d [%an]' --graph --date=short"
# Shell alias, so the tag name is computed when you run it, not when this
# script runs: release-<n>-<branch>-<sha>.
set_cfg --global alias.release '!f() { n=$(git tag -l "release-*" | wc -l | tr -d " "); git tag -a "release-$n-$(git symbolic-ref --short HEAD)-$(git rev-parse HEAD)" "$@"; }; f'

echo "Done."
