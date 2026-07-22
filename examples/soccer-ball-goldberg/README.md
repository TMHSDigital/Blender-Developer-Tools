# Soccer Ball Goldberg

A runnable example that builds a soccer ball as a **Goldberg polyhedron**: a
bmesh icosphere truncated at exactly 1/3 of every edge, yielding the truncated
icosahedron — 12 pentagons, 20 hexagons — with every face ordered by walking
the source mesh's own link topology (fan walk per vertex, loop order per
triangle). Nothing is hand-listed, following
[`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md) and the
[`always-free-bmesh`](../../rules/always-free-bmesh.mdc) rule.

**Sibling, not twin:** [`bmesh-gear`](../bmesh-gear/) witnesses parametric
extrusion ownership (counts from construction parameters, watertightness).
This witnesses polyhedral topology invariants — the truncated icosahedron is
an Archimedean solid, so its counts, vertex degree, edge uniformity, face
planarity, and circumsphere are all closed forms — plus **per-face-class
material binding** driven by face vertex count, never by enumeration order.

**What it witnesses:** truncation at 1/3 makes every new edge the same length
(`a/3`), which is what puts all 60 vertices on one sphere. The check asserts,
with tolerances printed on success:

- **Counts and characteristic.** V=60, E=90, F=32, Euler `V−E+F==2` — the
  sphere topology. Catches a leaked or dropped face/edge/vertex (probe:
  one face deleted → exit 3, topology `(60, 90, 31)`).
- **Face census.** Exactly 12 five-sided and 20 six-sided faces (exit 5).
- **Uniform degree 3.** Every vertex touches exactly three edges, and every
  edge borders exactly two faces — the Goldberg dual property, watertight
  (exit 6/7).
- **Edge uniformity.** Max deviation from the mean length, measured
  **6.471e-06** against tol 3.0e-05 (exit 8). Catches a vertex dragged off
  the lattice (probe: one vertex shifted 0.05 → exit 8, deviation
  **4.726e-02**, three orders of magnitude over tolerance).
- **Face planarity.** Worst vertex-to-plane distance **1.888e-06** against
  the same tolerance, measured against an independent Newell normal — not
  Blender's polygon normal (exit 9).
- **Circumsphere.** Centroid on the origin (`0.000e+00`, tol 1e-6) and every
  vertex equidistant from it: max deviation **8.956e-06** (exit 10/11).
- **Panel binding by class.** Exactly two materials; every 5-gon carries
  slot 1 (black), every 6-gon slot 0 (white). The builder assigns by
  `len(poly.vertices)`, and the check re-derives the expectation the same
  way — so an enumeration-order shortcut fails (probe: last-12-faces-black →
  exit 13, **24 misbound faces**; inverted classes → exit 13, **32
  misbound**). Enumeration order coinciding with class order is a
  construction artifact, not a contract — the check exists for the cases
  where it doesn't.

**Tolerance basis:** mesh coordinates are float32 and `create_icosphere`'s
own trig lands the invariants at a deterministic ~9e-6 noise floor (measured
values are byte-identical on 4.5.11 and 5.1.2). The 3e-5 gates sit ~3x above
that floor; any genuine contract break is orders of magnitude larger.

**Version witness:** check output is byte-identical on Blender 4.5.11 LTS and
5.1.2 — same counts, same deviations. One authoring hazard surfaced and is
noted in the code: `Object.to_mesh_clear()` takes **no argument** on current
Blender (passing the mesh raises TypeError) — see
[`depsgraph-and-evaluated-data`](../../skills/depsgraph-and-evaluated-data/SKILL.md).

The render is the proof: the faceted Goldberg cage is smoothed by an
**unapplied** Subsurf modifier (panel materials carry through Catmull-Clark
per face class), and the ball is grounded by its depsgraph-evaluated lowest
vertex — center-at-circumradius floats the ball, because the smoothed surface
sinks toward the face inradii. Invert the panel binding and the still
inverts with it: white pentagons on a black ball, wrong on sight.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python soccer_ball_goldberg.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python soccer_ball_goldberg.py -- --output ball.png
blender --background --python soccer_ball_goldberg.py -- --output ball.png --engine cycles
```

It exits non-zero on failure (topology, census, degree, edge uniformity,
planarity, circumsphere, or panel binding). The `blender-smoke` workflow runs
the check on Blender 4.5 LTS and 5.1.
