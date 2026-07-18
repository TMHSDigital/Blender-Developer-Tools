# Parent Inverse Orrery

A runnable example that assembles a brass orrery — sun, three planets on pivot arms, one
moon — entirely through the data API, witnessing the parenting contract that generated
Blender code gets wrong most often. `child.parent = pivot` alone re-interprets the child's
local matrix in the pivot's space and the child visibly teleports; keeping the world
transform takes the two-line idiom:

```python
child.parent = pivot
child.matrix_parent_inverse = pivot.matrix_world.inverted()
```

**What it witnesses:** the check first proves the trap is real (a bare-parented probe
jumps by more than half a unit), then that the idiom restores the probe's world position
to within 1e-5. It also asserts the second half of the contract — `matrix_world` is the
*last-evaluated* matrix, stale after any transform edit until
`bpy.context.view_layer.update()` — and finally that every planet and the two-level moon
land exactly on their closed-form orbit positions after the pivots spin.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python parent_inverse_orrery.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python parent_inverse_orrery.py -- --output orrery.png
blender --background --python parent_inverse_orrery.py -- --output orrery.png --engine cycles
```

It exits non-zero on failure (no jump from the trap, keep-world error, stale-matrix
contract broken, or an orbit off its closed form). The `blender-smoke` workflow runs the
check on Blender 4.5 LTS and 5.1.
