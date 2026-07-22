# Custom Normals + Shade by Angle

A runnable example that builds a jerry can prop — rounded-slab shell,
pressed X ribs, spout and cap, three-post handle — and verifies the shading
contract a game prop's silhouette depends on: which edges read hard and
which read smooth is mesh DATA, carried since Blender 4.1 by face smooth
flags plus a `sharp_edge` attribute,
following [`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md).

**Pipeline arc neighbor:** collision in
[`collision-hull-proxy`](../collision-hull-proxy/) (the pair partner — same
prop-pipeline audience), tangent space in
[`triangulate-tangents`](../triangulate-tangents/) — normal maps are baked
against exactly this shading, and engines harden or soften the same edges
at ingest.

**Scope:** this witnesses the bpy-level contract a prop pipeline relies on.
It is not an engine exporter and does not claim engine/FiveM compatibility
— it proves the mesh-data properties such an asset's shading must have.

**What it witnesses:**

- **The legacy shading API is gone — on both supported versions.**
  `use_auto_smooth`, `use_custom_normals`, and `calc_normals` are
  AttributeError on 4.5 LTS *and* 5.1. AI-generated Blender code still
  emits `mesh.use_auto_smooth = True` constantly; any script carrying that
  habit dies immediately, and this check keeps it dead.
- **Shade-by-angle is exact.** `mesh.set_sharp_from_angle(30°)` (which also
  sets the face smooth flags — probed on both versions) marks sharp exactly
  the edges whose *independently recomputed* dihedral angle crosses the
  threshold: Shell 48 of 72 edges, rib 12 of 12, neck 128 of 304 — an exact
  set match, not a count approximation.
- **The evaluated shading matches the attribute's promise.** Through
  depsgraph evaluation, loop normals across a smooth edge are welded
  (deviation 0.0, tol 1e-3) and loop normals across a sharp edge carry
  their face normals split by exactly the dihedral (angle error 0.0 rad,
  tol 5e-3), all unit length (err 5.6e-08).
- **Custom split normals survive depsgraph evaluation** — with a
  quantization budget, not float precision: `normals_split_custom_set`
  stores per-loop normals in int16, so a 144-loop round-trip reads back
  within **1.407e-04** (tol 2e-4), unit length within 1.1e-07. Asserting
  float-exact custom normals is a real bug this check catches.
- **The divergence: the legacy `shade_auto_smooth` OPERATOR is a
  version-split trap.** It builds the Smooth-by-Angle node-group modifier
  from a bundled asset. Headless on **4.5 LTS the asset load never
  finishes**: the op returns `{'CANCELLED'}` — no exception — and the mesh
  stays **untouched** (measured: 0 smooth faces, 0 modifiers). Any script
  that ignores the return set ships flat shading and never knows. On
  **5.1** it FINISHES and adds the `Smooth by Angle` NODES modifier. The
  portable path is the data API above, version-gated here explicitly.

**What each check catches on failure:** author/audit threshold drift
(probe: sharp marks applied at 20° but audited at 30°, exit 5, 4 extra
edges); the two halves of the contract out of sync (probe: `sharp_edge`
set but face smooth flags lost, exit 6, smooth-edge loops split by
3.83e-01); float-exactness assumed of custom normals (probe: tolerance
1e-6, exit 7, measured 1.407e-04); and any future version that resurrects
the legacy API or changes the operator's headless behavior (exit 3/8).

**Version witness:** every value above is identical on Blender 4.5.11 LTS
and 5.1.2 except the `shade_auto_smooth` operator behavior, which is
asserted per version (CANCELLED + untouched on 4.5, FINISHED + NODES
modifier on 5.1).

The render shows the same can shaded three ways — flat (faceted corners),
smooth-everywhere (the smeared AI bug: ribs melt, highlights warp at the
rim), and by-angle (the contract: smooth walls, crisp edges) — under a
strip light whose reflection exposes every normal discontinuity.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python custom_normals_shade.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python custom_normals_shade.py -- --output cans.png
blender --background --python custom_normals_shade.py -- --output cans.png --engine cycles
```

It exits non-zero on failure (legacy API resurrected, sharp-set/dihedral
mismatch, broken normal welds, custom normals lost or dequantized in
evaluation, or legacy-operator divergence drift). The `blender-smoke`
workflow runs the check on Blender 4.5 LTS and 5.1.
