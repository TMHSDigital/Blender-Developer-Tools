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

**Render as proof:** dual pinwheel from the same closed-form palette the
check asserts. CORNER (left) holds eight crisp petals to the hub; naive
POINT (right) smears — petal colors bleed across the shared hub and ring
verts into a swirl. The broken state is in-frame by design: the right fan
*is* the falsification variant. Fully matte petal materials
(`Specular IOR Level = 0`) so the flat color data carries no specular line,
per `docs/VISUAL-STYLE.md`.

## Run

```bash
blender --background --python attribute_domain_shear.py --
blender --background --python attribute_domain_shear.py -- --output shear.png
blender --background --python attribute_domain_shear.py -- --output shear.png --engine cycles
```

Exits non-zero on failure. The `blender-smoke` workflow runs the check on
Blender 4.5 LTS and 5.1. The `--output` render path additionally measures
framing against the Layer 1 band via `examples/gallery_framing.py` (exit 10
on violation) before writing the still.
