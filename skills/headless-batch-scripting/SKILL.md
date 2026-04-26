---
name: headless-batch-scripting
description: Run Blender headless via blender --background --python script.py for batch jobs. What changes without a UI, how to avoid UI-dependent operators, the temp_override pattern when ops must be used, and argparse after the -- separator.
standards-version: 1.9.4
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

`--background` (or `-b`) tells Blender not to launch a UI window. `--python` (or `-P`) runs a Python script. The script receives `sys.argv` containing everything after the `--` separator.

## What changes without a UI

The Blender API is the same in headless mode but several context-dependent behaviors break:

| Subsystem | Headless behavior |
| --- | --- |
| `bpy.context.window`, `bpy.context.area`, `bpy.context.region` | Often `None` |
| `bpy.context.active_object` | `None` if no scene is loaded or no active object set |
| `bpy.context.selected_objects` | Empty by default |
| Most `bpy.ops.<editor>.*` operators | Fail with "context is incorrect" because they expect an editor that does not exist |
| Modal operators | Cannot be used; no event loop |
| Drag and drop, file dialogs, keymaps | All gone |
| Scene rendering (`bpy.ops.render.render`) | Works fine, this is the standard headless render path |

The headless API surface is essentially "everything that operates on `bpy.data` directly" plus a small whitelist of operators that do not depend on UI state (most `render.*`, most `wm.*` save/load, scene-level edits).

## Rule of thumb: `bpy.data` is your friend

The single most important pattern: **prefer `bpy.data.*` over `bpy.ops.*`** in batch scripts.

```python
# WRONG: requires a 3D viewport context to even poll.
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.object.delete()

# RIGHT: works headless.
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
```

```python
# WRONG: requires UI for the file dialog.
bpy.ops.export_scene.obj(filepath="/tmp/out.obj")  # may also fail because the OBJ exporter is now under wm.obj_export

# RIGHT in 5.x: the new exporter operates on bpy.data, not the active object selection.
bpy.ops.wm.obj_export(filepath="/tmp/out.obj", export_selected_objects=False)
```

The `mesh-editing-and-bmesh` skill covers the rest of the `bpy.data` and `bmesh` patterns. This skill is about **when** the headless context forces you toward those patterns.

## When you must use a `bpy.ops` that wants UI: `temp_override`

A few `bpy.ops` calls have no `bpy.data` equivalent and genuinely need an editor context. For these, use `bpy.context.temp_override`:

```python
import bpy

def find_window_and_area():
    for window in bpy.data.window_managers[0].windows:
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


run_in_view3d_context(bpy.ops.object.transform_apply, location=True, rotation=True, scale=True)
```

In **pure** headless mode (`--background`), there are no windows at all, so this pattern only works if you have a "GUI but headless" setup (e.g. `blender --python` without `--background`, running on a virtual framebuffer).

For true headless, your only option is to find a `bpy.data` equivalent or pre-bake the operation into the .blend file.

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
    parser.add_argument("--engine", default="CYCLES", choices=["CYCLES", "BLENDER_EEVEE_NEXT"])
    args = parser.parse_args(argv)

    scene = bpy.context.scene
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

- `bpy.ops.render.render(write_still=True)` is one of the few `bpy.ops` calls that work in `--background`.
- `BLENDER_EEVEE_NEXT` is the 5.x EEVEE engine identifier. On 4.5 LTS, use `BLENDER_EEVEE`. Detect via `bpy.app.version`.

## Detecting Blender version in scripts

```python
import bpy

major, minor, _patch = bpy.app.version

if (major, minor) >= (5, 0):
    eevee_engine = 'BLENDER_EEVEE_NEXT'
else:
    eevee_engine = 'BLENDER_EEVEE'
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

1. **Calling UI-dependent `bpy.ops` in headless** without a `temp_override`:

   ```python
   bpy.ops.object.select_all(action='DESELECT')  # fails: no view3d
   ```

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

## References

- Blender command-line arguments: https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html
- `bpy.context.temp_override`: https://docs.blender.org/api/current/bpy.types.Context.html
- `bpy.app.version`: https://docs.blender.org/api/current/bpy.app.html
