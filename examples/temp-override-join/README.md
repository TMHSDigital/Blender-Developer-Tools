# Temp-Override Join

A runnable example that assembles a hurricane lantern from seven separate part objects
with one `object.join` under `bpy.context.temp_override`, following the
[`prefer-temp-override-over-context-copy`](../../rules/prefer-temp-override-over-context-copy.mdc)
rule and the [`operators`](../../skills/operators/SKILL.md) skill: operators that need a
fabricated active/selection context run under `temp_override(**kwargs)`, not the deprecated
`bpy.context.copy()` dict-pass form removed in Blender 5.x.

The parts are the way a prop artist blocks the lantern out: a red enamel fount, an amber
glass globe, an iron wire guard, the two hurricane side air tubes, the bell cap, the wire
bail with its wooden grip, and the brass wick knob and filler cap. Each is its own object
with its own mesh, materials and transform. The join produces the single `Lantern` object an
engine wants.

**What it witnesses:** `object.join` under `temp_override` actually consumes the sources
and merges their material slots. The check asserts that exactly one mesh remains and it is
the target, that all six sources are gone, and that no geometry was lost (verts and faces
equal the sum over the parts). The joined mesh must carry exactly the five part materials,
once each, and every material must still own exactly the faces its parts brought. So the
glass is still glass and the grip is still wood. The local Z span must run from the fount's
foot (0) to the top of the grip (closed form 2.303), which proves the part transforms were
applied. A no-op override (the 5.x failure mode of the old dict-pass path) leaves seven
objects.

**The render is the joined object.** Everything in the still is one mesh object. It shows
five materials because the slots merged and the per-face indices were remapped. If they had
not been, the lantern would render in the target's red enamel from grip to foot. A shadowless
warm point light inside the globe (render-only) stands in for the lit wick.

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
| 5 | Verts / faces ≠ the sum over the seven parts |
| 6 | Source objects still present |
| 7 | Local Z span ≠ [0, 2.303]: a part transform was not applied |
| 8 | Material slots ≠ the five part materials, once each |
| 9 | Faces per material ≠ what the parts brought (indices not remapped) |
| 10 | `--output` framing gate (`gallery_framing`) |
| 11 | `--output` asset-quality floors (`gallery_asset_quality`) |
| 12 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--no-override`.

