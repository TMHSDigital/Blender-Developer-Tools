# Lightmap UV Channel

A runnable example building the second UV layer engines require for baked
lighting, on an asset built to be reused: a market cart (bed, axle, two
wheels, four posts, arched canvas canopy — ground-level pivot at `z=0`,
identity transforms by construction, `Cart.*` datablocks, watertight parts
throughout). UV0 is the texture channel (deterministic dominant-axis box
projection per face); UVLight is the baked-lighting atlas
(`smart_project` → `lightmap_pack`).

**What it witnesses** (all independently derived, nothing trusted from the
packer):

- **The flag trap.** `uv_layers.new()` does **not** move the active flags —
  the first layer keeps `active` + `active_render`, so a UV op runs against
  channel 0 unless you move `active` yourself (probed: unwrap+pack with the
  flags unmoved destroys channel 0, measured drift **2.068**). Worse, the
  edit-mode UV ops **clear both flags** — the sequence must re-assert them.
  The check pins, per part: exactly two layers `UVMap`/`UVLight`,
  `active == UVLight` (edit target), `active_render == UVMap` (render
  target).
- **Channel zero untouched.** UV0 loops snapshotted before the UVLight
  unwrap, compared after: drift **0.0** on every part (tol 1e-6).
- **Bounds.** Every UVLight loop inside `[0, 1]` within 1e-5.
- **Non-overlap.** UV1 triangles binned into a 256² spatial hash and tested
  pairwise with strict SAT (epsilon-separated, so shared edges don't count):
  **0** overlapping pairs.
- **Margin.** `MARGIN_DIV` semantics measured live: nominal margin ==
  `MARGIN_DIV × 0.01` UV units; the check requires the measured min
  island-pair distance ≥ half the nominal — measured **0.00401**
  (≈ 2× the nominal 0.002, the packer's per-island margin applied twice).
- **Island census + watertight parts.** Connected components counted
  independently per part; loops conserved; every part manifold.

**What each check catches on failure:** wrong layer names/count (exit 3);
flags not re-established after the ops (exit 4); channel 0 touched by the
UV1 unwrap (exit 5 — probed via the clobber trap, drift 2.068); UV1 loops
outside the unit square (exit 6); overlapping islands (exit 7 — probed by
translating an island onto a neighbor, 15 SAT hits); margin floor broken
(exit 8 — probed with `MARGIN_DIV=0`, measured 2e-5 < 0.001); non-watertight
part (exit 9).

**Authoring hazards pinned while building this** (probes in
`.scratch`-style bisect scripts; the reasons the check code re-fetches
layers by name and re-asserts flags):

- Holding a `MeshUVLoopLayer` reference across edit-mode UV ops and then
  iterating its `.data` **segfaults Blender 4.5.11 headless**
  (`EXCEPTION_ACCESS_VIOLATION`, 5/5 repro); the same read survives on
  5.1.2. Re-fetch `mesh.uv_layers[name]` after CustomData-reallocating
  calls. Second confirmation of the UV-handle lifetime hazard found
  authoring `triangulate-tangents`.
- `bpy.ops.uv.lightmap_pack` **silently packs nothing** (exit OK) when the
  active layer has no UVs yet — unwrap first, then pack.

**Pipeline arc neighbors:** UV-layer authoring in
[`uv-layer-grid`](../uv-layer-grid/), tangent-space from UVs in
[`triangulate-tangents`](../triangulate-tangents/), export round-trip in
[`gltf-export-roundtrip`](../gltf-export-roundtrip/), pivot discipline in
[`prop-origin-transform`](../prop-origin-transform/).

**Version witness:** check output is byte-identical on Blender 4.5.11 LTS
and 5.1.2 (9 parts, 1114 islands, drift 0, overlap 0, min island distance
0.00401). The UV *layout* is packer-version-dependent by design; the
contracts are layout-independent invariants.

**Render as proof:** the cart beside its UV1 atlas board — the Bed's
packed lightmap built from live UV data, so a change in the atlas moves
the board geometry. The falsification variant (`--falsify`) translates the
second-largest island onto the largest: a big emissive-red island visibly
stacked over the atlas (15 SAT hits in the check probe).

## Run

```bash
blender --background --python lightmap_uv_channel.py --
blender --background --python lightmap_uv_channel.py -- --output atlas.png
blender --background --python lightmap_uv_channel.py -- --falsify overlap.png
```

Exits non-zero on failure. The `blender-smoke` workflow runs the check on
Blender 4.5 LTS and 5.1. The `--output` render path additionally measures
framing against the Layer 1 band via `examples/gallery_framing.py` (exit 10
on violation) before writing the still.
