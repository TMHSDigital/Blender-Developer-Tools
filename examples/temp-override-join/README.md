# Temp-Override Join

A runnable example that joins three unit cubes into a staircase using
`bpy.context.temp_override`, following the
[`prefer-temp-override-over-context-copy`](../../rules/prefer-temp-override-over-context-copy.mdc)
rule and the [`operators`](../../skills/operators/SKILL.md) skill: operators that need a
fabricated active/selection context run under `temp_override(**kwargs)`, not the deprecated
`bpy.context.copy()` dict-pass form removed in Blender 5.x.

**What it witnesses:** `object.join` under `temp_override` actually consumes the sources.
The check asserts closed-form topology (verts = 8 × steps, faces = 6 × steps), that exactly
one mesh remains, that the sources are gone, and that the local Z span covers all three
steps (`[-0.5, 2.5]`). A no-op override (the 5.x failure mode of the old dict-pass path)
leaves only step 0 and the Z span fails.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python temp_override_join.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python temp_override_join.py -- --output join.png
blender --background --python temp_override_join.py -- --output join.png --engine cycles
```

It exits non-zero on failure (wrong object count, topology mismatch, sources still alive,
or incomplete Z span). The `blender-smoke` workflow runs the check on Blender 4.5 LTS and
5.1.
