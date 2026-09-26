# GP Line Art Contour

A runnable example that builds a lighthouse on a rocky islet — tower, gallery,
lantern room, keeper's cottage, a hauled-up rowboat and a diorama sea — as one
cel-shaded mesh, attaches a Grease Pencil `LINEART` modifier with
`source_type='OBJECT'`, and proves the contour contract through the depsgraph,
including the 4.5 → 5.1 stroke-width trap.

**What it witnesses:** the Line Art modifier contract AI-generated NPR code most
often gets wrong.

- **Contours are a modifier, not Freestyle and not hand-authored strokes.**
  `modifiers.new(..., 'LINEART')` on a GPv3 object, with `target_layer` /
  `target_material` set, evaluates the source mesh's edges into drawing strokes.
- **`source_object` is load-bearing.** Clearing it yields **0** evaluated
  strokes (proven in the same check pass). Restoring it recovers the drawing.
- **Edge-type flags matter.** A freshly added LINEART with every edge type off
  (contour, crease, material borders, intersections, loose, edge marks) emits
  **0** strokes. The configured modifier draws **255** strokes / **1393**
  points on every binary, and the gates (**≥ 240** strokes, **≥ 1320** points)
  sit above the count left when any *one* edge type is dropped — contour 234
  strokes, crease 171 / 1099, material borders 247 / 1305, intersections
  179 / 921 — so each is load-bearing: the band borders on the tower are
  material-border ink, the waterline around each rock is intersection ink.
  Rebuilding the modifier must recover exactly the first pass's counts.
- **Stroke width renamed.** 4.5 exposes both `thickness` (legacy px, set to 22
  here) and `radius`; 5.1 removes `thickness` (`AttributeError`) and keeps
  `radius` only (portable path: `mod.radius = 0.021`).
- **GPv3 address** matches `grease-pencil-rosette`: `grease_pencils_v3` on 4.5,
  `grease_pencils` on 5.x.

**What each check catches on failure:** wrong GPv3 collection (exit 2),
`thickness` present/absent on the wrong side of 5.0 (exit 3), lost
`source_object` assignment or `use_contour` (exit 4), drawing below the gates
(exit 5), source clear not zeroing strokes (exit 6), flags-off not zeroing
strokes or a rebuild not recovering the same counts (exit 7).

**Version witness:** stroke counts match on 4.5.11 LTS, 5.1.2 and 5.2.1 LTS
(255 strokes / 1393 points). The divergence is `thickness` vs `radius`.

**The still:** the check and the still share one camera, because Line Art is
view-dependent — the strokes the check counts are the strokes the still draws.
The mesh is shaded flat (three cel tones), so the black ink is what makes it
read as an inked illustration: clear `source_object` and the same render is a
flat, lineless low-poly model — no band borders, no waterline, no outlines.

### Stage deviation

Line Art is a non-photoreal contract: the hero's materials are cel-shaded
(Diffuse → Shader to RGB → constant ramp, emitted) instead of Principled, so
the ink reads against flat tone fields. The stage itself — floor, wall, world,
key, fill and warm wedge — is the default. The cel shading uses Shader to RGB,
which is EEVEE-only, so `--engine cycles` does not render the look.

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
| 5 | Evaluated drawing below the stroke/point gates |
| 6 | Cleared `source_object` still produced strokes |
| 7 | Every edge type off still produced strokes, or the rebuild did not recover the same counts |
| 8 | `--output` produced no file |
| 10 | Gallery framing violation |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--no-contour`.
