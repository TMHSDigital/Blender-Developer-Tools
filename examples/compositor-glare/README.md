# Compositor Glare

A runnable example that puts bloom where it actually lives: the compositor. Three
emissive rings are rendered, then a `Glare` (Fog Glow) node fed by `Render Layers`
grows the halo — wired through `scene.compositing_node_group` on Blender 5.x and
through `scene.node_tree` on 4.x, because the 5.0 compositor rewrite removed the
scene-level tree entirely (`scene.use_nodes = True` now raises `AttributeError`).

The Glare node changed shape with it: on 4.x it takes legacy enum properties
(`glare_type='FOG_GLOW'`, `quality='HIGH'`, `size=6`), while on 5.x the same
choices are menu/float **input sockets** (`inputs['Type'].default_value =
'Fog Glow'`). The 4.x `threshold` property is a dead shim — the real threshold
is the `Threshold` input socket on both versions. And EEVEE has no `use_bloom`
toggle on either version (removed in 4.2): bloom is a compositor node, period.

**What it witnesses:** the halo is the compositor's output, proven with pixels.
The check renders the scene twice at 96×54 (single-sample Cycles, noise-free) —
once with `use_compositing` on, once off — and samples a column of pixels above
the middle ring's silhouette via `world_to_camera_view`. With the compositor on,
the halo luminance just outside the silhouette is far above zero and falls off
strictly with distance (the Fog Glow kernel signature); with it off, those same
pixels are exactly zero. The structural check pins the wiring
(`Render Layers → Glare → output`), the version-correct tree plumbing, and the
absence of any EEVEE bloom toggle.

## Run

```bash
# Cheap correctness check (two tiny renders) — the CI check:
blender --background --python compositor_glare.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python compositor_glare.py -- --output rings.png
blender --background --python compositor_glare.py -- --output rings.png --engine cycles
```

It exits non-zero on failure (wrong tree plumbing, wrong Glare configuration, a
missing or non-falling halo, or halo pixels that appear without the compositor).
The `blender-smoke` workflow runs the check on Blender 4.5 LTS and 5.1.
