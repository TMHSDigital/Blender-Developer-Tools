#!/usr/bin/env bash
# Print the release bump a set of commits calls for: major, minor, patch or none.
#
# stdin: full commit messages, each terminated by NUL
#   git log RANGE --format='%B%x00' | bash .github/scripts/bump-kind.sh
#
#   major  a feat/fix subject marked breaking (`feat!:`, `fix(scope)!:`), or a
#          body line starting `BREAKING CHANGE:` / `BREAKING-CHANGE:` (the
#          conventional-commit footer; case-sensitive, so prose that merely
#          mentions a breaking change in a subject does not cut a major)
#   minor  a feat/feature subject
#   patch  a fix subject
#   none   anything else (docs, chore, ci, ...), which does not release
#
# release.yml uses the level; pages.yml only needs "not none". Both call this
# script so the two decisions cannot drift apart.
set -euo pipefail

rank=0
while IFS= read -r -d '' msg || [ -n "${msg:-}" ]; do
  msg="${msg#$'\n'}"
  subject="${msg%%$'\n'*}"
  if printf '%s\n' "$subject" | grep -qiE '^(feat|feature|fix)(\(.+\))?!:' \
     || printf '%s\n' "$msg" | tail -n +2 | grep -qE '^BREAKING[ -]CHANGE: '; then
    rank=3
  elif printf '%s\n' "$subject" | grep -qiE '^(feat|feature)(\(.+\))?:'; then
    [ "$rank" -lt 2 ] && rank=2
  elif printf '%s\n' "$subject" | grep -qiE '^fix(\(.+\))?:'; then
    [ "$rank" -lt 1 ] && rank=1
  fi
  msg=""
done

case "$rank" in
  3) echo major ;;
  2) echo minor ;;
  1) echo patch ;;
  *) echo none ;;
esac
