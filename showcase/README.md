# Showcase

Budget-conformance props. **Not examples.**

An example witnesses one API contract and carries a falsifier that makes a
real assertion fail. A recognizable crate witnesses no API contract.
Forcing one into `examples/` produces a vacuous check. Showcase pieces
assert that generated geometry meets **declared asset budgets**.

"It rendered without error" is not an assertion. A tolerance so wide
nothing can violate it is not an assertion.

This directory is a sibling of `examples/`, not nested under it. The
manifest key is `showcase`. Counts are separate from the example total.

## Conventions

Every piece is a directory `showcase/<name>/` with a script, a README that
includes an exit-code table, a falsifier, a `catalog.json` row, a gallery
entry in `showcase/gallery.json`, and a rendered still.

- **Deterministic.** Fixed seed (or no RNG). Identical output across runs
  on the same binary, and across Blender 4.5, 5.1, and 5.2. If a value
  legitimately cannot match across versions, the piece README names it,
  states a tolerance, and justifies it. DECIMATE COLLAPSE triangle counts
  are the usual suspect — prefer ratio bands, not exact counts.
- **Budgets declared** in the script as named constants and documented in
  the piece README. Suggested axes: triangle count, material count, UV
  bounds, bounding-box dimensions, LOD ratios, collider triangle ceiling,
  export file written.
- **Assertions recompute** those budgets from the generated result. They
  never restate constants the script set (`if n == DECLARED` where `n` was
  assigned `DECLARED` is not a check).
- **Falsifier** breaks one pipeline stage so a **named** budget fails and
  the piece exits its documented code. Prove default and falsifier on
  4.5.11, 5.1.2, and 5.2.1. `--skip-decimate` is the LOD-ratio
  falsifier (exit 9), `--stray-vert` the mesh-hygiene falsifier (exit
  15), `--lift-z` the grounded-zmin falsifier (exit 16), and
  `--fat-rungs` (or the piece's equivalent) the joint-fit falsifier
  (exit 17), and `--round-band` (or equivalent) the seat-conformance
  falsifier (exit 18). `--twin-sole` duplicates a ground plate so the
  coplanar-face budget fails (exit 15). `--short-stile` /
  `--short-post` lift a member out of its cup (exit 18 or 19).
  `--clip-ring` pulls a hung ring off the eye centerline (exit 18).
  A budget with no falsifier witnesses nothing:
  prove each one fails once, and check the exit code, not just
  non-zero.
- **A falsifier must fail the budget it targets.** Declare the target in
  the piece README's falsifier table — flag, target budget, exit code —
  and make the run exit *that* code. A falsifier that trips an earlier
  check is red for the wrong reason and proves nothing about its target.
  Fix a collision by changing the model or the falsifier; never widen a
  band so an ill-aimed falsifier lands. `stone-archway`'s `--flat-arch`
  laid the voussoirs as a lintel, which is 0.62 m shorter and so failed
  the bounding box (exit 8) instead of the intrados circle fit (exit 19);
  `--off-circle` replaced it by keeping the whole envelope and wandering
  only the radius. `tests/check_falsifier_targets.py` checks the
  declaration statically, and with `--run BLENDER` executes each falsifier
  and asserts the observed exit matches.
- **Hygiene budgets.** Copied combinatorics from
  `examples/mesh-hygiene-audit` (do not import the example). Every piece
  asserts on the generated mesh: non-manifold edges 0, loose verts 0,
  loose edges 0, doubles at 1e-5 0, zero-area faces 0, n-gons 0, world
  AABB min Z within 1e-4 of 0, and coplanar disjoint face pairs 0. Count
  the last one over faces that share **no** vertex: the triangles of one
  flat fan cap are coplanar and close-centred by construction, and
  counting those makes the budget unsatisfiable rather than meaningful.
  Count the coplanar pairs **cross-shell**, not merely over faces that
  share no vertex: two quads two steps apart on one flat cap share no
  vertex and are coplanar and close-centred by construction. Counting
  those reported 96 pairs on `hay-bale`, none of them a hazard, which is
  the same unsatisfiable-budget trap in a second disguise. Z-fighting is
  two separate bodies landing on one plane, and that is a cross-shell
  pair by definition.
  Multi-body props do **not** require Euler characteristic 2 — that is a
  single-shell contract. Two boxes that share a coplanar face z-fight;
  two that share a vertex weld into one shell. Seat a joint with a named
  overlap or rebate computed from the host (a cage post into its rail, a
  glass pane behind its muntin, a plinth step into its base) rather than
  hoping the numbers happen not to coincide. A hang-station versus
  arm-station split lets a contact falsifier move one member without
  dragging the rest of the assembly. Pairs of parts meant to touch assert a BVH
  surface gap below a named epsilon (vert-vert is the wrong metric for
  thin straps and collars). A spanning board whose only vertices sit at
  the far ends will report a false gap to a mid-span knuckle; put a
  local shell at the joint station, or measure a slice there.
- **Named supports (exit 16).** AABB `zmin` is necessary but not
  sufficient on a multi-support prop: a wheel, a sled floor, or one
  planted foot can ground the box while the other feet float. Split the
  mesh into shells and assert each named support (shoe, tyre, foot) has
  its own `zmin` within epsilon of 0. `--short-legs` (or the piece's
  equivalent) is the falsifier: float the named supports while leaving
  something else on the ground so the AABB gate would still pass.
- **Joint-fit budgets.** Parts that interpenetrate on purpose — a tenon
  in a mortise, a peg in a hub — assert how deep the overlap goes, not
  just that it exists. Split the mesh into shells by edge connectivity,
  assert the expected shell count, and for each joint assert three
  named minima recomputed from vertex positions: the inserted part stays
  clear of the host's chamfer, it seats far enough past the host's near
  face, and it stops short of the host's far face. A part exactly as
  thick as its host passes a "parts overlap" test while erupting through
  the host's chamfer as a spike — that is the class this catches.
  Measure in the construction frame (un-rotate by any rake) so a tilted
  host does not inflate its own AABB.
- **Diagonal from stations (exit 17).** A brace, gooseneck or scroll is
  an oriented primitive or a tube between named host endpoints, not a
  hypot-length box rotated about its centroid. The centroid form is
  short of one host and punches through the other. `--short-brace` /
  `--float-spout` (or the piece's equivalent) is the falsifier.
- **Even shaping terms and mirror symmetry (exit 19).** Where a prop has
  mirrored members — two belts, two brackets, a pair of feet — every
  closed-form term in the host's shaping function must be **even** in
  the mirrored axis. `hay-bale` used `sin(x*24)`, which is odd, so its
  two belt stations sampled different surface heights and the wraps
  shipped 5.4 mm out of step; `cos` fixed it exactly. Assert it: pair the
  mirrored shells and compare their axis positions and extents within a
  named epsilon. A bounding box cannot see this, and neither can a
  per-member budget that only ever looks at one member.
- **Wrappers follow the host's profile, and the host is finished first
  (exit 16/18).** Build, bevel and **ground the host, then** hang the
  wrapper on the finished surface by raycasting the host's own
  cross-section at the wrapper's station. Placing a wrapper against
  half-built geometry and shifting everything afterwards leaves each one
  a different distance off the floor. A constant-section rectangle on a
  rounded host stands proud at the middle of each face and is swallowed
  at the corners — `hay-bale`'s belts stopped 2.9–8.3 mm above the floor
  with a visible notch, while the AABB `zmin` gate stayed green because
  the loaf grounded the box. Assert **per wrapper shell** that the loop
  passes under the host, not just that something touches Z=0.
- **Seat conformance (exit 18).** A band, hoop, strap or collar wrapped
  around a host asserts a **banded** seat depth — a minimum so it cannot
  float and a maximum so it cannot sink — sampled per angular segment
  rather than as a single global figure. Derive the wrapper's profile
  from the host's own radius function instead of a circle, and classify
  inner versus outer vertices against the host surface at each vertex's
  own angle. A global midpoint radius misclassifies outer chamfer
  vertices as inner ones the moment the host is out of round, which is
  how a hoop that visibly gapped on one side still passed.   The paired
  falsifier makes the wrapper a true circle on an out-of-round host.
  Measure the depth **station-locally**, along the vertex's own direction
  from the station axis — not by nearest-surface distance. A wrapper
  seated in a concave waist has its nearest host face on the bulge
  shoulder at a neighbouring station, and the wrap then reads as sitting
  10 mm outside a host it is in fact hugging. Bin the samples by
  **rounding** to the nearest station, never by flooring: a station on a
  bin boundary puts its inner and outer rings in different bins, and the
  inner-only bin reports the wrapper's outer offset as its seat depth.
- **Level sole on a raked leg (exit 18).** A raked stile does not sit
  in a world-axis cube. Build the sleeve in the member frame so it
  follows the rake; add the tread after the rake as its own
  axis-aligned plate, from Z=0 up to a height that covers the tilted
  sleeve. The member end stays inside the sleeve by a named bite and
  above the tread. `--short-stile` starts the member above the sleeve
  so the bite fails while the AABB zmin still passes.
- **Hung ring (exit 18).** A hitching ring is a torus whose center is
  the eye center plus the hang direction times the major radius, so
  the eye lies on the ring centerline, and the tube is thinner than
  the eye's inner radius. The shank stops in the top of the eye tube;
  continuing it to the eye center runs the pin through the ring. A
  torus parked on a face is not a hung ring. `--clip-ring` lifts the
  ring off that centerline. `--short-post` starts the post above the
  shoe cup so the seated-post budget fails (exit 19) while the sole
  still grounds the AABB.
- **Sampled host seat (exit 17/18 on scatter).** Instanced scatter
  seats by sampling the host surface Z at each instance's XY, biting a
  named depth, then clamping instance verts above the slab floor. A
  closed-form icosphere (or equivalent) replaces the GN cube so the
  scatter is stones, not open crates; a per-shell face floor is the
  budget that catches a cube leftover (exit 19). `--poke-rock` skips
  the clamp and over-bites; `--float-rocks` seats above the host.
- **Orthogonal members (exit 19).** Boards, planks or arms that should
  sit on a world axis assert their AABB secondary extent stays within a
  named bound of the member thickness. A closed-form yaw of 0.12 rad
  reads as an accident, not weathering. `--yaw-boards` is the
  falsifier. Fingerboard tips are a wedge whose base is the board's own
  thickness×height, bitten into the board so the base face is inside
  it — not a 45° cube of a different size glued on the end.
- **Wall-mount zmin (exit 16).** A wall sconce plants the plaque bottom
  at Z=0. Lifting every vert by a hanging height so the asset floats in
  its own space is not the same as placing it on a wall in the engine.
- **Plumb and real-world size (exit 19).** Assert that the axis of a
  turned or lofted body is vertical, by comparing the XY centroid of a
  bottom slab against a top slab — not the exact `zmin` and `zmax`
  rings, which may be a handful of vertices once a rim is notched or
  chipped. Separately assert the body's own diameter and height against
  the dimensions the README states in metres, with a named tolerance.
  The outer AABB does not cover this: on a prop with an appendage the
  AABB is the appendage, and the body can drift to any size underneath
  it.
- **Material face floors.** Every declared material asserts a named
  minimum face count on the finished mesh, recomputed from
  `polygon.material_index`. This catches the slot-assignment wipe class:
  `obj.data.materials.clear()` resets every polygon's `material_index`
  to 0 on some versions, which renders the piece single-material while
  the slot count still passes. Assign slots by index-preserving
  append/replace, never clear-and-rebuild.
- **Exit codes** are file-local: `0` success, argparse `2`, `3` and above
  in check order. `9` is legal. FATAL `sys.exit(1)` is a crash, never a
  named check. `15`–`19` are reserved across pieces for the hygiene
  family above: `15` hygiene, `16` grounded, `17` joint fit, `18` seat
  conformance and contact, `19` plumb and real-world size.
- **Shading is part of the model.** A flat-shaded low-poly body and a
  smooth-shaded one are different objects to a viewer. Smoothing a
  wobbled 36-gon erases every bit of surface modelling in it and leaves
  a featureless drum, so decide per part and say why. Nothing here is
  measurable, which is exactly why it has to be looked at.
- **Rendered still and gallery entry.** Showcase pieces are visual by
  definition. The pathology / sidecar exemption does not apply. Call
  `examples/gallery_framing.check_framing` on the `--output` path only.
  The `deviation=` parameter is gone; bleed compositions call
  `measure_framing_deviation` and assert at the call site. Do not move
  or modify `gallery_framing.py` — import it by resolving the repo root
  (see the shipping-crate script).
- **Contact sheet (required).** Composite the candidate hero beside the
  pinned calibration set — canonical membership is in `CLAUDE.md`
  § Quality Gates — commit it as
  `docs/gallery/contact-sheets/<name>-contact-sheet.webp`, link it in the
  PR body, and report a per-criterion verdict: stage darkness, wedge
  warmth, subject fill, saturation, thumbnail legibility, plus mean
  luminance against the calibration band. A claim without the committed
  composite is not evidence.

  Required because it has caught a real defect in showcase work. The
  first sheets for `crate-stack` and `stone-archway` showed both wedge
  pools reading as cool grey bands rather than the warm pool the house
  style calls for; both were relit as a result. Nothing else in the
  pipeline looks at the still beside its peers, so nothing else could
  have seen it.

- **Asset sheet (required).** Render the hero alone — neutral
  three-quarter view, plain studio lighting, no staging tricks, no
  labels, no comparison props — composite it beside the pinned
  asset-quality reference set rendered the same way, commit under
  `docs/gallery/asset-sheets/`, and report a verdict. The piece ships
  only if it is not identifiable as the least-designed object in that
  lineup.

  Required because showcase is *entirely* game props, which is exactly
  the scope `docs/VISUAL-STYLE.md` § Asset quality names, and because it
  covers something no other gate here does. Budgets measure geometry
  conformance; the contact sheet measures staged presentation. Neither
  removes the scene, and a strong scene carries a weak model. The
  recorded evidence is `socket-attach-points`: it passed every
  measurable floor on its first draft — `edge90` 0.000, ten materials,
  no default datablock names — and was then judged bad by eye and
  rebuilt from scratch. The floors scored the bevels, not the design.

  `examples/gallery_asset_quality.check_asset_quality` returns **11** on
  violation, the same call pattern as `gallery_framing`. Showcase
  numbering already spends 11 on the collider-triangle ceiling, so remap
  the return at the call site rather than letting two budgets share a
  code.

- **Composition.** The README names which shipped skills and snippets the
  piece composes. Duplicated helpers stay inlined or copied; showcase
  scripts do not import snippets as a package.

## Layout

```text
showcase/
  README.md              # this file
  gallery.json           # this tree's gallery index (pieces[])
  <name>/
    <name>.py
    README.md
    preview.webp
```

Hero stills live at `docs/gallery/assets/<name>-hero.webp` like examples.
`scripts/build_gallery.py` merges `showcase/gallery.json` into the same
`docs/gallery/` site as examples, tagged `showcase`.

## Smoke

`tests/smoke/catalog.json` takes opaque script paths. A showcase row is
enough; `blender-smoke.yml` has no path filter and runs the whole catalog
on every PR. Measure wall-clock before adding the next piece.
