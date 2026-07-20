# UV Layer Grid

A runnable example that witnesses the UV-layer authoring hazard behind
`bmesh.ops.create_grid(..., calc_uvs=True)`: the flag is a **silent no-op**
unless a UV layer already exists on the BMesh. AI-generated Blender code
commonly trusts `calc_uvs=True`, wires an Image Texture, and ships a mesh that
renders as one flat color — every fragment samples texel (0, 0).

Found while authoring [`image-pixels-testcard`](../image-pixels-testcard/);
lifted into its own smoke-gated witness so the contract cannot quietly drift.

**What it witnesses:** three related contracts on the same grid topology
(`SEG×SEG` faces, `(SEG+1)²` verts, size `1.0` → coords in `[-1, 1]`):

1. **Silent no-op** — `create_grid(..., calc_uvs=True)` with no prior
   `bm.loops.layers.uv.new(...)` leaves `len(bm.loops.layers.uv) == 0` and
   `mesh.uv_layers` empty after `to_mesh`.
2. **Pre-create repair** — create the UV layer first, then `calc_uvs=True`
   fills every loop. UVs must match the closed form
   `u = (x/size + 1)/2`, `v = (y/size + 1)/2` within `1e-6`, both on the
   BMesh and after persisting to `mesh.uv_layers.active.data`.
3. **Explicit assignment fallback** — `calc_uvs=False`, then
   `uv.new("UVMap")` and a loop write of the same closed form. Does not
   depend on `calc_uvs` at all; same tolerance.

**What each check catches on failure:**

- *Silent no-op* — `calc_uvs=True` starts creating a layer on its own
  (falsified: expecting `n_layers == 0` fails if a layer appears; temporarily
  pre-creating a layer before the hazard probe exits 3).
- *Topology* — `create_grid` segment/size contract drift (wrong face/vert
  counts).
- *Closed-form UVs* — `calc_uvs` filling a different parameterization, or a
  one-texel shift (falsified: adding `0.1` to every U exited 6 with measured
  error `0.1`).
- *Mesh persistence* — UV layer or loop data lost across `to_mesh`.
- *Explicit path* — loop assignment or the closed form itself regressing.
- *Pixel witness* (with `--output`) — the saved PNG is read back and probed
  at each panel's projected center: the hazard panel must be one flat teal
  (per-channel spread ≤ 0.02, ordering b>g>r), the repaired panel a
  high-contrast checker (spread ≥ 0.25). Falsified twice: secretly giving the
  hazard panel UVs exited 11 with measured spread `0.7333`; repainting texel
  (0,0) magenta exited 12 with measured rgb `(0.927, 0.118, 0.536)`.

**Version divergence:** none probed — the silent no-op and closed-form UV
fill assert identically on Blender 4.5 LTS and 5.1. The only gate in the file
is the EEVEE engine id for the optional render (`BLENDER_EEVEE_NEXT` on 4.x,
`BLENDER_EEVEE` on 5.x).

**Render:** two easel panels sharing one neon checker image. Left is the
hazard (no UV layer) — flat teal of texel (0, 0). Right is the repair
(pre-create + `calc_uvs`) — full magenta/cyan checker. If the UV contract
failed, both panels would read the same — and the still is not just an
illustration: the script re-reads its own render and exits non-zero unless
the pixels prove the flat-vs-checker split (measured on 5.1.2: hazard spread
`0.0078`, repair spread `0.7294`).

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python uv_layer_grid.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python uv_layer_grid.py -- --output uv.png
blender --background --python uv_layer_grid.py -- --output uv.png --engine cycles
```

It exits non-zero on failure and prints every measured error and tolerance on
success, so CI logs carry the numbers. The `blender-smoke` workflow runs the
check on Blender 4.5 LTS and 5.1.
