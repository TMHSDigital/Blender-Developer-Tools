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

**Subset** (3 of the 18 attributes; the full map is below): `use_automasking_topology` and
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

## Who hits this

Sculpt add-ons, brush-preset importers and tool-setting UIs that read or
write `brush.use_automasking_*` / `brush.automasking_*`. On 5.2 the first
such access raises `AttributeError: 'Brush' object has no attribute ...`.
A panel that draws it disappears from the UI, and an importer stops
halfway through a preset.

Two traps on the way to fixing it:

- **The prefix rule is not uniform.** The ten `use_automasking_*`
  booleans keep their identifiers on the new struct. The eight
  `automasking_*` values drop the prefix, so a blanket
  `getattr(mas, old_name)` port breaks on exactly those eight.
- **A brush made without a mode has no settings struct.**
  `bpy.data.brushes.new(name)` returns a brush whose
  `mesh_automasking_settings` is `None` on 5.2. It must be created with
  `mode="SCULPT"`. A reader that trusts the pointer then dereferences
  `None`.

The version-safe reader is the one this example asserts
(`read_current`): take `.mesh_automasking_settings` when it exists and is
not `None`, otherwise fall back to the `Brush` attributes. Writes go
through the same struct and round-trip: setting `cavity_factor` and
`use_automasking_topology` on it reads back unchanged on 5.2.1.

## Full attribute map

Measured by listing `Brush` RNA on 4.5.11 and 5.1.2 (18 automasking
properties, identical on both), and `MeshAutomaskingSettings` RNA on 5.2.1
(19 properties).

| 4.5 / 5.1 `Brush.` | 5.2 `Brush.mesh_automasking_settings.` |
| --- | --- |
| `use_automasking_topology` | `use_automasking_topology` |
| `use_automasking_face_sets` | `use_automasking_face_sets` |
| `use_automasking_boundary_edges` | `use_automasking_boundary_edges` |
| `use_automasking_boundary_face_sets` | `use_automasking_boundary_face_sets` |
| `use_automasking_cavity` | `use_automasking_cavity` |
| `use_automasking_cavity_inverted` | `use_automasking_cavity_inverted` |
| `use_automasking_custom_cavity_curve` | `use_automasking_custom_cavity_curve` |
| `use_automasking_start_normal` | `use_automasking_start_normal` |
| `use_automasking_view_normal` | `use_automasking_view_normal` |
| `use_automasking_view_occlusion` | `use_automasking_view_occlusion` |
| `automasking_boundary_edges_propagation_steps` | `boundary_edges_propagation_steps` |
| `automasking_cavity_blur_steps` | `cavity_blur_steps` |
| `automasking_cavity_curve` | `cavity_curve` |
| `automasking_cavity_factor` | `cavity_factor` |
| `automasking_start_normal_falloff` | `start_normal_falloff` |
| `automasking_start_normal_limit` | `start_normal_limit` |
| `automasking_view_normal_falloff` | `view_normal_falloff` |
| `automasking_view_normal_limit` | `view_normal_limit` |
| — | `cavity_curve_op` (new in 5.2, no Brush counterpart) |

On 5.2.1 the only automasking-named property left on `Brush` is the
`mesh_automasking_settings` pointer itself.

## Re-verified

| Measurement | 4.5.11 | 5.1.2 | 5.2.1 |
| --- | --- | --- | --- |
| `bpy.types.MeshAutomaskingSettings` exists | no | no | yes |
| Automasking properties on `Brush` | 18 | 18 | 1 (the pointer) |
| `mesh_automasking_settings`, `mode="SCULPT"` | no attribute | no attribute | struct |
| `mesh_automasking_settings`, default mode | no attribute | no attribute | `None` |
| Brushes in factory-empty | 0 | 0 | 0 |
| default exit | 0 | 0 | 0 |
| `--assume-brush-attrs` exit | 0 | 0 | 5 |

Exiting 0 on 4.5.11 and 5.1.2 under the falsifier is correct by design.
The old attributes still exist there, so the naive read works; the
falsifier exists to fail where they were removed.

## API reference

- [`bpy.types.MeshAutomaskingSettings`](https://docs.blender.org/api/current/bpy.types.MeshAutomaskingSettings.html)
  (5.2 only)
- [`bpy.types.Brush`](https://docs.blender.org/api/current/bpy.types.Brush.html)
  ([4.5 LTS](https://docs.blender.org/api/4.5/bpy.types.Brush.html), where
  the `use_automasking_*` / `automasking_*` attributes live)
- [`BlendDataBrushes.new`](https://docs.blender.org/api/current/bpy.types.BlendDataBrushes.html#bpy.types.BlendDataBrushes.new)
  — the `mode` argument

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
