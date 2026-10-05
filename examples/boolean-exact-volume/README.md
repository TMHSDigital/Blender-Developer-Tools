# Boolean Exact Volume

A runnable example that cuts a 2 m cube with a 2 × 1 × 1 m slab using the **Boolean
modifier on the EXACT solver**, in all three operations (UNION, DIFFERENCE, INTERSECT),
then proves that each result has the **closed-form volume** and is a **closed
2-manifold**. The hard part is deliberate: the slab's top face lies in the cube's top
plane, the coplanar case where floating-point booleans go wrong. The results are read
through the depsgraph lifetime contract from
[`depsgraph-and-evaluated-data`](../../skills/depsgraph-and-evaluated-data/SKILL.md)
(`evaluated_get` → `to_mesh` → `to_mesh_clear`), and the operands are built with bmesh
and freed in `try`/`finally` as
[`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md) requires.

**What it witnesses:** with A = [0,2]³ and B = [1,3] × [0.5,1.5] × [1,2], the overlap is
A ∩ B = [1,2] × [0.5,1.5] × [1,2], so the closed forms are V(A ∪ B) = 8 + 2 − 1 = 9,
V(A − B) = 8 − 1 = 7 and V(A ∩ B) = 1 cubic metre. Each operand pair sits in an object
matrix that is translated and turned 18° about Z, so the modifier has to carry B into A's
space. For every result the check:

- sums the signed volume over the evaluated mesh's own triangles (divergence theorem,
  world space) and requires the closed form to 1e-6 relative (measured 8.999999,
  6.999999 and 1.000000 — float32 coordinates through a rotation). A positive volume
  also means the normals point outward;
- requires a closed 2-manifold: every edge borders exactly two faces, with no loose verts
  or edges;
- requires that the result's volume differs from V(A) by at least 0.5 m³, so the
  modifier really acted and the witness cannot pass vacuously.

**The trap it exposes:** the floating-point solver is faster and is right in general
position, but it mishandles coplanar faces. `--float-solver` runs the same three
operations on it and gets a union of 7.708 m³ against the closed form 9, so check 3
fails with the measured error. That solver was `'FAST'` through 4.5 LTS and is `'FLOAT'`
from 5.0, so a script that hard-codes either name breaks on the other series
(`fast_solver_id()` branches on `bpy.app.version`). `'EXACT'` is the same identifier on
4.5, 5.1 and 5.2.

The still shows the three operations side by side on a walnut plinth, each named by a
brass plaque in front of it. On the left, the union in teal glaze, with the slab's free
end grown out of the cube. In the middle, the difference in machined bronze, with the
notch cut down through the top face and the removed slab drawn as frosted amber glass.
On the right, the intersection: the 1 m³ overlap cube in orange glaze, inside frosted
ghosts of both operands. Thin rods trace the operands' edges (steel for the cube, amber
for the coplanar slab).

Everything shown is render-only and is built after the check has run. The results on
display are frozen copies of the checked meshes with a 12 mm chamfer; the measured
modifier objects and the cutter objects never render. The ghosts are grown 2 mm and
4 mm so none of their faces is coplanar with a result or with each other.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python boolean_exact_volume.py --

# Falsifier: the floating-point solver (FLOAT / FAST) on the coplanar case. Must exit 3.
blender --background --python boolean_exact_volume.py -- --float-solver

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python boolean_exact_volume.py -- --output boolean.png --engine cycles
```

## Version notes

`BooleanModifier.solver` lists `'FAST'`, `'EXACT'`, `'MANIFOLD'` on 4.5 LTS and
`'FLOAT'`, `'EXACT'`, `'MANIFOLD'` on 5.1 and 5.2 LTS: the floating-point solver was
renamed in 5.0. Measured identically on 4.5.11, 5.1.2 and 5.2.1: EXACT union 8.999999
(12 faces), difference 6.999999 (10 faces), intersection 1.000000 (6 faces), all closed
2-manifolds; `--float-solver` union 7.708379.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | A result's volume is off its closed form (`--float-solver` lands here) |
| 4 | A result is not a closed 2-manifold (an edge without exactly two faces, or loose geometry) |
| 5 | A result's volume is within 0.5 m³ of operand A's (the witness would pass vacuously) |
| 6 | `--output` produced no file |
| 10 | `--output` framing violation (Layer 1 fill / margin gate, `gallery_framing`) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`. Its catalog falsifier is `--float-solver` (expects exit 3).
