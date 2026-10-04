#!/usr/bin/env bash
# Release gate: exit non-zero unless CI evidence for $SHA is green.
#
#   1. Validate (push event) finished and succeeded on exactly this SHA.
#   2. If the SHA was merged from a PR, every check on that PR passed or was
#      skipped. Blender Smoke runs on PRs only, so this is its evidence.
#
# Env: GH_TOKEN, SHA, GITHUB_REPOSITORY. Optional: GATE_EVENT (default push),
# GATE_TIMEOUT seconds (default 1500), GATE_POLL seconds (default 20).
set -euo pipefail

repo="${GITHUB_REPOSITORY:?}"
sha="${SHA:?}"
event="${GATE_EVENT:-push}"
deadline=$((SECONDS + ${GATE_TIMEOUT:-1500}))

while :; do
  read -r status conclusion < <(
    gh run list --repo "$repo" --workflow validate.yml --commit "$sha" \
      --event "$event" --limit 1 --json status,conclusion \
      --jq '.[0] // {} | "\(.status // "none") \(.conclusion // "none")"'
  )
  [ "$status" = "completed" ] && break
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "::error::Validate did not finish for $sha (last status: $status)"
    exit 1
  fi
  echo "Validate status for $sha: $status; waiting"
  sleep "${GATE_POLL:-20}"
done

if [ "$conclusion" != "success" ]; then
  echo "::error::Validate concluded '$conclusion' for $sha; not releasing"
  exit 1
fi
echo "Validate: success"

pr=$(gh api "repos/$repo/commits/$sha/pulls" --jq '.[0].number // empty')
if [ -z "$pr" ]; then
  echo "No PR is associated with $sha (direct push); Validate alone gates this release"
  exit 0
fi

# gh exits non-zero while checks are pending or failing even with --json, so
# judge the output, not the exit status. One call yields "<count>:<bad>", where
# <bad> lists every check that did not pass or skip. Anything else means gh
# could not read the checks (rate limit, 5xx, network): fail closed.
out=$(gh pr checks "$pr" --repo "$repo" --json name,bucket \
  --jq '"\(length):" + ([.[] | select(.bucket != "pass" and .bucket != "skipping") | "\(.name)=\(.bucket)"] | join(", "))' \
  2>/dev/null) || true
count=${out%%:*}
bad=${out#*:}
case "$out" in *:*) ;; *) count="" ;; esac
case "$count" in
  ''|*[!0-9]*|0)
    echo "::error::could not read checks for PR #$pr; not releasing"
    exit 1
    ;;
esac
if [ -n "$bad" ]; then
  echo "::error::PR #$pr has checks that did not pass: $bad; not releasing"
  exit 1
fi
echo "PR #$pr: $count checks passed or were skipped"
