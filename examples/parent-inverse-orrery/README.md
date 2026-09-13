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

# Falsifier: parent without MPI. Must exit non-zero (orbit closed form).
blender --background --python parent_inverse_orrery.py -- --skip-mpi

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python parent_inverse_orrery.py -- --output orrery.png
blender --background --python parent_inverse_orrery.py -- --output orrery.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Bare parenting did not jump |
| 4 | Keep-world idiom off |
| 5 | Stale `matrix_world` contract broken |
| 6 | Planet off closed-form orbit (`--skip-mpi` lands here) |
| 7 | Moon off closed-form orbit |
| 8 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--skip-mpi`.

