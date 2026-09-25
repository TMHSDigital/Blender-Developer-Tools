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
  recovers the silhouette (**2** strokes / **12** points on every binary for
  this crystal + camera; Line Art chains the bipyramid's edges into long
  strokes, so the count is low and the gates are lower bounds).
- **Stroke width renamed.** 4.5 exposes both `thickness` (legacy px, set to 45
  here) and `radius`; 5.1 removes `thickness` (`AttributeError`) and keeps
  `radius` only (portable path: `mod.radius = 0.028`).
- **GPv3 address** matches `grease-pencil-rosette`: `grease_pencils_v3` on 4.5,
  `grease_pencils` on 5.x.

**What each check catches on failure:** wrong GPv3 collection (exit 2),
`thickness` present/absent on the wrong side of 5.0 (exit 3), lost
`source_object` assignment (exit 4), contour too thin (exit 5), source clear
not zeroing strokes (exit 6), flags-off or restore failure (exit 7).

**Version witness:** stroke counts match on 4.5.11 LTS, 5.1.2 and 5.2.1 LTS
(2 strokes / 12 points). The divergence is `thickness` vs `radius`.

**The still:** the crystal is a hexagonal bipyramid (an equator ring and two
apexes), set tip-down in a two-tier hex mount on the floor. The mount is
render staging, derived from the crystal's lowest evaluated vertex; it is built
after the check, so it never enters the Line Art counts. The still's camera
drops its aim and dollies in along the check camera's bearing, so the crystal
fills the frame with the mount's foot inside it.

## Run

```bash
# Depsgraph contour check — the CI check:
blender --background --python gp_lineart_contour.py --

# Falsifier: use_contour off. Must exit non-zero.
blender --background --python gp_lineart_contour.py -- --no-contour

# Also render the gallery still:
blender --background --python gp_lineart_contour.py -- --output lineart.png
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage; also GPv3 collection address contract |
| 3 | LINEART `thickness` / `radius` trap for this Blender |
| 4 | LINEART type, source, or `use_contour` (`--no-contour` lands here) |
| 5 | Evaluated contour too thin |
| 6 | Cleared `source_object` still produced strokes |
| 7 | Contour+crease off still produced strokes, or restore failed |
| 8 | `--output` produced no file |
| 10 | Gallery framing violation |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--no-contour`.
