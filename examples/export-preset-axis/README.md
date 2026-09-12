# Export Preset Axis

A runnable example that exports the same radio-beacon mesh under the Unity
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

The still stages the two reimports side by side: standing Unity left, lying
Godot right. If `export_yup` were the same on both, the pair would match.

## Run

```bash
# Cheap correctness check (no render) - the CI check:
blender --background --python export_preset_axis.py --

# Falsifier: both presets Y-up. Must exit non-zero.
blender --background --python export_preset_axis.py -- --same-axis

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python export_preset_axis.py -- --output beacon.png
blender --background --python export_preset_axis.py -- --output beacon.png --engine cycles
```

It exits non-zero on failure (RNA drift, source not Z-dominant, Unity disk
not converted, Godot disk not Z-up, Unity not standing, Godot not lying,
orientations equal). The `blender-smoke` workflow runs the check on Blender
5.2 LTS and 4.5 LTS (5.1 on the weekly cron).
