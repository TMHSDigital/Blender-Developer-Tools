"""The pinned gallery reference sets, defined once (#523). Stdlib only.

CONTACT_SET is the contact-sheet calibration set (scripts/contact_sheet.py
composites a candidate hero beside it). ASSET_SET is the asset-quality
reference lineup (scripts/asset_sheet.py renders the candidate beside it, and
tests/check_asset_sheet_select.py requires an assetSelect on each entry).

CLAUDE.md § Quality Gates names both sets for readers; it mirrors this file and
tests/check_reference_sets.py fails when the two disagree. To change a set,
edit it here and in that CLAUDE.md bullet in the same commit.
"""

CONTACT_SET = ("armature-bend", "damped-track-aim", "bmesh-gear")

ASSET_SET = (
    "collision-hull-proxy",
    "socket-attach-points",
    "vertex-color-ao",
    "wheelbarrow",
    "apothecary-shelf",
)
