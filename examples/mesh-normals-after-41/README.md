# Mesh normals after 4.1

Check-only witness for the normals API that replaced auto smooth in Blender
4.1, on 4.5 LTS and 5.x alike. A 16-sided cylinder is enough. There is no
gallery still, because the witness is attribute presence and normal vectors
(same class as [`eval-mesh-datablock-name`](../eval-mesh-datablock-name/)).

Follows [`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md)
§ Normals after 4.1 and the
[`no-removed-normals-api`](../../rules/no-removed-normals-api.mdc) rule.

**What it witnesses:**

- `Mesh.use_auto_smooth`, `auto_smooth_angle`, `calc_normals_split`,
  `free_normals_split` and `create_normals_split` do not exist. The pre-4.1
  auto smooth code raises `AttributeError: 'Mesh' object has no attribute
  'use_auto_smooth'`.
- `Mesh.set_sharp_from_angle(angle=radians(30))` on the flat-shaded
  cylinder marks the 32 cap-rim edges sharp, not the 16 side seams (22.5°
  apart). It also sets **all 18 faces smooth**, which code ported from auto
  smooth does not expect. `normals_domain` becomes `CORNER`.
- `Mesh.corner_normals` needs no `calc_normals_split()`. A rim vertex has
  two corner normals, (0, 1, 0) for the smooth side and (0, 0, −1) for the
  cap. Flattening the faces afterwards and reading again gives three, with
  no recompute call.

**What failure each check would catch:**

- exit 3 — a removed attribute exists again, or the pre-4.1 code was run
  (`--legacy-api` lands here: it raises)
- exit 4 — `set_sharp_from_angle` marked a different edge count
  (`--sharp-angle 10` lands here: all 48 edges)
- exit 5 — the rim vertex does not have exactly two corner normals
  (`--flatten-after` lands here: three)
- exit 6 — `set_sharp_from_angle` did not turn the flat faces smooth
  (`--skip-set-sharp` lands here)

## Who hits this

Import and cleanup scripts, exporters and add-ons written before 4.1, and
models trained on them, that set `mesh.use_auto_smooth = True` or call
`mesh.calc_normals_split()` before reading loop normals. On 4.5 LTS and 5.x
both raise. Replacements:

- `mesh.set_sharp_from_angle(angle=...)` for a one-off, destructive
  auto smooth (marks sharp edges, smooths faces)
- `bpy.ops.object.shade_auto_smooth(angle=...)` for the non-destructive
  version. On 5.2.1 it added a "Smooth by Angle" geometry-nodes modifier. On
  4.5.14 under `--background --factory-startup` it returned `{'CANCELLED'}`
  and added nothing, so headless 4.5 scripts should use
  `set_sharp_from_angle`.
- `mesh.corner_normals` (was `loop.normal` after `calc_normals_split()`),
  `mesh.vertex_normals`, `mesh.polygon_normals`

## Re-verified

| Measurement | 4.5.14 | 5.2.1 |
| --- | --- | --- |
| removed attributes present | none | none |
| pre-4.1 code (`--legacy-api`) | `AttributeError` | `AttributeError` |
| sharp edges at 30° / 10° | 32 / 48 of 48 | 32 / 48 of 48 |
| faces smooth after `set_sharp_from_angle` | 18 of 18 | 18 of 18 |
| rim-vertex corner normals (smooth / flattened after) | 2 / 3 | 2 / 3 |
| `shade_auto_smooth` under `--background` | `{'CANCELLED'}` | `{'FINISHED'}`, Smooth by Angle modifier |
| default exit | 0 | 0 |
| falsifier exits (`--legacy-api`, `--sharp-angle 10`, `--flatten-after`, `--skip-set-sharp`) | 3 / 4 / 5 / 6 | 3 / 4 / 5 / 6 |

## API reference

- [`Mesh.set_sharp_from_angle`](https://docs.blender.org/api/current/bpy.types.Mesh.html#bpy.types.Mesh.set_sharp_from_angle)
  ([4.5 LTS](https://docs.blender.org/api/4.5/bpy.types.Mesh.html#bpy.types.Mesh.set_sharp_from_angle))
- [`Mesh.corner_normals`](https://docs.blender.org/api/current/bpy.types.Mesh.html#bpy.types.Mesh.corner_normals),
  [`Mesh.normals_domain`](https://docs.blender.org/api/current/bpy.types.Mesh.html#bpy.types.Mesh.normals_domain)
- [`object.shade_auto_smooth`](https://docs.blender.org/api/current/bpy.ops.object.html#bpy.ops.object.shade_auto_smooth)

## Run

```bash
blender --background --python mesh_normals_after_41.py --
blender --background --python mesh_normals_after_41.py -- --legacy-api
blender --background --python mesh_normals_after_41.py -- --sharp-angle 10
blender --background --python mesh_normals_after_41.py -- --flatten-after
blender --background --python mesh_normals_after_41.py -- --skip-set-sharp
```

## Exit codes

Per-script sequential checks.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | A removed normals attribute exists, or the pre-4.1 code raised (`--legacy-api`) |
| 4 | `set_sharp_from_angle` marked the wrong number of edges (`--sharp-angle 10`) |
| 5 | Rim vertex corner normals are not exactly two (`--flatten-after`) |
| 6 | `set_sharp_from_angle` did not smooth the flat faces (`--skip-set-sharp`) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke passes no extra flags on the happy path. Its catalog falsifiers are
`--legacy-api` (exit 3), `--sharp-angle 10` (exit 4), `--flatten-after`
(exit 5) and `--skip-set-sharp` (exit 6).
