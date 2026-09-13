# VSE linear modifiers attribute

Pathology witness for the 5.2 removal of `Sequence.use_linear_modifiers`.
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

**What it witnesses:** `ColorStrip.use_linear_modifiers` is a bool you can
set on 4.5.11 and 5.1.2. The same getattr/setattr is `AttributeError` on
5.2.1. `hasattr` then read never raises on any of the three.

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
