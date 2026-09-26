# Attribute Domain Shear

A runnable example that witnesses what `POINT` versus `CORNER` **means** on
`Mesh.color_attributes` once the mesh has shared vertices — the domain is not
a storage detail, it decides where colors can live. Companion to
[`color-attribute-wheel`](../color-attribute-wheel/) (which covers
`color_attributes.new()` versus the deprecated alias, CORNER sizing ==
`len(loops)`, and `active_color`); this example covers the trap one step
later, when AI code knows the API exists but authors per-face colors into a
`POINT`-domain attribute.

**Pipeline arc neighbors:** attribute authoring in
[`color-attribute-wheel`](../color-attribute-wheel/), mesh topology gates in
[`mesh-hygiene-audit`](../mesh-hygiene-audit/), tangent-space UV contracts in
[`triangulate-tangents`](../triangulate-tangents/).

**What it witnesses:** a pinwheel of K=8 triangles around **one raised hub
vertex** shared by every wedge (plus a shared outer ring). The contract,
all closed form:

- **Storage sizes.** CORNER attr data == `len(loops)` == 3K; POINT attr ==
  `len(vertices)` == K+1.
- **CORNER authoring is exact.** The hub corner of wedge i reads palette[i]
  within 1e-6 — K faces at one vertex may disagree there.
- **POINT naive authoring shears by construction.** A per-wedge authoring
  loop ("paint each wedge its color") rewrites every shared vertex once per
  neighbor, and the **last write wins**: the hub reads palette[K-1], ring
  vert i reads palette[i] — except ring vert 0, which the wrap-around last
  wedge rewrites to palette[K-1]. The measured mean deviation from intended
  equals the palette closed form (0.751031) exactly.

**What each check catches on failure:** wedge 3 miscolored in the CORNER
pass (exit 4); naive writes reversed, so the hub reads palette[0] (exit 5);
a ring vert corrupted, breaking the overwrite-ordering witness (exit 6);
a constant palette, collapsing the shear so the probe cannot distinguish
naive from correct (exit 7). Sizes wrong for the declared domain (exit 3).

**Version witness:** output is byte-identical on Blender 4.5.11 LTS and
5.1.2 — the `color_attributes` domain API is stable across both.

**Render as proof:** two striped patio parasols, painted by the same two
authoring functions the check asserts. The canopy is the check's fan grown
into fabric: eight gores around **one shared apex vertex**, each gore a strip
of faces whose vertices all sit on the two seams it shares with its
neighbours, so the naive loop touches exactly the kind of shared vertex the
check measures. CORNER (left) keeps crisp crimson and cream stripes. Naive
POINT (right) rewrites every seam and the apex with the later gore's color:
the stripes smear pink along the seams, and gore 0, crimson by intent,
renders cream because its seam and the apex were last written by gore 7.
That gore is turned to face the camera. The broken state is in frame by
design: the right parasol *is* the falsification variant. The canopy fabric
is fully matte (`Specular IOR Level = 0`) so the flat color data carries no
specular line, per `docs/VISUAL-STYLE.md`.

The render uses a two-tone palette (crimson and cream, alternating). It is
not the check's palette. The check keeps its eight distinct hues because an
off-by-two ordering bug would pass unnoticed under a period-2 palette. A
parasol reads as broken only when stripes everyone expects to be crisp go
soft. Both palettes go through the same `assign_corner` and
`assign_point_naive`. Those functions take a `faces_per_wedge` stride
(gore-major face order). It is 1 on the check's fan, so the check's writes
are unchanged, and its output is identical before and after.

The staging is render-only and does not touch the checked mesh. Each parasol
is eight named parts with five materials: canopy, aluminium ribs and
stretchers, brass runner, finial and tilt knuckle, teak upper and lower pole,
and a cast-iron base. The canopy tilts 24 degrees toward the camera about the
knuckle so the whole top reads. One bold label stands in front of each base.
The render path runs the framing gate (exit 10) and the asset-quality floors
on one parasol (exit 11).

## Run

```bash
blender --background --python attribute_domain_shear.py --
blender --background --python attribute_domain_shear.py -- --no-overwrite
blender --background --python attribute_domain_shear.py -- --output shear.png
blender --background --python attribute_domain_shear.py -- --output shear.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper and `11` the shared asset-quality helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | CORNER or POINT attribute size wrong |
| 4 | CORNER hub corners off wedge color |
| 5 | POINT hub is not last-write (`--no-overwrite` lands here) |
| 6 | Outer ring verts off last-write order |
| 7 | Measured shear off palette closed form, or ~0 |
| 9 | `--output` produced no file |
| 10 | Gallery framing violation |
| 11 | Asset-quality floor violation (render path only) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--no-overwrite`.

