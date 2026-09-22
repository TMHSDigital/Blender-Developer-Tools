# Geometry Nodes bundle round-trip

Combine Bundle / Separate Bundle packing a cube plus Scale, Offset, and
Mark — witnessing [`geometry-nodes-python`](../../skills/geometry-nodes-python/SKILL.md)
item-name round-trip, not tree structure.

## Which RNA, on which Blender

| Blender | Combine / Separate RNA | Legacy `GeometryNodeCombineBundle` | This example |
| --- | --- | --- | --- |
| 4.5 LTS | not defined | defined, but evaluates **empty** unless `preferences.experimental.use_bundle_and_closure_nodes` is on (default **off**) | skips, exit 77 |
| 5.0, 5.1, 5.2 LTS | [`NodeCombineBundle`](https://docs.blender.org/api/current/bpy.types.NodeCombineBundle.html) / [`NodeSeparateBundle`](https://docs.blender.org/api/current/bpy.types.NodeSeparateBundle.html) | **undefined** — `nodes.new` raises `RuntimeError: Node type GeometryNodeCombineBundle undefined` | runs |

If you are porting a 4.5 script to 5.x and `nodes.new("GeometryNodeCombineBundle")`
raises "undefined", the 5.x id has no `GeometryNode` prefix: use
`NodeCombineBundle` / `NodeSeparateBundle`. On 4.5 the reverse holds: `NodeCombineBundle` is
undefined, and the legacy node can be created with the experimental
flag off — it just evaluates to nothing, which is the easy trap.
4.5 API pages: [`GeometryNodeCombineBundle`](https://docs.blender.org/api/4.5/bpy.types.GeometryNodeCombineBundle.html),
[`PreferencesExperimental`](https://docs.blender.org/api/4.5/bpy.types.PreferencesExperimental.html).

Every cell above was re-verified by probe on **4.5.11 LTS, 5.0.1, 5.1.2
and 5.2.1 LTS**. On 4.5.11 the flag exists and reads `False`; a
legacy Combine → Separate carrying a cube evaluates to 0 verts / 0 faces
with it off and 8 / 6 with it on. On 5.0.1, 5.1.2 and 5.2.1 the flag is
gone from `PreferencesExperimental`.

The catalog floor is `min_version` 5.0 and the example prints
`SMOKE_SKIP: Bundles require Blender 5.0+` (exit 77) below it.
`--force-run` bypasses the skip and creates the 5.x RNA, so 4.5 fails
for that reason — `NodeCombineBundle` undefined, caught by the FATAL
wrapper as exit 1 — not a hidden pass. On 5.x `--force-run` changes
nothing and exits 0.

## What it witnesses

Closed form (1 m cube, Scale=2, Offset=`(1.5, 0, 0)`, Mark=`0.314159`):

- verts/faces = 8/6
- x-extent `[0.5, 2.5]`
- POINT `bundle_mark` = `0.314159` on all 8 verts

**Count alone is not enough.** A cube that never entered the bundle is
still 8/6 (`--bypass`). Bbox from the unpacked Scale/Offset is the second
axis; the named attribute from the unpacked Float is the third. Each
axis has its own falsifier, and each falsifier leaves the axes before
it green, so it fails on the axis it names.

No gallery still. The contract is item names + typed round-trip; the
visible mesh is one cube and the attribute is invisible. Failure would
not read at thumbnail.

**What failure each check would catch:**

- exit 77 — Blender &lt; 5.0 and not `--force-run`
- exit 2 — `GeometryNodeCombineBundle` on 5.x (`--legacy-rna`)
- exit 3 — item names do not pair, so Separate yields no geometry
  (`--mismatch` renames the geometry item → 0/0)
- exit 4 — count matches but the unpacked Scale/Offset did not arrive
  (`--bypass`, `--pack-scale 1`)
- exit 5 — count and bbox match but the Float item did not travel
  (`--mismatch-mark` renames only the Float item → `bundle_mark` 0.0)

## Run

```bash
blender --background --python gn_bundle_roundtrip.py --
blender --background --python gn_bundle_roundtrip.py -- --force-run
blender --background --python gn_bundle_roundtrip.py -- --mismatch-mark
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `77` is the smoke skip protocol, not a product check.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper); `--force-run` on 4.5 lands here |
| 2 | argparse / usage; carrier mesh rewritten; `--legacy-rna` on 5.x |
| 3 | Evaluated vert/face count off closed form (`--mismatch`) |
| 4 | Unpacked Scale/Offset x-extent off (`--bypass`, `--pack-scale 1`) |
| 5 | `bundle_mark` missing or off closed form (`--mismatch-mark`) |
| 77 | `SMOKE_SKIP:` Bundles require Blender 5.0+ |

Measured on 4.5.11 / 5.0.1 / 5.1.2 / 5.2.1:

| Flag | 4.5.11 | 5.0.1 | 5.1.2 | 5.2.1 |
| --- | --- | --- | --- | --- |
| (none) | 77 | 0 | 0 | 0 |
| `--force-run` | 1 | 0 | 0 | 0 |
| `--bypass` | 77 | 4 | 4 | 4 |
| `--legacy-rna` | 77 | 2 | 2 | 2 |
| `--mismatch` | 77 | 3 | 3 | 3 |
| `--mismatch-mark` | 77 | 5 | 5 | 5 |
| `--pack-scale 1` | 77 | 4 | 4 | 4 |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS (5.1 on the
weekly cron, the `needs-5.1` PR label, or manual dispatch) and skips on 4.5
LTS. Smoke does not pass `--bypass`, `--legacy-rna`, `--mismatch`,
`--mismatch-mark`, or `--force-run`.
