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
