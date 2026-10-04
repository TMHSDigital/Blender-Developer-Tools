# Solidify Even Thickness

A runnable example that solidifies an open, folded strip with the **Solidify** modifier and
proves, fold by fold, what `use_even_offset` does to the shell's thickness. The strip is a
zigzag profile extruded along Y, folded at bend angles of **60°, 90° and 120°**. The
evaluated shells are read through the depsgraph lifetime contract from
[`depsgraph-and-evaluated-data`](../../skills/depsgraph-and-evaluated-data/SKILL.md)
(`evaluated_get` → `to_mesh` → `to_mesh_clear`), and the strip is built with bmesh in a
`try`/`finally`, as [`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md)
requires.

**What it witnesses:** in the default Simple mode (`solidify_mode = 'EXTRUDE'`) with
`offset = -1`, the original surface stays put and every vertex gets a copy pushed
`thickness` along its vertex normal. At a fold the vertex normal is the bisector of the
two face normals, which meet at the bend angle φ. So:

- **without** `use_even_offset` the copy moves *t* along the bisector, and the shell's
  perpendicular thickness at the fold is **t · cos(φ/2)**, which is t · sin(θ/2) for the
  interior angle θ = 180° − φ. With t = 0.16 that is 0.1386 at 60°, 0.1131 at 90° and
  0.0800 at 120°: half the thickness you asked for;
- **with** `use_even_offset` the copy moves **t / cos(φ/2)** along the bisector, and the
  thickness is exactly *t* at every fold.

The check builds both closed forms from the profile itself, taking the face planes from
the segment directions and never from Blender's normals. It measures each shell's
perpendicular thickness at every fold and free edge and requires agreement to 1e-5
(measured: 3.7e-8). It also asserts the topology the measurement relies on: 2N evaluated
vertices, the first N being the untouched original surface, and copy *i* at vertex N + *i*.
Finally it checks that the thinning is real, so the witness cannot pass vacuously.

**The trap it exposes:** `use_even_offset` is off by default. A script that solidifies a
bent panel, a folded bracket or a box with `thickness = t` gets a wall that is noticeably
thinner at every corner, down to half at a 120° bend, and nothing errors. `--no-even`
leaves the flag off on the shell that the check expects to be even, and check 4 fails
with the measured thickness.

The still shows both shells in teal glaze side by side on a walnut plinth, viewed nearly
end-on. The cut section, Solidify's rim, is drawn in selection-orange enamel through
`material_offset_rim`, so the band's width is the shell's thickness. On the left, with
`use_even_offset = False`, the band pinches at every fold, and to half at the sharp V. A
red line on that cut face traces where a *t*-thick shell's inner face would run: it is
the even shell's own evaluated copy positions, placed through the plain shell's
transform, so the gap between the orange band and the red line is the thickness lost at
each fold, drawn at true size. On the right, with `use_even_offset = True`, the band stays
one width all the way round. Engraved brass plaques name each setting, and brass dowels
hold the raised folds off the plinth.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python solidify_even_thickness.py --

# Falsifier: leave use_even_offset off on the shell checked as even. Must exit 4.
blender --background --python solidify_even_thickness.py -- --no-even

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python solidify_even_thickness.py -- --output solidify.png --engine cycles
```

## Version notes

The Solidify modifier properties used here (`solidify_mode`, `thickness`, `offset`,
`use_even_offset`, `use_rim`, `material_offset_rim`) and the output vertex order
(originals first, then copies) are the same on 4.5 LTS, 5.1 and 5.2 LTS. The defaults
are also the same: `'EXTRUDE'`, offset −1, even off, rim on, quality normals off. All
values were measured identically on 4.5.11, 5.1.2 and 5.2.1.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Evaluated topology is not the original surface plus one copy per vertex (2N verts, originals untouched) |
| 4 | The even shell is not *t* thick at every fold, or its copies are off t / cos(φ/2) (`--no-even` lands here) |
| 5 | The plain shell is off the t · cos(φ/2) closed form at a fold |
| 6 | The plain shell thins by less than the floor (the witness would pass vacuously) |
| 7 | `--output` produced no file |
| 10 | `--output` framing violation (Layer 1 fill / margin gate, `gallery_framing`) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`. Its catalog falsifier is `--no-even` (expects exit 4).
