# Lattice Deform

A runnable example that deforms a subdivided column with a **2×2×2 lattice** set to
`'KEY_LINEAR'` interpolation on all three axes, then proves, vertex by vertex, that the
Lattice modifier's output is exactly the **trilinear interpolation** of the eight deformed
control points. The deformed mesh is read through the depsgraph lifetime contract from
[`depsgraph-and-evaluated-data`](../../skills/depsgraph-and-evaluated-data/SKILL.md)
(`evaluated_get` → `to_mesh` → `to_mesh_clear`), and the lattice points are edited the way
[`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md) recommends for
data-level work: through `bpy.data`, never `bpy.ops`.

**What it witnesses:** `LatticePoint.co` is the read-only rest position and
`LatticePoint.co_deform` is the one you move. With linear interpolation a vertex at
normalized rest coordinates (u, v, w) inside the lattice lands on
Σ wᵢ · `co_deform`ᵢ with wᵢ = (u or 1−u)(v or 1−v)(w or 1−w), mapped through the lattice
object's matrix. The check computes that closed form independently for all 602 vertices,
through a lattice object that is translated and non-uniformly scaled (1.7 × 1.7 × 2.4),
and requires agreement to 1e-5 in world space (measured: 5.6e-7). It also asserts the
undeformed lattice is the identity and that the deformation is not trivially small
(max displacement 0.53).

**The trap it exposes:** a new lattice defaults to `'KEY_BSPLINE'`. B-spline weights
smooth over the control points instead of interpolating them, so a script that moves a
corner and expects the mesh to follow it linearly gets a softer, smaller pull. On a
2×2×2 lattice the rest state is still the identity, so nothing looks wrong until a
point moves. `--bspline` keeps the default and fails check 4 with the measured error.

The still shows the rule as a before-and-after on a walnut plinth: on the left a
render-only twin of the column, undeformed, inside its rest cage; on the right the
checked column inside the deformed cage, with the two moved corners in selection orange
and a short orange rod from each back to its rest position. The column carries a glazed
two-tone checker in Generated (rest) coordinates, so the squares are square before the
lattice acts, and their shear and taper in the still are the deformation. Lattices do
not render, so both cages are drawn as thin steel rods built from the corner positions
after the check has run.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python lattice_deform.py --

# Falsifier: keep the default KEY_BSPLINE interpolation. Must exit 4.
blender --background --python lattice_deform.py -- --bspline

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python lattice_deform.py -- --output lattice.png --engine cycles
```

## Version notes

The Lattice datablock API (`points_u/v/w`, `interpolation_type_u/v/w`, `points[i].co` /
`co_deform`, point order u fastest, then v, then w) and the `'LATTICE'` modifier are the
same on 4.5 LTS, 5.1 and 5.2 LTS. Measured identically on 4.5.11, 5.1.2 and 5.2.1:
602 vertices, trilinear max error 5.6e-7, max displacement 0.5311; `--bspline` max error
0.2145.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Undeformed lattice moved the mesh (identity check) |
| 4 | A vertex is off the trilinear closed form, or the vertex count changed (`--bspline` lands here) |
| 5 | Max displacement below the floor (the witness would pass vacuously) |
| 6 | `--output` produced no file |
| 10 | `--output` framing violation (Layer 1 fill / margin gate, `gallery_framing`) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`. Its catalog falsifier is `--bspline` (expects exit 4).
