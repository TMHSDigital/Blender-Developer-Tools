# Geometry Nodes zone iterate

A Repeat Zone row and a For Each Element tower that witness
[`geometry-nodes-python`](../../skills/geometry-nodes-python/SKILL.md)
zone pairing — not tree structure.

`pair_with_output` is load-bearing. Unpaired Repeat Input has no Geometry
sockets; unpaired For Each evaluates empty (`Cannot evaluate node group` on
4.5). For Each's main `Geometry` output is the input mesh passthrough;
generated cubes live on `Generation_0`.

Closed forms (cube = 8 verts / 6 faces):

- Repeat: join one translated cube per iteration. verts = `8 × (1 + N)` with
  N=3 → 32. X-centers at `k × 1.2` for k = 0..3.
- For Each: one cube per POINT, Z-offset by `Index × 0.6`. verts = `8 × P`
  with P=6 → 48. Z-centers at `i × 0.6 + 0.21`.

**Count alone is not enough.** Joining N+1 cubes at the origin hits 32 verts
with a single X-center (`--no-offset`). The center axis is the second witness.

Same on 4.5 LTS and 5.x (zones are 4.3+). No skip.

**What failure each check would catch:**

- exit 3 — Repeat pairing broken or iterations wrong (`--unpair-repeat` → 0/0;
  `--repeat-iterations 1` → 16/12)
- exit 4 — Repeat count matches but cubes collapsed (`--no-offset`)
- exit 5 — For Each pairing broken, element count wrong, or main-socket
  passthrough (`--unpair-foreach` → 0/0; `--foreach-count 3` → 24/18;
  `--foreach-main` → 6/0)
- exit 6 — For Each count matches but Z-centers do not

## Run

```bash
blender --background --python gn_zone_iterate.py --
blender --background --python gn_zone_iterate.py -- --output zones.png
```

The `--output` render path measures framing via `examples/gallery_framing.py`
(exit 10 on violation).

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage; also carrier mesh was rewritten |
| 3 | Repeat evaluated vert/face count off closed form |
| 4 | Repeat X-centers off closed form |
| 5 | For Each evaluated vert/face count off closed form |
| 6 | For Each Z-centers off closed form |
| 10 | Gallery framing violation |
| 12 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`, `--no-offset`, `--unpair-foreach`, or
`--unpair-repeat`.
