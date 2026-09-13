# GN socket identifier rename

A jo-block (steel plinth + copper column) whose Geometry Nodes tree
witnesses the 5.2 socket-identifier collapse on
`FunctionNodeCompare` and `FunctionNodeRandomValue`. Follows
[`geometry-nodes-python`](../../skills/geometry-nodes-python/SKILL.md).

On 4.5.11 and 5.1.2, Compare INT exposes `A_INT` / `B_INT` and Random
Value FLOAT exposes `Min_001` / `Max_001` / `Value_001`. On 5.2.1 those
identifiers are gone — the live sockets reuse `A` / `B` and `Min` /
`Max` / `Value`. Looking up the unique *enabled* socket of a given name
wires on all three. Hard-coding the pre-5.2 identifiers raises on 5.2.

**What it witnesses:** identifier-agnostic wiring produces a 16-vert
evaluated mesh (plinth + column) with POINT `gauge_h == 1.80` on exactly
the eight column verts. Compare INT `7 > 2` switches the column in
(vert count). Random Value FLOAT with min=max=`HEIGHT` is stored as a
named attribute (Random is a field; using it as a constant Size source
evaluates to 0 — hazard found while authoring). zmax `1.94` is the
construction axis, not the Random axis.

Scaffolding matches
[`cross-version-property-delete`](../cross-version-property-delete/)
(`check()` returns, argparse naive-API flag, FATAL wrapper). That
example does **not** version-branch, so the per-version inventory
assert is the `gn-modifier-inputs` shape.

**What failure each check would catch:**

- exit 4 — identifier inventory wrong for this Blender
- exit 5 — pre-5.2 identifier lookup failed (`--legacy-ids` on 5.2)
- exit 6 — enabled-name lookup failed
- exit 7 — Compare did not switch the column in (8 verts)
- exit 8 — column not sitting on the plinth
- exit 9 — `gauge_h` not 1.80 on eight verts (Random unwired)

`--legacy-ids` is the falsifier: wire by `Min_001` / `A_INT`. It exits
**0 on 4.5.11 and 5.1.2** (those identifiers still exist) and **5 on
5.2.1**. Unlike `--same-axis`, it is not red on every binary.

No `SMOKE_SKIP`. Do not pass `deviation=` to `check_framing`.

## Run

```bash
blender --background --python gn_socket_rename.py --
blender --background --python gn_socket_rename.py -- --legacy-ids
blender --background --python gn_socket_rename.py -- --output gauge.png
```

The `--output` render path measures framing against the Layer 1 band via
`examples/gallery_framing.py` (exit 10 on violation) before writing the
still.

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 4 | Identifier inventory wrong for this Blender version |
| 5 | Pre-5.2 identifier missing (`--legacy-ids` on 5.2) |
| 6 | Enabled-name socket lookup failed |
| 7 | Evaluated vert count off (Compare did not switch the column in) |
| 8 | Evaluated zmax off closed form |
| 9 | POINT `gauge_h` not 1.80 on eight column verts |
| 10 | Gallery framing violation |
| 12 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--legacy-ids`.
