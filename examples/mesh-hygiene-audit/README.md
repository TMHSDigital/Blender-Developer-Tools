# Mesh Hygiene Audit

A runnable example that builds an octagonal street valve body and runs the
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
winding, Euler 2 for a closed solid). It is not an engine exporter.

**What it witnesses:** every gate is derived from mesh combinatorics or the
divergence-theorem volume — never from a prior-run capture:

- **No ngons.** `len(poly.vertices) <= 4` for every face.
- **No loose vertices.** Every vert has degree ≥ 1.
- **Manifold edges.** Every edge borders exactly 2 faces (closed solid).
- **No zero-area faces.** Face area > 1e-10; prints measured `min_area`.
- **Outward winding.** Positive signed volume (divergence theorem).
- **Euler sphere.** `V − E + F == 2` for the clean closed manifold
  (measured: verts=66 edges=136 faces=72, volume≈0.652001, min_area≈1.146e-02).

**What each check catches on failure:** loose vert injected (exit 4);
face deleted → boundary edges (exit 5); edge dissolved → ngon (exit 3);
all faces flipped → signed volume negated (exit 7); face collapsed →
zero-area (exit 6).

**Version witness:** output is byte-identical on Blender 4.5.11 LTS and
5.1.2 — same counts, same volume, same `min_area`.

**Render as proof:** dual panel, same brass on both. DIRTY stages a
camera-facing through-hole (boundary edges) plus a loose vert; emissive
beads/edge tubes are built from the live mesh incidence the check uses —
not decorative paint. CLEAN is the intact manifold. An out-of-frame AREA
light rakes through the hole from behind so the aperture reads warm without
a visible light panel in frame.

**Not depicted in the still (check-proven only):** ngon dissolve, zero-area
collapse, and full-mesh winding invert — they do not read as geometry at
thumbnail scale without faking annotation.

## Run

```bash
blender --background --python mesh_hygiene_audit.py --
blender --background --python mesh_hygiene_audit.py -- --output hygiene.png
blender --background --python mesh_hygiene_audit.py -- --output hygiene.png --engine cycles
```

Exits non-zero on failure. The `blender-smoke` workflow runs the check on
Blender 4.5 LTS and 5.1.
