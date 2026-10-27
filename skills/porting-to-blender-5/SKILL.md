---
name: porting-to-blender-5
description: "Port an add-on or script from Blender 3.x/4.x to 5.x (5.2 LTS) while keeping 4.5 LTS working: a triage recipe that runs the code headless on the target version and maps each traceback to its fix, and one table of every break the pack covers (bgl, action.fcurves, use_auto_smooth, Principled sockets, sequences, context dicts, ID properties, compositor node_tree, Grease Pencil, NodesModifier inputs, EEVEE id, use_nodes, bl_info) linking to the skill, rule or example that owns it. Use when the user asks to port, upgrade or update an add-on for Blender 5, or hits AttributeError, KeyError, TypeError or ModuleNotFoundError right after updating Blender."
standards-version: 1.10.0
---

# Porting to Blender 5

## Trigger

Use this skill when the user:

- Asks to "port", "upgrade", "update" or "make compatible" an add-on or script for Blender 5.x
- Gets `AttributeError`, `KeyError`, `TypeError` or `ModuleNotFoundError` from code that worked on an older Blender
- Wants one codebase that runs on both 4.5 LTS and 5.2 LTS

This skill is an index. Each row points at the skill, rule or runnable example that owns the fix, with the version facts measured there. Load the linked skill for the details; do not port from this table alone.

## Triage: let the target version tell you what broke

1. **Run it headless on the target version** with tracebacks turned into a failing exit code:

   ```bash
   blender --background --factory-startup --python-exit-code 1 --python my_script.py --
   ```

   For an add-on, run a script that imports the package and calls `register()`. An import-time break (`bgl`) never gets as far as your operators. See `headless-batch-scripting`.
2. **Read the first traceback, fix it, run again.** Breaks hide behind each other: an add-on that dies importing `bgl` has not reached its `action.fcurves` call yet.
3. **Map the error to the table below** by the attribute or key it names.
4. **Re-run on 4.5 LTS** if you still support it. Several fixes need a version branch (rows marked *branch*). Branch on the `bpy.app.version` tuple, never on `version_string` (see the `version-branch-skeleton.py` snippet).
5. **Grep for the silent ones.** Some breaks raise nothing: they quietly do the wrong thing (rows marked *silent*). Search the codebase for those patterns even if every run is green.

## The breaks the pack covers

| Old code | Changed in | What happens on 5.x | Fix | Owner |
| --- | --- | --- | --- | --- |
| `import bgl`, `bgl.glEnable`, `bgl.glLineWidth` | removed 5.0 | `ModuleNotFoundError`; the add-on never registers | `gpu.state`, `POLYLINE_*` shaders, `gpu_extras.batch` | [`gpu-drawing-and-overlays`](${CLAUDE_PLUGIN_ROOT}/skills/gpu-drawing-and-overlays/SKILL.md), rule [`no-bgl`](${CLAUDE_PLUGIN_ROOT}/rules/no-bgl.mdc) |
| `from_builtin('3D_UNIFORM_COLOR')` and other `2D_`/`3D_` shader names | gone (rejected on 5.2.1) | `ValueError` | `UNIFORM_COLOR`, `SMOOTH_COLOR`, ... | [`gpu-drawing-and-overlays`](${CLAUDE_PLUGIN_ROOT}/skills/gpu-drawing-and-overlays/SKILL.md) |
| `blf.size(font_id, size, dpi)` | 4.0 | `TypeError` | `blf.size(font_id, size)` | [`gpu-drawing-and-overlays`](${CLAUDE_PLUGIN_ROOT}/skills/gpu-drawing-and-overlays/SKILL.md) |
| `action.fcurves`, `action.groups` | removed 5.0 (slotted model since 4.4) | `AttributeError` | channelbag per slot; *branch*: `action_ensure_channelbag_for_slot` is 5.0+ only | [`slotted-actions-animation`](${CLAUDE_PLUGIN_ROOT}/skills/slotted-actions-animation/SKILL.md), [`turntable`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/turntable) |
| `mesh.use_auto_smooth`, `auto_smooth_angle`, `calc_normals_split()` | removed 4.1 | `AttributeError` | `set_sharp_from_angle`, `corner_normals` | rule [`no-removed-normals-api`](${CLAUDE_PLUGIN_ROOT}/rules/no-removed-normals-api.mdc), snippet [`set-sharp-from-angle.py`](${CLAUDE_PLUGIN_ROOT}/snippets/set-sharp-from-angle.py), [`mesh-normals-after-41`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/mesh-normals-after-41) |
| `bsdf.inputs["Emission"]`, `["Specular"]`, `["Clearcoat"]`, `["Subsurface"]`, `["Transmission"]` | renamed 4.0 (Principled v2) | `KeyError: ... key "Emission" not found` | `Emission Color`, `Specular IOR Level`, `Coat Weight`, ... | [`procedural-materials-and-shaders`](${CLAUDE_PLUGIN_ROOT}/skills/procedural-materials-and-shaders/SKILL.md) |
| `group.inputs.new(...)` on a node group | removed 4.0 | `AttributeError` | `group.interface.new_socket(...)` | [`procedural-materials-and-shaders`](${CLAUDE_PLUGIN_ROOT}/skills/procedural-materials-and-shaders/SKILL.md), [`geometry-nodes-python`](${CLAUDE_PLUGIN_ROOT}/skills/geometry-nodes-python/SKILL.md) |
| `scene.render.engine = 'BLENDER_EEVEE_NEXT'` | id changed 5.0 | `TypeError` (enum) | *branch*: `'BLENDER_EEVEE'` on 5.0+, `'BLENDER_EEVEE_NEXT'` on 4.2–4.5 | [`procedural-materials-and-shaders`](${CLAUDE_PLUGIN_ROOT}/skills/procedural-materials-and-shaders/SKILL.md) |
| `mat.use_nodes = True` (also worlds, lights) | deprecated 5.0, removed in 6.0 | `DeprecationWarning`; node tree exists anyway | *branch*: only on `< (5, 0, 0)` | [`procedural-materials-and-shaders`](${CLAUDE_PLUGIN_ROOT}/skills/procedural-materials-and-shaders/SKILL.md) |
| `scene.node_tree` (compositor) | removed 5.0 | `AttributeError` | *branch*: a compositor node group on `scene.compositing_node_group` | [`compositor-glare`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/compositor-glare) |
| `sequence_editor.sequences` | removed 5.0 | `AttributeError` | `.strips` (already on 4.5) | [`vse-python`](${CLAUDE_PLUGIN_ROOT}/skills/vse-python/SKILL.md), rule [`no-legacy-vse-sequences`](${CLAUDE_PLUGIN_ROOT}/rules/no-legacy-vse-sequences.mdc) |
| `new_effect(..., frame_end=...)` | changed 5.0 | `TypeError` | *branch*: `length=` on 5.0+ | [`vse-python`](${CLAUDE_PLUGIN_ROOT}/skills/vse-python/SKILL.md) |
| `scene["my_prop"]`, `"my_prop" in scene.keys()` for a registered `bpy.props` property | 5.0 | `KeyError`, or *silent*: `keys()` no longer lists it | attribute access, `property_unset`, `is_property_set` (no branch needed) | [`custom-properties`](${CLAUDE_PLUGIN_ROOT}/skills/custom-properties/SKILL.md), [`cross-version-property-delete`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/cross-version-property-delete) |
| `mod["Socket_1"] = value` on a NODES modifier | removed 5.2 | `TypeError: ... id properties not supported` | *branch*: the 5.2 RNA input properties | [`geometry-nodes-python`](${CLAUDE_PLUGIN_ROOT}/skills/geometry-nodes-python/SKILL.md), [`gn-modifier-inputs`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/gn-modifier-inputs) |
| `bpy.data.grease_pencils` holding legacy GPencil, `grease_pencils_v3` | 5.0 (GPv3 takes the name) | *silent* wrong type on 4.5, `AttributeError` on 5.x | *branch*: `grease_pencils_v3` on 4.5, `grease_pencils` on 5.x | [`grease-pencil-rosette`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/grease-pencil-rosette) |
| `bpy.ops.x.y(context_dict, ...)`, `bpy.context.copy()` override | removed 4.0 | `TypeError` | `with bpy.context.temp_override(...)` | rule [`prefer-temp-override-over-context-copy`](${CLAUDE_PLUGIN_ROOT}/rules/prefer-temp-override-over-context-copy.mdc) |
| `bl_info` only, no `blender_manifest.toml` | Extensions Platform 4.2 | not installable as an extension (`validate`: manifest not found) | add a manifest; keep `bl_info` beside it if pre-4.2 matters | [`bl-info-migration`](${CLAUDE_PLUGIN_ROOT}/skills/bl-info-migration/SKILL.md), [`addon-register-lifecycle`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/addon-register-lifecycle) |
| hard-coded add-on module name in `preferences.addons["my_addon"]` | extensions 4.2 | `KeyError`: the module is `bl_ext.<repo>.my_addon` | `__package__` | [`extension-runtime-and-packaging`](${CLAUDE_PLUGIN_ROOT}/skills/extension-runtime-and-packaging/SKILL.md) |
| COLOR strip transform scale after a resolution change | 5.2 | *silent*: `width`/`height` are baked from the scene resolution | *branch*: set `width`/`height` on 5.2+ | [`vse-python`](${CLAUDE_PLUGIN_ROOT}/skills/vse-python/SKILL.md) |
| `evaluated_get(dg).data.name != obj.data.name` as an "is evaluated" test | 5.2 | *silent*: names are equal on 5.2 | track where the mesh came from, not its name | [`eval-mesh-datablock-name`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/eval-mesh-datablock-name) |
| GPU drawing under `--background` | new in 5.2 | `SystemError` on 5.1 and older | 5.2+: `gpu.init()` first | [`gpu-offscreen-draw`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/gpu-offscreen-draw) |

## The dual-version shim

Keep one code path and branch only where the table says *branch*:

```python
import bpy

IS_5 = bpy.app.version >= (5, 0, 0)

if IS_5:
    from bpy_extras.anim_utils import action_ensure_channelbag_for_slot

def eevee_id():
    return "BLENDER_EEVEE" if IS_5 else "BLENDER_EEVEE_NEXT"

def strips(se):
    return se.strips  # present on 4.5 too: no branch needed
```

Prefer the replacement that works on both versions when one exists (`.strips`, attribute access for properties, `temp_override`, `corner_normals`, `gpu.state`). Branch only for real splits. Never probe with `hasattr(action, "slots")` to tell 4.5 from 5.x: `slots` exists on both. The `version-branch-skeleton.py` snippet has the pattern: [`snippets/version-branch-skeleton.py`](${CLAUDE_PLUGIN_ROOT}/snippets/version-branch-skeleton.py).

## Common AI mistakes

| Mistake | Instead |
| --- | --- |
| Fixing only the first traceback and declaring the port done | Re-run until clean, then grep for the *silent* rows |
| `try: import bgl` fallbacks kept "for 4.5" | `gpu` works on 4.5 too; delete `bgl` entirely |
| Branching on `bpy.app.version_string` | Compare the `bpy.app.version` tuple |
| Porting by renaming attributes from memory | Load the owning skill; several renames also changed types (`Specular Tint` is now a color) |
| Dropping 4.5 support by accident | Run the smoke on both LTS lines before calling it done |

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`compositor-glare`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/compositor-glare): Bloom where it actually lives — a compositor Glare (Fog Glow) node fed by Render Layers. Falsify: `--threshold-high` (exit 4).
- [`cross-version-property-delete`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/cross-version-property-delete): Custom ID properties are removed with del, not property_unset. Falsify: `--skip-delete` (exit 7).
- [`eval-mesh-datablock-name`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/eval-mesh-datablock-name): Pathology witness for the 5.2 change in `Object.evaluated_get(depsgraph).data.name`. Falsify: `--assume-distinct-names` (exit 6).
- [`gpu-offscreen-draw`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/gpu-offscreen-draw): Check-only witness for drawing with the `gpu` module, the replacement for the `bgl` module that 5.x removed. Blender 5.2+. Falsify: `--skip-blend` (exit 5).
- [`grease-pencil-rosette`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/grease-pencil-rosette): Grease Pencil v3's attribute-based API — layer → frames.new(1).drawing → add_strokes → per-point position/radius/opacity/vertex_color — drawing five nested neon rose curves. Falsify: `--open-strokes` (exit 5).
- [`mesh-normals-after-41`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.158.0/examples/mesh-normals-after-41): Check-only witness for the normals API that replaced auto smooth in Blender 4.1, on 4.5 LTS and 5.x alike. Falsify: `--legacy-api` (exit 3).

<!-- examples:end -->
