---
name: headless-batch-scripting
description: "Run Blender unattended with blender --background --python, arguments after the -- separator, --factory-startup and --python-exit-code, and temp_override for operators that need context. Use when the user renders, exports or processes .blend files from a CLI, CI job or batch script, passes arguments to a Blender script, or hits 'poll() failed, context is incorrect' or a job that exits 0 despite a Python traceback. Targets 5.2 LTS with 4.5 LTS fallback."
standards-version: 1.10.0
---

# Headless Batch Scripting

## Trigger

Use this skill when the user:

- Wants to render, export, or process .blend files from a CLI or CI pipeline
- Mentions `blender --background`, `--python`, "headless", "batch render", "no UI"
- Has an operator script that fails with `RuntimeError: Operator bpy.ops.X.Y.poll() failed, context is incorrect`
- Needs to pass arguments to a Blender Python script

## The basic shape

```powershell
blender --background --python my_script.py
```

Or with a specific .blend file:

```powershell
blender --background scene.blend --python my_script.py
```

Or with arguments after `--`:

```powershell
blender --background scene.blend --python my_script.py -- --output out.png --frames 1,5,10
```

`--background` (or `-b`) tells Blender not to launch a UI window. `--python` (or `-P`) runs a Python script. The script's `sys.argv` is Blender's **full** command line (`blender`, `--background`, `--python`, ...); slice off everything up to and including `--` to get your own arguments, as the parser below does.

Two flags matter for unattended runs:

- `--factory-startup` ignores the user's startup file and preferences (add-ons, themes, auto-run settings), so the job behaves the same on every machine.
- `--python-exit-code N` makes an uncaught exception in the script exit Blender with code `N`. Without it, a traceback still exits **0**, and CI reports success.

## What changes without a UI

The Blender API is the same in headless mode but several context-dependent behaviors break:

| Subsystem | Headless behavior |
| --- | --- |
| `bpy.context.window`, `bpy.context.area`, `bpy.context.region` | Often `None` |
| `bpy.context.active_object` | `None` if no scene is loaded or no active object set |
| `bpy.context.selected_objects` | Whatever the loaded file saved (the factory startup selects its cube); never assume it |
| Editor operators (`view3d.*`, `screen.*`) | Fail with "context is incorrect": the script's context has no area/region. Override one from the loaded file's screen (below) |
| Modal operators | Cannot be used; no event loop |
| Drag and drop, file dialogs, keymaps | All gone |
| Scene rendering (`bpy.ops.render.render`) | Works fine, this is the standard headless render path |

The headless API surface is "everything that operates on `bpy.data` directly" plus every operator that polls on objects or data rather than on an editor (`object.*`, import/export, `render.*`, `wm.*` save/load). Editor operators need the override described below.

## Rule of thumb: `bpy.data` is your friend

The single most important pattern: **prefer `bpy.data.*` over `bpy.ops.*`** in batch scripts.

```python
# FRAGILE: object operators do run under --background, but they act on
# whatever the selection happens to be, and each call is a full operator
# round-trip (slow in a loop).
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.object.delete()

# RIGHT: explicit, selection-independent, fast.
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
```

```python
# WRONG: export_scene.obj was the legacy Python OBJ add-on, removed in 4.0.
bpy.ops.export_scene.obj(filepath="/tmp/out.obj")  # AttributeError on 4.x / 5.x

# RIGHT in 5.x: the new exporter operates on bpy.data, not the active object selection.
bpy.ops.wm.obj_export(filepath="/tmp/out.obj", export_selected_objects=False)
```

The `mesh-editing-and-bmesh` skill covers the rest of the `bpy.data` and `bmesh` patterns. This skill is about **when** the headless context forces you toward those patterns.

## Which operators run headless

Two kinds of operator behave differently under `--background`:

- **Object and data operators** (`object.*`, `mesh.*` outside edit-mode UI, `export_scene.*`, `wm.*_export`, `render.render`): they poll on `context.object` / selection, not on an editor, so they run headless. `bpy.ops.object.select_all(action='DESELECT')` and `bpy.ops.object.transform_apply(...)` both return `{'FINISHED'}` under `--background` on 4.5 LTS and 5.2 LTS. Narrow them with an object/selection override, no window needed:

  ```python
  with bpy.context.temp_override(object=obj, active_object=obj, selected_editable_objects=[obj]):
      bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
  ```

- **Editor operators** (`view3d.*`, `screen.*`, `uv.*` that read the editor): they poll on an area/region and fail with `poll() failed, context is incorrect` unless you override one. A file loaded under `--background` still has its window and screen, so you can borrow the 3D viewport area from it.

## When you must use an editor operator: `temp_override` with window/area/region

A few `bpy.ops` calls have no `bpy.data` equivalent and genuinely need an editor context. For these, use `bpy.context.temp_override`:

```python
import bpy

def find_window_and_area():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                return window, area
    return None, None


def run_in_view3d_context(callable_, *args, **kwargs):
    window, area = find_window_and_area()
    if window is None or area is None:
        raise RuntimeError("No 3D viewport available")

    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    with bpy.context.temp_override(window=window, area=area, region=region):
        return callable_(*args, **kwargs)


run_in_view3d_context(bpy.ops.view3d.snap_cursor_to_selected)
```

This works under `--background` too: the window and screen come from the loaded file (the factory startup has one window whose screen includes a `VIEW_3D` area), so `bpy.ops.view3d.snap_cursor_to_selected()` returns `{'FINISHED'}` with the override and fails its poll without it. It fails only when the loaded file's screen has no 3D viewport, which is why the helper raises instead of assuming one. Prefer a `bpy.data` equivalent whenever one exists; it does not depend on what the file's UI layout happened to be.

## Argument parsing after `--`

Blender consumes its own flags before `--`. Anything after `--` is yours:

```python
import argparse
import sys

argv = sys.argv
if "--" in argv:
    argv = argv[argv.index("--") + 1:]
else:
    argv = []

parser = argparse.ArgumentParser(description="Batch render N frames")
parser.add_argument("--output", required=True, help="Output filepath template, like /tmp/out_####.png")
parser.add_argument("--frames", default="1", help="Comma-separated frames or ranges, e.g. 1,5,10-20")
args = parser.parse_args(argv)
```

The `if "--" in argv` guard handles the case where the user did not pass any of their own arguments.

## A complete worked example: headless batch render

```python
"""Batch render specified frames to PNG. Usage:

  blender --background scene.blend --python batch_render.py -- --output /tmp/r_####.png --frames 1,5,10
"""

import argparse
import os
import sys
import bpy


def parse_frames(spec):
    frames = []
    for chunk in spec.split(","):
        if "-" in chunk:
            lo, hi = chunk.split("-", 1)
            frames.extend(range(int(lo), int(hi) + 1))
        else:
            frames.append(int(chunk))
    return frames


def main():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--frames", default="1")
    parser.add_argument("--engine", default="CYCLES", choices=["CYCLES", "EEVEE"])
    args = parser.parse_args(argv)

    scene = bpy.context.scene
    if args.engine == "EEVEE":
        # EEVEE's engine id is 'BLENDER_EEVEE' on 5.0+, 'BLENDER_EEVEE_NEXT' on 4.2-4.5.
        scene.render.engine = 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'
    else:
        scene.render.engine = args.engine
    scene.render.image_settings.file_format = 'PNG'

    output_dir = os.path.dirname(args.output) or "."
    os.makedirs(output_dir, exist_ok=True)

    for frame in parse_frames(args.frames):
        scene.frame_set(frame)
        scene.render.filepath = args.output.replace("####", f"{frame:04d}")
        bpy.ops.render.render(write_still=True)
        print(f"Rendered frame {frame} -> {scene.render.filepath}")


if __name__ == "__main__":
    main()
```

Notes:

- `bpy.ops.render.render(write_still=True)` works in `--background`, like other operators that do not need a window or editor area.
- EEVEE's engine identifier is `BLENDER_EEVEE` on Blender 5.0+ and `BLENDER_EEVEE_NEXT` on 4.2-4.5 LTS (the id was reclaimed in 5.0 after legacy EEVEE was removed in 4.2). Detect via `bpy.app.version`.

## Detecting Blender version in scripts

```python
import bpy

major, minor, _patch = bpy.app.version

if (major, minor) >= (5, 0):
    eevee_engine = 'BLENDER_EEVEE'
else:
    eevee_engine = 'BLENDER_EEVEE_NEXT'
```

`bpy.app.version` is a `(major, minor, patch)` tuple, always reliable.

## Exit codes

`blender --background --python ...` exits 0 on success and non-zero only if Blender itself errors. Your Python script's exceptions get logged but **do not change the exit code by default**.

For CI, explicitly call `sys.exit`:

```python
try:
    main()
except Exception as e:
    print(f"FATAL: {e}", file=sys.stderr)
    sys.exit(1)
```

## Common AI mistakes

1. **Calling an editor operator in headless** without a window/area/region `temp_override`:

   ```python
   bpy.ops.view3d.snap_cursor_to_selected()  # poll() failed, context is incorrect
   ```

   Object operators such as `object.select_all` and `object.transform_apply` do not need this; they run under `--background` as-is.

2. **Using `bpy.context.scene` before a scene is loaded**. After Blender starts, the default startup file is loaded, so `context.scene` works. But if you've called `bpy.ops.wm.read_factory_settings(use_empty=True)`, dereferencing `context.scene.collection` may surprise you.

3. **Forgetting the `--` argv split**. Without it, `argparse` sees Blender's own flags and rejects them.

4. **Writing into the current working directory** assuming it's where the .blend lives. Cwd in `--background` is wherever the user ran Blender from. Use absolute paths or `bpy.path.abspath("//foo")` for relative-to-blend paths.

5. **Not handling Blender exit code**. Wrap `main()` and `sys.exit(1)` on failure.

6. **Trying to use modal operators** in `--background`. There is no event loop.

## Related

- `mesh-editing-and-bmesh` for `bpy.data` patterns to use in batch scripts
- `addon-scaffolding` for the registration patterns when an add-on must run headless
- Rule `prefer-data-over-ops-in-loops`
- Snippet `temp-override-context.py`

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`gltf-export-roundtrip`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/gltf-export-roundtrip): A sci-fi supply crate exported to glTF and re-imported, verifying the round-trip against the depsgraph-evaluated mesh within float tolerances. Falsify: `--no-yup` (exit 9).
- [`temp-override-join`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/temp-override-join): Join seven lantern parts into one object under bpy.context.temp_override — the supported replacement for the removed context.copy() dict-pass form. Falsify: `--no-override` (exit 3).
- [`usd-export-evaluation-mode`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/usd-export-evaluation-mode): The USD exporter evaluation_mode chooses viewport versus render modifier quality. Falsify: `--subdivision BEST_MATCH` (exit 4).

<!-- examples:end -->

## References

- Blender command-line arguments: https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html
- `bpy.context.temp_override`: https://docs.blender.org/api/current/bpy.types.Context.html
- `bpy.app.version`: https://docs.blender.org/api/current/bpy.app.html
