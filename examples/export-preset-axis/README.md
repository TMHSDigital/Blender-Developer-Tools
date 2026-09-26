# Export Preset Axis

A runnable example that exports the same radio-mast mesh under the Unity
and Godot glTF presets from
[`engine-export-presets`](../../skills/engine-export-presets/SKILL.md) and
re-imports both files. The check is on coordinates, not a screenshot: Unity
(`export_yup=True`) stands; Godot (`export_yup=False`) lies.

**What it witnesses:** named engine presets are not comments on the same
kwargs. glTF axis RNA is `export_yup`, not FBX `axis_forward` / `axis_up`.

- **Disk POSITION follows the closed form.** Unity bakes
  `(x, y, z) -> (x, z, -y)` with no node rotation. Godot writes raw Z-up
  `(x, y, z)`. The check reads accessor min/max from the `.gltf` JSON.
- **Re-import proves the conversion.** Blender's importer always treats the
  file as Y-up: `blender = (gltf.x, -gltf.z, gltf.y)`. Unity restores the
  source. Godot permutes again, so the mast lies along `-Y`.
- **The two reimports differ.** Unity `z_span` matches source height; Godot
  `y_span` matches that height. `--same-axis` exports both with
  `export_yup=True`; both stand and the differ check exits 9.
- **Exporter RNA is guarded.** Every kwarg passed must still exist on
  `bpy.ops.export_scene.gltf`.

Neighbor of [`gltf-export-roundtrip`](../gltf-export-roundtrip/) (Y-up bake
vs Z-up on disk for one file) and [`unapplied-scale-gltf`](../unapplied-scale-gltf/)
(`export_apply` is modifiers, not object scale). This example names the
Unity vs Godot presets and asserts the re-imported orientations diverge.

The subject is a radio mast chosen because "up" is unmistakable on it: a
stepped concrete footing, a bolted base flange, a tapered mast in red and
white aviation bands with steel collars, three sector panel antennas, a
shrouded microwave dish on a raked arm, an equipment cabinet, and a red
obstruction lamp under a lightning rod. The rod's point is the witnessed tip
vertex.

The still stages the two re-imports side by side: the Unity copy standing on
the left, the Godot copy lying along the floor on the right. Beside each sits
a modelled X/Y/Z axis gizmo (red, green, blue) showing that re-import's
frame. The gizmo is measured, not placed: the render path tries all 24
axis-aligned rotations and keeps the one that maps the source vertices onto
the re-imported vertices (worst nearest-vertex distance, printed as
`fit_err`; exit 12 if it exceeds 1 mm). The Unity gizmo comes out as the
identity, blue Z up. The Godot gizmo comes out as `Y -> +Z, Z -> -Y`: green
Y points up and blue Z runs along the lying mast. The mast didn't fall over.
The Godot file stores Z-up coordinates, and the importer reads them as
Y-up. If `export_yup` were the same on both, the two copies and both gizmos
would match.

## Run

```bash
# Cheap correctness check (no render) - the CI check:
blender --background --python export_preset_axis.py --

# Falsifier: both presets Y-up. Must exit non-zero.
blender --background --python export_preset_axis.py -- --same-axis

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python export_preset_axis.py -- --output mast.png
blender --background --python export_preset_axis.py -- --output mast.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper and `11` on the render path is
the shared asset-quality helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage; also exporter RNA missing expected glTF kwargs |
| 3 | Source mast is not Z-dominant, or tip drifted |
| 4 | glTF reimport produced no mesh |
| 5 | Unity disk POSITION is not `(x, z, -y)`, or Unity node has rotation |
| 6 | Godot disk POSITION is not raw Z-up; also `--output` produced no file |
| 7 | Unity reimport is not standing |
| 8 | Godot reimport is not lying along Y, or reimported tip mismatch |
| 9 | Reimported orientations did not differ (`--same-axis` lands here) |
| 10 | Gallery framing violation |
| 11 | `--same-axis` did not collapse the axis difference; also asset-quality floor violation (render path) |
| 12 | Render path: no axis-aligned rotation maps the source onto a re-import, so the gizmo frame could not be measured |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--same-axis`.
