# Signpost

A showcase piece, not an example. Procedural timber fingerboard
signpost (square post, collar and pyramidal cap, two painted planks
with diamond tips, iron shoe and straps) then the shipped pipeline:
unique-cell UVs, Cycles high-to-low normal bake, LOD chain, convex
collider, Unity glTF export.

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
| Base triangles | 430–580 | 504 / 504 / 504 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2183 / 0.2183 / 0.1746 |
| Materials | exactly 3 distinct, ≥24 metal and ≥12 board faces | 3 slots, 66 metal, 24 board |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.368, 0.201, 1.566) m ± 0.01 | (1.3679, 0.2014, 1.5660), zmin 0 |
| Collider tris | ≤ 140 | 56 |
| Export | written, size > 0 | 45164 / 45164 / 45152 bytes |

DECIMATE COLLAPSE triangle counts are **not** identical across series —
5.2.1 is more aggressive on LOD2. The gate is a ratio band, not an
exact count. Bake pixels are stochastic; the gate is `has_data` plus
operator `FINISHED`, not byte-identity. Construction uses no RNG.
Export byte counts differ by 12 B on 5.2.1 (glTF serializer), not a
gated axis.

`--skip-decimate` skips the LOD DECIMATE stage so LOD1 ratio is 1.0 and
exit 9 fires. That is the named budget the falsifier violates.

## Run

```bash
blender --background --python signpost.py --
blender --background --python signpost.py -- --skip-decimate
blender --background --python signpost.py -- --output signpost.png
```

Smoke does not pass `--output` or `--skip-decimate`.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build / no UV layer |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 3 distinct slots, or wood/board/metal faces missing |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | World AABB off declared outer size |
| 9 | LOD ratio band (`--skip-decimate` lands here) |
| 10 | Framing gate (render path only) |
| 11 | Collider triangle count above ceiling |
| 12 | Bake did not finish or image has no data |
| 13 | Export file missing or empty |
| 14 | `--output` produced no file |
