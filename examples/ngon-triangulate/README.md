# N-gon triangulate

Synthesizes one hexagon by dissolving a cube edge, then asserts the
hygiene / tangent contracts on that defective mesh. Inverse of
[`mesh-hygiene-audit`](../mesh-hygiene-audit/) (clean mesh, no ngons)
and neighbor of [`triangulate-tangents`](../triangulate-tangents/)
(`calc_tangents` aborts on any n-gon).

**Why this pathology:** the audit's n-gon gate is a snapshot on clean
geometry. AI-generated meshes often leave dissolved n-gons; glTF
silently triangulates, so an export-only check is vacuous (12 tris
either way).

**Pre-assertion (pathology exists):** exactly **1** face with **6**
loops, **5** faces total. `--no-dissolve` exits 3.

**Handling (second axis):** `Mesh.calc_tangents` aborts with
`tris/quads` until `bmesh.ops.triangulate` on that face; afterward
**4** tris + **4** quads, **28** loops, tangents succeed. Count-only
glTF tris = 12 for a cube *or* this mesh. `--skip-triangulate` exits 4.

No gallery still. A hexagon on a cube does not read at thumbnail
without fake annotation.

## Verified behaviour

`Mesh.calc_tangents` raises `RuntimeError` on any face with more than
four loops. The message is byte-identical on 4.5.11 LTS, 5.1.2, and
5.2.1 LTS:

```
Error: Tangent space can only be computed for tris/quads, aborting
```

`TANGENT_ABORT` matches on the `tris/quads` substring, so the check
survives a reword of the surrounding sentence but still fails if the
abort stops happening at all.

**Affected versions:** all three targeted series. Nothing here is
version-gated: the abort, the counts and both falsifier exits are the
same on 4.5.11 LTS, 5.1.2 and 5.2.1 LTS, so neither falsifier is
expected to exit 0 anywhere.

**The UV map comes first.** `calc_tangents` checks for a UV map before
it looks at face sizes. On a mesh with no UV layer it fails with a
different message, and the n-gon abort is never reached:

```
Error: Tangent space computation needs a UV Map, "(null)" not found, aborting   # 4.5.11 LTS
Error: Tangent space computation needs a UV Map, "" not found, aborting         # 5.1.2, 5.2.1 LTS
```

So a mesh that has both problems shows only the UV error; add a UV map
and the `tris/quads` abort appears next. `build()` adds `UVMap` so the
check witnesses the n-gon abort, and because the match is on
`tris/quads`, a missing UV map would fail the check (exit 4) rather than
pass it.

### Re-verified

Run on 4.5.11 LTS, 5.1.2 and 5.2.1 LTS with a scratch probe that
repeats the construction:

| Claim | 4.5.11 | 5.1.2 | 5.2.1 |
| --- | --- | --- | --- |
| n-gon + UV map: `tris/quads` abort, byte-identical text | yes | yes | yes |
| n-gon, no UV map: UV-map error instead | `"(null)"` | `""` | `""` |
| glTF index count / 3, dissolved mesh | 12 | 12 | 12 |
| glTF index count / 3, plain cube | 12 | 12 | 12 |
| default / `--no-dissolve` / `--skip-triangulate` exit | 0 / 3 / 4 | 0 / 3 / 4 | 0 / 3 / 4 |

## Falsifiers

Each flag breaks one stage and lands on the assertion that stage feeds.
Neither announces a failure; both let a real check catch the mesh.

| Flag | What it breaks | Exit |
| --- | --- | --- |
| `--no-dissolve` | never makes the n-gon, so the pre-assertion finds no pathology (`ngon count 0 != 1`) | 3 |
| `--skip-triangulate` | skips `bmesh.ops.triangulate`, so the handling assertion sees the n-gon survive (`ngons=1 tris=0 quads=4`) | 4 |

## API reference

| Name | 4.5 LTS | 5.2 LTS |
| --- | --- | --- |
| `Mesh.calc_tangents` | [4.5](https://docs.blender.org/api/4.5/bpy.types.Mesh.html#bpy.types.Mesh.calc_tangents) | [5.2](https://docs.blender.org/api/current/bpy.types.Mesh.html#bpy.types.Mesh.calc_tangents) |
| `bmesh.ops.dissolve_edges` | [4.5](https://docs.blender.org/api/4.5/bmesh.ops.html#bmesh.ops.dissolve_edges) | [5.2](https://docs.blender.org/api/current/bmesh.ops.html#bmesh.ops.dissolve_edges) |
| `bmesh.ops.triangulate` | [4.5](https://docs.blender.org/api/4.5/bmesh.ops.html#bmesh.ops.triangulate) | [5.2](https://docs.blender.org/api/current/bmesh.ops.html#bmesh.ops.triangulate) |

## Run

```bash
blender --background --python ngon_triangulate.py --
blender --background --python ngon_triangulate.py -- --no-dissolve
blender --background --python ngon_triangulate.py -- --skip-triangulate
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (the `__main__` wrapper prints `ERROR: <type>: <message>`) |
| 2 | argparse / usage |
| 3 | Pathology missing: n-gon count, loops, or face count (`--no-dissolve` lands here) |
| 4 | `calc_tangents` / triangulate handling (`--skip-triangulate` lands here, via the real handling assertion) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--no-dissolve` or `--skip-triangulate`.
