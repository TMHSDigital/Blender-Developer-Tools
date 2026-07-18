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

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python wave_displace.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python wave_displace.py -- --output wave.png
blender --background --python wave_displace.py -- --output wave.png --engine cycles
```

It exits non-zero on failure (span wrong, or any vertex off the closed form). The
`blender-smoke` workflow runs the check on Blender 4.5 LTS and 5.1.
