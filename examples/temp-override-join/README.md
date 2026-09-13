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

# Falsifier: join without temp_override. Must exit non-zero.
blender --background --python temp_override_join.py -- --no-override

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python temp_override_join.py -- --output join.png
blender --background --python temp_override_join.py -- --output join.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh object count after join ≠ 1 (`--no-override` lands here) |
| 4 | Joined target is not the sole remaining mesh |
| 5 | Topology ≠ 24 verts / 18 faces |
| 6 | Source objects still present |
| 7 | Local Z span did not cover all steps |
| 8 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--no-override`.

