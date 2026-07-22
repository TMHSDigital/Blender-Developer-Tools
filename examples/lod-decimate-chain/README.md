# LOD Decimate Chain

A runnable example that builds a retro toy rocket — a lathed body with an ogive
nose, three swept fin plates, a porthole, every dimension a closed form — and
evaluates it at LOD0/1/2 through the Decimate modifier via the depsgraph,
following [`depsgraph-and-evaluated-data`](../../skills/depsgraph-and-evaluated-data/SKILL.md)
and [`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md).

**Pipeline arc:** modeling/LOD here, weighting in
[`vertex-weight-limit`](../vertex-weight-limit/), export in
[`gltf-export-roundtrip`](../gltf-export-roundtrip/).

**What it witnesses:** the modifier-based LOD contract that game asset pipelines
rely on.

- **Decimate is non-destructive and lives in the depsgraph.** The evaluated
  mesh carries the reduction; the original datablock is byte-identical before
  and after evaluation. The check proves both — evaluated counts drop while
  `obj.data` keeps the closed-form counts (1,147 verts / 2,260 tris) — and
  every evaluated reference is released with `to_mesh_clear()`. An LOD chain
  that bakes the reduction into `obj.data` destroys the asset's LOD0.
- **The COLLAPSE ratio is a target, not a guarantee.** Each LOD's evaluated
  triangle count must land within 5% of `ratio x base_tris` — measured 0.00%
  at ratio 0.5 (1,130 tris) and 0.44% at ratio 0.18 (405 tris). A stacked
  second Decimate halves the effective ratio (50% excursion, caught); a
  dropped modifier leaves evaluated == original (caught).
- **LODs preserve silhouette-critical dimensions.** Height (3.12) and fin
  span are the rocket's readability; the evaluated bbox holds the base bbox
  within 1e-3 at every level (measured 7.7e-6). Decimate has no vertex
  pinning, so this is a real risk, not a formality: at an aggressive ratio
  0.02 the nose tip collapses (bbox drift 0.0206, caught).

The Decimate modifier API (`decimate_type='COLLAPSE'`, `ratio`) is stable
between Blender 4.5 LTS and 5.1 — the example runs identically on both, which
is itself the version witness (measured values match to the digit).

The render stages the three LODs in a row: LOD0's smooth lathe, LOD1's nearly
free halving, LOD2's visible crunch — the porthole degrades to a hexagon and
the nose facets coarsen, exactly the geometry the triangle counts assert.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python lod_decimate_chain.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python lod_decimate_chain.py -- --output rocket.png
blender --background --python lod_decimate_chain.py -- --output rocket.png --engine cycles
```

It exits non-zero on failure (base-topology drift, no reduction, a mutated
original datablock, a ratio-bounds excursion, or silhouette loss). The
`blender-smoke` workflow runs the check on Blender 4.5 LTS and 5.1.
