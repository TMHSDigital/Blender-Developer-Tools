# Driver Wave

A runnable example that drives sixteen column heights from a custom function registered in
`bpy.app.driver_namespace` — the pattern from
[`drivers-and-app-handlers`](../../skills/drivers-and-app-handlers/SKILL.md). Each column
gets a SCRIPTED driver on Z scale whose expression calls `wave_scale(i)`, producing a sine
skyline.

**What it witnesses:** the driver evaluation contract. Driven values appear only after a
view-layer update, and they land in **two** places that must agree: the depsgraph-evaluated
copy (`evaluated_get(dg).scale`) and the original datablock, which the animation system
flushes for display. The check asserts both against the closed-form profile.

Note for real add-ons: `driver_namespace` entries do **not** persist in `.blend` files —
re-register them from a `load_post` handler, or every driver that calls them fails on file
open. Headless, registering before driver creation (as here) is enough.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python driver_wave.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python driver_wave.py -- --output driver.png
blender --background --python driver_wave.py -- --output driver.png --engine cycles
```

It exits non-zero on failure (driven value wrong, or the flush-back disagreed). The
`blender-smoke` workflow runs the check on Blender 4.5 LTS and 5.1.
