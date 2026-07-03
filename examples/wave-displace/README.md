# Wave Displace

A runnable example that displaces a 96×96 grid (9,409 vertices) into a standing wave using
**one `foreach_get` and one `foreach_set`** — the bulk-IO pattern from
[`use-foreach-set-for-bulk-data`](../../rules/use-foreach-set-for-bulk-data.mdc) and the
[`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md) skill — instead of
9,409 individual `mesh.vertices[i].co` accesses.

**What it witnesses:** the bulk path is not just faster, it is *correct* — the check asserts
the vertex count is unchanged, the flat grid gained the expected Z span (the write actually
landed), and a probe vertex matches the closed-form wave exactly.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python wave_displace.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python wave_displace.py -- --output wave.png
blender --background --python wave_displace.py -- --output wave.png --engine cycles
```

It exits non-zero on failure (count changed, span wrong, or probe mismatch). The
`blender-smoke` workflow runs the check on Blender 4.5 LTS and 5.1.
