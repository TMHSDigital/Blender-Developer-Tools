# Mesh Hygiene Audit

A runnable example that builds an upright flanged street valve — body
casting, side outlet, 22 flange bolts, gland nut, threaded stem, brass
handwheel hub, rim and spokes — and runs the **engine-ingest mesh hygiene
checklist** on every part as executable topology checks, following
[`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md).

**Pipeline arc neighbors:** watertight / Euler on collision *hulls* in
[`collision-hull-proxy`](../collision-hull-proxy/), parametric closed solids
in [`bmesh-gear`](../bmesh-gear/), LOD face budgets in
[`lod-decimate-chain`](../lod-decimate-chain/), and join context in
[`temp-override-join`](../temp-override-join/). Hygiene is the gate a prop
pipeline runs on the *render* mesh before hull / LOD / export.

**Scope:** this witnesses the bpy-level contract a prop pipeline relies on
(tris+quads, no loose verts, manifold edges, no zero-area faces, consistent
and outward winding, Euler 2 for the genus-0 body casting). It is not an
engine exporter.

**What it witnesses:** every gate is derived from mesh combinatorics or the
divergence-theorem volume — never from a prior-run capture. Gates 3–7 run on
all eight parts; the Euler gate runs on the body casting, the one closed
genus-0 shell the other parts mount on (the handwheel rim is a torus, the
bolt and spoke meshes are many shells, so a single-sphere Euler test does
not describe them):

- **No ngons.** `len(poly.vertices) <= 4` for every face.
- **No loose vertices.** Every vert has degree ≥ 1.
- **Manifold edges.** Every edge borders exactly 2 faces (closed solid).
- **No zero-area faces.** Face area > 1e-10; prints measured `min_area`.
- **Consistent winding.** Every manifold edge is `BMEdge.is_contiguous` —
  a flipped patch leaves seam edges whose two faces traverse it the same way.
- **Outward winding.** Positive signed volume (divergence theorem).
- **Euler sphere.** `V − E + F == 2` on the body casting
  (measured: verts=802 edges=1632 faces=832, volume≈0.453344,
  min_area≈1.223e-03).

**What each check catches on failure** (`--inject KIND`, default target the
body casting, `--inject-part NAME` for any other part): `ngon` → exit 3;
`loose` → exit 4; `boundary` (one face deleted) → exit 5; `zero_area` (face
collapsed) → exit 6; `flip_patch` (one face flipped) → exit 7 on winding
seams; `flip` (all faces) → exit 7 on negative volume; `shell` (a leftover
second closed shell buried inside) → exit 8, the one defect every per-edge
gate misses. `--inject-ngon` is kept as an alias for `--inject ngon`.

**Version witness:** the check output is identical on Blender 5.2.1 LTS,
5.1.2 and 4.5.11 LTS — same counts, same volume, same `min_area`.

**Render as proof:** a dirty copy of the same valve (left) beside the clean
valve (right), same paint on both. The dirty body casting carries four real
gate failures, each placed on the camera-facing side: a hole through the
globe (open boundary), a flipped patch on the bonnet dome, an ngon merged
into the base-flange annulus, and three stray loose vertices. The markers are
read back from the dirty mesh's audit incidence, not from the staging code:
boundary edges become glowing red tubes, loose verts red beads, ngon faces an
amber material slot. The flipped patch and the inside of the hole need no
marker — the paint mixes to red on the shader's own `Backfacing` output, so
the renderer shows every face it sees from behind. On the clean valve that
same material shows no red anywhere, because no back side is visible on a
closed, outward-wound shell. The render path refuses to write a still
(exit 9) if staging loses any of the four defect classes.

**Not depicted in the still (check-proven only):** zero-area collapse and
the buried second shell — neither changes a single pixel.

## Run

```bash
blender --background --python mesh_hygiene_audit.py --
blender --background --python mesh_hygiene_audit.py -- --inject ngon
blender --background --python mesh_hygiene_audit.py -- --inject flip_patch --inject-part Valve.HandwheelRim
blender --background --python mesh_hygiene_audit.py -- --output hygiene.png
blender --background --python mesh_hygiene_audit.py -- --output hygiene.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper, `11` the shared asset-quality
helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Ngon present (`--inject ngon` lands here) |
| 4 | Loose vertices |
| 5 | Non-manifold or boundary edges |
| 6 | Zero-area faces |
| 7 | Winding seam edges, or signed volume ≤ 0 |
| 8 | Body casting Euler characteristic ≠ 2 |
| 9 | `--output` produced no file, or dirty staging lost a defect class |
| 10 | Gallery framing violation |
| 11 | Gallery asset-quality floor violation |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--inject`.
