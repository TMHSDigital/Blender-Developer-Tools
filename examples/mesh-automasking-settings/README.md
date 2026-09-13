# Mesh automasking settings move

Pathology witness for the 5.2 move of sculpt automasking RNA off `Brush`
into `MeshAutomaskingSettings`. There is no geometry and **no gallery
still** (same class as [`vse-linear-modifiers`](../vse-linear-modifiers/),
[`ngon-triangulate`](../ngon-triangulate/)).

Follows the version-gated assertion shape of
[`gn-modifier-inputs`](../gn-modifier-inputs/) (per-version contract, exit
0 on every matrix leg). Scaffolding matches
[`cross-version-property-delete`](../cross-version-property-delete/)
(`check()` returns, argparse naive-API flag, FATAL wrapper). That example
does **not** version-branch, so the gate itself is copied from
`gn-modifier-inputs`, not from `del`.

**Headless:** factory-empty has **zero** brushes. The script creates one
with `bpy.data.brushes.new("ProbeBrush", mode="SCULPT")`. `mode="SCULPT"`
is load-bearing on 5.2: a default-mode `new(name)` leaves
`mesh_automasking_settings is None`.

**Subset** (not all 18+ attributes): `use_automasking_topology` and
`use_automasking_cavity` keep their identifiers after the move; cavity
factor does not (`Brush.automasking_cavity_factor` vs
`MeshAutomaskingSettings.cavity_factor`). That pair covers the location
move and the nested identifier shortening.

**What it witnesses:** `bpy.types.MeshAutomaskingSettings` is absent on
4.5.11 and 5.1.2 and present on 5.2.1. Old `Brush.use_automasking_*` /
`Brush.automasking_*` getattr works on 4.5/5.1 and is `AttributeError` on
5.2. Reading `.mesh_automasking_settings` (with a Brush fallback) works
on all three.

**What failure each check would catch:**

- exit 3 — SCULPT brush never landed
- exit 4 — `MeshAutomaskingSettings` type presence wrong for this Blender
- exit 5 — old Brush attributes missing when required
  (`--assume-brush-attrs` on 5.2 lands here)
- exit 6 — old Brush attributes still present, or mas pointer is None, on 5.2+
- exit 7 — current-location read raised or returned the wrong types

`--assume-brush-attrs` is the falsifier: skip the version gate and demand
the 4.5 Brush RNA. It exits **0 on 4.5.11 and 5.1.2** (the old API still
works) and **5 on 5.2.1**. That is unlike `--same-axis`, which is red on
every binary.

No `SMOKE_SKIP`. Every matrix leg exercises the contract.

## Run

```bash
blender --background --python mesh_automasking_settings.py --
blender --background --python mesh_automasking_settings.py -- --assume-brush-attrs
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | SCULPT brush was not created |
| 4 | `MeshAutomaskingSettings` type presence wrong for this version |
| 5 | Old Brush automasking attributes missing when required (`--assume-brush-attrs` on 5.2) |
| 6 | Old Brush attributes still present, or mas is None, on 5.2+ |
| 7 | Current-location read raised or returned the wrong types |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--assume-brush-attrs`.
