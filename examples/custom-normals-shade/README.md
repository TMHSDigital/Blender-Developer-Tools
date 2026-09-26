# Custom Normals + Shade by Angle

A runnable example that builds a jerry can prop — a pressed-steel shell
whose front and back carry four raised rounded-triangle panels (the X is
the channel between them), a weld-seam bead round the side band, a triple
carry handle on welded feet, and a spout with red seal, domed cap, cam
lever, hinge and locking pin; olive paint chipped to steel on exposed edges
by a `wear` point attribute — and verifies the shading
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
  threshold: Shell 1144 of 4098 edges, Handle 32 of 368, Neck 128 of 272
  (1304 of 4738) — an exact set match, not a count approximation.
- **The evaluated shading matches the attribute's promise.** Through
  depsgraph evaluation, loop normals across a smooth edge are welded
  (deviation 0.0, tol 1e-3) and loop normals across a sharp edge are split
  by the dihedral (angle error 1.898e-03 rad, tol 5e-3 — the curved side
  band and the panels' rounded wall corners average a fan whose facets
  step at most 22.5 and 10 deg), all unit length (err 1.0e-07).
- **Custom split normals survive depsgraph evaluation** — with a
  quantization budget, not float precision: `normals_split_custom_set`
  stores per-loop normals in int16, so an 8196-loop round-trip reads back
  within **3.904e-05** (tol 2e-4), unit length within 1.7e-07. Asserting
  float-exact custom normals is a real bug this check catches. Each corner
  requests its face normal tilted 20 deg toward the corner bisector. The
  pattern matters: Blender's lnor encoder merges requests within one fan
  that sit closer than ~0.81 deg and snaps an in-plane angle under 0.81 deg
  to zero. On this shell an index-swept pattern measured the merge
  (1.38e-02) and a 144-direction cycle hit the snap on 13 corners
  (9.1e-03). Neither is storage precision, so the check keeps clear of both.
- **The divergence: the legacy `shade_auto_smooth` OPERATOR is a
  version-split trap.** It builds the Smooth-by-Angle node-group modifier
  from a bundled asset. Headless on **4.5 LTS the asset load never
  finishes**: the op returns `{'CANCELLED'}` — no exception — and the mesh
  stays **untouched** (measured: 0 smooth faces, 0 modifiers). Any script
  that ignores the return set ships flat shading and never knows. On
  **5.1** it FINISHES and adds the `Smooth by Angle` NODES modifier. The
  portable path is the data API above, version-gated here explicitly.

**What each check catches on failure:** author/audit threshold drift
(probe: sharp marks applied at 20° but audited at 30°, exit 5, 48 extra
edges on the shell); the two halves of the contract out of sync (probe:
`sharp_edge` set but face smooth flags lost, exit 6, smooth-edge loops
split by 3.902e-01); float-exactness assumed of custom normals (probe:
tolerance 1e-6, exit 7, measured 3.904e-05); and any future version that
resurrects the legacy API or changes the operator's headless behavior
(exit 3/8). The render path adds the Layer 1 gates: framing (exit 10) and
asset quality (exit 11).

**Version witness:** every value above is identical on Blender 4.5.11 LTS,
5.1.2 and 5.2.1 LTS except the `shade_auto_smooth` operator behavior, which is
asserted per version (CANCELLED + untouched on 4.5, FINISHED + NODES
modifier on 5.1 and 5.2).

The render shows three fresh builds of the same can, one per shading
treatment. Left, flat: the side-band corners, cap and handle break into
facets. Middle, smooth-everywhere (the shade-smooth-and-forget AI habit):
the flat fields smear into gradients and the pressed panels go pillowy.
Right, by-angle (the contract): crisp creases and smooth rounds, with the
`sharp_edge` attribute read back from the mesh and traced as thin cyan
lines, so the viewer sees exactly which edges the data marked hard. A
low strip light makes the highlight shapes diverge between the three.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python custom_normals_shade.py --

# Falsifier: mark sharp at 20° while auditing 30°. Must exit non-zero.
blender --background --python custom_normals_shade.py -- --mismatch-angle

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python custom_normals_shade.py -- --output cans.png
blender --background --python custom_normals_shade.py -- --output cans.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Legacy shading API present, or modern path missing |
| 4 | Non-manifold edges (dihedral test undefined) |
| 5 | Sharp set ≠ independent dihedral (`--mismatch-angle` lands here) |
| 6 | Evaluated loop normals not welded/split as the sharp set promises |
| 7 | Custom split normals lost or dequantized in evaluation |
| 8 | `shade_auto_smooth` operator behavior drifted from the version split |
| 9 | `--output` produced no file |
| 10 | Render path: Layer 1 framing violation (`gallery_framing`) |
| 11 | Render path: asset-quality floor violation (`gallery_asset_quality`) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--mismatch-angle`.
