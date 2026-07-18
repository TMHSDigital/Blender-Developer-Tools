# Grease Pencil Rosette

A runnable example that draws five nested neon rose curves as Grease Pencil v3 strokes —
layer → `frames.new(1).drawing` → `add_strokes([counts])` → per-point `position`, `radius`,
`opacity`, `vertex_color` — the attribute-based API that replaced legacy GPencil across the
4.x-to-5.x window, the largest bpy API break the gallery witnesses.

**What it witnesses:** GPv3 lives at *different addresses* on the two supported versions,
and the check asserts each side's actual contract:

- **Blender 4.5 LTS** — GPv3 is `bpy.data.grease_pencils_v3` (`GreasePencilv3`), while
  `bpy.data.grease_pencils` still holds **legacy** GPencil whose frames carry `.strokes`
  directly and have no `.drawing`. Same collection name, incompatible API — the trap is
  asserted, not just avoided.
- **Blender 5.x** — legacy is gone: GPv3 took over the `bpy.data.grease_pencils` name, and
  `grease_pencils_v3` / `bpy.types.GPencilStroke` no longer exist.

On the shared GPv3 surface it then asserts that stroke points are *views over attribute
layers*: writing `pt.radius` / `pt.opacity` / `pt.vertex_color` lazily materializes
`radius`, `opacity`, `vertex_color` (POINT) and `cyclic` (CURVE) layers in
`drawing.attributes`, and every closed-form rose position round-trips exactly through the
raw `position` attribute buffer via `foreach_get`.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python grease_pencil_rosette.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python grease_pencil_rosette.py -- --output rosette.png
blender --background --python grease_pencil_rosette.py -- --output rosette.png --engine cycles
```

It exits non-zero on failure (wrong version gate, structural mismatch, missing attribute
layers, or attribute-buffer deviation from the closed form). The `blender-smoke` workflow
runs the check on Blender 4.5 LTS and 5.1.
