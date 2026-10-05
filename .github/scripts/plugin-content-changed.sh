#!/usr/bin/env bash
# Exit 0 when plugin content changed between BASE and HEAD, 1 when it did not.
#
#   bash .github/scripts/plugin-content-changed.sh v0.143.9
#
# Plugin content is what scripts/build_plugin_dist.py ships: skills/, claude/,
# rules/, snippets/, templates/. release.yml cuts a patch release when this
# says yes even if no commit subject is feat:/fix:, so a `docs:` correction to
# a skill still reaches plugin users (#350).
set -euo pipefail
base="${1:?usage: plugin-content-changed.sh BASE}"
if git diff --quiet "$base" HEAD -- skills claude rules snippets templates; then
  exit 1
fi
exit 0
