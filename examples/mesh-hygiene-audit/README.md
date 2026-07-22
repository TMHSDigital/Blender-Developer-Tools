# Mesh Hygiene Audit

A runnable example that builds a fabricated street electrical pedestal —
stepped plinth, cabinet waist, drip-cap overhang — and runs the
**engine-ingest mesh hygiene checklist** as executable topology checks,
following [`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md).

**Pipeline arc neighbors:** watertight / Euler on collision *hulls* in
[`collision-hull-proxy`](../collision-hull-proxy/), parametric closed solids
in [`bmesh-gear`](../bmesh-gear/), LOD face budgets in
[`lod-decimate-chain`](../lod-decimate-chain/), and join context in
[`temp-override-join`](../temp-override-join/). Hygiene is the gate a prop
pipeline runs on the *render* mesh before hull / LOD / export.

**Scope:** this witnesses the bpy-level contract a prop pipeline relies on
(tris+quads, no loose verts, manifold edges, no zero-area faces, outward
winding, Euler 2 for a closed solid). It is not an engine exporter and does
not produce a shippable engine asset — it proves the topology properties
such an asset must have.

**What it witnesses:** every gate is derived from mesh combinatorics or the
divergence-theorem volume — never from a prior-run capture:

- **No ngons.** `len(poly.vertices) <= 4` for every face.
- **No loose vertices.** Every vert has degree ≥ 1.
- **Manifold edges.** Every edge borders exactly 2 faces (closed solid).
- **No zero-area faces.** Face area > 1e-10; prints measured `min_area`.
- **Outward winding.** Positive signed volume (divergence theorem).
- **Euler sphere.** `V − E + F == 2` for the clean closed manifold
  (measured: verts=24 edges=44 faces=22, volume≈0.989248).

**What each check catches on failure:** loose vert injected (exit 4);
face deleted → boundary edges (exit 5); edge dissolved → ngon (exit 3);
all faces flipped → signed volume negated (exit 7); face collapsed →
zero-area (exit 6).

**Version witness:** output is byte-identical on Blender 4.5.11 LTS and
5.1.2 — same counts, same volume, same `min_area`. The bmesh edge/face
incidence and polygon vertex-count APIs are stable across the pair.

The render is a dual panel: left **DIRTY** (boundary hole + loose-vert bead,
emissive hazard + wireframe) vs right **CLEAN** manifold. Failure = identical
panels or missing defect cues.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python mesh_hygiene_audit.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python mesh_hygiene_audit.py -- --output hygiene.png
blender --background --python mesh_hygiene_audit.py -- --output hygiene.png --engine cycles
```

It exits non-zero on failure (ngons, loose verts, non-manifold edges,
zero-area faces, inverted winding, or Euler ≠ 2). The `blender-smoke`
workflow runs the check on Blender 4.5 LTS and 5.1.
