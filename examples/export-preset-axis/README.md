# Export Preset Axis

A runnable example that exports the same radio-mast mesh twice: once with
the engine glTF preset from
[`engine-export-presets`](../../skills/engine-export-presets/SKILL.md)
(`export_yup=True`, the call Unity, Godot and Unreal all share), and once
naively with `export_yup=False`. It re-imports both files. The check is on
coordinates, not a screenshot: the preset copy stands; the Z-up copy lies.

**What it witnesses:** glTF is +Y up by spec, so `export_yup=False` is not
an engine preset, it is a bug every engine shows the same way. glTF axis RNA
is `export_yup`, not FBX `axis_forward` / `axis_up`.

- **Disk POSITION follows the closed form.** The preset bakes
  `(x, y, z) -> (x, z, -y)` with no node rotation. The naive export writes
  raw Z-up `(x, y, z)`. The check reads accessor min/max from the `.gltf`
  JSON.
- **Re-import proves the conversion.** Blender's importer, like Unity's,
  Godot's and Unreal's, treats the file as Y-up:
  `blender = (gltf.x, -gltf.z, gltf.y)`. The preset restores the source. The
  Z-up file permutes again, so the mast lies along `-Y`.
- **The two reimports differ.** The preset's `z_span` matches source
  height; the Z-up file's `y_span` matches that height. `--same-axis`
  exports both with `export_yup=True`; both stand and the differ check
  exits 9.
- **Exporter RNA is guarded.** Every kwarg passed must still exist on
  `bpy.ops.export_scene.gltf`.

Neighbor of [`gltf-export-roundtrip`](../gltf-export-roundtrip/) (Y-up bake
vs Z-up on disk for one file) and [`unapplied-scale-gltf`](../unapplied-scale-gltf/)
(`export_apply` is modifiers, not object scale). Until 0.143.x this example
called the Z-up export the "Godot preset". That was wrong: Godot is Y-up and
imports glTF per the spec, so the lying mast is what a Godot user would have
seen (#346).

The subject is a radio mast chosen because "up" is unmistakable on it: a
stepped concrete footing, a bolted base flange, a tapered mast in red and
white aviation bands with steel collars, three sector panel antennas, a
shrouded microwave dish on a raked arm, an equipment cabinet, and a red
obstruction lamp under a lightning rod. The rod's point is the witnessed tip
vertex.

The still stages the two re-imports side by side: the preset copy standing on
the left, the Z-up copy lying along the floor on the right. Beside each sits
a modelled X/Y/Z axis gizmo (red, green, blue) showing that re-import's
frame. The gizmo is measured, not placed: the render path tries all 24
axis-aligned rotations and keeps the one that maps the source vertices onto
the re-imported vertices (worst nearest-vertex distance, printed as
`fit_err`; exit 12 if it exceeds 1 mm). The preset gizmo comes out as the
identity, blue Z up. The Z-up gizmo comes out as `Y -> +Z, Z -> -Y`: green
Y points up and blue Z runs along the lying mast. The mast didn't fall over.
The Z-up file stores Z-up coordinates, and the importer reads them as
Y-up, as every glTF consumer does.

## Run

```bash
# Cheap correctness check (no render) - the CI check:
blender --background --python export_preset_axis.py --

# Falsifier: both exports Y-up. Must exit non-zero.
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
| 2 | argparse / usage |
| 3 | Source mast is not Z-dominant, or tip drifted |
| 4 | glTF reimport produced no mesh |
| 5 | Preset disk POSITION is not `(x, z, -y)`, or preset node has rotation |
| 6 | Z-up disk POSITION is not raw Z-up (checked after the re-import checks) |
| 7 | Preset reimport is not standing |
| 8 | Z-up reimport is not lying along Y, or reimported tip mismatch |
| 9 | Reimported orientations did not differ (`--same-axis` lands here; checked right after the preset stands) |
| 10 | Gallery framing violation (render path) |
| 11 | Asset-quality floor violation (render path) |
| 12 | Render path: no axis-aligned rotation maps the source onto a re-import, so the gizmo frame could not be measured |
| 13 | Exporter RNA missing expected glTF kwargs (checked first) |
| 14 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`. Its catalog falsifier is `--same-axis` (expects exit 9).
