# Ray Cast Space

A runnable example of the coordinate-space contract behind Blender's two ray casts, the
one AI-written code gets wrong most often. `Scene.ray_cast(depsgraph, origin, direction)`
takes and returns **world** space. `Object.ray_cast(origin, direction)` takes and returns
the object's **local** space. Feed world coordinates to `Object.ray_cast` and nothing
raises: it quietly misses, or hits the wrong spot.

**What it witnesses:** a target block carries a transform with every ingredient that
separates the two spaces: a translation, a 32° turn about Z, and non-uniform scale
(1.55 × 0.62 × 0.62). The example casts five rays at closed-form points on three of its
faces, arriving obliquely, and checks each one three ways:

1. **`Scene.ray_cast`** hits the closed-form world point (to 1e-4 m). Its normal matches
   the face's world normal, which comes from the inverse-transpose of `matrix_world`.
2. **`Object.ray_cast`** is fed the origin through `matrix_world.inverted()` and the
   direction through that matrix's 3×3 part only, because directions do not translate.
   It must hit the same polygon. Its local hit point, mapped back through `matrix_world`
   (and its normal through the inverse-transpose), must land on the same world point and
   normal.
3. **The trap must bite on this setup.** The same world origin and direction handed
   straight to `Object.ray_cast` either misses or lands at least 0.25 m from the true
   hit. Without this, the check could pass by coincidence.

Both 5.2 LTS and 4.5 LTS give identical results: every hit exact to under 1e-6 m, and
the world-coordinate trap's closest landing 0.287 m away.

The still shows the block glazed in a teal checker laid out in **object** coordinates.
The cells are square in local space, so the non-uniform scale stretches them into the
block's own grid. The block stands on a walnut plinth. Five orange rays run from brass
emitter balls to orange hit rings that sit exactly on three faces: the correct casts.
One red ray is the first front-face ray's world origin and direction read by
`Object.ray_cast` as if local. In the world that is the ray `matrix_world @ origin`
along `matrix_world.to_3x3() @ direction`. It starts somewhere else entirely and
strikes the far side of the block. A render-only Bevel modifier rounds the block's
edges after the check has run.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python ray_cast_space.py --

# Falsifier: feed WORLD coords to Object.ray_cast in the checked path. Must exit 4.
blender --background --python ray_cast_space.py -- --world-to-object

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python ray_cast_space.py -- --output ray.png
blender --background --python ray_cast_space.py -- --output ray.png --engine cycles
```

`--world-to-object` measured on 5.2.1 and 4.5.11:
`Object.ray_cast ray 0 mapped back to (1.5668, 1.22769, 1.38161), error 1.1253 m
(normal error 1.0000, polygon 2 vs Scene 3)`. The cast hit a different face of the
block, a metre from the true point.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | `Scene.ray_cast` missed, hit another object, or hit off the closed-form world point or normal |
| 4 | `Object.ray_cast` missed, or its local hit mapped back by `matrix_world` disagrees with the world point, normal or polygon (`--world-to-object` lands here) |
| 5 | The world-coordinate trap did not bite: world coords fed to `Object.ray_cast` landed within `TRAP_MIN` of a true hit |
| 6 | `--output` produced no file |
| 10 | `--output` framing violation (Layer 1 fill / margin gate, `gallery_framing`) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--world-to-object`.
