#!/usr/bin/env bash
# Release gate: exit non-zero unless CI evidence for $SHA is green.
#
#   1. Validate (push event) finished and succeeded on exactly this SHA.
#   2. If the SHA was merged from a PR, every check on that PR passed or was
#      skipped (that includes the PR's Blender Smoke run).
#   3. If it was a direct push, Blender Smoke (push event) finished and
#      succeeded on this SHA -- unless every file the push changed matches the
#      workflow's paths-ignore, in which case no smoke run exists to wait for.
#
# Env: GH_TOKEN, SHA, GITHUB_REPOSITORY. Optional: BEFORE (the push's previous
# head, to diff the whole push), GATE_EVENT (default push), GATE_TIMEOUT seconds
# for Validate (default 1500), SMOKE_TIMEOUT seconds (default 5400: the smoke
# job's 75-minute timeout-minutes plus 15 minutes for queueing), GATE_POLL
# seconds (default 20).
set -euo pipefail

repo="${GITHUB_REPOSITORY:?}"
sha="${SHA:?}"
event="${GATE_EVENT:-push}"

# wait_green WORKFLOW_FILE LABEL TIMEOUT: poll until the newest run of the
# workflow on $sha completes, then require success.
wait_green() {
  local wf="$1" label="$2" deadline=$((SECONDS + $3)) status conclusion
  while :; do
    read -r status conclusion < <(
      gh run list --repo "$repo" --workflow "$wf" --commit "$sha" \
        --event "$event" --limit 1 --json status,conclusion \
        --jq '.[0] // {} | "\(.status // "none") \(.conclusion // "none")"'
    )
    [ "$status" = "completed" ] && break
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "::error::$label did not finish for $sha (last status: $status)"
      exit 1
    fi
    echo "$label status for $sha: $status; waiting"
    sleep "${GATE_POLL:-20}"
  done
  if [ "$conclusion" != "success" ]; then
    echo "::error::$label concluded '$conclusion' for $sha; not releasing"
    exit 1
  fi
  echo "$label: success"
}

# smoke_applies: 0 when some changed file falls outside blender-smoke.yml's
# paths-ignore ("**.md", "docs/**", "assets/**"). Unreadable file lists count
# as "applies" so the gate fails toward waiting, not toward skipping. So do
# lists of 300 or more: the compare and commit APIs return at most 300 files,
# in path order, so a big docs/gallery regeneration can hide the code change
# that follows it alphabetically (#365).
smoke_applies() {
  local files
  if [ -n "${BEFORE:-}" ] && [ "${BEFORE}" != "0000000000000000000000000000000000000000" ]; then
    files=$(gh api "repos/$repo/compare/$BEFORE...$sha" --jq '.files[].filename' 2>/dev/null) || return 0
  else
    files=$(gh api "repos/$repo/commits/$sha" --jq '.files[].filename' 2>/dev/null) || return 0
  fi
  [ -n "$files" ] || return 0
  [ "$(printf '%s\n' "$files" | wc -l)" -lt 300 ] || return 0
  while IFS= read -r f; do
    case "$f" in
      *.md|docs/*|assets/*) ;;
      *) return 0 ;;
    esac
  done <<< "$files"
  return 1
}

wait_green validate.yml Validate "${GATE_TIMEOUT:-1500}"

pr=$(gh api "repos/$repo/commits/$sha/pulls" --jq '.[0].number // empty')
if [ -z "$pr" ]; then
  if smoke_applies; then
    wait_green blender-smoke.yml "Blender Smoke" "${SMOKE_TIMEOUT:-5400}"
  else
    echo "Direct push changed only smoke-ignored paths; Validate alone gates this release"
  fi
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
