# Triangulate + Tangents

A runnable example that builds a machined buckler — lathed dome with polar
UVs, unwrapped rim and underside strips, a fanned back cap — and verifies
the tangent-space contract a game engine's normal mapping depends on,
following [`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md).

**Pipeline arc neighbor:** weighting in
[`vertex-weight-limit`](../vertex-weight-limit/), export in
[`gltf-export-roundtrip`](../gltf-export-roundtrip/) — tangent space is what
the exported normal maps are baked against.

**What it witnesses:** the mikktspace contract engines implement, and the
hazards around it.

- **Deterministic triangulation and the engine basis.** `calc_loop_triangles`
  yields the closed-form count (two tris per quad + the cap fan, 720), and
  every loop tangent is unit length (err 1.3e-07) and exactly orthogonal to
  its loop normal (err 6.0e-08), with the bitangent exactly
  `bitangent_sign * (normal x tangent)` (err 0.0). One ngon anywhere in the
  mesh and `calc_tangents` **aborts the whole call** — the back cap is an
  explicit fan for exactly that reason.
- **The tangent frame follows the UVs.** On smooth-field triangles the
  per-loop tangents match the independently derived edge/UV-delta formula
  within mikktspace's vertex-welding tolerance (measured 2.3e-06, tol 0.15);
  a flipped frame inside a smooth field is never legal (0 measured). At UV
  seams the frame orientation is implementation-defined — 42 seam flips, 9
  at chart seams, identical on both versions — and planar UVs on a
  cylindrical wall are degenerate: they collapse the tangent onto the
  normal (dot 0.998, measured and fixed by unwrapping strips).
- **The reference-lifetime hazard (the real divergence).** A
  `MeshUVLoopLayer` handle held across `calc_tangents()` dangles: on
  Blender 4.5 reads through it return tangent floats, not UVs — measured
  while authoring as a phantom **471 flipped frames and 385 phantom seam
  positions, exit 0, a silent wrong answer**. On 5.1 the same stale read
  survives by memory-layout luck. The mikktspace math itself is
  byte-identical on 4.5.11 and 5.1.2; the apparent version divergence was
  entirely the corrupt handle. Never hold layer handles across
  CustomData-reallocating calls — re-fetch by name.

**What each check catches on failure:** a remeshed asset breaking the
triangulation count (probe: dropped profile ring, exit 3, 624 vs 720); a
wrong tangent formula in the independent derivation (probe: swapped du/dv,
exit 7, weld 1.459); and the stale-handle read (probe: no re-fetch — corrupt
measurements on 4.5, correct values on 5.1 by luck).

**Version witness:** mikktspace output is identical on Blender 4.5.11 LTS
and 5.1.2 (same weld deviations, same seam flips). The `calc_tangents(uvmap=)`
signature is stable. The lifetime hazard above is the only behavioral split,
and it corrupts measurements rather than raising.

The render shows the buckler on its cradle: brushed grooves circulating the
boss with the anisotropic sweep riding them — the circulating tangent field
made visible.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python triangulate_tangents.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python triangulate_tangents.py -- --output buckler.png
blender --background --python triangulate_tangents.py -- --output buckler.png --engine cycles
```

It exits non-zero on failure (topology drift, reallocated UV layer,
non-orthonormal basis, bitangent-convention drift, formula excursion, or a
flip inside a smooth field). The `blender-smoke` workflow runs the check on
Blender 4.5 LTS and 5.1.
