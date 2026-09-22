# Chopping block

A showcase piece, not an example. Procedural chopping block (a log round
with a riveted iron hoop and a felling axe buried in the sawn face) then
the shipped pipeline: unique-cell UVs, Cycles high-to-low normal bake,
LOD chain, convex collider, Unity glTF export.

The log is an out-of-round loft whose radius is a closed-form function
of angle and height; the hoop, its rivets, the top rim and the drying
checks are all generated from that same function, so they stay seated
when a dimension changes. The hoop is a lapped strip with two domed
rivets through the lap. The axe head is one lofted shell from poll to
bit with its chamfers modelled into the section profile, and the haft is
swept through the eye rather than pushed into it. The haft is oval,
bows away from the bit, and hooks toward it at the knob.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 1730–1870 | 1800 / 1800 / 1800 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 / 0.2200 / 0.2200 |
| Materials | exactly 4 distinct; ≥160 bark, ≥90 grain, ≥170 metal, ≥150 haft faces | 4 slots; 180 / 216 / 404 / 176 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.526, 0.526, 1.006) m ± 0.012 | (0.5264, 0.5264, 1.0064) |
| Collider tris | ≤ 560 | 538 |
| Export | written, size > 0 | 180588 / 180588 / 180572 bytes |

The triangle band, the outer AABB and the collider ceiling were re-fitted
in the quality pass that added the lap, the rivets and the 16-segment
oval haft (1472 → 1800 triangles, collider 434 → 538). The triangle band
is centred on the new measurement, ± 4 %.

### Hygiene

Recomputed from the generated mesh, not asserted about the script.

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Non-manifold edges | 0 | 0 |
| Loose verts / edges | 0 / 0 | 0 / 0 |
| Doubles merged at 1e-5 | 0 | 0 |
| Zero-area faces | 0 | 0 |
| N-gons | 0 | 0 |
| Coplanar disjoint face pairs | 0 | 0 |
| Grounded: `zmin` | within 1e-4 of 0 | 0.0000 |
| Log axis out of plumb | ≤ 1e-5 | 0.0000000 |
| Log size | 0.535 × 0.360 m ± 0.030 / ± 0.010 | 0.5464 × 0.3600 |
| Haft section, wide over thick at the grip | 1.25–1.60 | 1.3500 |

### Joint fit

Six shells that have to meet correctly: log, hoop, head, haft, and the
two rivets through the hoop's lap.

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Shell count | exactly 6 | 6 |
| Haft clearance inside the eye | ≥ 0.006 m | 0.01800 |
| Haft engagement through the eye | ≥ 0.020 m | 0.08225 |
| Haft breakout margin below the head | ≥ 0.006 m | 0.02175 |
| Bit bury below the sawn top | ≥ 0.030 m | 0.07871 |
| Bit inset from the rim | ≥ 0.030 m | 0.14647 |
| Hoop bite into the log, every segment | 0.002–0.007 m | 0.00371–0.00422 |
| Haft clearance above the log | ≥ 0.015 m, 0 verts inside | 0.07531, 0 |
| Rivet seat into the hoop, each rivet | 0.0008–0.0025 m | 0.00150, 0.00154 |
| Rivet dome proud of the hoop, each rivet | ≥ 0.0025 m | 0.00419, 0.00432 |

The hoop bite is binned by angular segment against the log's own radius
function. A single global midpoint radius misclassifies outer chamfer
vertices as inner ones on an out-of-round log, which is how a hoop that
visibly floated on one side still passed.

The rivet seat is measured radially at each rivet vertex's own angle,
against the hoop's outer face read off the mesh by a ray cast from the
axis. Each rivet is aimed down the hoop's surface normal, not the
radial: the log is out of round, so across one 12 mm head its surface
falls by up to 1.4 mm, and radially aimed heads seated 1.87 and 2.82 mm
against a 1.5 mm design bite, one edge sunk and the other lifted.

DECIMATE COLLAPSE triangle counts happen to agree across all three
series here; the gate is still a ratio band, not an exact count. Bake
pixels are stochastic; the gate is `has_data` plus operator `FINISHED`,
not byte-identity. Construction uses no RNG: two runs on each binary
print identical measurements, and the three binaries agree on every
gated axis. Export byte counts differ by 16 B on 5.2.1 (glTF
serializer), not a gated axis.

### Shading and materials

Only the axe head is flat-shaded: it is a chamfered forging, and its
facets are its form. The log and the hoop are smooth-shaded.
Flat-shaded, the log's 36 equal facets read as coopered staves and the
block as a tub, and the hoop threw one highlight per facet. The log's
wobble still reads in the silhouette, and its surface is carried by the
materials: vertical bark furrows with a bump, growth rings about an
off-centre pith on the sawn face, and dark radial checks drawn at the
same angles the geometry notches. Every material boundary is a hard
edge, so the sawn rim stays crisp against the bark.

The haft has its own material slot. It used to share the bark's, which
made the hickory handle the darkest wood on the piece.

### Falsifiers

Each violates one named budget. All seven were run on 4.5.11, 5.1.2 and
5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--fat-haft` | haft clearance inside the eye | 17 |
| `--round-band` | hoop bite into the log | 18 |
| `--float-rivets` | rivet seat into the hoop | 18 |
| `--round-haft` | haft section wide over thick | 19 |

`--fat-haft` thickens the haft across the cheeks only, which is the
dimension the eye clearance measures. Scaling the whole oval section
grew the knob 16 mm past the bounding box, so it exited 8 instead.

## Run

```bash
blender --background --python chopping_block.py --
blender --background --python chopping_block.py -- --skip-decimate
blender --background --python chopping_block.py -- --stray-vert
blender --background --python chopping_block.py -- --lift-z
blender --background --python chopping_block.py -- --fat-haft
blender --background --python chopping_block.py -- --round-band
blender --background --python chopping_block.py -- --float-rivets
blender --background --python chopping_block.py -- --round-haft
blender --background --python chopping_block.py -- --output chopping-block.png
```

Smoke passes no flags.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build / no UV layer |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 4 distinct slots, or a face-count floor missed |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | World AABB off declared outer size |
| 9 | LOD ratio band (`--skip-decimate` lands here) |
| 10 | Framing gate (render path only) |
| 11 | Collider triangle count above ceiling |
| 12 | Bake did not finish or image has no data |
| 13 | Export file missing or empty |
| 14 | `--output` produced no file |
| 15 | Mesh hygiene: loose, non-manifold, zero-area, doubles, n-gons, z-fight |
| 16 | Not grounded: bounding box `zmin` off 0 |
| 17 | Joint fit: shell count, eye clearance, engagement, breakout, bury, inset |
| 18 | Contact fit: hoop bite band, haft fouling the log, or a rivet off its seat band |
| 19 | Log out of plumb, off its stated real-world size, or a round haft section |
