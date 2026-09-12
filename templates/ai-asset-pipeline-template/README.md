# AI Asset Pipeline Template

A working starter for a headless Blender job that takes a GLB in and
writes an engine-ready LOD set plus optional collider. Provider-agnostic:
the input is a file path, not a generation vendor.

## Usage

```powershell
blender --background --python pipeline.py -- `
    --input .\source.glb `
    --outdir .\out `
    --preset unity `
    --lod-budgets 1024,256,64 `
    --collider convex
```

Linux / macOS:

```bash
blender --background --python pipeline.py -- \
    --input ./source.glb \
    --outdir ./out \
    --preset unity \
    --lod-budgets 1024,256,64 \
    --collider convex
```

The `--` separator is required. Everything before it is consumed by
Blender (`--background`, `--python`). Everything after it is forwarded
to `pipeline.py` as `sys.argv`.

Optional `--draco` enables glTF Draco compression on export.

`--preset` is one of `unity` (Y-up glTF), `godot` (Z-up glTF), `unreal`
(centimeter glTF: 100x bake then `export_yup=True`). FBX for Unreal lives
in `snippets/export_preset_unreal.py`; this template emits GLB so a CI
job can check the `glTF` magic bytes the same way for every preset.

## What it does

1. Parses script-side args after `--`.
2. Imports the GLB into an empty scene.
3. Checks scene units (metric meters), applies object rotation/scale,
   sits the origin on the lowest Z, recalculates face normals, and
   prints the evaluated triangle count.
4. Builds an LOD chain from `--lod-budgets`.
5. Optionally builds a convex hull or AABB box collider.
6. Exports each LOD (and the collider) under the chosen engine preset.
7. Returns explicit exit codes so a CI pipeline can detect failures.

Cleanup order follows `ai-mesh-cleanup`. LOD, collider, and export
helpers are duplicated from the snippets named in `pipeline.py`'s
header; templates are not a package.

## Exit codes

Same convention as `templates/headless-batch-script-template/`
(`script.py` / its README: 0 success, 2+ distinct failure modes;
argparse usage errors also exit 2). Not a repo-wide table; examples such
as `export-preset-axis` number their own checks independently.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 2 | Input file missing, or argparse rejected the flags (including an unsupported `--preset`) |
| 3 | Input is not a readable GLB (bad magic or import failure) |
| 4 | `--lod-budgets` missing, non-positive, or not strictly decreasing |
| 5 | Import produced no mesh |
| 6 | `outdir` is not a directory, or glTF export failed / wrote no file |

## Expected environment

- Blender on the system `PATH` (or invoked by absolute path).
- `--outdir` already exists. The script does not create it.
- `--input` is a GLB with at least one mesh. With no meshes the script
  returns exit code 5.

## Common gotchas

- **Forgetting the `--`**. Blender treats the following args as its
  own and complains. The script never sees them.
- **Output path with spaces on Windows**. Quote the whole path:
  `--outdir ".\out folder"`.
- **Running without `--background`**. The script still works, but
  Blender opens a UI window and stays open after the script finishes.
  Use `--background` for unattended runs.
- **Unreal mutates selected meshes** (100x scale bake). Each export
  selects one object. Do not re-export the same object as Unity afterward
  without restoring scale.
- **Operators that need a 3D Viewport context**. Some operators only
  work when a `VIEW_3D` area exists. In headless mode, none does.
  Either rewrite using `bpy.data.*`, or fabricate a window+area via
  `temp_override` (advanced; see the `headless-batch-scripting` skill).

## Extending the template

This template covers one pipeline (import, clean, LOD, collider, export).
For more complex workflows, factor each step into its own function and
return early with distinct exit codes. The `main()` function is the
orchestration point; everything else should be pure helpers.

## See also

- Skill `ai-mesh-cleanup` for the cleanup order.
- Skill `engine-export-presets` for Unity / Godot / Unreal axis and units.
- Skill `headless-batch-scripting` for the full pattern catalog.
- Rule `prefer-temp-override-over-context-copy` for why we avoid
  `bpy.context.copy()`.
- Snippet `lod_chain.py`, `convex_hull_collider.py`, `export_preset_unity.py`.
