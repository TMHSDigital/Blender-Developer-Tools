# N-gon triangulate

Synthesizes one hexagon by dissolving a cube edge, then asserts the
hygiene / tangent contracts on that defective mesh. Inverse of
[`mesh-hygiene-audit`](../mesh-hygiene-audit/) (clean mesh, no ngons)
and neighbor of [`triangulate-tangents`](../triangulate-tangents/)
(`calc_tangents` aborts on any n-gon).

**Why this pathology:** the audit's n-gon gate is a snapshot on clean
geometry. AI-generated meshes often leave dissolved n-gons; glTF
silently triangulates, so an export-only check is vacuous (12 tris
either way).

**Pre-assertion (pathology exists):** exactly **1** face with **6**
loops, **5** faces total. `--no-dissolve` exits 3.

**Handling (second axis):** `Mesh.calc_tangents` aborts with
`tris/quads` until `bmesh.ops.triangulate` on that face; afterward
**4** tris + **4** quads, **28** loops, tangents succeed. Count-only
glTF tris = 12 for a cube *or* this mesh. `--skip-triangulate` exits 4.

No gallery still. A hexagon on a cube does not read at thumbnail
without fake annotation.

## Run

```bash
blender --background --python ngon_triangulate.py --
blender --background --python ngon_triangulate.py -- --no-dissolve
blender --background --python ngon_triangulate.py -- --skip-triangulate
```
