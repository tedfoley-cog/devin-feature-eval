#!/usr/bin/env bash
# Grade a coding-task PR: clone the PR branch and run the hidden test suite.
# Env: PR_URL (required), RUN_KEY. Exit 0 = pass; prints score on last line.
set -euo pipefail

PR_URL="${PR_URL:?PR_URL required}"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# PR_URL like https://github.com/owner/repo/pull/123
REPO_URL=$(echo "$PR_URL" | sed -E 's#(https://[^/]+/[^/]+/[^/]+)/pull/[0-9]+#\1#')
PR_NUM=$(echo "$PR_URL" | sed -E 's#.*/pull/([0-9]+).*#\1#')

git clone -q "$REPO_URL.git" "$WORK/repo"
cd "$WORK/repo"
git fetch -q origin "pull/$PR_NUM/head:prbranch"
git checkout -q prbranch

# Project-specific test invocation (dispatch backend):
pip install -q -e ".[dev]" >/dev/null 2>&1 || pip install -q -e . >/dev/null 2>&1
if python -m pytest tests/ -x -q; then
  echo "1.0"
else
  echo "0.0"
  exit 1
fi
