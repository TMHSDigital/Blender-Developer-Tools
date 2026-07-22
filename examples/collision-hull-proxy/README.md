# Collision Hull Proxy

A runnable example that builds a fire hydrant street prop — lathed barrel,
bonnet dome, three outlet caps, operating nut — plus the collision a game
prop pipeline ingests: a **compound of four convex hull pieces**, one per
part group, each built with `bmesh.ops.convex_hull` from a coarse collision
cage, following [`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md).

**Pipeline arc neighbor:** LODs in
[`lod-decimate-chain`](../lod-decimate-chain/), tangent space in
[`triangulate-tangents`](../triangulate-tangents/), export in
[`gltf-export-roundtrip`](../gltf-export-roundtrip/) — collision bounds are
the piece an engine's physics ingest checks first, and the piece whose
failure rejects the whole prop.

**Scope:** this witnesses the bpy-level contract a prop pipeline relies on
(watertight convex pieces that enclose the render mesh within budget). It is
not an engine exporter and does not produce a shippable FiveM/engine asset —
it proves the geometry properties such an asset must have.

**What it witnesses:** engines (GTA/FiveM-style prop workflows included)
ingest collision as a *compound of convex pieces*, each piece under a
per-piece face limit (255 is the common cap). The example builds that
structure and derives every property from closed forms, per piece:

- **Containment.** Every render-mesh vertex lies on the inner side of every
  face plane of its piece's hull — max excursion **4.4e-08** (tol 2e-4). This
  holds by construction, not luck: the cage is a coarse lathe whose rings are
  inflated by `sec(π/n)`, so each n-gon cage ring *circumscribes* its render
  ring exactly. Proud details (a rim, a nut) must be paid for in cage rows;
  concave details (the grooves) are free — the hull bridges over them. That
  trade-off is the collision-authoring lesson.
- **Convexity.** The same plane test restricted to the hull's own vertices
  (4.8e-08) — what a convex solver assumes when it uploads the piece.
- **Watertight + manifold.** Every hull edge borders exactly two faces, and
  V − E + F = 2: a convex hull is a topological sphere.
- **Outward winding.** Positive signed volume by the divergence theorem
  (body piece 1.022381) — inverted collision is a physics no-op.
- **Budget.** Every piece ≤ 255 faces: body 70, pumper 60, side caps 60+60;
  the compound totals 250. The naive approach fails this — a hull of the
  *dense render mesh* measures **380 faces**, over budget, which is why real
  pipelines hull a cage, never the render mesh.

**What each check catches on failure:** an artist editing the render mesh
after the hull was generated (probe: pumper lug stretched 2×, exit 3,
measured escape 0.730000); inverted hull winding (probe: polygons flipped,
exit 5, signed volume −1.022381, the exact negation); a non-watertight piece
(probe: one face deleted, exit 4, three border edges).

**Version witness:** output is byte-identical on Blender 4.5.11 LTS and
5.1.2 — same piece counts, same volumes, same excursions.
`bmesh.ops.convex_hull` and `foreach_get` are stable across the pair.

The render shows the prop inside its four faceted translucent hull pieces:
if any piece failed to enclose its geometry, painted metal would poke
through the shell in frame.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python collision_hull_proxy.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python collision_hull_proxy.py -- --output hydrant.png
blender --background --python collision_hull_proxy.py -- --output hydrant.png --engine cycles
```

It exits non-zero on failure (render geometry escaping a hull, inverted
winding, a non-watertight or non-convex piece, Euler drift, or a piece over
the 255-face budget). The `blender-smoke` workflow runs the check on
Blender 4.5 LTS and 5.1.
