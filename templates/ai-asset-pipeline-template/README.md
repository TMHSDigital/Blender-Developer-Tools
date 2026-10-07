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

`--preset` is one of `unity`, `godot`, `unreal`. All three write the same
spec-compliant glTF: +Y up, meters, transforms applied. glTF fixes its
axes and units, Godot imports it as-is, and Unreal's glTF importer converts
meters to centimeters itself, so no preset changes `export_yup` or bakes a
scale. The flag is kept as the hook for engine-specific import hints (for
example Godot's `-convcolonly` collider name suffix). FBX for Unreal, which
does need axis and scale kwargs, lives in `snippets/export_preset_unreal.py`;
this template emits GLB so a CI job can check the `glTF` magic bytes the
same way for every preset.

## What it does

1. Parses script-side args after `--`.
2. Imports the GLB into an empty scene.
3. Keeps **every** mesh in the file. Shared (instanced) mesh data gets one
   copy per object, parents are cleared with the world placement kept,
   rotation and scale are applied, and all parts are joined into one
   object (`object.join`, which keeps material slots). A body plus
   separate wheels ships as one asset with the wheels in place; nothing
   is dropped. Split the parts in your own code before this step if your
   engine wants them as separate assets.
4. Checks the joined asset's largest bounding-box extent against
   0.01 m to 100 m (`MIN_EXTENT_M` / `MAX_EXTENT_M`). A fresh scene is
   always metric at scale 1.0, so this measures the imported geometry,
   not the scene settings. A prop written in centimeters as meters
   fails here instead of shipping 100x too large.
5. Sits the origin on the lowest world Z, recalculates face normals,
   and prints the evaluated triangle count.
6. Builds an LOD chain from `--lod-budgets` and asserts that each LOD's
   evaluated triangle count is at or under its budget.
7. Optionally builds a convex hull or AABB box collider.
8. Exports each LOD (and the collider) under the chosen engine preset.
9. Returns explicit exit codes so a CI pipeline can detect failures.

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
| 7 | `--collider convex` produced a hull that is not closed (an edge without exactly two faces), e.g. a flat input |
| 8 | The joined asset's largest extent is outside 0.01 m to 100 m (wrong source units) |
| 9 | An LOD's evaluated triangle count is over its `--lod-budgets` entry |
| 12 | `transform_apply` or `object.join` raised `RuntimeError` (for example multi-user data that was not isolated) |

10 and 11 are skipped on purpose. The repo's shared render gates use them
(framing and asset quality), so a template never reuses them.

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
- **Instanced and parented glTF nodes**. Two nodes on one mesh import as
  two objects sharing one Mesh (`users == 2`), and `transform_apply`
  refuses that data. A mesh under a rotated root has an identity
  `matrix_basis`, so the rotation lives only in `matrix_world`. The
  script isolates and unparents before applying. If you remove that
  step, a shared-mesh input exits 12. A parented input exits 0 but ships
  with its origin off the ground: on the smoke fixture, z=3.0 against a
  geometry minimum of z=2.0.
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
