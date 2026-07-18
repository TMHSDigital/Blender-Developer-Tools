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

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python text_version_stamp.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python text_version_stamp.py -- --output stamp.png
blender --background --python text_version_stamp.py -- --output stamp.png --engine cycles
```

It exits non-zero on failure (wrong subclass, missing font, body/version mismatch,
non-planar flat text, extrude/bevel closed form off, geometry not regenerating, or a
`to_mesh_clear()` reference surviving). The `blender-smoke` workflow runs the check on
Blender 4.5 LTS and 5.1. The render scales the stamp to a constant width, so the frame
holds for any version-string length.
