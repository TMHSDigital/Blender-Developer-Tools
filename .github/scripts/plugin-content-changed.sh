#!/usr/bin/env bash
# Exit 0 when plugin content changed between BASE and HEAD, 1 when it did not.
#
#   bash .github/scripts/plugin-content-changed.sh v0.143.9
#
# Plugin content is every path scripts/build_plugin_dist.py ships (its
# --list-paths: skills/, claude/, rules/, snippets/, templates/, the manifests,
# live-session/, LICENSE), so the list has one owner (#494). release.yml cuts a
# patch release when this says yes even if no commit subject is feat:/fix:, so
# a `docs:` correction to a skill or an MCP pin bump in live-session/ reaches
# plugin users (#350). Exit 2 if the path list cannot be read. PYTHON
# overrides the interpreter (default python3).
set -euo pipefail
base="${1:?usage: plugin-content-changed.sh BASE}"
here="$(cd "$(dirname "$0")" && pwd)"
paths=()
while IFS= read -r p; do
  p="${p%$'\r'}"
  [ -n "$p" ] && paths+=("$p")
done < <("${PYTHON:-python3}" "$here/../../scripts/build_plugin_dist.py" --list-paths)
if [ "${#paths[@]}" -eq 0 ]; then
  echo "::error::plugin-content-changed.sh: build_plugin_dist.py --list-paths printed nothing" >&2
  exit 2
fi
if git diff --quiet "$base" HEAD -- "${paths[@]}"; then
  exit 1
fi
exit 0
