# Evaluated mesh datablock name

Pathology witness for the 5.2 change in
`Object.evaluated_get(depsgraph).data.name`. A cube plus SUBSURF is
enough; there is no gallery still (same class as
[`vse-linear-modifiers`](../vse-linear-modifiers/),
[`ngon-triangulate`](../ngon-triangulate/)).

Follows [`depsgraph-and-evaluated-data`](../../skills/depsgraph-and-evaluated-data/SKILL.md)
and the version-gated assertion shape of
[`gn-modifier-inputs`](../gn-modifier-inputs/) (per-version contract, exit
0 on every matrix leg). Scaffolding matches
[`cross-version-property-delete`](../cross-version-property-delete/)
(`check()` returns, argparse naive-API flag, FATAL wrapper). That example
does **not** version-branch, so the gate itself is copied from
`gn-modifier-inputs`, not from `del`.

**What it witnesses:** with source mesh named `SourceMesh`,
`evaluated_get().data.name` is generic `Mesh` on 4.5.11 and 5.1.2, and
`SourceMesh` on 5.2.1. `to_mesh().name` is `SourceMesh` on all three —
that accessor is not the witness. SUBSURF `levels=1` on a cube is
load-bearing: 8 source verts vs 26 evaluated (Catmull-Clark). Name
comparison that treats inequality as "this is evaluated" is silently
wrong on 5.2; nothing raises.

**What failure each check would catch:**

- exit 3 — source cube was not 8 verts, or evaluated data is missing
- exit 4 — SUBSURF did not produce a distinct evaluated mesh (not 26 verts)
- exit 5 — source datablock name is not `SourceMesh`
- exit 6 — evaluated datablock name is wrong for this Blender
  (`--assume-distinct-names` on 5.2 lands here: names match)
- exit 7 — `to_mesh().name` is not `SourceMesh`

`--assume-distinct-names` is the falsifier: skip the version gate and
demand the 4.5/5.1 inequality. It exits **0 on 4.5.11 and 5.1.2** (the
names still differ) and **6 on 5.2.1**. That is unlike `--same-axis`,
which is red on every binary.

No `SMOKE_SKIP`. Every matrix leg exercises the contract.

## Run

```bash
blender --background --python eval_mesh_datablock_name.py --
blender --background --python eval_mesh_datablock_name.py -- --assume-distinct-names
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Source cube missing or not 8 verts |
| 4 | SUBSURF did not produce a distinct evaluated mesh |
| 5 | Source datablock name is not `SourceMesh` |
| 6 | Evaluated datablock name wrong for this version (`--assume-distinct-names` on 5.2) |
| 7 | `to_mesh().name` is not `SourceMesh` |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--assume-distinct-names`.
