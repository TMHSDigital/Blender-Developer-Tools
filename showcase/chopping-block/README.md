# Chopping block

A showcase piece, not an example. Procedural chopping block (a hooped
log round with a felling axe buried in the sawn face) then the shipped
pipeline: unique-cell UVs, Cycles high-to-low normal bake, LOD chain,
convex collider, Unity glTF export.

The log is an out-of-round loft whose radius is a closed-form function
of angle and height; the hoop, the top rim and the drying checks are all
generated from that same function, so they stay seated when a dimension
changes. The axe head is one lofted shell from poll to bit with its
chamfers modelled into the section profile, and the haft is swept
through the eye rather than pushed into it.

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
| Base triangles | 1410–1530 | 1472 / 1472 / 1472 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2188 / 0.2188 / 0.2188 |
| Materials | exactly 3 distinct; ≥160 bark, ≥90 grain, ≥24 metal faces | 3 slots; 252 / 252 / 288 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.526, 0.526, 1.012) m ± 0.01 | (0.5264, 0.5264, 1.0117) |
| Collider tris | ≤ 470 | 434 |
| Export | written, size > 0 | 150784 / 150784 / 150776 bytes |

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
| Grounded: `zmin` | within 1e-5 of 0 | 0.0000 |
| Log axis out of plumb | ≤ 2e-4 | 0.0000000 |
| Log size | 0.535 × 0.360 m ± 0.03 / ± 0.02 | 0.5464 × 0.3600 |

### Joint fit

Four shells that have to meet correctly: log, hoop, head, haft.

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Shell count | exactly 4 | 4 |
| Haft clearance inside the eye | ≥ 0.006 m | 0.01800 |
| Haft engagement through the eye | ≥ 0.020 m | 0.08049 |
| Haft breakout margin below the head | ≥ 0.006 m | 0.02351 |
| Bit bury below the sawn top | ≥ 0.030 m | 0.07871 |
| Bit inset from the rim | ≥ 0.030 m | 0.14647 |
| Hoop bite into the log, every segment | 0.002–0.007 m | 0.00371–0.00400 |
| Haft clearance above the log | ≥ 0.015 m, 0 verts inside | 0.07858, 0 |

The hoop bite is binned by angular segment against the log's own radius
function. A single global midpoint radius misclassifies outer chamfer
vertices as inner ones on an out-of-round log, which is how a hoop that
visibly floated on one side still passed.

DECIMATE COLLAPSE triangle counts happen to agree across all three
series here; the gate is still a ratio band, not an exact count. Bake
pixels are stochastic; the gate is `has_data` plus operator `FINISHED`,
not byte-identity. Construction uses no RNG. Export byte counts differ
by 8 B on 5.2.1 (glTF serializer), not a gated axis.

### Falsifiers

Each violates one named budget. All five were run on 4.5.11, 5.1.2 and
5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--fat-haft` | haft clearance inside the eye | 17 |
| `--round-band` | hoop bite into the log | 18 |

## Run

```bash
blender --background --python chopping_block.py --
blender --background --python chopping_block.py -- --skip-decimate
blender --background --python chopping_block.py -- --stray-vert
blender --background --python chopping_block.py -- --lift-z
blender --background --python chopping_block.py -- --fat-haft
blender --background --python chopping_block.py -- --round-band
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
| 5 | Material count ≠ 3 distinct slots, or a face-count floor missed |
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
| 17 | Axe joint fit: shell count, eye clearance, engagement, breakout, bury, inset |
| 18 | Contact fit: hoop bite band, or haft fouling the log |
| 19 | Log out of plumb, or off its stated real-world size |
