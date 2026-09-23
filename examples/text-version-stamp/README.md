# Text Version Stamp

A runnable example that builds a beveled 3D stamp of the running Blender version — a
`TextCurve` (`bpy.data.curves.new(type='FONT')`) whose `body` is the live
`bpy.app.version_string`, so every render self-documents which Blender produced it.
CI artifacts made this way are self-labeling.

**What it witnesses:** the TextCurve data-API contract. `curves.new(type='FONT')`
returns a Curve subclass, the built-in font ("Bfont Regular") is always loaded even
headless, `body` is plain assignable text that regenerates geometry on edit (more
characters → strictly wider evaluated mesh), and `extrude` / `bevel_depth` produce
exactly predictable solids: the evaluated mesh z-extent equals 2 × (extrude +
bevel_depth) and the round bevel widens the outline in-plane by 2 × bevel_depth.
Flat text (no extrude, no bevel) is already *filled* — faces exist — but strictly
planar. The check also witnesses the depsgraph lifetime hazard: after
`to_mesh_clear()` the returned Mesh reference is dead and any access raises
`ReferenceError`.

**Version divergence:** the string format itself differs — `"5.1.2"` on 5.x but
`"4.5.11 LTS"` on 4.5 (the suffix is part of `version_string`). The check therefore
asserts the contract that holds on both: `version_string` starts with the dotted
`bpy.app.version` tuple. Code that parses `version_string` as a bare semver breaks
on every LTS build; branch on the `bpy.app.version` tuple instead.

## Staging

The numerals stand on a dark plinth, with the steel caption set into the
plinth's front face. The caption used to float in the air above the
stamp, and an emissive bar lay along the bottom edge of the frame. The
still renders under the Standard view transform on the house stage.
Render path only; the checked text body and its extents are unchanged.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python text_version_stamp.py --

# Falsifier: body is not version_string. Must exit non-zero.
blender --background --python text_version_stamp.py -- --wrong-body

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python text_version_stamp.py -- --output stamp.png
blender --background --python text_version_stamp.py -- --output stamp.png --engine cycles
```

The render scales the stamp to a constant width, so the frame holds for any
version-string length.

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Not a FONT `TextCurve` with the built-in Bfont |
| 4 | `body` is not the live `version_string` (`--wrong-body` lands here) |
| 5 | Flat text is not a filled planar mesh |
| 6 | Extrude / bevel closed form failed |
| 7 | Appending characters did not widen the text |
| 8 | Mesh survived `to_mesh_clear()` |
| 9 | `--output` produced no file |
| 10 | Gallery framing violation |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--wrong-body`.
