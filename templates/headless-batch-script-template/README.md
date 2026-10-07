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
3. If `--apply-modifier` was passed, appends that modifier to the end of
   each mesh's stack. It then bakes the **whole** stack in stack order
   through the data API: `bpy.data.meshes.new_from_object` on the
   evaluated object, one depsgraph evaluation for every mesh, with no
   operator per object. The new modifier runs after any existing ones.
   Every modifier on the object is applied, not only the new one.
4. Exports the scene to a `.glb` at the given output path.
5. Returns explicit exit codes (0 success, 2-4 different failure modes)
   so a CI pipeline can detect failures.

## Exit codes

Same convention as `CONTRIBUTING.md` (file-local sequential checks; `9`
is legal; argparse usage is `2`). Not a repo-wide table.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 2 | argparse rejected the flags, or no mesh objects in the input `.blend` |
| 3 | Modifier apply raised `RuntimeError` |
| 4 | glTF export raised `RuntimeError` |

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
- **Modifier application order**. Do not swap the bake for
  `bpy.ops.object.modifier_apply(modifier=new.name)`. When the new
  modifier is not first in the stack, that operator evaluates it against
  the **base** mesh, prints only `Info: Applied modifier was not first,
  result may not be as expected`, and leaves the earlier modifiers live.
  `export_apply=True` then runs those afterwards, so the order is
  reversed. Measured on 4.5.11 and 5.2.1 with a cube carrying a live
  SUBSURF (levels 1) and `--apply-modifier TRIANGULATE`, the operator
  path exported 72 triangles, which is TRIANGULATE first and then
  SUBSURF. The stack bake gives 26 verts and 48 triangles, which is
  SUBSURF first and then TRIANGULATE. CI checks this case
  (`tests/smoke/check_glb_tris.py`).

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
