# Geometry Nodes bundle round-trip

Combine Bundle / Separate Bundle packing a cube plus Scale, Offset, and
Mark — witnessing [`geometry-nodes-python`](../../skills/geometry-nodes-python/SKILL.md)
item-name round-trip, not tree structure.

5.x RNA is `NodeCombineBundle` / `NodeSeparateBundle`.
`GeometryNodeCombineBundle` is the **4.5 experimental** id and is undefined
on 5.2. 4.5 LTS keeps the old names behind
`preferences.experimental.use_bundle_and_closure_nodes` (default **off**);
unflagged evaluation is empty. This example skips on 4.5
(`SMOKE_SKIP: Bundles require Blender 5.0+`, exit 77, catalog
`min_version` 5.0). `--force-run` bypasses the skip and creates the 5.x
RNA so 4.5 fails for that reason — not a hidden pass.

Closed form (1 m cube, Scale=2, Offset=`(1.5, 0, 0)`, Mark=`0.314159`):

- verts/faces = 8/6
- x-extent `[0.5, 2.5]`
- POINT `bundle_mark` = `0.314159` on all 8 verts

**Count alone is not enough.** A cube that never entered the bundle is
still 8/6 (`--bypass`). Bbox from the unpacked Scale/Offset is the second
axis; the named attribute from the unpacked Float is the third.

No gallery still. The contract is item names + typed round-trip; the
visible mesh is one cube and the attribute is invisible. Failure would
not read at thumbnail.

**What failure each check would catch:**

- exit 77 — Blender &lt; 5.0 and not `--force-run`
- exit 2 — `GeometryNodeCombineBundle` on 5.x (`--legacy-rna`)
- exit 3 — pairing/names broken (`--mismatch` → 0/0; `--force-run` on 4.5
  raises `NodeCombineBundle` undefined, caught as exit 1)
- exit 4 — count matches but unpacked Scale/Offset did not (`--bypass`,
  `--pack-scale 1`)
- exit 5 — bbox matches but `bundle_mark` did not travel through the bundle

## Run

```bash
blender --background --python gn_bundle_roundtrip.py --
blender --background --python gn_bundle_roundtrip.py -- --force-run
```
