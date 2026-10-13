#!/usr/bin/env bash
# Lalit Stock Application - stage everything, commit and push the current branch.
# Owner: Lalit Nayyar. Not financial advice.
# Linux/macOS counterpart of push.bat.
# Usage: ./push.sh ["commit message"]
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ ! -d .git ]]; then
  echo "Initializing git repository..."
  git init
  git branch -M main
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  read -r -p "Enter the remote repository URL (e.g. https://github.com/you/repo.git): " repo_url
  [[ -n "$repo_url" ]] || { echo "No URL entered. Aborting." >&2; exit 1; }
  git remote add origin "$repo_url"
fi

msg="$*"
[[ -n "$msg" ]] || msg="Update $(date '+%Y-%m-%d %H-%M')"

git add -A
git commit -m "$msg" || echo "Nothing to commit or commit failed."

branch="$(git rev-parse --abbrev-ref HEAD)"
git push -u origin "$branch" || { echo "Push failed. Check your remote URL and credentials." >&2; exit 1; }

echo "Done."
