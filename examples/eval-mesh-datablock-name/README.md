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

## Who hits this

Exporters, bakers and measurement scripts that receive "some mesh" and
decide whether it is the evaluated result or the original by comparing
names: `if mesh.name != obj.data.name: # evaluated`. On 5.2 that branch
never fires for a modified object, and nothing raises. The script
silently treats evaluated geometry as original: it writes the
modifier-free count into a report, or skips a `to_mesh_clear()` it
thinks it does not owe.

**It was never a reliable test.** Re-measured with the modifier removed,
`evaluated_get().data.name` equals the source name on **all three**
binaries, 4.5.11 included. On 4.5 and 5.1 the inequality held only for
objects whose modifiers produced a new mesh. The 5.2 change removed the
last case where it happened to work.

**What to do instead.** Do not infer "evaluated" from the datablock. The
caller knows which object it evaluated: keep that reference and branch on
where the mesh came from, not on what it is called. Two obvious ID
properties are no substitute. In a probe on the same SUBSURF cube,
`ID.is_evaluated` read `False` on the evaluated mesh, and `ID.original`
did not compare equal to the source mesh, on 4.5.11, 5.1.2 and 5.2.1
alike. Neither is offered here as a replacement.

## Re-verified

| Measurement | 4.5.11 | 5.1.2 | 5.2.1 |
| --- | --- | --- | --- |
| `evaluated_get().data.name`, SUBSURF | `Mesh` | `Mesh` | `SourceMesh` |
| `evaluated_get().data.name`, no modifier | `SourceMesh` | `SourceMesh` | `SourceMesh` |
| `to_mesh().name` | `SourceMesh` | `SourceMesh` | `SourceMesh` |
| Evaluated verts (SUBSURF / none) | 26 / 8 | 26 / 8 | 26 / 8 |
| default exit | 0 | 0 | 0 |
| `--assume-distinct-names` exit | 0 | 0 | 6 |

Exiting 0 on 4.5.11 and 5.1.2 under the falsifier is correct by design.
The naive assumption holds there for this modified cube, so there is
nothing to catch. The falsifier exists to fail where the assumption
broke.

## API reference

- [`Object.evaluated_get`](https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.evaluated_get)
  ([4.5 LTS](https://docs.blender.org/api/4.5/bpy.types.Object.html#bpy.types.Object.evaluated_get))
- [`Object.to_mesh`](https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.to_mesh)
  and [`Object.to_mesh_clear`](https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.to_mesh_clear)
- [`ID.is_evaluated`](https://docs.blender.org/api/current/bpy.types.ID.html#bpy.types.ID.is_evaluated),
  [`ID.original`](https://docs.blender.org/api/current/bpy.types.ID.html#bpy.types.ID.original)

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
