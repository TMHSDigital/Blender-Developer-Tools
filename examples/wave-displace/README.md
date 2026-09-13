# Wave Displace

A runnable example that displaces a 96×96 grid (9,409 vertices) into a standing wave using
**one `foreach_get` and one `foreach_set`** — the bulk-IO pattern from
[`use-foreach-set-for-bulk-data`](../../rules/use-foreach-set-for-bulk-data.mdc) and the
[`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md) skill — instead of
9,409 individual `mesh.vertices[i].co` accesses.

**What it witnesses:** the bulk path is not just faster, it is *correct* — the check asserts
the flat grid gained the expected Z span (the write actually landed) and that **every**
vertex matches the closed-form wave, so a stride or interleave bug in the flat buffer
cannot hide behind a lucky probe.

## Framing deviation

Edge-to-edge field — the displaced sheet fills the frame and crops at the left,
right, and bottom edges so the wave reads as a surface, not an object on a
stage (measured fill 1.000x/0.817y with edge touch on three sides). If wired
to `examples/gallery_framing.py`, call it with
`deviation="edge-to-edge wave field; the fill is the point"`.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python wave_displace.py --

# Falsifier: skip the foreach_set displacement. Must exit non-zero (z-span).
blender --background --python wave_displace.py -- --flat

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python wave_displace.py -- --output wave.png
blender --background --python wave_displace.py -- --output wave.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 4 | Z-span not in the closed-form band (`--flat` lands here) |
| 5 | A vertex is off the closed-form wave |
| 6 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--flat`.
