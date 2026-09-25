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
  `--flush-tyre` / `--stand-posts` restore a flush surface so the
  coplanar budget fails (exit 15). `--float-wheel` / `--float-stone`
  lift one named support while the rest still ground the AABB (exit 16).
  `--sink-tyre` / `--shallow-tenon` put a seat outside its band (exit
  18). `--drop-bucket` hides the hung subject (exit 18).
  `--skew-wheel` / `--turn-posts` break a mirror or placement budget
  (exit 19). `--float-rivets` lifts fasteners off their host (exit 18).
  `--round-haft` turns an oval section round (exit 19).
  `--float-nails` lifts nail heads off their strap (exit 18).
  `--short-mortar` stops every mortar joint shy of its stones (exit 18).
  `--open-ends` restores open U-band ends so the water is not contained
  (exit 18). `--pile-rocks` draws scattered stones together so they
  interpenetrate (file-local code; `terrain-scatter` uses 20).
  `--straddle-handle` mounts a fixture across a board gap (file-local
  code; `shipping-crate` uses 20). `--odd-loaf` breaks a body's own
  mirror symmetry (exit 19). `--lift-lid-bands` floats bands off a
  curved host (exit 18).
  `--sharp-iron` skips a chamfer pass so the edge-treatment budget fails
  (file-local code; `crate-stack` uses 21).
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
  only the radius. A falsifier that thickens a member scales **only the
  axis its budget measures**: `chopping-block`'s `--fat-haft` scaled the
  whole haft section, and once the section became an oval the swing-plane
  width grew the knob 16 mm past the bounding box, so it exited 8
  instead of 17 on eye clearance. Scaling across the cheeks alone
  restored exit 17 with the identical measured clearance.
  `tests/check_falsifier_targets.py` checks the
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
  seats by sampling the host surface, then clamping instance verts above
  the slab floor. A closed-form icosphere (or equivalent) replaces the GN
  cube so the scatter is stones, not open crates; a per-shell face floor
  is the budget that catches a cube leftover (exit 19). `--poke-rock`
  skips the clamp and over-bites; `--float-rocks` seats above the host.
- **A seated part is sealed all round (file-local code).** Sampling the
  host once, at the part's centre, and biting the lowest point below it
  leaves daylight under the downhill side of anything on a slope:
  `terrain-scatter`'s stones were sealed in at most 6 of 8 sectors, two
  in only 4, and the gap showed in the ground-contact view. Split the
  azimuth around each part's centroid into sectors, sample the host
  under every vertex (a ray down onto the host alone), and sink the part
  until each sector's most-buried vertex is below the ground. Assert
  every part is sealed in every sector. The falsifier restores the
  centre-sample rule (`--perch-rocks`).
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
- **A band is hooped onto its host, never set flush against it (exit
  15/18).** A tyre, ferrule, hoop or collar derives its **inner** radius
  from the host's **outer** radius minus a named interference, and its
  outer radius from the host plus its own thickness. Writing
  `r_mid = host_out + t/2, radial_t = t/2` — the obvious spelling —
  makes the band's inner cylinder and the host's tread the *same
  surface*, so every segment is a coplanar cross-shell pair around the
  whole circumference. `cart` shipped that way and measured 32 pairs
  (16 per wheel); the speckle was visible on the committed hero and in
  a clay pass, and no budget could see it. `--flush-tyre` restores the
  equality and is the falsifier.
- **A member is tenoned into its seat, never stood on it (exit
  15/18).** A post, leg or stile whose bottom face lands exactly on its
  host's top face puts both on one plane. Derive the member's bottom
  from the host's top minus a named seat depth, and hold the member's
  *top* fixed so nothing above it moves. `stone-well` stood its four
  roof posts on the coping and measured 4 pairs, one per post.
  Assert the seat as a **band** recomputed against the host surface read
  off the generated mesh — `max z` over the host's material — not
  against the constant the builder used, which witnesses nothing.
- **Posts go under the roof's corners, not the middle of its eaves
  (exit 19).** Where a hip or pyramid roof is carried on four posts,
  assert each post's plan bearing against a hip corner **recomputed from
  the generated mesh**, as a wrapped angular difference. Take the
  corners from the *pooled* vertices at the eave line: pulling them from
  a single shell picks one fascia board, whose own extremes sit 90° off
  the corners it is nailed to, and the budget then fails on a correct
  model. `stone-well` placed its posts on the axes, which cantilevered
  the roof's corners 0.80 m and stood one post dead centre in the well
  mouth in every orthographic view.
- **A roof is sized from what it must cover, not from what carries it.**
  Deriving the eave reach from the post ring plus an overhang gave
  `stone-well` a 1.64 m roof over a 1.08 m drum — an umbrella. Derive it
  from the covered body's own radius plus a named clearance
  (`EAVE_HALF = R_OUTER + CURB_OUT + EAVE_CLEAR`), and let the overhang
  fall out of that. Expect the convex-hull collider budget to move when
  the roof does; re-fit it and say so.
- **The subject hangs where it can be seen (exit 18).** A prop whose
  story is one small part — a bucket on a rope, a lantern on a hook —
  asserts that part's clearance above the body it hangs over, as a band,
  measured against the body read off the mesh. `stone-well`'s bucket sat
  down the shaft with only its rim level with the coping: invisible in
  the hero and in all six orthographic views, and no budget noticed.
  `--drop-bucket` is the falsifier.
- **Mirrored assemblies (exit 19).** Where a prop has a left and a
  right of the same part — two wheels, two brackets — pair the shells
  and assert they match in the two axes they share and in their extents,
  within a named epsilon, and are opposite in the mirrored axis. Size
  the falsifier's displacement to stay **inside** `BBOX_TOL` so the AABB
  gate cannot steal the failure: `cart`'s `--skew-wheel` moves one wheel
  6 mm along a track whose tolerance is 10 mm.
- **Segment counts are a silhouette budget, not a triangle budget.** A
  16-gon felloe reads as a polygon at hero size, and the flat facet
  facing the key light renders as a hard white plate. `cart` went to 24
  and the chords disappeared. Re-fit the triangle band around the new
  measured count rather than leaving the old one — and prefer a band
  *narrower* than the one it replaces, centred on the measurement.
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
  smooth-shaded one are different objects to a viewer, so decide per
  part and say why. Facet what is faceted in life — a chamfered axe
  head, a dressed stone. Do not facet an organic or turned surface with
  equal facets: `chopping-block`'s flat-shaded 36-gon log read as
  coopered staves and the whole block as a tub, and its flat-shaded iron
  hoop threw one highlight per facet, a row of piano keys. Smooth those
  and carry the surface — bark furrows, growth rings, drying checks — in
  the material, while the wobble keeps reading in the silhouette. Mark
  every material boundary as a hard edge so a sawn rim stays crisp
  against the bark. Nothing here is measurable, which is exactly why it
  has to be looked at.
- **One substance, one material slot.** A part made of something else
  gets its own slot and its own face floor, even when the colours are
  close. `chopping-block`'s hickory haft shared the bark slot, which made
  the handle the darkest wood on the piece and would have fissured it
  with the bark texture.
- **Fasteners are aimed down the host's surface normal (exit 18).** A
  rivet, bolt head or stud on an out-of-round host takes its axis from
  the normal of the host's own surface function at its station — not
  the radial — and its station is a host section, so the surface under
  it is exact rather than a chord. Assert the seat per fastener as a
  band measured radially at each vertex's own angle against the host
  read off the mesh, plus a proud minimum so the head is visible.
  `chopping-block`'s radially aimed rivets seated 1.87 and 2.82 mm
  against a 1.5 mm design bite, one edge sunk and the other lifted,
  because the log's wobble drops the surface 1.4 mm across one head.
  Aimed down the normal both seat at 1.50–1.54 mm. `--float-rivets` is
  the falsifier.
- **Edge treatment: no right angles (file-local code).** Real objects
  have chamfers that catch light. Where every box in a piece is
  chamfered, count manifold edges whose faces meet within 5° of 90° and
  assert **0** — a one-segment chamfer turns every 90° edge into two 45°
  ones, so a survivor is a bevel pass that was skipped. Chamfer thin
  stock at its own offset: `crate-stack`'s 3.5 mm iron takes 0.8 mm,
  where the timber's 1.8 mm would leave no flat. Pass `material=` to
  `bmesh.ops.bevel`: left at its default the chamfer faces took slot 0,
  and the iron plates rendered — and were classified — as timber.
  `--sharp-iron` is the falsifier. 15–19 are reserved, so the code is
  the piece's next free one.
- **A rim over a slope is bounded by its tilt step (file-local code).**
  The count above assumes box edges. Where a curved or sloping surface
  turns down into a wall — a terrain tile's edge, a mound's skirt — the
  fold runs from well under 90° to well over it, so bevel it with enough
  segments and bound the largest step in normal elevation between
  adjacent faces. Use elevation, not the dihedral: at a tile's corners two
  chamfer strips meet at a right angle in plan, which is a rounded
  corner, not a knife. Bevel gives the middle folds twice the end ones,
  so two segments leave 45° of a 90° edge in one step. The falsifier
  skips the bevel (`--sharp-rim`).
- **An L-section is one shell, not two boxes (exit 15).** Two
  overlapping boxes for the legs of an angle strap share the outer
  corner edge; chamfer them and both lay a strip on the same line — a
  coplanar cross-shell pair at every corner (`crate-stack`: 12). Extrude
  the L profile once, each cap as two convex quads meeting on the
  inner-corner diagonal, and skip that flat diagonal in the bevel.
- **Classify small parts by a size derived from the host.** A nail,
  rivet or stud told apart from its plate by world-AABB extent needs a
  threshold taken from the plate (`IRON_WRAP * 0.5`), not from the
  fastener: a yawed 10 mm head has a world AABB wider than 10 mm, and a
  fixed 10 mm threshold silently dropped 8 of 48 nails.
- **A joint is filled, not open (exit 18).** Masonry, brick and
  stacked-stone pieces separate their blocks with a named joint, and a
  joint left as air is a stack of floating blocks with daylight through
  every course. `stone-archway` shipped that way: 7 mm bed joints and
  9.7 mm voussoir joints, none of them touching. Fill each joint with its
  own mortar shell, sized from the two blocks it sits between, recessed
  behind their faces by more than the chamfer so it reads as a raked
  joint, and biting a named depth into both. Assert every mortar shell
  BVH-overlaps **exactly two** stones — one means a bed left hanging,
  none means the air gap came back. Keep the mortar shells out of any
  classifier that names stone parts; left in, a bed classifies as a
  course and every downstream stone budget measures the wrong
  neighbour. Add mortar after the chamfer pass, unchamfered: a 6 mm
  chamfer on a 10 mm bed eats it.
- **A vessel holds its contents (exit 18).** A trough, tub, barrel or
  bucket that shows a liquid must close every side of it. Touching the
  hull is not holding: `water-trough` passed a water-to-hull gap budget
  for a whole release with open U-band ends and the water's flat end face
  on show. Assert containment by casting rays outward from across each
  exposed face of the contents — perimeter **and** interior points, since
  a rim band covers the perimeter only — and require every ray to hit the
  vessel within a named reach. `--open-ends` is the falsifier.
- **Scattered parts do not interpenetrate (file-local code).** Jittered
  scatter pushes neighbours into each other, and nothing else in the
  hygiene family compares one scattered part with another. BVH-test every
  pair and assert **0** overlaps. Space the parts structurally: relax
  each pair of centres apart to the sum of the two parts' own radius
  bounds, each **derived** from the same constants that size that part,
  so scaling a part widens the spacing around it. A falsifier that only
  skips the relaxation proves nothing if the parts happen to miss anyway;
  `terrain-scatter`'s `--pile-rocks` also draws the scatter inward so
  collisions are guaranteed.
- **Scatter varies in size (file-local code).** Nine stones within 20%
  of one size, on a relaxed grid, read as planted. Give each scatter
  point a size factor (boulders among cobbles), and assert the ratio of
  the largest to the smallest footprint clears a floor. The falsifier
  sets every factor to 1 (`--uniform-rocks`).
- **Assert a body's symmetry on the body (exit 19).** Where mirrored
  parts are hung on a body, the body itself must be mirror-symmetric:
  give every vertex a partner at its mirror position within a named
  epsilon (a KD-tree lookup). A budget on the hung parts sees an odd
  shaping term only second-hand. **Triangulate non-planar quads along
  their short diagonals** before raycasting a body or shipping it: a
  fixed split is not mirror-symmetric, and `hay-bale` sampled surfaces
  5.6 mm apart at mirrored stations on vertices that matched to 71 um.
  Apply an odd-term falsifier *after* any angle-selected bevel, or the
  asymmetry changes which edges the bevel picks and the bounding box
  fires first.
- **Bands on a curved host are built on the host's arc (exit 18).** A
  band on a vault, drum or hoop is one slab on the host's own radius
  function, with the host's segment count, not a chain of boxes rotated
  per segment. Rotating a box to a circle's tangent at angle `t` about X
  needs `-t` when the arc is parameterised as `(sin t, cos t)`, and
  `treasure-chest`'s `+t` fanned every segment out like feathers. Assert
  the band radially in the host's construction frame, un-rotating any
  hinge swing and undoing any re-centring from a part known to be
  symmetric.
- **A fixture is mounted on a member, not across a gap (file-local
  code).** Handles, hinges, hasps and plates screwed to planked faces
  must land on one board. A height fixed as a fraction of the frame lands
  wherever the plank layout happens to put a gap: `shipping-crate`'s
  handle plates sat across the slot between two end boards. Snap the
  fixture to the centre of the nearest board, from the same layout
  function that places the boards, and assert each mounting plate sits
  inside a single board's extent with a named clearance at both edges.
- **Rock is broken, not smooth.** A smooth-shaded ellipsoid is an egg.
  Cleave it with a few closed-form planes (project every vertex beyond a
  plane onto it) and shade it flat, so it reads as broken stone. Cleaving
  takes volume off, so re-check scale against the host afterwards.
- **Keep a falsifier's envelope still.** A falsifier that moves the
  support the piece grounds on re-grounds the whole piece and moves the
  AABB with it. `water-trough`'s `--short-legs` lifted the shoes; the
  piece re-grounded on the legs and shrank 10 mm against a 10 mm
  tolerance, so a 1.5 mm model change tipped it from exit 16 to exit 8.
  Make the falsifier move only what its budget measures — the shoes
  float, the legs stretch to the floor — and check its AABB delta against
  the tolerance, not just its exit code. Re-check it whenever a design
  change moves which part sets the envelope. `hay-bale`'s ridge dropped
  from 14 mm to 6 mm, which made the knot loops the top of the box. The
  twine falsifiers, sized at 20 mm and 10 mm when the loaf's crest was the
  top, then lifted the knots past `BBOX_TOL` and exited 8. The fix was to
  size each one to its own budget, 8 mm against a 6 mm wrap gate and 6 mm
  against a 2 mm seat floor, never to widen the tolerance.
- **Stone is not noise stretched over a block.** A noise-driven colour
  mix sampled so its features streak read as wood grain on
  `stone-archway` at hero scale. Stone wants isotropic object-space
  mottling, fine speckle driving roughness and a small bump, and a
  seeded tone per block as a face attribute so no two stones match.
  Chain a baked normal map *under* that bump rather than replacing it.
- **Identical boards read as CG.** Planks cut from one material are one
  plank repeated. Give each shell a seeded tone and its own grain
  direction — its long axis, recovered from its vertices — as face
  attributes, and have the shader stretch its grain along that axis
  rather than a world axis, which a yawed member is off by its yaw.
  Nothing here is an assertion; it is found on the inspection sheet.
  The same holds for coopered staves: `wooden-barrel` and `wooden-bucket`
  were one flat tone until each stave got its own. Hoops are forged iron,
  dark and rusted, not the bright polished metal both pieces first shipped
  with.
- **A head or bottom is boards, not a slab (exit 17).** A barrel head or
  bucket bottom cut from one disk reads as a lid. Cut the croze outline
  across into boards with a named seam, so every board's outer edge is
  still the croze and the seat does not change. Assert the board count and
  that every seam lies in a band. Classify boards by their span in plan,
  not by a radius: a quarter of the head's width is smaller than any
  "round" test built for the whole disk. `--one-piece-head` /
  `--one-piece-bottom` are the falsifiers.
- **Rope is laid, not piped.** A smooth tube with a rope material is a
  plastic hose. Loft a three-lobed section and turn it one vertex step per
  ring, so each lobe winds along the path as a strand. That costs the same
  triangles as a round section of the same count. Fix the section's frame
  to the path's plane, or the lay jumps where the path turns vertical.
- **What passes through a part must clear its mount (exit 17).** A bail
  through an ear ring has to clear the plate the ring hangs on. Ring
  offsets sized to the ring (`RING_MAJOR * 0.25`) put the rope's axis 3 mm
  off the plate and its body through it. Size the offset from the thing
  passing through, and assert that no vertex of it lies inside the mount.
  `--sunk-rope` restores the old offset.
- **Variation goes into surface, never into function (exit 19).** A
  ladder's rung heights were jittered up to ±18 mm for "variation"; a
  climber's feet find rungs blind, so the pitch is part of what a ladder
  is. Jitter tone, grain and a few percent of turning, not spacing that
  something uses. Assert the pitch (every gap within a tolerance of the
  mean); `--drift-rungs` restores the old heights.
- **A plank wall is boards, and extra boards are paid for (exit 17).** A
  tray wall cut from one slab beside a planked floor reads as a box.
  Stack it from boards with a named seam, let the audits that find walls
  take the union of a wall's boards, and assert count and seam. If that
  breaks the triangle ceiling, take the triangles back from faces nobody
  sees (bottoms buried in a seat, undersides facing the chassis) rather
  than raising the ceiling. The falsifier keeps the triangles
  (`--wide-seams`), so it cannot trip the triangle floor instead.
- **Sort bmesh operator inputs.** A Python `set` of `BMEdge`s iterates in
  memory-address order. Handed to `bmesh.ops.bevel` it gives the same
  geometry in a different face order from run to run, which the
  `mat_index_counts` print exposed on `wooden-ladder`. Call
  `bm.edges.index_update()` and sort by index first.
- **A band wraps its host; it is never sunk into it (exit 18).**
  `hitching-post`'s bands were sized from the post's inner offset, so they
  sat inside the post and only the chamfered corners broke the surface,
  as black slits. Size a band from the host's face: inner face a named
  bite inside it, outer face proud of it. Assert the band's outer
  half-width against the host's (`--sunk-bands`). An overlap test alone
  passes a sunk band, because a sunk band overlaps too.
- **A forging is not a turning (exit 19).** A lathed, elliptical waist
  under a rectangular anvil face reads as a funnel. Loft forged parts from
  a squared section (a superellipse) and assert it: corner reach, how far
  a section vertex fills its bounding rectangle's corner, is 0.707 for an
  ellipse. `--round-waist` is the falsifier.
- **Paint wears through to what is under it.** A painted board is one
  flat colour until a mask lets the wood show at the edges and pores;
  shade the paint per board.
- **Iron is not chrome.** Cast and forged iron is near-black or rusted
  and rough. Metallic 1.0 with roughness under 0.4 reads as polished
  steel or plastic (`hand-pump` read as chrome).
- **The stage is bigger than the frame.** A 14 m set lets the back
  wall's edge into the corner of a three-quarter hero. Use 60 m.
- **A leaning prop is staged against something.** A ladder raked 12° in
  open air reads as falling. Render-only: put a wall section on the side
  it rakes toward, with its face through the top, and turn the piece so
  that side faces away from the camera.
- **A ring is threaded across its hole, never in its plane (exit 17).**
  `iron-cauldron`'s ear rings stood in the bail's own plane, so the bail
  ran through each ring's tube. Orient a ring so its hole axis follows
  whatever passes through it at that point. Assert that no ring vertex
  lies inside the thing passing through, by the nearest face's normal,
  and that it passes within the hole. `--edge-on-ears` is the falsifier.
- **A vessel has a base and a belly (exit 19).** A profile interpolated
  from a tiny bottom radius runs to a point: the cauldron was an onion.
  Build the belly from a stated base radius and belly height, offset the
  inner wall along the profile's normal (a sideways offset thins the
  wall to nothing where it runs flat), and assert the base radius and
  where the widest ring sits. `--pointed-pot` is the falsifier.
- **Stones are lumps, and no two match (file-local code).** A curved
  brick with a flat top reads as a kerb. Loft a chamfered section that
  swells mid-stone and pinches at capped ends, with seeded radial offset
  and a crown on the top course. Keep the beds flat so courses still
  seat. Assert the spread of stone radii (and top-course crowns) clears a
  floor; the falsifier gives every stone the same draw at the jitter's
  upper bound, so the envelope stays put (`--uniform-stones`).
- **A section that carries the read is a budget (exit 19).** Where a
  cross-section is what makes a part recognisable — an axe handle is
  oval, a broom handle is round — assert it as a ratio band at a named
  station, measured in the construction frame from a slab that holds
  exactly one ring. `--round-haft` is the falsifier.
- **A brace joins two members (exit 17).** A diagonal that stops in
  the air is a peg, not a brace. Assert that both ends reach past the
  inner face of the member each tenons into, measured per side, and
  count the braces so a classifier that silently drops one (a level
  brace fails a "diagonal" shape test) cannot pass vacuously. The
  falsifier stops one end short inside the envelope (`--short-brace`).
- **A joint bites; touching is not joining (file-local code or 17).**
  A BVH gap of zero is satisfied by one grazing bevel corner, which reads
  as a loose stick. Where a member tenons into another, assert the
  deepest vertex of the member inside the host shell (signed distance to
  the host's surface), at every end. Run it after plumb so a raked host
  reports as plumb. `--shallow-brace` (street-lantern) restores the
  grazing ends.
- **A platform bears on something (exit 17).** Every deck, floor or shelf
  needs bearers that tenon into the frame, and every joist must sit in a
  bearer at both ends. Count the bearers and joists so a dropped member
  cannot pass vacuously, and aim the falsifier at the joist span with
  the bearers kept, so the triangle floor and envelope do not steal it
  (`--short-joists`, watchtower).
- **A bent bar is one sweep (file-local code).** Wrought iron that bends
  from a foot into a post, or from a post into a back, is one bar. Sweep it
  along one path with parallel-transported frames. Do not stand a post on a
  separate foot arc. `park-bench` built its scroll feet that way, stopped
  each arc 8% short, and started each post at the arc's top. That left
  14 mm of daylight under all four posts. A BVH gap budget can't see this,
  because the toe still grounds and the post still meets its stretcher.
  Assert it from shells instead: the shell under each toe station must be a
  leg that reaches the seat. `--split-feet` is the falsifier.

  The same holds for timber that carries a load end to end. A barrow's
  shaft is the handle, the bearer under the tray and the fork, in one
  piece. `wheelbarrow` built it as three boxes and hid the middle one
  exactly under the tray's side wall, so the handle appeared to stop at
  the tray corner and the tray to carry everything. Sweep it through its
  stations with mitred joints, route it where it can be seen, and assert
  the count of shells that span the whole run (`--split-shafts`).
- **A tray that tips is a hopper, not a box (file-local code).** Build a
  tray, bin or trough that is emptied by tipping from a bottom outline
  and a top outline: flared sides, a raked tipping end. Each wall is the
  planar band between its two edges, the end boards housed into the
  sides. Measure the lean from the boards' own largest faces and assert
  a floor; the falsifier stands the walls vertical on the same top
  outline, so the envelope and size budgets stay put (`--box-tray`).
- **Measure a leaning board in its own plane.** A flared or raked board's
  outer face sits lower than its inner one, so AABB tests lie: a seam in
  Z between two stacked boards reads negative, and a zmin seat reads the
  outer bottom edge. Take each wall's up direction from its boards' largest
  face and measure seams along it; seat the wall on its lowest board's
  inner face. Derive both from the mesh, not the build constants, or the
  box-tray falsifier trips the seam gate first.
- **A carried member bites its carrier, measured where the vertices are
  (file-local code).** A slat on a rail, a back slat on an upright and an
  armrest on its leg each assert an overlap depth against a named minimum,
  and a count of the members, so a dropped slat cannot pass vacuously. A
  round rail has vertices only at its end rings, so the deepest rail vertex
  inside a mid-span slat is nowhere near the slat. Take the overlap either
  way round: under a slat, the slat's corner sits in the rail. Where neither
  member has a vertex at the crossing — a brace over a rail, mid-span — read
  both faces off the mesh and compare the planes, only where their heights
  overlap. `--float-slats` and `--float-brace` are the falsifiers.
- **A kit section fits its tile (file-local code).** A section that claims
  to tile at a pitch asserts its width along that axis is at most the tile
  and within a named band of it. Derive the post stations from the tile
  minus the reach of whatever is proudest, not from the post's own half
  width. `fence-kit` placed its posts from the post width alone. Its iron
  bands then stood 12 mm past each end, so adjacent copies interpenetrated
  by 24 mm, while its README said the width *was* the tile. `--wide-tile`
  restores the old stations. Check it before the AABB gate, or the envelope
  check fires first.
- **A fixture is bolted to the face it is seen on (file-local code).** A
  wall plate seated on the backing slab, behind the face of the stones
  laid over it, is buried: `wall-torch` showed only its four bolt heads.
  A plate-to-plaque gap budget passed, because the plate still touched the
  slab. Derive the seat from the proudest face (`stone_face_y()`), and
  assert two things from the mesh: the fixture stands proud of that face
  by a named minimum, and its back bites the face within a band.
  `--sink-plate` restores the old seat.
- **A ferrule grips the leg on the leg's axis (exit 18/20).** A vertical
  cup on the floor under a splayed leg can't hold it. The leg either
  saws through the wall or, as `tavern-stool` shipped, stops above an open
  ring with air around the foot. Build the sleeve on the leg's own axis,
  with its inner radius a named grip inside the leg. Bury its raked bottom
  in a level tread, and end the leg inside the sleeve above the tread.
  Measure the grip radially about the leg's principal axis, not by
  nearest-face signed distance: points in an open sleeve's hollow read as
  inside its wall.
- **Bake texels per UV cell (file-local code).** One UV cell per face
  and a 256 px bake gives a 1,700-face piece about 6 px per cell. The
  render's bilinear lookup then reads the next cell's normals across the
  border, as dark slivers on the hero (`tavern-stool`). Assert the smallest
  UV cell's extent in baked texels, from the mesh's UVs and the image's
  actual size, against a floor (12 px). `--low-bake` bakes at 256 px and
  is the falsifier.
- **Level on the stage.** A hero that tilts the piece about X, even by 2°,
  sinks one row of feet into the floor and lifts the other. Turn the piece
  only about Z.
- **Laid stone and cut timber vary piece by piece.** One flat grey on
  every stone reads as a moulded ring; one brown on every member reads
  as a single casting. Drive a per-shell tone (`PlankTone`) and, for
  wood, grain along each shell's long axis (`GrainDir`) from face
  attributes, seeded so the render is the same every run.
- **One connected assembly (exit 18, file-local).** Every joint in a
  piece is a bite, so joined members' surfaces cross. Build a BVH per
  shell, union the shells whose trees overlap, and assert **one**
  component. Per-part budgets pass a box resting a hair above its rails,
  because every plank still touches a wall. The contact graph shows the
  box as a second component. `cart`'s `--lift-bed` raises planks, walls
  and straps 7 mm and splits the graph in two.
- **A z-fight budget matches planes, not centres (exit 15).** A test that
  counts only faces whose centres coincide within 0.1 mm never fires on a
  real overlap. `grindstone` reported 0 for a whole release while its iron
  shoes, exactly as wide as the sill and flush with its end, shared three
  planes with every sill (a lit slit in each foot close-up). Use the
  cross-shell coplanar budget above, with a KD-tree range query at
  `COPLANAR_CENTRE_MAX` so it stays linear on a 5k-triangle piece. A shoe,
  cap or ferrule is a cup a named reveal proud of its host on every side;
  `--flush-shoes` restores the flush shoe.
- **Braces that meet tenon into the host's faces (exit 15).** Two
  diagonals run to the same centre line meet at one apex. Their chamfered
  end faces then land on each other inside the host: 6 coplanar pairs on
  `grindstone`, hidden in the bearing block. End each one a named bite
  inside the king post's face.
- **Carried parts bite their bearers (exit 18).** A tub, bed or shelf
  asserts how deep it bites each member that carries it, as a band, with
  the bearers counted. Stretchers left at sill height stopped 6 mm under
  `grindstone`'s trough, a dark slit that the sill seat and the dip band
  both passed. `--low-stretchers` restores them.
- **Chamfer n-gon caps, then triangulate.** A triangle-fan cap on a
  lathe, chamfered 5 mm at its rim, folded its centre out through the cap:
  8 non-manifold edges per nave on `cart`. An L-strap cap pre-split on its
  inner-corner diagonal left 24 per strap once the reflex corner was
  chamfered. Build caps as single n-gons, run the bevel passes, then
  `bmesh.ops.triangulate` every face over four corners, so the shipped
  mesh still has no n-gon.
- **The bake cage is narrower than the nearest neighbour.** `cage_extrusion`
  only has to cover the difference between high and low, under 2 mm for
  a chamfer. At 0.08 m, `cart`'s cage reached past the 74 mm between a
  side wall and its wheel. Rays from the wall hit the high-poly felloe,
  and the rim baked onto the board as a black staircase that no budget
  measures. Raising the bake resolution made it sharper, not smaller.
  Start from 0.01 m and look at the hero.
- **Aim an edge falsifier at one member.** Skipping a whole chamfer pass
  moves the triangle count by hundreds: `cart`'s whole-iron skip dropped
  1200 and exited 4 on the triangle floor. Leave one small member square
  instead (`--sharp-bar`, `--sharp-handle`, 20–24 right-angle edges and
  about 48 triangles), so only the edge budget can see it.
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
