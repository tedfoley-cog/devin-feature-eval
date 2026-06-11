#!/usr/bin/env bash
# Grade a coding-task PR: clone the PR branch and run the hidden test suite.
# Env: PR_URL (required), RUN_KEY. Exit 0 = pass; prints score on last line.
# Requires a local postgres reachable via DATABASE_CREDENTIALS (default
# postgres:dispatch) for the dispatch test suite.
set -euo pipefail

PR_URL="${PR_URL:?PR_URL required}"
export DATABASE_CREDENTIALS="${DATABASE_CREDENTIALS:-postgres:dispatch}"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# PR_URL like https://github.com/owner/repo/pull/123
REPO_URL=$(echo "$PR_URL" | sed -E 's#(https://[^/]+/[^/]+/[^/]+)/pull/[0-9]+#\1#')
PR_NUM=$(echo "$PR_URL" | sed -E 's#.*/pull/([0-9]+).*#\1#')

git clone -q "$REPO_URL.git" "$WORK/repo"
cd "$WORK/repo"
git fetch -q origin "pull/$PR_NUM/head:prbranch"
git checkout -q prbranch

# Project-specific test invocation (dispatch backend). Use a fresh venv so the
# PR branch's source is what actually gets imported (an active editable install
# from elsewhere would shadow it), and so runs don't contaminate each other.
python3 -m venv "$WORK/venv"
PY="$WORK/venv/bin/python"
"$PY" -m pip install -q --upgrade pip >/dev/null
"$PY" -m pip install -q -e ".[dev]" >/dev/null

# The dispatch suite has a known teardown quirk: DROP DATABASE at session
# finish can raise ObjectInUse, making pytest exit nonzero even when every
# test passed. Grade on the result summary, not the exit code.
set +e
OUT=$("$PY" -m pytest tests/ -q 2>&1)
set -e
SUMMARY=$(echo "$OUT" | grep -E "[0-9]+ (passed|failed)" | tail -1 || true)
echo "$SUMMARY" >&2

ERRORS=$(echo "$SUMMARY" | grep -oE "[0-9]+ error" | grep -oE "[0-9]+" || true)

if echo "$SUMMARY" | grep -qE "[0-9]+ failed"; then
  echo "0.0"
  exit 1
elif [ -n "$ERRORS" ] && { [ "$ERRORS" != "1" ] || ! echo "$OUT" | grep -q "ObjectInUse"; }; then
  # Errors other than the single known DROP DATABASE teardown quirk fail the run.
  echo "0.0"
  exit 1
elif echo "$SUMMARY" | grep -qE "[0-9]+ passed"; then
  echo "1.0"
else
  echo "0.0"
  exit 1
fi
