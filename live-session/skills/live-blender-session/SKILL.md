---
name: live-blender-session
description: "Work against the user's running Blender through the Blender Lab MCP server (the blender tools): read the scene with the summary, screenshot and docs tools before touching anything, save before any execute_blender_code call that mutates, prototype live, then hand back a script proven with blender --background. Use when the user has Blender open and asks about or wants changes to their current scene, file, selection or viewport, or when the blender MCP tools are available and a task needs real scene data rather than guesses. Needs Blender 5.1+ with the MCP add-on; on 4.5 LTS fall back to headless scripts."
standards-version: 1.10.0
---

# Live Blender Session (MCP)

## Trigger

Use this skill when:

- The `blender` MCP tools are available (`get_objects_summary`, `execute_blender_code`, ...) and the user refers to "my scene", "this file", "the selected object", or what is on screen
- A task needs facts only the open file has: object names, modifier stacks, material slots, units, what the viewport shows
- The user wants a change made in their open Blender, not a script to run later

Do not use it for work that must be reproducible (CI, batch jobs, anything another person will rerun). That is headless work; see `headless-batch-scripting`.

## What the server is

The plugin `blender-live-session` registers the official [Blender Lab MCP server](https://projects.blender.org/lab/blender_mcp), pinned to a reviewed commit. It talks to an add-on inside a running Blender (5.1 or newer) over `localhost:9876`. `execute_blender_code` runs whatever Python it is given in that session, **with no sandbox and no confirmation**. Treat it like typing into the user's Python console.

If a tool reports it cannot connect, the add-on is not running: ask the user to start it (Edit > Preferences > Add-ons > Blender MCP, or its auto-start option). Do not retry in a loop.

## Order of operations

1. **Read before you write.** Start with the tools that only read:
   - `get_objects_summary`, `get_object_detail_summary`: names, types, transforms, modifiers, materials
   - `get_blendfile_summary_datablocks`, `..._path_info`, `..._missing_files`, `..._of_linked_libraries`, `..._usage_guess`: what the file is and what it depends on
   - `get_screenshot_of_window_as_image`, `get_screenshot_of_area_as_image`, `render_viewport_to_path`, `render_thumbnail_to_path`: what the user is looking at
   - `search_api_docs`, `get_python_api_docs`, `search_manual_docs`: the API for the version actually running

   Never assume an object, collection or material name. Read it.
2. **Check the version** before choosing an API path. `bpy.app.version` decides between, for example, `.sequences` and `.strips`, or `action.fcurves` and the slotted-action channelbag (see `vse-python`, `slotted-actions-animation`). Branch on the tuple, never on `version_string`.
3. **Save before mutating.** If `bpy.data.is_dirty` is true or `bpy.data.filepath` is empty, stop and ask the user to save, or offer to save a copy with `bpy.ops.wm.save_as_mainfile(filepath=..., copy=True)`. A live mutation can only be undone with the user's own Ctrl+Z, and some operations (purges, `bpy.data.*.remove`) are not undoable at all.
4. **Mutate in small, inspectable steps.** One `execute_blender_code` call per logical change, each returning a `result` dict that states what changed (names, counts, before/after values). Prefer `bpy.data` edits over `bpy.ops` (see `prefer-data-over-ops-in-loops`); operators in the live session act on whatever the user has selected and in whatever editor has focus.
5. **Show the result.** Screenshot or render the viewport after a visible change so the user can judge it.
6. **Hand back a script.** Anything worth keeping becomes a standalone script that runs with `blender --background file.blend --python fix.py --python-exit-code 1` and asserts its own outcome. The live session found the fix; the headless run proves it.

## Returning data from execute_blender_code

Assign a JSON-serialisable dict to `result`; printed output is not a reliable channel.

```python
import bpy

obj = bpy.data.objects.get("Chair")
if obj is None:
    result = {"error": "no object named Chair", "objects": [o.name for o in bpy.data.objects]}
else:
    result = {
        "type": obj.type,
        "modifiers": [(m.name, m.type) for m in obj.modifiers],
        "materials": [s.material.name if s.material else None for s in obj.material_slots],
        "dimensions": tuple(round(v, 4) for v in obj.dimensions),
    }
```

Return names and numbers, not Blender objects: an `Object` comes back as its `repr`, which is useless to reason about.

## Live findings are not verification

A behaviour observed in the live session can depend on things a fresh process does not have: the user's preferences and add-ons, the current selection and active object, an evaluated depsgraph that has not been refreshed, or state left over from earlier calls. Before telling the user something works:

- Re-run it headless with `--factory-startup` on a saved copy of the file, or
- Use the `*_for_cli` variants (`execute_blender_code_for_cli`, `get_blendfile_summary_datablocks_for_cli`, ...), which open the file in a separate `blender --background` process. They use `BLENDER_PATH` when `blender` is not on `PATH`.

Say which one you did. "Worked in the live session" is a prototype result, not a test.

## Common AI mistakes

| Mistake | Consequence | Do instead |
| --- | --- | --- |
| Calling `execute_blender_code` first to "look around" with `bpy.ops` | Changes selection, mode or active object as a side effect | Use the summary tools, or read `bpy.data` without operators |
| Mutating an unsaved file | Nothing to go back to if the change is wrong | Ask the user to save, or save a copy first |
| Looping `bpy.ops` over many objects live | Slow, and each call acts on the current selection | `bpy.data` / bmesh / `foreach_set` (see `mesh-editing-and-bmesh`) |
| Assuming the 4.5 API because the pack targets it | Wrong path on the 5.x the user is running | Read `bpy.app.version` first |
| Reporting a live result as proof | It may not reproduce in a clean process | Prove it headless or with a `*_for_cli` tool |
| Leaving the user in Edit Mode or a temp override state | Their next action behaves unexpectedly | Restore the mode and selection you found |

## On Blender 4.5 LTS

The MCP add-on needs Blender 5.1 or newer, so a 4.5 LTS user has no live session. Work headless: ask for the `.blend` path and run `blender --background` scripts (see `headless-batch-scripting`), or have the user paste the output of a short read-only script you write for them.

## References

- Blender Lab MCP server: https://projects.blender.org/lab/blender_mcp
- `bpy.app.version`: https://docs.blender.org/api/current/bpy.app.html
- `bpy.ops.wm.save_as_mainfile`: https://docs.blender.org/api/current/bpy.ops.wm.html
- Command-line arguments (`--background`, `--factory-startup`, `--python-exit-code`): https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html
