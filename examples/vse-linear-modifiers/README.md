# VSE linear modifiers attribute

Pathology witness for the 5.2 removal of `Strip.use_linear_modifiers`.
A COLOR strip is enough; there is no geometry and **no gallery still**
(same class as [`exit-pre-sidecar`](../exit-pre-sidecar/),
[`ngon-triangulate`](../ngon-triangulate/)).

Follows [`vse-python`](../../skills/vse-python/SKILL.md) and the
version-gated assertion shape of
[`gn-modifier-inputs`](../gn-modifier-inputs/) (per-version contract, exit
0 on every matrix leg). Scaffolding matches
[`cross-version-property-delete`](../cross-version-property-delete/)
(`check()` returns, argparse naive-API flag, FATAL wrapper). That example
does **not** version-branch — `del` is the same on 4.5 and 5.x — so the
gate itself is copied from `gn-modifier-inputs`, not from `del`.

**What it witnesses:** `use_linear_modifiers` is a bool you can set on a
strip on 4.5.11 and 5.1.2. The same getattr/setattr is `AttributeError` on
5.2.1. `hasattr` then read never raises on any of the three.

**The identifier is `Strip`, not `Sequence`.** Earlier text here named
`Sequence.use_linear_modifiers`. `bpy.types.Sequence` does not exist on
4.5.11, 5.1.2 or 5.2.1. The strip types are `Strip` / `ColorStrip`, and
the attribute is defined on the `Strip` base (the class chain is
`ColorStrip → EffectStrip → Strip`), so every strip type had it. Anyone
searching the API docs for `Sequence` will not find it.

**What failure each check would catch:**

- exit 3 — COLOR strip never landed
- exit 4 — attribute missing where the naive/legacy path requires it
  (`--assume-present` on 5.2 lands here)
- exit 5 — attribute still present, or getattr silent, on 5.2+
- exit 6 — setattr did not round-trip on 4.5 / 5.1
- exit 7 — the `hasattr` guard still raised

`--assume-present` is the falsifier: skip the version gate and demand the
4.5 RNA. It exits **0 on 4.5.11 and 5.1.2** (the old API still works) and
**4 on 5.2.1**. That is unlike `--same-axis`, which is red on every
binary.

No `SMOKE_SKIP`. Every matrix leg exercises the contract.

## Who hits this

Add-ons, presets and conform scripts that set
`strip.use_linear_modifiers = True` so colour-balance and curve modifiers
work in linear space. On 5.2 that line raises
`AttributeError: 'ColorStrip' object has no attribute 'use_linear_modifiers'`
(or the matching strip type), and the script stops at the first strip.
The RNA description on 4.5 and 5.1 reads:

> Calculate modifiers in linear space instead of sequencer's space

The default is `False` on both. On 5.2.1 there is no replacement
property: no identifier containing `linear` exists on `Strip` or on the
strip modifier (`COLOR_BALANCE` listed as a representative). Guard the
write with `hasattr`, as `guarded_read` does for the read. This example
does not claim how 5.2 chooses the colour space for strip modifiers; it
measures only that the switch is gone from RNA.

## Re-verified

| Measurement | 4.5.11 | 5.1.2 | 5.2.1 |
| --- | --- | --- | --- |
| `bpy.types.Sequence` exists | no | no | no |
| Attribute defined on | `Strip` | `Strip` | — (removed) |
| Default | `False` | `False` | — |
| `linear`-named property on `Strip` / strip modifier | yes / no | yes / — | no / no |
| default exit | 0 | 0 | 0 |
| `--assume-present` exit | 0 | 0 | 4 |

Exiting 0 on 4.5.11 and 5.1.2 under the falsifier is correct by design.
The attribute exists there, so the naive read works; the falsifier
exists to fail where it was removed.

**Observed while re-verifying, outside this contract:** on 5.1.2 in
background mode, `strip.modifiers.new(name=..., type="COLOR_BALANCE")` on
a COLOR strip created in factory-empty crashes Blender with
`EXCEPTION_ACCESS_VIOLATION`. The same call works on 4.5.11 and 5.2.1.
This example never adds a modifier, so its checks are unaffected.

## API reference

- [`bpy.types.Strip`](https://docs.blender.org/api/current/bpy.types.Strip.html)
  ([4.5 LTS](https://docs.blender.org/api/4.5/bpy.types.Strip.html#bpy.types.Strip.use_linear_modifiers),
  where `use_linear_modifiers` is documented)
- [`bpy.types.StripModifier`](https://docs.blender.org/api/current/bpy.types.StripModifier.html)

## Run

```bash
blender --background --python vse_linear_modifiers.py --
blender --background --python vse_linear_modifiers.py -- --assume-present
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | COLOR strip was not created |
| 4 | `use_linear_modifiers` missing when required (`--assume-present` on 5.2) |
| 5 | Attribute still present or getattr silent on 5.2+ |
| 6 | setattr round-trip failed |
| 7 | `hasattr`-guarded read raised |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--assume-present`.
