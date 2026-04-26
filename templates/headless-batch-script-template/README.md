# Headless Batch Script Template

A working starter for a Blender batch script that runs without the UI.
The script opens a `.blend` from disk, optionally applies a modifier to
every mesh, and exports to glTF.

## Usage

```powershell
blender --background <input.blend> --python script.py -- `
    --output .\out\result.glb `
    --apply-modifier SUBSURF `
    --subsurf-levels 2
```

Linux / macOS:

```bash
blender --background <input.blend> --python script.py -- \
    --output ./out/result.glb \
    --apply-modifier SUBSURF \
    --subsurf-levels 2
```

The `--` separator is required. Everything before it is consumed by
Blender (`--background`, `--python`, the input file). Everything after
it is forwarded to `script.py` as `sys.argv`.

## What it does

1. Parses script-side args after `--`.
2. Iterates every mesh object in the loaded `.blend`.
3. If `--apply-modifier` was passed, adds that modifier and applies it
   in place. The application step uses `bpy.context.temp_override`
   rather than the deprecated context-dict-passing form, so the script
   works on Blender 4.5 LTS and 5.x.
4. Exports the scene to a `.glb` at the given output path.
5. Returns explicit exit codes (0 success, 2-4 different failure modes)
   so a CI pipeline can detect failures.

## Expected environment

- Blender on the system `PATH` (or invoked by absolute path).
- Write access to the output directory. The script does not create
  parent directories; create them in your shell wrapper if needed.
- Input `.blend` exists and contains at least one mesh object. With no
  meshes the script returns exit code 2.

## Common gotchas

- **Forgetting the `--`**. Blender treats the following args as its
  own and complains. The script never sees them.
- **Output path with spaces on Windows**. Quote the whole path:
  `--output ".\out folder\result.glb"`.
- **Running without `--background`**. The script still works, but
  Blender opens a UI window and stays open after the script finishes.
  Use `--background` for unattended runs.
- **Operators that need a 3D Viewport context**. Some operators only
  work when a `VIEW_3D` area exists. In headless mode, none does.
  Either rewrite using `bpy.data.*`, or fabricate a window+area via
  `temp_override` (advanced; see the `headless-batch-scripting` skill).
- **Modifier application order**. The script adds modifiers at the end
  of the existing modifier stack and applies them, so they run after
  any pre-existing modifiers. If the input file already has modifiers,
  this may not produce what you expect.

## Extending the template

This template covers a single batch operation (apply modifier + export).
For more complex workflows, factor each step into its own function and
return early with distinct exit codes. The `main()` function is the
orchestration point; everything else should be pure helpers.

## See also

- Skill `headless-batch-scripting` for the full pattern catalog.
- Rule `prefer-temp-override-over-context-copy` for why we avoid
  `bpy.context.copy()`.
- Snippet `temp-override-context.py` for the minimal override pattern.
