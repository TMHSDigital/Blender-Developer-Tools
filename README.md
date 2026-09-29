<h1 align="center">Blender Developer Tools</h1>

---

<p align="center">
  <strong>Skills, rules, snippets, templates, and runnable examples for Blender Python development</strong>
</p>

<p align="center">
  <a href="https://github.com/TMHSDigital/Blender-Developer-Tools/releases"><img src="https://img.shields.io/github/v/release/TMHSDigital/Blender-Developer-Tools?style=flat-square&color=e87d0d&label=release" alt="Release" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-CC--BY--NC--ND--4.0-384d54?style=flat-square" alt="License" /></a>
</p>

<p align="center">
  <a href="https://github.com/TMHSDigital/Blender-Developer-Tools/actions/workflows/validate.yml"><img src="https://img.shields.io/github/actions/workflow/status/TMHSDigital/Blender-Developer-Tools/validate.yml?branch=main&style=flat-square&label=validate" alt="Validate" /></a>
  <a href="https://github.com/TMHSDigital/Blender-Developer-Tools/actions/workflows/blender-smoke.yml"><img src="https://img.shields.io/github/actions/workflow/status/TMHSDigital/Blender-Developer-Tools/blender-smoke.yml?branch=main&style=flat-square&label=blender%204.5%20%2B%205.2%20smoke" alt="Blender smoke tests" /></a>
  <a href="https://github.com/TMHSDigital/Blender-Developer-Tools/actions/workflows/drift-check.yml"><img src="https://img.shields.io/github/actions/workflow/status/TMHSDigital/Blender-Developer-Tools/drift-check.yml?branch=main&style=flat-square&label=drift-check" alt="Drift check" /></a>
</p>

<p align="center">
  <strong>16 skills</strong> &nbsp;&bull;&nbsp; <strong>9 rules</strong> &nbsp;&bull;&nbsp; <strong>3 templates</strong> &nbsp;&bull;&nbsp; <strong>27 snippets</strong> &nbsp;&bull;&nbsp; <strong>60 examples</strong> &nbsp;&bull;&nbsp; <strong>60 showcase pieces</strong>
</p>

<p align="center">
  <a href="https://tmhsdigital.github.io/Blender-Developer-Tools/gallery/">Examples Gallery</a>
  &nbsp;&bull;&nbsp; <a href="#quick-start">Quick start</a>
  &nbsp;&bull;&nbsp;   <a href="#examples">Examples</a>
  &nbsp;&bull;&nbsp; <a href="showcase/">Showcase</a>
  &nbsp;&bull;&nbsp; <a href="skills/">Skills</a>
  &nbsp;&bull;&nbsp; <a href="rules/">Rules</a>
  &nbsp;&bull;&nbsp; <a href="templates/">Templates</a>
  &nbsp;&bull;&nbsp; <a href="snippets/">Snippets</a>
  &nbsp;&bull;&nbsp; <a href="ROADMAP.md">Roadmap</a>
</p>

---

## Overview

This repository ships **16 skills, 9 rules, 3 templates, 27 snippets, 60 examples, and 60 showcase pieces** for Blender Python development targeting Blender 5.2 LTS (current stable) with Blender 4.5 LTS fallback support. Blender 5.1 is prior stable.

The content is consumed by AI coding agents reading these files directly from a checkout — **there is no MCP server in this repository, and none is required**. Cursor applies `rules/*.mdc` automatically wherever their scope globs match and takes skills by name in chat; Claude Code reads `skills/` and `rules/` from the project workspace, or from this repo kept as a referenced checkout. Any agent that can read files in a workspace can use it the same way. There is no build step for the content — edit the Markdown and Python files directly.

| Layer | Role |
| --- | --- |
| **Skills** | Guided workflows: scaffolding, operators, panels, properties, mesh and bmesh, headless batch, slotted actions, geometry nodes, procedural materials, depsgraph queries, drivers and handlers, `bl_info` migration, video sequencer, imported-mesh cleanup, engine export presets |
| **Rules** | Guardrails for the most common AI mistakes: ops-in-loops, bmesh leaks, legacy `bl_info` only, prop assignments, deprecated context-copy override, per-element loops over bulk mesh data, import without scale check, export without evaluated geometry, mixed glTF/FBX axis RNA |
| **Templates** | A working Extensions Platform add-on starter, a headless batch script starter, and a GLB-in engine-ready asset pipeline |
| **Snippets** | 27 small standalone Python files demonstrating canonical patterns |
| **Examples** | Runnable headless scripts under [`examples/`](examples/). Each asserts an API contract and exits non-zero on failure. |
| **Showcase** | Budget-conformance props under [`showcase/`](showcase/). Not examples. Conventions: [`showcase/README.md`](showcase/README.md) |

## Quick start

```bash
git clone https://github.com/TMHSDigital/Blender-Developer-Tools.git
```

- **Cursor** — point Cursor at the checkout (or symlink `rules/` into your project). The `.mdc` rules apply automatically by glob scope; skills are referenced by name in chat.
- **Claude Code** — copy `skills/` and `rules/` into your project workspace, or keep this repo as a checkout that Claude Code references directly.
- **Get Blender** — download **5.2 LTS** (primary target) or **4.5 LTS** (supported fallback) from [blender.org/download/lts](https://www.blender.org/download/lts/); current stable lives at [blender.org/download](https://www.blender.org/download/). The `blender` command below is that binary — on macOS it is inside the app bundle at `/Applications/Blender.app/Contents/MacOS/Blender`.
- **Run an example** — every example is a self-checking headless script (exit non-zero on failure, no GPU needed for the check):

```bash
blender --background --python examples/bmesh-gear/bmesh_gear.py --
```

## Supported Blender versions

| Version | Status |
| --- | --- |
| Blender 5.2 LTS | Primary target (current stable; all examples assume 5.2 unless a 4.5 path is shown) |
| Blender 5.1 | Prior stable (weekly cron; PR via `needs-5.1` or manual dispatch) |
| Blender 4.5 LTS | Fallback supported (skills show both code paths where 4.x and 5.x APIs diverge) |

## Falsifiers

Every one of the 60 examples carries a **falsifier**: a flag that changes the
input so a real assertion fails. It never disables the assertion, skips the
check, or short-circuits to an error — it feeds the script something the
contract says must not pass, and the same check that guards the happy path
catches it.

```bash
# The contract holds: exit 0
blender --background --python examples/bmesh-gear/bmesh_gear.py --

# The falsifier: skip the extrude, so the topology no longer matches the
# closed form. The topology check fires and the script exits 3.
blender --background --python examples/bmesh-gear/bmesh_gear.py -- --no-extrude
```

This is what makes a green run mean something. An assertion that has only
ever passed witnesses nothing — it could be comparing a constant to itself.
Proving each one fails once, on demand, is the difference between a test
suite and a set of scripts that print "OK". Shipping an example requires
demonstrating the falsifier's non-zero exit and reporting the measured error.

`--api`, `--check-pixels`, and `--output` are not falsifiers; they select a
code path rather than break a contract. Full conventions, including the
per-script exit-code model, are in
[`CONTRIBUTING.md`](CONTRIBUTING.md#exit-codes).

## Showcase

Budget-conformance props. Not examples. Conventions: [`showcase/README.md`](showcase/README.md).

<details>
<summary><strong>60 showcase pieces</strong> — click to expand the preview grid</summary>

<p align="center">
  <a href="showcase/shipping-crate/"><img src="showcase/shipping-crate/preview.webp" width="24%" alt="Shipping crate: a wooden slat crate stencilled PORT ROYAL and NO 17, with iron corner brackets and an end handle, on a dark studio floor, warm wedge on the back wall" /></a>
  <a href="showcase/stone-well/"><img src="showcase/stone-well/preview.webp" width="24%" alt="Stone well: a round well of varied grey stones with a grained wooden pyramid roof on posts, rope and a bucket on rusted iron hoops, on a dark studio floor" /></a>
  <a href="showcase/wooden-barrel/"><img src="showcase/wooden-barrel/preview.webp" width="24%" alt="Wooden barrel: a 20-stave wine-cask with a head of four boards, chord-lofted iron hoops, and a bung on a dark studio floor" /></a>
  <a href="showcase/campfire/"><img src="showcase/campfire/preview.webp" width="24%" alt="Campfire: a two-course ring of warm, soot-dark fieldstones around a tripod of charring logs over ember-cracked coals on a dark studio floor, warm wedge on the back wall" /></a>
  <a href="showcase/market-stall/"><img src="showcase/market-stall/preview.webp" width="24%" alt="Market stall: a grained timber frame with post feet, diagonal side braces, slatted counter, rafters, and a striped canvas awning on a dark studio floor, warm wedge on the back wall" /></a>
  <a href="showcase/street-lantern/"><img src="showcase/street-lantern/preview.webp" width="24%" alt="Street lantern: a cast-iron lamp post with a fluted column, brass collars, a ladder bar and a scrolled, braced arm, its banded lantern lit amber from inside" /></a>
  <a href="showcase/treasure-chest/"><img src="showcase/treasure-chest/preview.webp" width="24%" alt="Treasure chest: a slatted wooden chest with iron bands, corner brackets, and an open lid on a dark studio floor" /></a>
  <a href="showcase/terrain-scatter/"><img src="showcase/terrain-scatter/preview.webp" width="24%" alt="Terrain scatter: a Geometry Nodes hill tile of patchy grass over dark earth, nine faceted stones sunk into it among grass tufts and pebbles, on a dark studio floor" /></a>
  <a href="showcase/fence-kit/"><img src="showcase/fence-kit/preview.webp" width="24%" alt="Fence kit: a run of three weathered post-and-rail sections on a packed-earth strip sharing one post at each joint, with pyramidal caps, diagonal board braces, and iron bands" /></a>
  <a href="showcase/watchtower/"><img src="showcase/watchtower/preview.webp" width="24%" alt="Watchtower: a grained timber lookout seen from low and close, with X-braces, hatch ladder, a plank platform on deck girts, and a weathered cedar shake roof on a dark studio floor" /></a>
  <a href="showcase/cart/"><img src="showcase/cart/preview.webp" width="24%" alt="Cart: a two-wheel wooden cart with spoked wheels, slatted bed, and shafts on a dark studio floor" /></a>
  <a href="showcase/park-bench/"><img src="showcase/park-bench/preview.webp" width="24%" alt="Park bench: a wrought-iron bench whose round-bar legs curl into scrolled feet, with wooden slats and a reclined back, on a dark studio floor" /></a>
  <a href="showcase/wheelbarrow/"><img src="showcase/wheelbarrow/preview.webp" width="24%" alt="Wheelbarrow: a wooden tray with walls of stacked boards and iron straps, a spoked wheel, rear legs, and handles on a dark studio floor" /></a>
  <a href="showcase/anvil/"><img src="showcase/anvil/preview.webp" width="24%" alt="Anvil: a forged-steel London-pattern anvil with a hammer-polished face on a hooped timber stump, a hammer at its foot" /></a>
  <a href="showcase/water-trough/"><img src="showcase/water-trough/preview.webp" width="24%" alt="Water trough: a staved wooden trough on pegged trestle legs, iron straps bolted and clipped over the rim, rippled water inside and a bung in one end" /></a>
  <a href="showcase/hitching-post/"><img src="showcase/hitching-post/preview.webp" width="24%" alt="Hitching post: a square timber post with a pyramidal cap, a cross-arm on two knee braces with iron end caps, iron bands wrapped around it, two hitching rings and a nailed horseshoe on a dark studio floor" /></a>
  <a href="showcase/grindstone/"><img src="showcase/grindstone/preview.webp" width="24%" alt="Grindstone: a sandstone wheel dipping into a water-filled trough on a timber A-frame, with iron axle, hubs and a crank turned toward the viewer, on a dark studio floor" /></a>
  <a href="showcase/hand-pump/"><img src="showcase/hand-pump/preview.webp" width="24%" alt="Hand pump: a green-enamelled cast-iron village pump with a fluted barrel, ball finial and counterweighted handle on a stepped wooden plinth, a hooped wooden bucket under its spout" /></a>
  <a href="showcase/signpost/"><img src="showcase/signpost/preview.webp" width="24%" alt="Signpost: a timber crossroads post with three painted fingerboards lettered MILLBROOK 2, OAKHAM 5 and FORD 1, iron straps, and a pyramidal cap on a dark studio floor" /></a>
  <a href="showcase/chopping-block/"><img src="showcase/chopping-block/preview.webp" width="24%" alt="Chopping block: a bark-sided log round with growth rings and drying checks on its sawn top, a riveted iron hoop, a felling axe buried in the top, and split billets and chips at its foot, on a dark studio floor" /></a>
  <a href="showcase/wooden-bucket/"><img src="showcase/wooden-bucket/preview.webp" width="24%" alt="Wooden bucket: a coopered pail with a three-strand rope bail through iron ear rings and chord-lofted iron hoops on a dark studio floor" /></a>
  <a href="showcase/wall-torch/"><img src="showcase/wall-torch/preview.webp" width="24%" alt="Wall torch: a dressed stone plaque with an iron plate and arm holding a cup, a leaning wooden torch with a pitch-wrapped head and a bright flame, on a dark studio floor" /></a>
  <a href="showcase/tavern-stool/"><img src="showcase/tavern-stool/preview.webp" width="24%" alt="Tavern stool: a dished round wooden seat holding a pewter tankard, on turned splayed legs with stretchers at two heights and iron ferrules on flat treads, on a dark studio floor" /></a>
  <a href="showcase/iron-cauldron/"><img src="showcase/iron-cauldron/preview.webp" width="24%" alt="Iron cauldron: a round-bellied cast-iron pot hanging by its bail from a timber tripod on a dark studio floor" /></a>
  <a href="showcase/wooden-ladder/"><img src="showcase/wooden-ladder/preview.webp" width="24%" alt="Wooden ladder: an oak ladder with six pale turned hickory rungs through-tenoned into its rails, iron tie-rods under the end rungs and iron shoes, leaning on a barn-board wall with a rope coil on a rung" /></a>
  <a href="showcase/hay-bale/"><img src="showcase/hay-bale/preview.webp" width="24%" alt="Hay bale: a bound straw bale with two sisal twine belts on a dark studio floor" /></a>
  <a href="showcase/crate-stack/"><img src="showcase/crate-stack/preview.webp" width="24%" alt="Crate stack: three slatted shipping crates stacked and yawed, each with iron corner straps and runners, on a dark studio floor" /></a>
  <a href="showcase/stone-archway/"><img src="showcase/stone-archway/preview.webp" width="24%" alt="Stone archway: a semicircular masonry arch with coursed piers, projecting imposts, nine voussoirs and a proud keystone, on a dark studio floor" /></a>
  <a href="showcase/rope-bridge/"><img src="showcase/rope-bridge/preview.webp" width="24%" alt="Rope bridge: a sagging plank deck on foot ropes between two pairs of log posts, with lashed hemp hand ropes, suspenders, and ropes staked to the ground, on a dark studio floor" /></a>
  <a href="showcase/grain-sacks/"><img src="showcase/grain-sacks/preview.webp" width="24%" alt="Grain sacks: three burlap sacks gathered and tied with twine, two standing and one lying slumped in front, one blue-striped and one red-striped, on a dark studio floor" /></a>
  <a href="showcase/brazier/"><img src="showcase/brazier/preview.webp" width="24%" alt="Brazier: an iron fire bowl with a rolled rim on three S-curved forged legs, holding ash and a heap of glowing charcoal, on a dark studio floor" /></a>
  <a href="showcase/apothecary-shelf/"><img src="showcase/apothecary-shelf/preview.webp" width="24%" alt="Apothecary shelf: a stained wooden shelf unit with an arched crest, gallery rails and three drawers, stocked with labelled glass bottles, flasks and glazed jars, on a dark studio floor" /></a>
  <a href="showcase/wooden-yoke/"><img src="showcase/wooden-yoke/preview.webp" width="24%" alt="Wooden yoke: a carved oak ox yoke with upturned ends standing on two bent hickory oxbows pinned above the beam, with an iron ring hung under its centre, on a dark studio floor" /></a>
  <a href="showcase/butter-churn/"><img src="showcase/butter-churn/preview.webp" width="24%" alt="Butter churn: a tall staved oak churn narrowing toward the top, bound by three iron hoops, with a two-board lid and a maple dasher handle rising through it, on a dark studio floor" /></a>
  <a href="showcase/bookshelf/"><img src="showcase/bookshelf/preview.webp" width="24%" alt="Bookshelf: a stained wooden bookcase of cloth and leather hardbacks, some standing, some stacked flat and two leaning on their neighbours, on a dark studio floor" /></a>
  <a href="showcase/book-trolley/"><img src="showcase/book-trolley/preview.webp" width="24%" alt="Book trolley: a double-sided wooden library book truck on four casters, two sloped troughs of hardbacks leaning back spines out and loose books stacked on its deck, on a dark studio floor" /></a>
  <a href="showcase/basketball-hoop/"><img src="showcase/basketball-hoop/preview.webp" width="24%" alt="Basketball hoop: an in-ground goal with a padded square gooseneck pole, a framed backboard with a red shooter's square, an orange rim and a white net, standing on a concrete court pad with a faded green key, free-throw circle and three-point arc, two basketballs on the concrete" /></a>
  <a href="showcase/pine-tree/"><img src="showcase/pine-tree/preview.webp" width="24%" alt="Pine tree: a mature Scots pine with a tall bare bole, dead lower limbs and a broad, rounded crown of soft blue-green needle brushes over red limbs, on a small disc of needle-litter soil with mossy stones, on a dark studio floor" /></a>
  <a href="showcase/desk-lamp/"><img src="showcase/desk-lamp/preview.webp" width="24%" alt="Desk lamp: a red balanced-arm lamp with a stepped base, parallel-rod arms, chrome springs and knurled knobs, and a domed shade glowing around its bulb, on a dark studio floor" /></a>
  <a href="showcase/quad-drone/"><img src="showcase/quad-drone/preview.webp" width="24%" alt="Quad drone: a white-and-graphite camera quadcopter on four carbon arms with red lock rings, twin-blade props, rubber-footed skids and a three-axis gimbal camera, on a dark studio floor" /></a>
  <a href="showcase/soccer-goal/"><img src="showcase/soccer-goal/preview.webp" width="24%" alt="Soccer goal: a white 5 by 2 m youth goal with sloped rear supports and a sagging diamond-mesh net edged in red rope, on a turf patch with a painted goal line, on a dark studio floor" /></a>
  <a href="showcase/fallen-log/"><img src="showcase/fallen-log/preview.webp" width="24%" alt="Fallen log: a mossy log settled into a soil mound, its dark furrowed bark peeled in patches, a hollow ringed butt, tiers of shelf fungi, toadstools, ferns and fallen leaves, on a dark studio floor" /></a>
  <a href="showcase/office-chair/"><img src="showcase/office-chair/preview.webp" width="24%" alt="Office chair: a graphite mesh-back task chair with a muted-teal two-tone seat, a mesh headrest and 4D armrests on a polished five-star base, standing on a smoked chair mat beside a snake plant in a stone planter" /></a>
  <a href="showcase/hover-bike/"><img src="showcase/hover-bike/preview.webp" width="24%" alt="Hover bike: a teal sci-fi speeder with pearl racing stripes, a stitched black saddle, clip-on bars and two ducted fans with orange spinners, parked on landing skids, on a dark studio floor" /></a>
  <a href="showcase/weight-rack/"><img src="showcase/weight-rack/preview.webp" width="24%" alt="Weight rack: a red half rack holding a barbell loaded with blue and yellow bumpers on J-hooks, plates on storage horns and two hex dumbbells, on a dark studio floor" /></a>
  <a href="showcase/boulder-cluster/"><img src="showcase/boulder-cluster/preview.webp" width="24%" alt="Boulder cluster: a speckled granite block, a banded sandstone boulder split in two and a slab resting on a smaller boulder, sunk in a grassy soil mound with pebbles and wildflowers, on a dark studio floor" /></a>
  <a href="showcase/floor-fan/"><img src="showcase/floor-fan/preview.webp" width="24%" alt="Floor fan: a sage-green 1950s pedestal fan with a chrome wire guard over four brass blades, its head turned on a tilt yoke, a telescoping column and a round cast base, its cord looped to a plug, on a dark studio floor" /></a>
  <a href="showcase/motor-scooter/"><img src="showcase/motor-scooter/preview.webp" width="24%" alt="Motor scooter: a pastel sea-green 1960s step-through scooter with a two-tone cream and oxblood dual saddle, louvred side cowls, a curved chrome-trimmed leg shield, split-rim wheels and a black silencer, on its centre stand on a dark studio floor" /></a>
  <a href="showcase/bowling-pins/"><img src="showcase/bowling-pins/preview.webp" width="24%" alt="Bowling pins: ten white pins with red neck stripes racked on a dark pin deck at the end of a glossy maple lane with arrows and dots, a marbled violet ball on the approach, between gutters and kickbacks, on a dark studio floor" /></a>
  <a href="showcase/pond-edge/"><img src="showcase/pond-edge/preview.webp" width="24%" alt="Pond edge: a dark rippled pond on a raised soil disc, cattails with brown seed heads and rush tufts on the far bank, notched lily pads and two pink-white water lilies, wet stones and a branch at the waterline, on a dark studio floor" /></a>
  <a href="showcase/stand-mixer/"><img src="showcase/stand-mixer/preview.webp" width="24%" alt="Stand mixer: a slate-blue retro tilt-head stand mixer with a chrome trim band and a brushed steel bowl on a stone countertop, beside a wire whisk, a steel measuring cup and two brown eggs in a terracotta dish, on a dark studio floor" /></a>
  <a href="showcase/cargo-loader/"><img src="showcase/cargo-loader/preview.webp" width="24%" alt="Cargo loader: a yellow bipedal powered-lift exoframe in a crouch, hydraulic rams and pinned clevises on its legs and arms, an open roll-cage cockpit with a seat, harness and amber beacon, a power pack behind, holding a corrugated blue-grey crate on two forks, on a dark studio floor" /></a>
  <a href="showcase/archery-target/"><img src="showcase/archery-target/preview.webp" width="24%" alt="Archery target: a straw boss with a gold, red, blue, black and white face and five arrows, leaning on a timber easel numbered 12 with a hinged rear leg and a splay chain, on a turf patch with a leather quiver and a snapped arrow in the grass, on a dark studio floor" /></a>
  <a href="showcase/cactus-garden/"><img src="showcase/cactus-garden/preview.webp" width="24%" alt="Cactus garden: a ribbed, many-armed saguaro, rows of spines and cream flowers on its crown, a barrel cactus with red hooked spines and yellow fruit, a prickly pear with magenta fruit, an agave rosette and sandstone rocks on a raised sand disc, on a dark studio floor" /></a>
  <a href="showcase/espresso-machine/"><img src="showcase/espresso-machine/preview.webp" width="24%" alt="Espresso machine: a brushed stainless E61 espresso machine with twin gauges, a chrome group head and a walnut-handled portafilter over a shot cup, cups on its warmer tray, beside a tamper, milk pitcher and knock box on a stone counter" /></a>
  <a href="showcase/road-bicycle/"><img src="showcase/road-bicycle/preview.webp" width="24%" alt="Road bicycle: a deep red lugged-steel road bicycle leaning on its kickstand, with chromed lugs and fork socks, tan-wall 700c wheels, a honey leather saddle, cream-taped drop bars and a chain over a double crankset" /></a>
  <a href="showcase/skate-ramp/"><img src="showcase/skate-ramp/preview.webp" width="24%" alt="Skate ramp: a plywood quarter-pipe with a steel coping and kicker plate, screw rows, sheet seams and a red stencilled roundel, its open side showing studs and sills, a skateboard on the deck" /></a>
  <a href="showcase/palm-tree/"><img src="showcase/palm-tree/preview.webp" width="24%" alt="Palm tree: a coconut palm leaning on a raised disc of beach sand, its ringed trunk curving up to a crown of drooping pinnate fronds over green coconuts, fallen coconuts, a frond and driftwood below" /></a>
  <a href="showcase/wingback-armchair/"><img src="showcase/wingback-armchair/preview.webp" width="24%" alt="Wingback armchair: an oxblood leather wingback with a deep-button tufted back, rolled arms trimmed with brass nailheads and a piped seat cushion, beside a side table with a brass reading lamp and books on a fringed rug" /></a>
  <a href="showcase/planet-rover/"><img src="showcase/planet-rover/preview.webp" width="24%" alt="Planet rover: a six-wheeled rocker-bogie rover with gold-foil sides, a camera mast, a dish antenna and a finned power unit, its arm drilling a boulder on red-grey regolith" /></a>
</p>

[`shipping-crate`](showcase/shipping-crate/) — procedural crate through UVs, bake, LOD, collider, and Unity glTF, asserting recomputed budgets. Falsifier `--skip-decimate` exits 9.

[`stone-well`](showcase/stone-well/) — procedural round stone well, shingled roof, windlass, rope and bucket through the same pipeline. Falsifier `--skip-decimate` exits 9.

[`wooden-barrel`](showcase/wooden-barrel/) — procedural 20-stave wine-cask with boarded, croze-seated heads and chord-lofted hoops through the same pipeline. Falsifiers `--round-band` exits 18, `--one-piece-head` exits 17.

[`campfire`](showcase/campfire/) — procedural fieldstone ring, logs, and ash through the same pipeline. Falsifiers `--skip-decimate` exits 9, `--uniform-stones` exits 20.

[`market-stall`](showcase/market-stall/) — procedural timber stall with striped awning and counter through the same pipeline. Falsifiers `--skip-decimate` exits 9, `--short-brace` exits 17.

[`street-lantern`](showcase/street-lantern/) — procedural hanging lantern with iron post, brass fittings, and amber cage through the same pipeline. Falsifiers `--skip-decimate` exits 9, `--shallow-brace` exits 20.

[`treasure-chest`](showcase/treasure-chest/) — procedural slatted chest with iron bands, corner brackets, and an open lid through the same pipeline. Falsifier `--skip-decimate` exits 9.

[`terrain-scatter`](showcase/terrain-scatter/) — Geometry Nodes hill tile with bevelled masonry scatter through the same pipeline. Falsifier `--skip-decimate` exits 9.

[`fence-kit`](showcase/fence-kit/) — procedural post-and-rail fence section through the same pipeline. Falsifier `--skip-decimate` exits 9.

[`watchtower`](showcase/watchtower/) — procedural timber lookout with X-braces, hatch ladder, platform, and coursed shake roof through the same pipeline. Falsifiers `--skip-decimate` exits 9, `--short-joists` exits 17.

[`cart`](showcase/cart/) — procedural two-wheel wooden cart with spoked wheels, slatted bed, and shafts through the same pipeline. Falsifier `--skip-decimate` exits 9.

[`park-bench`](showcase/park-bench/) — procedural wrought-iron park bench with scrolled legs and slatted seat through the same pipeline. Falsifier `--skip-decimate` exits 9.

[`wheelbarrow`](showcase/wheelbarrow/) — procedural wheelbarrow with board-built tray walls, a spoked wheel, iron straps, legs, and handles through the same pipeline. Falsifiers `--skip-decimate` exits 9, `--wide-seams` exits 17.

[`anvil`](showcase/anvil/) — procedural London-pattern anvil on a timber stump through the same pipeline. Falsifiers `--skip-decimate` exits 9, `--round-waist` exits 19.

[`water-trough`](showcase/water-trough/) — procedural watertight water trough on a timber stand through the same pipeline. Falsifier `--skip-decimate` exits 9.

[`hitching-post`](showcase/hitching-post/) — procedural timber hitching post with a cross-arm, wrapped iron bands and iron rings through the same pipeline. Falsifiers `--skip-decimate` exits 9, `--sunk-bands` exits 18.

[`grindstone`](showcase/grindstone/) — procedural grindstone on a timber trestle with iron axle and crank through the same pipeline. Falsifier `--skip-decimate` exits 9.

[`hand-pump`](showcase/hand-pump/) — procedural cast-iron village hand pump through the same pipeline. Falsifier `--skip-decimate` exits 9.

[`signpost`](showcase/signpost/) — procedural timber fingerboard signpost through the same pipeline. Falsifiers `--skip-decimate` (9), `--stray-vert` (15), `--yaw-boards` (19).

[`chopping-block`](showcase/chopping-block/) — procedural hooped timber stump with an embedded axe through the same pipeline. Falsifier `--skip-decimate` exits 9.

[`wooden-bucket`](showcase/wooden-bucket/) — procedural coopered pail with a three-strand rope bail through the ear rings through the same pipeline. Falsifiers `--float-handle` and `--sunk-rope` exit 17.

[`wall-torch`](showcase/wall-torch/) — procedural wall-mounted torch sconce with a stone plaque, iron bracket, and flame through the same pipeline. Falsifiers `--skip-decimate` (9), `--stray-vert` (15), `--float-arm` (17).

[`tavern-stool`](showcase/tavern-stool/) — procedural tavern stool with turned legs, stretchers, and iron ferrules through the same pipeline. Falsifier `--skip-decimate` exits 9.

[`iron-cauldron`](showcase/iron-cauldron/) — procedural round-bellied iron cauldron on a timber tripod through the same pipeline. Falsifiers `--skip-decimate` exits 9, `--pointed-pot` exits 19.

[`wooden-ladder`](showcase/wooden-ladder/) — procedural timber ladder with raked stiles, evenly pitched rungs, and iron shoes through the same pipeline. Falsifiers `--skip-decimate` exits 9, `--drift-rungs` exits 19.

[`hay-bale`](showcase/hay-bale/) — procedural bound hay bale with sisal twine through the same pipeline. Falsifier `--skip-decimate` exits 9.

[`rope-bridge`](showcase/rope-bridge/) — procedural rope footbridge whose plank deck is fitted to a parabola recomputed from the plank tops, with lashed hand ropes and staked foot ropes, through the same pipeline. Falsifiers `--vee-deck` exits 19, `--float-suspenders` exits 18.

[`grain-sacks`](showcase/grain-sacks/) — procedural pile of burlap grain sacks settled onto flat bases and tied with twine, through the same pipeline. Falsifiers `--round-bottom` exits 19, `--slip-tie` exits 17.

[`brazier`](showcase/brazier/) — procedural iron brazier with ash and glowing charcoal whose tip angle is recomputed from a density-weighted mass centre and the feet on the floor, through the same pipeline. Falsifiers `--tuck-legs` exits 19, `--overfill` exits 18.

[`apothecary-shelf`](showcase/apothecary-shelf/) — procedural apothecary shelf stocked with fifteen labelled bottles, flasks and jars, whose headroom under the shelf above is recomputed per vessel, through the same pipeline. Falsifiers `--tall-flask` exits 20, `--short-shelves` exits 17.

[`wooden-yoke`](showcase/wooden-yoke/) — procedural double ox yoke on two bent hickory bows with a hung ring, whose neck openings are measured between the bow legs and up to the saddles, through the same pipeline. Falsifiers `--pinch-bows` exits 19, `--edge-on-ring` exits 17.

[`butter-churn`](showcase/butter-churn/) — procedural staved plunge churn whose dasher stroke is recomputed from the inner wall read off the staves and the plunger's reach, through the same pipeline. Falsifiers `--wide-dasher` exits 20, `--tight-hole` exits 18.

[`bookshelf`](showcase/bookshelf/) — procedural bookcase of thirty-eight rounded-spine hardbacks, standing, stacked and leaning, whose leaning books' contact with their neighbour's head edge is recomputed as a band, through the same pipeline. Falsifiers `--air-lean` and `--deep-lean` exit 22, `--crowd-books` exits 23.

[`book-trolley`](showcase/book-trolley/) — procedural double-sided library book truck on four casters, forty-seven hardbacks in four sloped troughs, whose every book's fore-edge depth in its backrest is recomputed as a band beside its shelf seat, through the same pipeline. Falsifiers `--off-back` and `--deep-back` exit 21, `--skew-caster` exits 19.

[`basketball-hoop`](showcase/basketball-hoop/) — the first `sports` piece: procedural in-ground basketball goal on a patch of driveway court (square gooseneck pole swept in one piece with bend webs, bolted into a two-pour concrete pad, braced board in an aluminium frame, breakaway regulation rim, knotted twelve-loop net, faded court paint, two basketballs), whose rim height over the court, inside diameter, board gap and level, every net loop threaded on its rim hook, each ball resting on its slab, the anchor bolts set through the plate into the slab, and every paint line set into its slab, are recomputed from the mesh, through the same pipeline. Falsifiers `--drop-net` exits 18, `--tilt-rim` 19, `--loose-pad` 20, `--float-ball` 21, `--short-bolts` 22, `--float-paint` 23.

[`pine-tree`](showcase/pine-tree/) — the first `nature` piece: procedural mature Scots pine on a needle-litter soil disc (a buttressed trunk with plated lower bark bedded in the soil, surface roots, eight seeded whorls of heavy crooked limbs, 113 overlapping brushes of long thin needle strands each on its own twig, dead stubs and limbs, hanging cones, fallen cones, mossy stones and sticks), whose every limb's seat in the bark, whorl spacing, trunk plumb and crown balance, every clump seated on its own carrier and the ground cover bedded in the soil are recomputed from the mesh, through the same pipeline. Falsifiers `--float-branches` exits 17, `--lean-crown` 19, `--bunch-whorls` 20, `--short-twigs` 22, `--float-litter` 23.

[`desk-lamp`](showcase/desk-lamp/) — the first `household` piece: procedural balanced-arm desk lamp (stepped cast base, two parallelogram arm sections pinned through knuckle bosses, three tension springs hung on cross bars, domed shade with reflector and lamp, draped flex and plugged cable), whose every joint pin coaxial through the eyes it joins, every spring end seated on its bar, and mass centre over the base footprint are recomputed from the mesh, through the same pipeline. Falsifiers `--offset-pin` exits 17, `--unhook-spring` 18, `--hollow-base` 19, `--unscrew-bulb` 20.

[`quad-drone`](showcase/quad-drone/) — the first `vehicles` piece: procedural camera quadcopter (two-tone moulded shell with panel lines, grilles, visor and battery pack, four folding arms hinged on pinned clevises, slotted brushless motors carrying twisted, swept two-blade props, rubber-footed skids, a three-axis gimbal camera), whose motor axes on an exact X, the gap between neighbouring prop discs, every foot on the ground and the mass centre over the landing footprint are recomputed from the mesh, through the same pipeline. Falsifiers `--float-foot` exits 16, `--unlock-arm` 17, `--long-blades` 18, `--narrow-skids` 19, `--drop-lens` 20.

[`soccer-goal`](showcase/soccer-goal/) — the second `sports` piece: procedural freestanding 5 × 2 m youth soccer goal (posts and crossbar in one oval aluminium extrusion with a net channel, mitred and welded at the corners, cast corner brackets, foot connectors and rear hubs, sloped supports and a steel ground frame pinned by staples and spikes, a sagging diamond-mesh net with a red head rope through 53 nylon clips, a turf patch with a painted goal line), whose ground bars bedded in the turf, supports seated in their sockets, head rope threaded through every clip, clear mouth size with plumb posts, and catenary sag of the back panel are recomputed from the mesh, through the same pipeline. Falsifiers `--float-bar` exits 16, `--short-support` 17, `--unclip-net` 18, `--wide-mouth` 19, `--taut-net` 20.

[`fallen-log`](showcase/fallen-log/) — the second `nature` piece: procedural fallen forest log (one furrowed lathe along a bowed axis, bark peeled to sapwood scored by beetle galleries, a rotted hollow saw-cut butt with growth rings, a splintered snapped top, broken branch stubs, moss cushions on the top and shaded side, three tiers of bracket fungi, a soil mound with toadstools, ferns and fallen leaves), whose bed along its length, brackets rooted in the bark, mass centre over its contact patch, moss on up- and shade-facing surfaces and ground cover rooted in the soil are recomputed from the mesh, through the same pipeline. Falsifiers `--hump-ground` exits 17, `--float-fungi` 18, `--tilt-ground` 19, `--sunny-moss` 20, `--float-litter` 21.

[`office-chair`](showcase/office-chair/) — the second `household` piece: procedural ergonomic task chair on a chair mat at a desk corner (polished aluminium five-star base with ribbed spokes and five swivelled hooded twin-wheel casters, a chrome gas lift in a telescoping cover under a synchro-tilt mechanism with tension knob and paddles, a two-tone sculpted cushion with thigh channels, a waterfall front and piped welts in a moulded shell, an elastomeric mesh back and mesh headrest on graphite frames with an S-curved lumbar pad on sliders, 4D armrests, a smoked polycarbonate mat and a snake plant in a stone planter), whose mat flat on the floor with every wheel pressed into it, five-star spacing with plumb swivel stems on one circle, gas-lift column coaxial with hub and socket, mirrored level armrests with seat height and mass centre inside the caster contact hull, single connected chair, lumbar sliders clamped on the frame and leaves rooted in the soil are recomputed from the mesh, through the same pipeline. Falsifiers `--float-caster` and `--curl-mat` exit 16, `--skew-spoke` 17, `--offset-column` 18, `--uneven-arms` 19, `--loose-wheel` 20, `--float-lumbar` 21, `--float-leaves` 22.

[`hover-bike`](showcase/hover-bike/) — the second `vehicles` piece: procedural sci-fi hover bike (a sculpted two-tone fuselage with panel seams, intake grilles, tail vents and cooling fins, a stitched pleated saddle, clip-on bars with grips, levers and an emissive instrument cluster, a flyscreen and headlight pod, two glowing exhaust nozzles, two ducted fans with canted stator vanes and handed seven-blade rotors, booms with foot pegs, and two landing skids on struts), whose skids on the floor, rotor hubs coaxial with their shrouds, blade-tip clearance to the shroud wall, mirror-symmetric fuselage with seat height, equal blade spacing, mass centre inside the skids' contact polygon and single connected assembly are recomputed from the mesh, through the same pipeline. Falsifiers `--float-skid` exits 16, `--offset-hub` 17, `--long-blades` 18, `--odd-hull` 19, `--skew-blade` 20, `--narrow-skids` 21, `--pop-lens` 22.

[`weight-rack`](showcase/weight-rack/) — the third `sports` piece: procedural home-gym half rack (punched, numbered square uprights on bolted base plates and padded feet, side rails on bolted flanges, a pull-up bar, J-hooks with UHMW-lined saddles and spotter arms on pull pins, four plate-storage horns, an Olympic barbell with a knurled shaft, collars and sleeves loaded with 20 and 15 kg bumpers and 5 kg iron plates behind spring clips, and two hex dumbbells on the floor), whose pads and dumbbell heads on the floor, pull pins coaxial with their holes, bar seated in both saddles and level, plates coaxial and seated along their sleeves, balanced load and single connected rack are recomputed from the mesh, through the same pipeline. Falsifiers `--float-foot` exits 16, `--offset-pin` 17, `--float-bar` 18, `--hook-high` 19, `--gap-plate` 20, `--odd-load` 21, `--loose-horn` 22.

[`boulder-cluster`](showcase/boulder-cluster/) — the third `nature` piece: procedural glacial boulder cluster (four boulders cut from ellipsoids by cleavage planes with weathered bevels: a speckled granite block, a banded sandstone boulder split in two with matching crack faces and bedding, and a sandstone slab resting flat on a smaller granite boulder, with lichen crusts and moss cushions on the tops and north faces, sunk into a soil mound with grass tufts, pebbles and wildflowers), whose boulders sunk into the soil all round, slab seated on its support and balanced over its footprint, split halves matching across the crack, growth facing up or north and ground cover rooted in the soil are recomputed from the mesh, through the same pipeline. Falsifiers `--perch-boulder` exits 17, `--float-slab` 18, `--perch-slab` 19, `--skew-half` 20, `--sunny-lichen` 21, `--float-cover` 22.

[`floor-fan`](showcase/floor-fan/) — the third `household` piece: procedural 1950s oscillating pedestal fan (a hollow two-tier cast base on a rubber gasket with a rotary speed switch and badge, a telescoping column with a knurled height-lock collar, a strap yoke with a tilt knob, a slotted motor housing with an oscillation knob, a two-half wire guard of spokes and rings welded to clipped rim rings, four swept brass blades on a hub with a spinner nut, and a cord to a plug), whose rotor and head coaxial with the guard, spokes seated in their rim rings, plumb column on the base's axis, blade-tip clearance, equal blade spacing, tip-over angle and single connected assembly are recomputed from the mesh, through the same pipeline. Falsifiers `--offset-hub` exits 17, `--short-spoke` 18, `--lean-column` 19, `--long-blades` 20, `--skew-blade` 21, `--hollow-base` 22, `--loose-spinner` 23.

[`motor-scooter`](showcase/motor-scooter/) — the third `vehicles` piece: procedural 1960s Italian step-through motor scooter (a pressed-steel tail with two bulbous side cowls, louvres on the engine side and chrome belt trims, a floorboard with runner strips pressed up into the tail and a leg shield convex in plan, arched into the headset and rimmed in chrome, with a horn cast and grille, a single-sided front end with a raked column, trailing link, coil spring and a crested mudguard, a headset carrying the headlamp, speedometer, grips, levers and mirrors, a two-tone piped dual saddle with a grab strap, 10-inch split rims in block-tread tyres, an alloy engine case with a finned cylinder, silencer and kick-start, a luggage rack, tail lamp and plate, and a centre stand), whose tyres and stand feet grounded, wheel axles level and parallel, steering trail, body mirror symmetry excluding the engine side, wheelbase, mass centre inside the support polygon, single connected assembly and the leg shield seated in the floorboard are recomputed from the mesh, through the same pipeline. Falsifiers `--float-tyre` exits 16, `--toe-wheel` 17, `--steep-head` 18, `--odd-body` 19, `--short-wheelbase` 20, `--narrow-stand` 21, `--pop-speedo` 22, `--lift-shield` 23.

[`bowling-pins`](showcase/bowling-pins/) — the fourth `sports` piece: procedural pin deck end of a ten-pin lane (a slab of 39 V-seamed maple boards crossed by the pin-deck joint, ten inlaid pin spots on a 12 in triangle, targeting arrows and range dots, channel gutters, cappings, kickbacks with sloped noses, aluminium caps and kick plates, a steel pit edge and sleepers; ten pins lathe-turned from the regulation profile table with red neck stripes and a crown band; an 8.5 in marbled ball drilled by an exact Boolean with a countersunk thumb hole and two parallel finger holes), whose sleepers grounded, pins centred on their spots, seated, plumb and to size, spots on the exact lattice, turned profile, ball resting on the lane at its radius, hole depths, bores, span and bridge, boards flush and parallel and single connected assembly are recomputed from the mesh, through the same pipeline. Falsifiers `--float-sleeper` exits 16, `--offset-pin` 17, `--float-pin` 18, `--lean-pin` 19, `--wide-rack` 20, `--fat-neck` 21, `--float-ball` 22, `--shallow-holes` 23, `--proud-board` 24, `--lift-arrows` 25.

[`pond-edge`](showcase/pond-edge/) — the fourth `nature` piece: procedural pond margin on a raised soil disc (a bank sloping from turf through wet mud into a shallow basin, its cut edge showing its soil horizons; the water its own rippled sheet at a declared level, its rim run on under the bank; a cattail clump of arching strap leaves and five stems, each threaded through a velvet seed head with a bare spike; rush and turf tufts; five notched lily pads and two layered water lilies floating; wet stones, a half-submerged branch, pebbles and fallen leaves), whose leaves and stems rooted in the mud, pads floating at the water level, water level and ripple band, seed heads threaded on their stems, water enclosed by the bank and cover joined to the soil are recomputed from the mesh, through the same pipeline. Falsifiers `--float-reeds` exits 17, `--sink-pad` 18, `--flat-water` 19, `--slip-heads` 20, `--short-water` 21, `--float-cover` 22.

[`stand-mixer`](showcase/stand-mixer/) — the fourth `household` piece: procedural retro tilt-head stand mixer on a honed stone countertop section (a cast enamel base foot, neck and streamlined head lofted from superellipse sections, on four rubber feet; a tilt hinge pinned through two neck knuckles; a chrome trim band, blank badge, speed and tilt-lock levers; an attachment hub with cap and thumb screw; a planetary socket carrying a flat beater into a 4.5 L brushed stainless bowl with a rolled rim and strap handle under three bayonet lugs; a cord to a plug; a whisk, a measuring cup and two eggs in a glazed dish), whose feet on the counter, hinge pin coaxial through its knuckles, bowl seated and concentric on its plate, height and brim capacity, beater coaxial with its socket, beater's dime-test clearance to the bowl, mass centre inside the feet and single connected assembly are recomputed from the mesh, through the same pipeline. Falsifiers `--float-foot` exits 16, `--offset-hinge` 17, `--offset-bowl` 18, `--shallow-bowl` 19, `--offset-beater` 20, `--long-beater` 21, `--bunch-feet` 22, `--loose-cap` 23.

[`cargo-loader`](showcase/cargo-loader/) — the fourth `vehicles` piece: procedural sci-fi industrial cargo loader, a bipedal powered-lift exoframe (broad flat feet with rubber soles, grip cleats and toe bumpers; hydraulic legs of lofted box-section shins and thighs pinned at the ankle, knee and hip; arms hung from shoulder yokes on towers; every joint a clevis with a chrome pin through two lug bushings and an eye bushing; eight rams, each a collared cylinder with a chromed rod, a pinned bracket at each end and a hose; fork carriages with hazard-striped faces and forged L-tines; an open roll-cage cockpit with a bucket seat, four-point harness, joystick consoles, amber beacon and work lights; a power pack with a slatted grille, cooling fins, hazard bands, exhaust stacks and cable looms; a corrugated cargo crate held on the tines), whose soles grounded, clevis pins coaxial with their bushings, crate resting on both tines, soles level, ram rods coaxial with their cylinders, rod strokes, mass centre of loader and crate inside the soles' support polygon and single connected assembly are recomputed from the mesh, through the same pipeline. Falsifiers `--float-foot` exits 16, `--offset-pin` 17, `--lift-crate` 18, `--tilt-sole` 19, `--skew-rod` 20, `--bottom-ram` 21, `--overload` 22, `--loose-light` 23.

[`archery-target`](showcase/archery-target/) — the fifth `sports` piece: procedural archery range target (a compressed-straw boss coiled from rope courses that show on its back and edge, bound with doubled jute twine tight over the crests; an 80 cm ten-zone World Archery face with ring lines, an X ring and a printed X, held by target pins; a timber easel leaning it back 12° on toe skids with knee braces, a ledge with a stop lip on a bolted rail and gussets, a numbered butt board, a strap hinge pinned to a rear leg in a steel ferrule and foot, a splay chain between eye bolts; five arrows in the face, one glancing into the edge, one snapped with its fletched half on the grass, a leather quiver of arrows among grass tufts on a turf patch), whose supports bedded in the turf, hinge pin coaxial with its knuckles, boss seated on its ledge and leaning on both legs, regulation gold height and size, points buried in the straw, fletching clear of the face, vanes at 120°, ring radii of the scoring table, forward tip angle and single connected assembly are recomputed from the mesh, through the same pipeline. Falsifiers `--float-foot` exits 16, `--offset-hinge` 17, `--lift-boss` 18, `--high-boss` 19, `--shallow-arrow` 20, `--short-arrow` 21, `--skew-vane` 22, `--wide-gold` 23, `--short-skids` 24, `--loose-pin` 25.

[`cactus-garden`](showcase/cactus-garden/) — the fifth `nature` piece: procedural Sonoran cactus garden on a raised sand-and-gravel disc (a 2.2 m saguaro of fourteen pleated ribs with rounded crests, three arms leaving the trunk through a smooth collar and turning up through wide elbows, a corky boot and scars, felt areoles with radiating spine clusters down every crest and cream flowers on the crown; a fishhook barrel cactus with a red hooked central at every areole and a ring of yellow fruit; a prickly pear of twelve broad sage paddles fused pad on pad in four tiers, with glochids and magenta fruit; a blue agave rosette, cleaved sandstone rocks, a bleached branch, fallen saguaro ribs, dry bunchgrass and gravel), whose arms biting into the trunk, pads jointed into their parents, plumb saguaro with its mass over its foot, ribs at equal stations, spines rooted in the skin, plants bedded in the sand and cover joined to the sand are recomputed from the mesh, through the same pipeline. Falsifiers `--short-arm` exits 17, `--shallow-pad` 18, `--lean-saguaro` 19, `--skew-ribs` 20, `--float-spines` 21, `--perch-barrel` 22, `--float-cover` 23.

[`espresso-machine`](showcase/espresso-machine/) — the fifth `household` piece: procedural prosumer E61 espresso machine on a honed stone countertop section (a black chassis behind a brushed stainless front panel, side panels folded round its edges with louvred vent slots cut through each sheet, a warmer tray with a bent rail and four upturned cups, adjustable feet; the chromed E61 group with its neck, gasket, mushroom cap and a lever pinned through two bosses; a spouted portafilter with a walnut handle; steam and hot-water valves with fluted bakelite knobs and wands on ball joints; twin gauges with printed dials in chrome bezels; a toggle and pilot lamp; a drip tray whose slotted grate carries a shot cup of espresso; a knock box, a tamper and a milk pitcher), whose feet on the counter, lever pin coaxial through its bosses, cups seated on their hosts, body size, portafilter coaxial and seated to the gasket, gauge glasses recessed in their bezels, drip tray inside the footprint, mass centre inside the feet and single connected assembly are recomputed from the mesh, through the same pipeline. Falsifiers `--float-foot` exits 16, `--offset-pin` 17, `--sink-cup` 18, `--narrow-body` 19, `--offset-pf` 20, `--drop-pf` 21, `--proud-gauge` 22, `--shift-tray` 23, `--bunch-feet` 24, `--loose-knob` 25.

[`road-bicycle`](showcase/road-bicycle/) — the fifth `vehicles` piece: procedural 1970s lugged-steel road bicycle leaning on its side kickstand (a 56 cm diamond frame in chromed, spear-pointed lugs, tapered stays with chrome tips, a chrome-crowned fork with socks; two 700c wheels of 36 spokes laced three-cross from both flanges of small-flange hubs to nipples through box-section rims, quick-release skewers, tan-wall tyres with a file-tread crown; a 52/42 crankset with quill pedals, toe clips and straps, a six-speed freewheel and a roller chain of 112 individual links solved round the ring, the cog and both jockeys; front and rear derailleurs, down-tube shifters, side-pull calipers, gum-hooded levers on cotton-taped drop bars, a quill stem, a leather saddle on rails, a bottle in a bolted cage), whose hubs coaxial with their dropouts, spoke seats in flange and nipple, wheels in the frame's plane, steering trail, three-cross lacing, chain seated on ring and cog, straight chain line, mass centre inside the tyres-and-foot triangle and one connected assembly are recomputed from the mesh, through the same pipeline. Falsifiers `--float-tyre` exits 16, `--slip-wheel` 17, `--short-spoke` 18, `--dish-wheel` 19, `--steep-head` 20, `--bunch-spokes` 21, `--lift-chain` 22, `--shift-rollers` 23, `--tuck-stand` 24, `--pop-bottle` 25.

[`skate-ramp`](showcase/skate-ramp/) — the sixth `sports` piece: procedural backyard quarter-pipe, 1.2 m on a 1.8 m transition (five plywood transition templates on 2x4 sills with sistered studs and a back post, nine 2x4 stringers under a two-layer plywood skin with joints offset between layers and landing on stringers, screw rows over every stringer, a steel coping pipe on welded, bolted tabs, a steel kicker plate ground to a lip on a toe block, a worn stencilled roundel and wheel marks; a skateboard on the deck with a seven-ply concave deck, kicktails, grip tape, two trucks and four wheels on bearings), whose sills on the floor, templates seated on sills and under the skin, wheels on the deck, circular transition, coping reveal, flush kicker plate, staggered seams, screws over stringers, coaxial wheels and one connected assembly are recomputed from the mesh, through the same pipeline. Falsifiers `--float-sill` exits 16, `--short-rib` 17, `--small-wheel` 18, `--sag-skin` 19, `--sink-coping` 20, `--proud-plate` 21, `--stack-seams` 22, `--miss-screws` 23, `--skew-wheel` 24, `--lift-grip` 25.

[`palm-tree`](showcase/palm-tree/) — the sixth `nature` piece: procedural coconut palm on a raised disc of rippled beach sand (a 4.47 m trunk rising from a swollen, lobed bole with a mat of 24 roots flaring out into the sand, leaning along a curve and coming back upright under the crown, tapering, ringed with 25 leaf scars at an even pitch; a fibrous boss of leaf bases carrying eighteen pinnate fronds in a golden-angle spiral, each a curved, drooping rachis with 36 pairs of folded leaflets hanging below it in a V, young fronds rising and old ones hanging; two dead fronds, two spear leaves and twelve green and ripening coconuts in bunches under the frond bases; two fallen coconuts, a fallen frond, driftwood, seashells and sea grass), whose fronds seated in the crown, coconuts attached under it, trunk height and lean with the crown's mass inside the root plate, leaf-scar rings at an even pitch, trunk and roots bedded in the sand, fallen coconuts resting in it and beach litter joined to it are recomputed from the mesh, through the same pipeline. Falsifiers `--short-petioles` exits 17, `--drop-coconut` 18, `--short-roots` 19, `--bunch-rings` 20, `--perch-trunk` 21, `--float-nuts` 22, `--float-cover` 23.

[`wingback-armchair`](showcase/wingback-armchair/) — the sixth `household` piece: procedural reading corner on a fringed wool rug (a Queen Anne / Chesterfield wingback in oxblood leather: a reclined back deep-button tufted with thirteen buttons on a diamond lattice, each seated in a funnelled dimple, the leather puffed into pillows and folded into sharp pleats along every line joining two buttons; wings sweeping forward into rolled arms with a tucked English roll, crowned scroll fronts, piped welts and rows of brass nailheads, a nailed front rail, a loose crowned cushion with piped welts on both seams, cabriole front legs on pad feet and splayed rear legs in brass ferrules; beside it a walnut tripod side table with a brass reading lamp, a linen shade and two cloth-bound books), whose feet sunk into the rug, legs tenoned into the body, buttons seated in their dimples, mirror symmetry and size, diamond lattice, table's mass centre inside its feet, cushion resting on the deck and evenly spaced, seated nailheads are recomputed from the mesh, through the same pipeline. Falsifiers `--float-foot` exits 16, `--short-legs` 17, `--sink-buttons` 18, `--odd-wing` 19, `--drift-buttons` 20, `--narrow-tripod` 21, `--lift-cushion` 22, `--bunch-nails` 23.

[`planet-rover`](showcase/planet-rover/) — the sixth `vehicles` piece: procedural six-wheeled planetary science rover on a patch of rocky red-grey regolith (a cream warm-electronics body with quilted gold-foil blankets, a deck of instrument boxes, inlets and a calibration target, a finned power unit on struts between two radiator banks; a rocker on each side pivoting on a boss in the body and a bogie pinned in a clevis on its front end, the two rockers linked through a differential bar on the deck; six drum wheels with 24 chevron grousers, curved flexure spokes and drive actuators, the four corners on steering actuators; a camera mast, a high-gain dish on a two-axis gimbal, a whip; a 5-DOF arm drilling a boulder; harnesses along every leg; ruts behind the wheel lines and 19 broken rocks), the regolith fitted so every wheel sinks 11–19 mm into it. `--float-wheel` exits 16 on every wheel sunk in band, `--offset-pin` 17 on the pivot pins coaxial with their bushings, `--sink-grousers` 18 on the grousers seated on the drum, `--lean-mast` 19 on the mast plumb and the rover's size, `--jam-rocker` 20 on the rockers equal and opposite through the differential, `--offset-steer` 21 on the steering axes through the wheel centres, `--camber-wheel` 22 on the axles level and lateral, `--bunch-grousers` 23 on the grouser pitch, `--overload-turret` 24 on the mass centre inside the support polygon by the 45° tip margin, `--loose-dish` 25 on one connected assembly, while the envelope holds.

</details>

## Examples

Runnable, smoke-gated demos live in [`examples/`](examples/) — each is executed headless on
Blender 5.2 LTS and 4.5 LTS by the `blender-smoke` workflow (5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch), so the screenshots reflect code
that actually runs. Browse them all with filters and full-size renders in the
**[examples gallery](https://tmhsdigital.github.io/Blender-Developer-Tools/gallery/)**,
or expand a category below.

<p align="center">
  <a href="examples/grease-pencil-rosette/"><img src="examples/grease-pencil-rosette/preview.webp" width="24%" alt="Grease pencil rosette: five nested neon rose curves mounted as a sign on a brass-framed black lacquer board" /></a>
  <a href="examples/parent-inverse-orrery/"><img src="examples/parent-inverse-orrery/preview.webp" width="24%" alt="Parent inverse orrery: a brass tabletop orrery with a glowing yellow sun and three planets" /></a>
  <a href="examples/compositor-glare/"><img src="examples/compositor-glare/preview.webp" width="24%" alt="Compositor glare: three neon rings with colored bloom halos" /></a>
  <a href="examples/image-pixels-testcard/"><img src="examples/image-pixels-testcard/preview.webp" width="24%" alt="Image pixels testcard: a studio monitor showing a procedural broadcast test card" /></a>
</p>

<details>
<summary><strong>Materials, shading &amp; compositing</strong> — 7 examples</summary>

<table>
<tr>
<td width="46%" valign="middle">
<a href="examples/swatch-grid/"><img src="examples/swatch-grid/preview.webp" alt="Swatch grid: six material spheres on a two-tier walnut riser, each labelled by an engraved brass plaque — mirror gold, copper and red plastic behind; blue plastic, a glowing emissive globe and white rough in front" /></a>
</td>
<td valign="middle">

### [swatch-grid](examples/swatch-grid/)

A procedural-materials swatch grid — Principled metal and dielectric, the emission pattern,
and the cross-version `set_specular` shim. Doubles as a live proof of the EEVEE engine-id
mapping (`BLENDER_EEVEE` on 5.x, `BLENDER_EEVEE_NEXT` on 4.2-4.5).

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/shader-node-group/"><img src="examples/shader-node-group/preview.webp" alt="Shader node group: five speckled stoneware mugs in oxblood, amber, celadon, teal and cobalt sharing one DippedGlaze node group with different Tint parameters" /></a>
</td>
<td valign="middle">

### [shader-node-group](examples/shader-node-group/)

One reusable `DippedGlaze` group declared via `tree.interface.new_socket`, instanced in five
materials with different Tint values. Witnesses the grouping contract: shared datablock
(`users == 5`), parameters on the group **node** — five mugs share one foot band, dip line
and speckle, and differ only in colour.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/compositor-glare/"><img src="examples/compositor-glare/preview.webp" alt="Compositor glare: three neon rings - violet, cyan, and amber - with colored bloom halos and mirrored reflections on a dark studio floor" /></a>
</td>
<td valign="middle">

### [compositor-glare](examples/compositor-glare/)

Bloom through the compositor on both sides of the 5.0 rewrite — a `Glare` (Fog Glow)
node fed by `Render Layers`, wired via `scene.compositing_node_group` on 5.x and
`scene.node_tree` on 4.x. Witnesses with pixels that the halo falls off strictly with
the compositor on and is exactly zero with it off — and that EEVEE has no `use_bloom`.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/color-attribute-wheel/"><img src="examples/color-attribute-wheel/preview.webp" alt="Color attribute wheel: a domed ceramic HSV color wheel plate with a white center fading into a vivid rainbow rim, ringed in brass and standing on a walnut easel on a dark studio floor with a warm light pool behind it" /></a>
</td>
<td valign="middle">

### [color-attribute-wheel](examples/color-attribute-wheel/)

The modern color-attributes API — `mesh.color_attributes.new()` on the `CORNER`
domain, not the deprecated `vertex_colors` alias, filled by expanding per-vertex
HSV across face corners with `foreach_get`/`foreach_set`. Asserts the attribute
is sized to loop count (not vertex count), is `active_color`, and that the
shader `Attribute` node is actually linked to Base Color.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/image-pixels-testcard/"><img src="examples/image-pixels-testcard/preview.webp" alt="Image pixels testcard: a hooded broadcast reference monitor on a walnut desk showing a procedural broadcast test card — seven neon color bars behind the classic dark circle, a luminance ramp, and a PLUGE row with a white bottom-left origin marker — in a dark studio with a warm pool raking the back wall" /></a>
</td>
<td valign="middle">

### [image-pixels-testcard](examples/image-pixels-testcard/)

A procedural broadcast test card written into `bpy.data.images.new()` with one
`pixels.foreach_set()` call. Asserts the buffer is always flat RGBA (`channels == 4`
even with `alpha=False`), that byte storage quantizes at exactly ≤ 0.5/255 and
strictly > 0 while `float_buffer=True` round-trips at float32 precision, that
`scale()` reallocates (stale-size reads raise), and the `save()` trap: `source`
silently flips to `FILE`, the buffer drops, and later `pixels` reads come from
whatever sits on disk — proven with an imposter file. `save_render()` is the
non-destructive path.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/png-exr-alpha/"><img src="examples/png-exr-alpha/preview.webp" alt="PNG vs EXR alpha: two thin-bezel monitors on a walnut-topped console in a dark studio — left the float→PNG false-unpremul mangling clamps dark rows to white, right the EXR-clean straight buffer, brass desk plates reading FLOAT → PNG and FLOAT → EXR" /></a>
</td>
<td valign="middle">

### [png-exr-alpha](examples/png-exr-alpha/)

`float_buffer=True` images saved to PNG are written as RGBA16 and unpremultiplied
as if associated-alpha — straight-authored dark values at low alpha clamp to white
(closed-form error **0.98** at `(0.02, a=1/255)`). OpenEXR preserves float RGBA;
byte images stay straight 8-bit. Also witnesses `EXR color_mode='RGB'` dropping alpha.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/sky-texture-sun-elevation/"><img src="examples/sky-texture-sun-elevation/preview.webp" alt="Sky texture sun elevation: diptych of a red-granite obelisk on a paved plaza lit only by the sky — left panel sun at 8 degrees, navy dusk with an orange horizon glow and the obelisk face raked orange, right panel sun at 55 degrees, bright blue midday sky, sunlit paving and a short shadow" /></a>
</td>
<td valign="middle">

### [sky-texture-sun-elevation](examples/sky-texture-sun-elevation/)

World `ShaderNodeTexSky` driving Background Color — the sky contract AI lighting
code misses across 4.5 → 5.1. `sky_type` is `NISHITA` on 4.5 LTS and
`MULTIPLE_SCATTERING` on 5.1 (`NISHITA` gone); `dust_density` exists only on 4.5
(`aerosol_density` on 5.1). Two tiny Cycles EXR zenith probes assert
`sun_elevation` 8° → 55° brightens zenith (rise **2.25x** / **1.50x**, gate ≥ 1.25).
Gallery still is a sky-lit obelisk diptych (8° dusk | 55° midday) so the contract reads at thumbnail scale.

</td>
</tr>
</table>

</details>

<details>
<summary><strong>Mesh, curves &amp; text</strong> — 13 examples</summary>

<table>
<tr>
<td width="46%" valign="middle">
<a href="examples/bmesh-gear/"><img src="examples/bmesh-gear/preview.webp" alt="Bmesh gear: a brass 14-tooth gear in a small gear train, meshing with a blued 8-tooth pinion and a spoked 22-tooth gunmetal wheel, each bolted through a hub boss to a dark steel backplate on a walnut plinth" /></a>
</td>
<td valign="middle">

### [bmesh-gear](examples/bmesh-gear/)

A 14-tooth gear built entirely with bmesh — with `bm.free()` in a `try`/`finally`, as the
ownership contract demands. Asserts the closed-form vert/edge/face counts and that the
result is watertight (every edge borders exactly two faces).

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/uv-layer-grid/"><img src="examples/uv-layer-grid/preview.webp" alt="UV layer grid: two walnut-framed tile panels on oak studio easels with brass placards — left, NO UV LAYER, one flat teal face (the calc_uvs silent no-op hazard), right, UV LAYER FIRST, a saturated magenta-cyan checker (the pre-create repair), under a warm wall pool" /></a>
</td>
<td valign="middle">

### [uv-layer-grid](examples/uv-layer-grid/)

`bmesh.ops.create_grid(..., calc_uvs=True)` is a silent no-op unless a UV layer already
exists — without one an Image Texture samples texel (0, 0) everywhere. Asserts the hazard,
the pre-create repair against closed-form grid UVs, and an explicit assignment fallback —
then re-reads its own render and fails unless the pixels prove the flat-vs-checker split.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/wave-displace/"><img src="examples/wave-displace/preview.webp" alt="Wave displace: a cast bronze tile in a walnut frame whose top is displaced into smooth standing-wave crests, verdigris pooled in the troughs" /></a>
</td>
<td valign="middle">

### [wave-displace](examples/wave-displace/)

Bulk vertex IO at real scale — 9,409 vertices displaced into a standing wave with **one
`foreach_get` and one `foreach_set`**, no per-vertex access. Asserts the count is unchanged,
the Z span matches the amplitude, and a probe vertex matches the closed-form wave.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/shape-key-blend/"><img src="examples/shape-key-blend/preview.webp" alt="Shape-key blend: three cobalt-glazed ceramic vases with an ochre band on a dark studio floor - the same vase at Tall shape-key values 0, 0.5 and 1, squat jar to amphora to flared trumpet vase, left to right, with thin pale rings of the jar's belly around the tallest" /></a>
</td>
<td valign="middle">

### [shape-key-blend](examples/shape-key-blend/)

A relative Tall shape key that turns a squat ceramic jar into a trumpet vase,
lifting and flaring the rim — authored through `shape_key_add` / `key_blocks` / `.value`. Witnesses that shape keys do not rewrite
`mesh.vertices`: every evaluated vert matches `basis + value × (key − basis)`.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/curve-bevel-arc/"><img src="examples/curve-bevel-arc/preview.webp" alt="Curve bevel arc: a red horseshoe magnet built from one beveled Bezier curve, its filled end caps turned to the camera as steel pole faces, iron filings arcing between the poles and Bezier-wire paper clips clinging to them" /></a>
</td>
<td valign="middle">

### [curve-bevel-arc](examples/curve-bevel-arc/)

A beveled Bezier semicircle authored on `bpy.types.Curve` — `splines.new('BEZIER')`,
`bezier_points`, `bevel_depth`, `use_fill_caps` — so the curve renders as a solid tube
without a prior mesh conversion — staged as a horseshoe magnet whose capped ends
are the pole faces. Asserts eight points, `bevel_depth == 0.15`, and evaluated
topology 1044 verts / 1028 faces.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/text-version-stamp/"><img src="examples/text-version-stamp/preview.webp" alt="Text version stamp: beveled gold version numerals standing on a chamfered dark stone plinth with a BLENDER caption on a brushed-steel nameplate — the body text is the live bpy.app.version_string" /></a>
</td>
<td valign="middle">

### [text-version-stamp](examples/text-version-stamp/)

A beveled 3D stamp of the running Blender version — a `TextCurve` whose `body` is the
live `bpy.app.version_string`, so every render self-documents which Blender made it.
Asserts the TextCurve solids closed form (evaluated z-extent = 2 × (extrude +
bevel_depth), bevel widening the outline by 2 × bevel_depth), that flat text is filled
but planar, that body edits regenerate geometry, that `version_string` is not bare
semver on LTS builds (`"4.5.11 LTS"`), and that a Mesh reference dies at
`to_mesh_clear()`.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/depsgraph-export/"><img src="examples/depsgraph-export/preview.webp" alt="Depsgraph-evaluated export: the sparse control cage of a game controller drawn as orange wire and vertex beads over faint blue facets, beside the smooth subdivided cobalt controller with sticks, d-pad and colored face buttons that the OBJ export contains, on a dark studio floor with a warm light pool behind" /></a>
</td>
<td valign="middle">

### [depsgraph-export](examples/depsgraph-export/)

A depsgraph-evaluated export — builds a game controller whose shell is a 90-vertex quad cage
under `SUBSURF`, measures every mesh via `evaluated_get().to_mesh()` / `to_mesh_clear()`,
asserts the evaluated shell matches the Catmull-Clark closed form (1,410 vertices), and asserts
`wm.obj_export` ships the modifier-applied geometry (exported vertex count == evaluated > base).

</td>
</tr>
<tr>
<td width="46%" valign="middle">
check-only, no gallery still — no geometry
</td>
<td valign="middle">

### [eval-mesh-datablock-name](examples/eval-mesh-datablock-name/)

`evaluated_get().data.name` is generic `Mesh` on 4.5.11 and 5.1.2 and equals
the source name on 5.2.1. `to_mesh().name` stays the source name on all
three. `--assume-distinct-names` is red only on 5.2.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/usd-export-evaluation-mode/"><img src="examples/usd-export-evaluation-mode/preview.webp" alt="USD export evaluation_mode: two brass goblets on dark plinths, each re-imported from its own USDA file — left an eight-sided 130-point VIEWPORT export, right a smooth 8450-point RENDER export" /></a>
</td>
<td valign="middle">

### [usd-export-evaluation-mode](examples/usd-export-evaluation-mode/)

`wm.usd_export` `evaluation_mode='RENDER'` versus `'VIEWPORT'`. TESSELLATE writes
the closed-form Catmull-Clark counts (26/24 vs 98/96); default BEST_MATCH writes
the 8-vert cage and the mode is silent. Asserts the USDA point counts, not the
still.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/vse-cut-list/"><img src="examples/vse-cut-list/preview.webp" alt="VSE cut list: a reference monitor showing the two-by-two program wall — crimson, teal, and amber color strips plus the mid cross-blend cell, composited by the sequencer over a scene strip — above a timeline console laying out the same strip spans as coloured blocks with handle notches and a playhead" /></a>
</td>
<td valign="middle">

### [vse-cut-list](examples/vse-cut-list/)

The sequencer API rename from 4.5 LTS to 5.x — `strips` (never `.sequences`), `new_effect`
ending in `length=` vs `frame_end=`, and `left_handle`/`right_handle`/`duration` replacing
the deprecated `frame_final_*`. Asserts closed-form spans, GC wiring and clamping, the
consumed-input compositing contract, and a save/reload round-trip.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/light-link-studio/"><img src="examples/light-link-studio/preview.webp" alt="Light link studio: two identical porcelain chess kings on dark plinths, the LINKED king glowing under an amber key with a warm floor inlay beneath it, the UNLINKED king cool grey beside it - one key light restricted to the hero collection" /></a>
</td>
<td valign="middle">

### [light-link-studio](examples/light-link-studio/)

Object light linking proven in pixels: a key linked to the hero's collection
lights only the hero (4.0x luminance ratio at projected centers), and
unlinking in the same check raises the decoy 244% with 0.0% hero drift. The
API is `obj.light_linking` — the Light datablock has none — and EEVEE Next
honors linking too (measured), with Cycles pinned for deterministic samples.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/vse-gamma-cross/"><img src="examples/vse-gamma-cross/preview.webp" alt="VSE gamma cross: a hooded grading monitor on a walnut riser beside a three-trackball control surface, its screen showing every frame of an orange-to-azure cross as two filmstrips - the GAMMA_CROSS strip on top sinking to dark grey at mid-cross, the linear CROSS strip beneath passing through violet" /></a>
</td>
<td valign="middle">

### [vse-gamma-cross](examples/vse-gamma-cross/)

The GAMMA_CROSS fade is not the naive linear mix: it blends in a gamma-0.5
space, `((1-t)·√A + t·√B)²` with `t = (frame − start) / duration` — never 1
inside the effect. Per-frame sample renders assert the closed form (mid dips
0.250 below the sRGB lerp), and the AgX-default sampling trap is documented
(`view_transform = 'Standard'` is mandatory for any pixel witness).

</td>
</tr>
<tr>
<td width="46%" valign="middle">
check-only, no gallery still — no geometry
</td>
<td valign="middle">

### [vse-linear-modifiers](examples/vse-linear-modifiers/)

`ColorStrip.use_linear_modifiers` is a bool on 4.5.11 and 5.1.2; the same
getattr is `AttributeError` on 5.2.1. Version-guarded `hasattr` then read
exits 0 on all three. `--assume-present` is red only on 5.2.

</td>
</tr>
</table>

</details>

<details>
<summary><strong>Geometry Nodes</strong> — 7 examples</summary>

<table>
<tr>
<td width="46%" valign="middle">
<a href="examples/gn-sdf-remesh/"><img src="examples/gn-sdf-remesh/preview.webp" alt="Geometry Nodes SDF remesh: a vase kitbashed from overlapping clay primitives beside the same kit fused by the SDF remesh into one cobalt-glazed shell" /></a>
</td>
<td valign="middle">

### [gn-sdf-remesh](examples/gn-sdf-remesh/)

A Geometry Nodes SDF remesh (`MeshToSDFGrid` → `GridToMesh` at the SDF zero-level).
Witnesses the fix that an SDF grid is meshed with **Grid to Mesh**, not Volume to Mesh,
and that a `Set Material` node carries the material through the remesh.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/gn-instance-grid/"><img src="examples/gn-instance-grid/preview.webp" alt="GN instance grid: a cobalt-blue 3x3 macropad whose nine cream keycaps are instanced onto a Geometry Nodes Mesh Grid, one orange accent key picked out by a position-field Set Material" /></a>
</td>
<td valign="middle">

### [gn-instance-grid](examples/gn-instance-grid/)

A generative Geometry Nodes tree — Mesh Grid → Instance on Points (a modeled keycap via
`Object Info`) → Realize Instances — attached as a `NODES` modifier with no Group Input.
Asserts evaluated topology is verts = faces = 1089 (9 keycaps × 121), and a position-field
`Set Material` lands the orange accent on exactly one keycap.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/gn-modifier-inputs/"><img src="examples/gn-modifier-inputs/preview.webp" alt="GN modifier inputs: three spiral staircases from one shared Geometry Nodes tree, 1, 2 and 3 meters tall with 7, 17 and 27 oak treads, proving per-modifier Height writes land on 5.2 RNA and on 4.5 dict assignment" /></a>
</td>
<td valign="middle">

### [gn-modifier-inputs](examples/gn-modifier-inputs/)

One Geometry Nodes spiral-staircase tree, three modifier copies. Writes a Float Height
input through `mod.properties.inputs` on 5.2 and `mod[identifier]` on 4.5/5.1; the tree
turns 1 / 2 / 3 m into 7 / 17 / 27 treads. Asserts readback and evaluated Z-extent equal
1 / 2 / 3. The 5.1 dict form raises TypeError on 5.2.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/gn-zone-iterate/"><img src="examples/gn-zone-iterate/preview.webp" alt="GN zone iterate: four amber-to-red blocks on a walnut plinth (Repeat Zone) beside a spindle of six teal-to-mint blocks (For Each Element) on a dark studio floor, proving pair_with_output actually iterates" /></a>
</td>
<td valign="middle">

### [gn-zone-iterate](examples/gn-zone-iterate/)

Repeat Zone and For Each Element only iterate after `pair_with_output`. Asserts
evaluated cubes against closed forms — Repeat `8×(1+N)` with X-centers at
`k×1.2`, For Each `8×P` with Z-centers at `i×0.6+0.21` — not that the zone
nodes exist. Unpaired evaluates empty; For Each's main Geometry socket is a
passthrough.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/gn-sim-fountain/"><img src="examples/gn-sim-fountain/preview.webp" alt="GN simulation fountain: a two-tier sandstone fountain whose twenty jets are strings of cyan droplet beads, each bead a stepped Simulation Zone position threaded on its thin closed-form ballistic arc" /></a>
</td>
<td valign="middle">

### [gn-sim-fountain](examples/gn-sim-fountain/)

A Simulation Zone integrates twenty jets under gravity with the exact
constant-g update, and every stepped frame lands on `p0 + v0 t - g t^2/2`
(worst 6.6e-7 m). Two silent traps, identical on 4.5, 5.1 and 5.2: a direct
`frame_set(N)` jump runs one step, not N; and `calculate_to_frame` returns
`PASS_THROUGH` headless and leaves interpolated frames. Only a bake gives
random access.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/gn-socket-rename/"><img src="examples/gn-socket-rename/preview.webp" alt="GN socket rename: a brushed copper height-gauge column on a granite surface plate, graduated every 0.1 m from its stored gauge_h attribute, with a brass scriber resting on a stack of steel gauge blocks" /></a>
</td>
<td valign="middle">

### [gn-socket-rename](examples/gn-socket-rename/)

Compare INT and Random Value FLOAT socket identifiers collapsed in 5.2
(`A_INT` / `Min_001` gone; `A` / `Min` reused). Enabled-name lookup wires
on 4.5, 5.1, and 5.2. Asserts 16 verts and POINT `gauge_h=1.80` on eight
column verts. `--legacy-ids` is red only on 5.2.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
check-only, no gallery still — item-name round-trip is not thumbnail-legible
</td>
<td valign="middle">

### [gn-bundle-roundtrip](examples/gn-bundle-roundtrip/)

Combine / Separate Bundle on 5.x (`NodeCombineBundle`, not
`GeometryNodeCombineBundle`). Asserts evaluated 8/6 plus x-extent
`[0.5, 2.5]` and POINT `bundle_mark=0.314159` — count-only is a cube that
never entered the bundle. Skips 4.5 (`min_version` 5.0); `--force-run`
fails creating the 5.x RNA.

</td>
</tr>
</table>

</details>

<details>
<summary><strong>Animation, rigging &amp; constraints</strong> — 6 examples</summary>

<table>
<tr>
<td width="46%" valign="middle">
<a href="examples/turntable/"><img src="examples/turntable/preview.webp" alt="Turntable: a copper Suzanne on a lathed display turntable with a vented motor base, a platter rim ticked once per keyed frame, and an amber arrow showing the keyed turn" /></a>
</td>
<td valign="middle">

### [turntable](examples/turntable/)

A slotted-actions Z-rotation turntable keyed through the cross-version channelbag path
(`get_channelbag_for_slot`). Witnesses the slotted-actions fix: ensure-helper channelbag on
5.x, `strip.channelbag` on 4.4/4.5.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/driver-wave/"><img src="examples/driver-wave/preview.webp" alt="Driver wave: a pipe-organ facade of sixteen brass pipes on a walnut windchest whose heights form a sine wave, each driven by a driver_namespace function" /></a>
</td>
<td valign="middle">

### [driver-wave](examples/driver-wave/)

A `driver_namespace` function driving sixteen column heights through SCRIPTED drivers.
Witnesses the evaluation contract: driven values appear after a view-layer update on the
evaluated copy **and** the flushed-back original, and both must match the closed form.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
check-only, no gallery still — no geometry
</td>
<td valign="middle">

### [exit-pre-sidecar](examples/exit-pre-sidecar/)

`bpy.app.handlers.exit_pre` writes `$BDT_SMOKE_SIDECAR` as Blender dies; the
harness asserts `exit_pre-ok` after the process exits. Skips 4.5
(`min_version` 5.1). `--silent-handler` / `--no-handler` miss the file;
`--wrong-text` / `--write-in-main` fail the content check.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/damped-track-aim/"><img src="examples/damped-track-aim/preview.webp" alt="Damped Track aim: twelve red-and-brass spotlight heads on stands in an open ring, each lens constrained to face a glowing amber orb on a brass pedestal" /></a>
</td>
<td valign="middle">

### [damped-track-aim](examples/damped-track-aim/)

Aim constraints via the data API — `Object.constraints.new('DAMPED_TRACK')` with
`target` and `TRACK_Z`, not `bpy.ops.object.constraint_add` in a headless loop.
Asserts twelve unmuted Damped Track constraints and evaluated local `+Z` alignment
toward the core (dot ≥ 0.998).

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/armature-bend/"><img src="examples/armature-bend/preview.webp" alt="Armature bend: three ribbed bellows hoses on steel foot flanges showing rest, half, and full curl under a four-bone armature, per-bone weight bands blending teal through amber to coral at the joints" /></a>
</td>
<td valign="middle">

### [armature-bend](examples/armature-bend/)

A four-bone chain built with `edit_bones` skins a tapered tube through name-bound
vertex groups, posed into a curl and read back through the depsgraph. Asserts that
`edit_bones` is empty outside edit mode, and that the armature modifier is exactly
linear blend skinning — every evaluated vertex equals
Σ wᵢ · (`pose_bone.matrix` @ `bone.matrix_local.inverted()`) @ rest, with the root
ring pinned and the tip deflected. A straight tube is a failure.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/parent-inverse-orrery/"><img src="examples/parent-inverse-orrery/preview.webp" alt="Parent inverse orrery: a brass tabletop orrery with a glowing yellow sun, three planets on pivot arms inside brass orbit rings, and a silver moon, on a dark studio floor" /></a>
</td>
<td valign="middle">

### [parent-inverse-orrery](examples/parent-inverse-orrery/)

A brass orrery parented entirely through the data API — the keep-world idiom
`child.parent = pivot; child.matrix_parent_inverse = pivot.matrix_world.inverted()`
carries arms, planets, and a two-level moon through spinning pivots. Asserts bare
`.parent =` really teleports, `matrix_world` is stale until `view_layer.update()`,
and every orbit lands on its closed form.

</td>
</tr>
</table>

</details>

<details>
<summary><strong>Context &amp; Grease Pencil</strong> — 5 examples</summary>

<table>
<tr>
<td width="46%" valign="middle">
<a href="examples/temp-override-join/"><img src="examples/temp-override-join/preview.webp" alt="Temp-override join: a red enamel hurricane lantern with a glowing amber globe, wire guard, brass knob and wooden bail grip, joined from seven parts into one object" /></a>
</td>
<td valign="middle">

### [temp-override-join](examples/temp-override-join/)

A hurricane lantern joined from seven part objects under `bpy.context.temp_override` — the
supported replacement for the removed `context.copy()` dict-pass form. Asserts one mesh
remains, sources are gone, and the five part materials merge with every face kept on its own.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/cross-version-property-delete/"><img src="examples/cross-version-property-delete/preview.webp" alt="Cross-version property delete: two stage lamps on one stand — the left lamp keeps its ID property and glows, lighting a placard reading obj[&quot;accession&quot;] = 42; the right lamp had del obj[&quot;accession&quot;] and stands dark" /></a>
</td>
<td valign="middle">

### [cross-version-property-delete](examples/cross-version-property-delete/)

Custom ID properties are removed with `del id_block[key]`, not `property_unset`.
IDs are built with `bpy.data.objects.new` — the snippet `__main__` keys off
`active_object` and is dark headless. Same `del` on 4.5 LTS and 5.x.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
check-only, no gallery still — no geometry
</td>
<td valign="middle">

### [mesh-automasking-settings](examples/mesh-automasking-settings/)

`MeshAutomaskingSettings` is absent on 4.5.11 and 5.1.2, present on 5.2.1.
Old `Brush` automasking attributes are gone on 5.2; read
`.mesh_automasking_settings` instead. `--assume-brush-attrs` is red only
on 5.2.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/grease-pencil-rosette/"><img src="examples/grease-pencil-rosette/preview.webp" alt="Grease pencil rosette: five nested neon rose curves drawn as tapered Grease Pencil v3 strokes, cyan through magenta to red, mounted as a neon sign on a brass-framed black lacquer board and washing it with coloured spill" /></a>
</td>
<td valign="middle">

### [grease-pencil-rosette](examples/grease-pencil-rosette/)

Five nested rose curves drawn with the Grease Pencil v3 attribute API — layer →
`frames.new(1).drawing` → `add_strokes` → per-point position, radius, opacity, and
vertex color. Asserts the GPv3 address break: on 4.5 GPv3 is `grease_pencils_v3`
while `grease_pencils` is still legacy; on 5.x legacy is gone and GPv3 owns the
name. Point writes lazily materialize attribute layers, and every position
round-trips through the raw `POINT` buffer.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/gp-lineart-contour/"><img src="examples/gp-lineart-contour/preview.webp" alt="GP Line Art contour: a cel-shaded red-and-white lighthouse on a rocky islet with a keeper's cottage and rowboat, inked in bold black Grease Pencil Line Art strokes, proving modifiers.new LINEART with source_object evaluation" /></a>
</td>
<td valign="middle">

### [gp-lineart-contour](examples/gp-lineart-contour/)

Grease Pencil `LINEART` modifier ink via the depsgraph on a cel-shaded
lighthouse diorama — not Freestyle and not hand-drawn strokes. `source_object`
is load-bearing (clear → 0 strokes); every edge type off → 0; the drawing is
**255** strokes / **1393** points on all three binaries, gated so dropping any
one edge type fails. Stroke width: `thickness` exists on 4.5, `AttributeError`
on 5.1 — portable path is `radius`.

</td>
</tr>
</table>

</details>

<details>
<summary><strong>Game asset pipeline</strong> — 22 examples</summary>

<table>
<tr>
<td width="46%" valign="middle">
<a href="examples/gltf-export-roundtrip/"><img src="examples/gltf-export-roundtrip/preview.webp" alt="glTF export round-trip: one olive-drab sci-fi supply crate on a dark studio floor, its right half traced by an amber wire cage of the re-imported glTF triangles that lands exactly on every bevel, rivet and vent slat, proving the export/import round-trip preserves the asset" /></a>
</td>
<td valign="middle">

### [gltf-export-roundtrip](examples/gltf-export-roundtrip/)

A game-prop supply crate round-tripped through `bpy.ops.export_scene.gltf` and
the importer — the check reads the `.gltf` JSON and `.bin` buffer directly.
Witnesses the +Y-up convention baked into vertex data with no node rotation,
`export_apply` shipping the evaluated mesh (one disk vertex per evaluated
loop), V-flipped UVs, and per-triangle material bindings — all against the
depsgraph-evaluated mesh. The exporter/importer RNA signatures are probed
byte-identical on 4.5.11 and 5.1.2 and guarded against future renames.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/export-preset-axis/"><img src="examples/export-preset-axis/preview.webp" alt="Export preset axis: a red-and-white radio mast exported under Unity and Godot glTF presets and re-imported side by side on a dark studio floor, each beside a red-green-blue axis gizmo - Unity standing with blue Z up, Godot lying with green Y up and blue Z along the mast - proving the two files have different vertex orientation" /></a>
</td>
<td valign="middle">

### [export-preset-axis](examples/export-preset-axis/)

The same radio-mast mesh under the Unity (`export_yup=True`) and Godot
(`export_yup=False`) glTF presets. Re-importing each file proves the axis
conversion: Unity stands, Godot lies along `-Y`. `--same-axis` exports both
Y-up and the differ check exits 9. Neighbor of
[`gltf-export-roundtrip`](examples/gltf-export-roundtrip/).

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/lod-decimate-chain/"><img src="examples/lod-decimate-chain/preview.webp" alt="LOD decimate chain: three identical cream-and-red retro rockets with brass trim and a porthole on a dark studio floor, each under a dark triangle wireframe that coarsens left to right, labelled 4784, 2392 and 860 tris" /></a>
</td>
<td valign="middle">

### [lod-decimate-chain](examples/lod-decimate-chain/)

One recognizable asset at three LODs via `DECIMATE` modifiers evaluated through
the depsgraph. Asserts the reduction is non-destructive (the original datablock
keeps its closed-form counts), each LOD's evaluated triangle count lands within
5% of `ratio x base` (measured 0.00–0.13%), and the silhouette-critical bbox
survives within 1e-3 — with a stacked Decimate and an oblique fin's shaved
plate corner as the caught failure modes. A wireframe of each evaluated mesh
makes the density drop visible.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/bake-normal-high-to-low/"><img src="examples/bake-normal-high-to-low/preview.webp" alt="Bake normal high to low: an unlit tangent-space normal map card, the 3200-tri ribbed bronze source plate, and the 900-tri collapse-decimated plate wearing that map, captioned on a dark studio floor" /></a>
</td>
<td valign="middle">

### [bake-normal-high-to-low](examples/bake-normal-high-to-low/)

Cycles cage-bakes a ribbed hatch onto a `DECIMATE COLLAPSE` LOD. Asserts the
map is not flat (frac 0.7211, MAD 0.09356 vs `(0.5, 0.5, 1.0)`) while a
flat-source control is (frac 0.0000). `--flat-source` exits 5. Byte-identity
across 4.5 / 5.1 / 5.2 is not the contract — Cycles bake is stochastic.
Neighbor of [`lod-decimate-chain`](examples/lod-decimate-chain/).

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/vertex-weight-limit/"><img src="examples/vertex-weight-limit/preview.webp" alt="Vertex weight limit: an orange industrial robot arm reaching down with a two-jaw gripper, painted with its own post-limit skin weights - each rigid segment glows in its bone colour and the back cables grade blue to teal to violet to magenta across the joints" /></a>
</td>
<td valign="middle">

### [vertex-weight-limit](examples/vertex-weight-limit/)

The game-engine max-four-bone-influences constraint, enforced through the data
API (`v.groups` + `VertexGroup.remove` + renormalize) rather than the
`bpy.ops.object.vertex_group_limit_total` context path. Asserts the pre-limit
cables really carry five influences, no vertex ends over the cap, weights still
sum to one, the pose survives pruning, and the modifier is still exact linear
blend skinning read back from the mesh's own deform layer. The render paints
those post-limit weights onto the arm as a colour attribute.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/triangulate-tangents/"><img src="examples/triangulate-tangents/preview.webp" alt="Triangulate and tangents: a machined steel buckler on a walnut stand - pointed brass boss, domed face cut with concentric lathe grooves, riveted brass rim - proving the mikktspace tangent field a normal map depends on" /></a>
</td>
<td valign="middle">

### [triangulate-tangents](examples/triangulate-tangents/)

The normal-mapping tangent-space contract: deterministic triangulation
(`calc_tangents` aborts on any ngon), unit orthogonal tangent frames,
`bitangent == sign * (n x t)`, and mikktspace matching the independent
edge/UV-delta formula on smooth fields. Documents the planar-on-cylinder UV
degeneracy (tangent collapses onto the normal) and the stale layer-handle
hazard that silently corrupts measurements on 4.5.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/gltf-skin-roundtrip/"><img src="examples/gltf-skin-roundtrip/preview.webp" alt="glTF skin round-trip: two orange-plated mech scorpions face off on a dark studio floor - the authored one on the left with its tail coiled over its back and claws tucked, the re-imported one on the right driven through its imported bones into a strike, tail reared high and claws raised" /></a>
</td>
<td valign="middle">

### [gltf-skin-roundtrip](examples/gltf-skin-roundtrip/)

The skinning counterpart to `gltf-export-roundtrip`: a 21-bone rigged mech
scorpion exported with `export_skins` and re-imported, asserting the joint
list, JOINTS_0/WEIGHTS_0 unit sums, bone/parent/rest-matrix round-trip,
bit-exact weights, and identical deformation of the re-imported rig — plus
the parenting hazard: unparented skinned meshes let the exporter bind an
armature by name.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/collision-hull-proxy/"><img src="examples/collision-hull-proxy/preview.webp" alt="Collision hull proxy: a red fire hydrant street prop with a yellow bonnet on a dark studio floor, enclosed in four faceted translucent cyan collision shells - the compound convex hull set a game engine ingests" /></a>
</td>
<td valign="middle">

### [collision-hull-proxy](examples/collision-hull-proxy/)

The compound-collision contract prop pipelines (engines generally,
FiveM/GTA-style prop workflows specifically) ingest: one convex hull piece
per part group, built with `bmesh.ops.convex_hull` from a coarse
`sec(π/n)`-inflated cage — never the dense render mesh, whose hull measures
380 faces, over the 255-face per-piece engine budget. Closed-form plane
tests prove containment (4.4e-08), convexity, watertightness, outward
winding, and Euler characteristic 2 per piece. Proud details cost cage rows;
concave grooves are free.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/custom-normals-shade/"><img src="examples/custom-normals-shade/preview.webp" alt="Custom normals and shade by angle: three olive-drab jerry cans with X-pressed panels, triple handles and red-sealed spouts on a dark studio floor - one faceted flat, one smeared glossy by smooth-everything, one crisp by-angle with its sharp edges traced in thin amber lines - proving the post-4.1 shading contract" /></a>
</td>
<td valign="middle">

### [custom-normals-shade](examples/custom-normals-shade/)

The shading contract a prop's silhouette depends on: since Blender 4.1,
hard edges are mesh data (face smooth flags + `sharp_edge` attribute), and
`use_auto_smooth` / `use_custom_normals` / `calc_normals` are AttributeError
on **both** 4.5 LTS and 5.1. `set_sharp_from_angle` marks sharp exactly the
edges an independent dihedral recompute predicts; evaluated loop normals
weld across smooth edges and split by the dihedral across sharp ones;
custom split normals survive depsgraph evaluation within their int16
quantization (3.904e-05, not float-exact). Documents the legacy
`shade_auto_smooth` operator trap: CANCELLED headless on 4.5, FINISHED
with the Smooth-by-Angle modifier on 5.1.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/mesh-hygiene-audit/"><img src="examples/mesh-hygiene-audit/preview.webp" alt="Mesh hygiene audit: two blue flanged street valves with brass handwheels — the left dirty copy with a red-outlined hole, a red flipped patch on the bonnet, an amber ngon on the base flange and three red loose-vert beads, the right one intact — proving the engine-ingest topology checklist" /></a>
</td>
<td valign="middle">

### [mesh-hygiene-audit](examples/mesh-hygiene-audit/)

The mesh-cleanliness contract a prop pipeline relies on before engine ingest:
no ngons, no loose vertices, every edge bordering exactly two faces, no
zero-area faces, contiguous and outward winding on all eight parts of a
flanged street valve, and Euler `V − E + F == 2` on its body casting
(measured 802/1632/832, volume 0.453344). Companion to
[`collision-hull-proxy`](examples/collision-hull-proxy/) (hull watertightness)
and [`bmesh-gear`](examples/bmesh-gear/) (parametric closed solids). Still: a
dirty copy with a hole, flipped patch, ngon and loose verts marked from live
audit data beside the intact valve; the paint glows red on any back face.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/prop-origin-transform/"><img src="examples/prop-origin-transform/preview.webp" alt="Prop origin transform: two green street utility pedestals, each centred in a floor pivot ring — left, the orange conduit elbow parented with matrix_parent_inverse stays bolted to its mount; right, bare child.parent = parent throws the elbow into the air beyond the slab while a glowing cyan outline marks its empty seat — proving scale apply, base origin, and matrix_parent_inverse" /></a>
</td>
<td valign="middle">

### [prop-origin-transform](examples/prop-origin-transform/)

The origin / scale-apply / MPI contract a prop pipeline relies on before
engine ingest: data-API scale bake to exactly `(1,1,1)`, local bbox
`min.z == 0` (origin at base), world AABB unchanged across the bake, and
`matrix_parent_inverse` so a flanged conduit elbow stays on its mount.
Extends [`parent-inverse-orrery`](examples/parent-inverse-orrery/) without
retreading orbits. Dual-panel still: TRAP (bare parent — empty socket +
teleported flange) vs MPI KEEP.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/soccer-ball-goldberg/"><img src="examples/soccer-ball-goldberg/preview.webp" alt="Soccer ball Goldberg: a round white soccer ball with black pentagon panels and dark stitched seams around every hexagon, resting on mown pitch turf beside a chalked touchline — a bmesh icosphere truncated at one-third per edge into the Goldberg polyhedron, proving closed-form counts, uniform degree, equal edges, planar faces, one circumsphere, and panels bound by face vertex count" /></a>
</td>
<td valign="middle">

### [soccer-ball-goldberg](examples/soccer-ball-goldberg/)

The truncated icosahedron as a bmesh contract: every icosphere edge cut at
exactly `1/3`, faces ordered by link-topology walks (nothing hand-listed),
and every invariant asserted as a closed form — `60/90/32`, Euler 2, uniform
degree 3, edge lengths within 3e-5, planar faces against an independent
Newell normal, one circumsphere, and the black pentagons / white hexagons
bound by face vertex count, never enumeration order. Sibling to
[`bmesh-gear`](examples/bmesh-gear/) (parametric extrusion): this one
witnesses polyhedral invariants plus per-face-class material binding. The
smoothed render inverts on sight if the panel binding does.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/car-mirror-symmetry/"><img src="examples/car-mirror-symmetry/preview.webp" alt="Car mirror symmetry: a smooth candy-red stylized hatchback on a dark studio floor, tinted glass, black pillars and arch cladding, a chrome window sill, silver five-spoke alloy wheels, and a matched headlamp and door-mirror pair either side of one centered grille — lofted as one half and completed by the Mirror modifier evaluated through the depsgraph, proving 2n-c counts, exact negated-X partners, a welded watertight centerline, and wheels mirrored about origins on the plane" /></a>
</td>
<td valign="middle">

### [car-mirror-symmetry](examples/car-mirror-symmetry/)

The Mirror + depsgraph contract: the datablock holds only the authored half
(676/1289/614, 104 centerline verts) while the evaluated mesh is the welded
whole — exactly `2n − c` verts, watertight with Euler 2, every vertex paired
at negated X (deviation 0.0). Wheels, lamps, grille, mirrors and handles mirror
about object origins parked **on** the symmetry plane — offset the data, never the object.
Companion to [`depsgraph-export`](examples/depsgraph-export/) (evaluated-vs-
original) and [`shape-key-blend`](examples/shape-key-blend/) (non-destructive
evaluation). Break the mirror and the render is literally half a car.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/attribute-domain-shear/"><img src="examples/attribute-domain-shear/preview.webp" alt="Attribute domain shear: two striped patio parasols on a terracotta paver deck behind slate placards — left CORNER-domain with crisp crimson and cream stripes, right naive POINT-domain with the stripes smeared pink along the seams and the front red panel gone white, proving last-write-wins shear at shared vertices" /></a>
</td>
<td valign="middle">

### [attribute-domain-shear](examples/attribute-domain-shear/)

What `POINT` versus `CORNER` **means** on `Mesh.color_attributes` once a mesh
has shared vertices. An eight-wedge pinwheel around one raised hub: CORNER
authoring holds each wedge's exact color (hub corners disagree by face,
err ≤ 1e-6), while the naive per-wedge POINT loop rewrites every shared
vertex once per neighbor and the **last write wins** — the hub reads
palette[K−1], and the measured shear matches the palette closed form
(0.751031) exactly. Companion to
[`color-attribute-wheel`](examples/color-attribute-wheel/) (domain sizing,
`active_color`, the shader Attribute node). The render paints two striped
parasols with the same authoring functions. The broken state is in frame:
the right parasol's stripes smear along the seams and one crimson panel
turns cream.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/degenerate-bevel-weld/"><img src="examples/degenerate-bevel-weld/preview.webp" alt="Degenerate bevel weld: two blue hard-shell equipment cases — left with a flat end panel and clean chamfer bands, right with its rim rolled into a knife ridge traced by a thin red-orange seam line and small amber pins at the zero-area faces, proving the half-dimension bevel collapse ships degenerate triangles" /></a>
</td>
<td valign="middle">

### [degenerate-bevel-weld](examples/degenerate-bevel-weld/)

The half-dimension bevel collapse, isolated. A slab beveled at
`offset == min_dim/2` pinches its band into exactly **12 zero-area faces**
(4 min-axis edges × 3 segments) with 16 coincident verts and `min_area`
down 3.2e5× — and a stdlib re-parse of the exported GLB counts **32
degenerate triangles shipped** to disk, where an engine merge-by-distance
welds their loops. Companion to
[`gltf-export-roundtrip`](examples/gltf-export-roundtrip/) (where the count
check first caught the weld) and [`mesh-hygiene-audit`](examples/mesh-hygiene-audit/)
(topology gates). Seam markers are placed from live mesh data.

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/modular-kit-snap/"><img src="examples/modular-kit-snap/preview.webp" alt="Modular kit snap: a corridor run of four tiling segments — dark steel walls with painted teal panels, diamond-plate walkways, hazard-striped orange trim rails, and ceiling light strips converging on a glowing amber doorway, with every joint seamless because the boundary verts snap exactly to the tile grid" /></a>
</td>
<td valign="middle">

### [modular-kit-snap](examples/modular-kit-snap/)

A tiling corridor kit where the snap is the contract. **16 boundary verts**
on `x ∈ {0, 4}` within **1e-6 m**, opposing end loops coincident under the
tile offset, and a linked duplicate's joint positions matching within 1e-6 —
zero gap, zero overlap. Shell bbox equals the declared tile exactly, the
tube is manifold except its two open ends, and all twelve detail parts are
contained inside the tile. The unsnapped probe (3 mm skew) fails with the
measured error printed. Companion to
[`prop-origin-transform`](examples/prop-origin-transform/) (pivot discipline)
and [`mesh-hygiene-audit`](examples/mesh-hygiene-audit/) (topology gates).

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/lightmap-uv-channel/"><img src="examples/lightmap-uv-channel/preview.webp" alt="Lightmap UV channel: a wooden market cart on spoked wheels with a cream canvas canopy beside a walnut-framed atlas display glowing with the bed's packed lightmap islands — proof the second UV layer packs with no overlaps, channel zero untouched" /></a>
</td>
<td valign="middle">

### [lightmap-uv-channel](examples/lightmap-uv-channel/)

The second UV layer engines need for baked lighting, on a reusable market
cart. Per-part `UVMap`/`UVLight` with **`active` vs `active_render` pinned**
(the edit-mode UV ops clear both flags — re-assert or lose them), channel
zero untouched by the second unwrap (drift **0.0**, the clobber probe
measures **2.068**), every island inside [0,1], **0** overlapping islands
by an independent SAT scan, and a measured min island distance of
**0.00401** against the stated margin. Companion to
[`uv-layer-grid`](examples/uv-layer-grid/) (UV authoring) and
[`triangulate-tangents`](examples/triangulate-tangents/) (tangents from UVs).

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/socket-attach-points/"><img src="examples/socket-attach-points/preview.webp" alt="Socket attach points: a cobalt-and-graphite survey quadcopter with carbon-weave arms hovering over a studio stage, orange mount pads ringing each canted rotor, a gimbal camera pod under the belly and a sensor mast on the deck — every module seated exactly on its named socket" /></a>
</td>
<td valign="middle">

### [socket-attach-points](examples/socket-attach-points/)

Named `SKT_` empties as the spawn contract, on a reusable survey drone. All
**7** socket world matrices land within **1.788e-07** of the authored
transform with orthonormal right-handed bases, each socket's **+Z** equals its
mount pad's **Newell normal** (**1.794e-07**) by a derivation independent of
the basis construction, and modules seat at offset **exactly 0.0** with
identity local transforms. Freezing the root preserves world matrices but
clears **7/7** parent-inverses and pushes the root scale into the children —
both halves asserted. The no-parent-inverse probe jumps **0.690128 m**.
Companion to [`prop-origin-transform`](examples/prop-origin-transform/)
(pivot discipline) and
[`parent-inverse-orrery`](examples/parent-inverse-orrery/) (parent-inverse
under animation).

</td>
</tr>
<tr>
<td width="46%" valign="middle">
<a href="examples/vertex-color-ao/"><img src="examples/vertex-color-ao/preview.webp" alt="Vertex colour AO: a stone village well of chamfered, irregular blocks on a dark studio stage, its V-groove masonry joints, shaft mouth and coping undersides darkened by ambient occlusion baked into a colour attribute rather than by the lights" /></a>
</td>
<td valign="middle">

### [vertex-color-ao](examples/vertex-color-ao/)

Baked occlusion in a colour attribute, checked against a **formula** instead
of a captured value: the cosine-weighted hemisphere integral for a wall of
height `H` at distance `d` is `1 - ½(1 - 1/√(1+k²))`, `k = H/d`, and the
integrator matches it to **6.760e-04** across two decades of `k`. An
unoccluded plate bakes to exactly **1.0**. `FLOAT_COLOR` round-trips exactly
while **`BYTE_COLOR` is sRGB-encoded 8-bit** — 0.735 reads back
**0.7379107**, matching an independent encode/quantise/decode model to
**3.189e-07**. Both survive depsgraph evaluation at deviation **0.0**.
Companion to [`color-attribute-wheel`](examples/color-attribute-wheel/) and
[`attribute-domain-shear`](examples/attribute-domain-shear/).

</td>
</tr>
<tr>
<td width="46%" valign="middle">
check-only, no gallery still — a hexagon on a cube is not thumbnail-legible
</td>
<td valign="middle">

### [ngon-triangulate](examples/ngon-triangulate/)

Synthesizes one 6-loop hexagon by dissolving a cube edge. Pre-asserts the
n-gon exists (1 face / 6 loops / 5 faces), then `calc_tangents` aborts until
`bmesh.ops.triangulate` yields 4 tris + 4 quads / 28 loops. glTF tri count
is 12 either way. Inverse of [`mesh-hygiene-audit`](examples/mesh-hygiene-audit/).

</td>
</tr>
<tr>
<td width="46%" valign="middle">
check-only, no gallery still — unapplied scale looks like modeled non-uniform size
</td>
<td valign="middle">

### [unapplied-scale-gltf](examples/unapplied-scale-gltf/)

Unit cube with object scale `(2, 1, 0.5)`. Pre-asserts unapplied non-uniform
scale and local ±1 verts, then glTF `export_apply=True` still writes Y-up
node.scale `(2, 0.5, 1)` with local POSITION. `export_apply` is modifiers
only. Inverse of [`gltf-export-roundtrip`](examples/gltf-export-roundtrip/).

</td>
</tr>
<tr>
<td width="46%" valign="middle">
check-only, no gallery still — coincident cubes look like one cube
</td>
<td valign="middle">

### [coincident-vert-weld](examples/coincident-vert-weld/)

Two cubes in one mesh: 16 verts / 8 unique / still manifold. Pre-asserts
the duplicates, then glTF ships 24 tris / 48 positions / 8 unique.
`remove_doubles` collapses to one cube. Inverse of
[`degenerate-bevel-weld`](examples/degenerate-bevel-weld/).

</td>
</tr>
</table>

</details>

## How content is organized

```
skills/<name>/SKILL.md   - 16 skill files, YAML frontmatter, one canonical pattern each
rules/<name>.mdc         - 9 rule files, anti-pattern + correction
templates/<name>/        - 3 template directories (extension-addon-template, headless-batch-script-template, ai-asset-pipeline-template)
snippets/<name>.py       - 27 standalone Python snippets, 5 to 50 lines each
```

## Using rules in Cursor

The `.mdc` files in `rules/` apply automatically when Cursor opens a Blender Python project, scoped by the `globs` in each rule's frontmatter. The nine rules are:

- `prefer-data-over-ops-in-loops`: flags `bpy.ops.*` calls inside object iteration
- `always-free-bmesh`: flags `bmesh.new()` without paired `bm.free()` in `try`/`finally`
- `target-extensions-platform-format`: flags add-ons missing `blender_manifest.toml`
- `type-annotate-props-and-defend-context`: flags `bpy.props` assignment form and unguarded `context.active_object`
- `prefer-temp-override-over-context-copy`: flags `bpy.context.copy()` passed to operators (deprecated 4.x, removed 5.x)
- `use-foreach-set-for-bulk-data`: flags Python loops over `mesh.vertices` setting `co`, normals, or other per-element bulk data
- `validate-imported-mesh-scale`: flags glTF/FBX import then mesh work with no `transform_apply` and no unit-scale check
- `no-unapplied-modifiers-on-export`: flags export of objects with live modifiers when the export does not request evaluated geometry
- `use-correct-axis-rna-per-exporter`: flags `export_scene.gltf` calls that pass FBX `axis_forward` / `axis_up`, and `export_scene.fbx` calls that pass glTF `export_yup`

Symlink or clone this repo, then point Cursor at it as a skills/rules source.

## Using the templates

`templates/extension-addon-template/` is a working Blender extension. Copy the directory, edit `blender_manifest.toml` (id, version, name, maintainer), and install via Edit > Preferences > Get Extensions > Install From Disk. The template registers an Operator, a Panel, and a PropertyGroup, and demonstrates the `register_classes_factory` pattern with symmetric `register()` and `unregister()`.

`templates/headless-batch-script-template/` is a working starter for unattended Blender batch jobs. It opens a `.blend`, optionally adds and applies a modifier to every mesh, and exports to glTF, with explicit exit codes for CI integration. Run with `blender --background <input.blend> --python script.py -- --output ...`.

`templates/ai-asset-pipeline-template/` is a working starter for a headless GLB-in / engine-ready-out job. It imports a GLB, runs the `ai-mesh-cleanup` order, emits an LOD chain and optional collider, and exports under a Unity, Godot, or Unreal glTF preset. Run with `blender --background --python pipeline.py -- --input ... --outdir ... --preset unity`.

## Snippets

Each snippet is a standalone Python file under `snippets/`. They are not loaded as a package. Open one, copy the relevant lines into your script, and adapt the names. Each file's header comment cites the Blender doc URL or research section the pattern came from.

## Canonical references

| Resource | Use it for |
| --- | --- |
| [Blender 5.2 LTS Python API](https://docs.blender.org/api/current/) | Authoritative reference for current stable APIs |
| [Blender 5.1 Python API](https://docs.blender.org/api/5.1/) | Prior stable |
| [Blender 4.5 LTS Python API](https://docs.blender.org/api/4.5/) | LTS reference when targeting 4.5 |
| [Extensions Platform manual](https://docs.blender.org/manual/en/latest/advanced/extensions/index.html) | `blender_manifest.toml` schema, hosting, install flow |
| [developer.blender.org](https://developer.blender.org/) | Release notes, breaking change tracking, design docs |

When community content (Stack Overflow, older add-on source) conflicts with the official docs, prefer the docs. The 2.x to 4.x to 5.x churn around Actions, Extensions, and property handling has invalidated a lot of older material.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the candidate pool and what ships next. Releases are cut automatically from
conventional commits; the full history lives in [CHANGELOG.md](CHANGELOG.md).

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the
workflow, [SECURITY.md](SECURITY.md) for reporting vulnerabilities, and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community standards. New examples must
follow the anatomy of [`examples/bmesh-gear/`](examples/bmesh-gear/) and the render
look in [`docs/VISUAL-STYLE.md`](docs/VISUAL-STYLE.md).

## License

Copyright (c) 2026 TM Hospitality Strategies. Licensed under [CC-BY-NC-ND-4.0](LICENSE).
