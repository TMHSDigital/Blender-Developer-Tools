# GP Line Art Contour

A runnable example that builds a faceted crystal, attaches a Grease Pencil
`LINEART` modifier with `source_type='OBJECT'`, and proves the contour contract
through the depsgraph — including the 4.5 → 5.1 stroke-width trap.

**What it witnesses:** the Line Art modifier contract AI-generated NPR code most
often gets wrong.

- **Contours are a modifier, not Freestyle and not hand-authored strokes.**
  `modifiers.new(..., 'LINEART')` on a GPv3 object, with `target_layer` /
  `target_material` set, evaluates silhouette edges into drawing strokes.
- **`source_object` is load-bearing.** Clearing it yields **0** evaluated
  strokes (proven in the same check pass). Restoring it recovers the contour.
- **Edge-type flags matter.** A freshly added LINEART with `use_contour` and
  `use_crease` both off emits **0** strokes; turning contour (+ crease) back on
  recovers the silhouette (**10** strokes / **34** points on both binaries for
  this crystal + camera).
- **Stroke width renamed.** 4.5 exposes both `thickness` (legacy px, set to 45
  here) and `radius`; 5.1 removes `thickness` (`AttributeError`) and keeps
  `radius` only (portable path: `mod.radius = 0.028`).
- **GPv3 address** matches `grease-pencil-rosette`: `grease_pencils_v3` on 4.5,
  `grease_pencils` on 5.x.

**What each check catches on failure:** wrong GPv3 collection (exit 2),
`thickness` present/absent on the wrong side of 5.0 (exit 3), lost
`source_object` assignment (exit 4), contour too thin (exit 5), source clear
not zeroing strokes (exit 6), flags-off or restore failure (exit 7).

**Version witness:** stroke counts match on 4.5.11 LTS and 5.1.2
(10 strokes / 34 points). The divergence is `thickness` vs `radius`.

## Run

```bash
# Depsgraph contour check — the CI check:
blender --background --python gp_lineart_contour.py --

# Also render the gallery still:
blender --background --python gp_lineart_contour.py -- --output lineart.png
```

It exits non-zero on failure. The `blender-smoke` workflow runs the check on
Blender 4.5 LTS and 5.1.
