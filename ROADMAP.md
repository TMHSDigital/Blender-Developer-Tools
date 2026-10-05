<!-- standards-version: 1.10.0 -->

# Roadmap

**Current:** v0.143.12

Themes are listed in order. Shipped themes note the release they landed in (for reference,
not a commitment); upcoming themes are intentionally **not** pinned to a version number, so
shipping another example or skill never forces a roadmap renumber. The release pipeline
derives the actual version from conventional-commit types.

| Theme | Skills | Rules | Templates | Snippets | Status |
| --- | --- | --- | --- | --- | --- |
| Foundation | 8 | 4 | 1 | 10 | Shipped (v0.1.0) |
| Materials, drivers, migration | 12 | 6 | 2 | 17 | Shipped (v0.2.0) |
| Examples and demos (smoke-gated) | 12 | 6 | 2 | 17 | Shipped (v0.3.0) |
| More examples (turntable, SDF remesh) | 12 | 6 | 2 | 17 | Shipped (v0.4.0) |
| 5.2 LTS targeting, GN modifier inputs | 12 | 6 | 2 | 17 | Shipped |
| VSE COLOR strip intrinsic size (undocumented 5.2) | 13 | 6 | 2 | 17 | Shipped |
| Skills: modal operators, USD pipelines, mathutils | — | — | — | — | Upcoming (the USD `evaluation_mode` example shipped; the skill has not) |
| AI asset pipeline: post-generation cleanup | 14 | 8 | 2 | 21 | Shipped (v0.54.0) |
| AI asset pipeline: engine export presets | 15 | 9 | 2 | 24 | Shipped |
| AI asset pipeline: headless template | 15 | 9 | 3 | 24 | Shipped |
| AI asset pipeline: high-to-low bake | 16 | 9 | 3 | 27 | Shipped |
| AI asset pipeline: live-session bridge (spike) | - | - | - | - | Upcoming |
| Stable (1.0) | — | — | — | — | Upcoming; criteria below |

## What "Stable (1.0)" means

Proposed criteria, none of which depend on content volume:

- **Install paths that work and are tested:** Claude Code plugin and Cursor plugin
  each install from a documented command, verified on a clean profile.
- **Stable skill and rule names:** renaming or removing a skill or rule after 1.0
  is a breaking change (major version), so agents and docs that cite them keep working.
- **Supported Blender policy written down:** the current LTS plus the previous LTS
  are smoke-tested on every PR; a version leaves support with a release note.
- **Measured payoff:** the agent eval harness (#373) publishes a with/without
  pass rate for the current release.
- **Predictable releases:** plugin versions change only when plugin content
  changes (#350).

## v0.1.0 - Foundation

The 8 skills:

- `addon-scaffolding` -- Extensions Platform manifest, file layout, register/unregister symmetry
- `operators` -- `bpy.types.Operator` lifecycle, `bl_idname`, redo, defensive context handling
- `ui-panels` -- `bpy.types.Panel` declarative `draw()`, layout primitives, conditional UI
- `custom-properties` -- `bpy.props` annotations, PropertyGroup, PointerProperty, storage tradeoffs
- `mesh-editing-and-bmesh` -- when to use bpy.data vs bpy.ops vs bmesh, foreach_set, depsgraph eval
- `headless-batch-scripting` -- `blender --background --python`, temp_override, argparse after `--`
- `slotted-actions-animation` -- Blender 5.x Slotted Actions, channelbag, 4.5 LTS fallback bridge
- `geometry-nodes-python` -- programmatic GN tree construction, interface sockets, NODES modifier

The 4 rules:

- `prefer-data-over-ops-in-loops`
- `always-free-bmesh`
- `target-extensions-platform-format`
- `type-annotate-props-and-defend-context`

The 1 template:

- `extension-addon-template` -- Extensions Platform format, register_classes_factory, PointerProperty binding, symmetric register/unregister

The 10 snippets:

- `canonical-object-creation.py`
- `canonical-object-deletion.py`
- `depsgraph-evaluated-mesh.py`
- `bmesh-load-edit-free.py`
- `temp-override-context.py`
- `foreach-set-vertices.py`
- `register-classes-factory.py`
- `pointerproperty-binding.py`
- `cross-version-property-delete.py`
- `action-ensure-channelbag-for-slot.py`

## v0.2.0 - Materials, drivers, migration

The 4 new skills:

- `procedural-materials-and-shaders` -- node tree construction for Principled BSDF, emissive, node groups; cross-version socket-name handling for `Specular IOR Level`
- `depsgraph-and-evaluated-data` -- `evaluated_get` plus `to_mesh` plus `to_mesh_clear` lifetime contract, OBJ-style exporter worked example
- `drivers-and-app-handlers` -- driver expressions, `bpy.app.driver_namespace` escape hatch, application handler pattern with `@persistent`, the new 5.1 `exit_pre` handler
- `bl-info-migration` -- three-step migration from legacy `bl_info` to Extensions Platform, before-and-after diff, dual-format pattern

The 2 new rules:

- `prefer-temp-override-over-context-copy` -- `bpy.context.copy()` deprecation in 4.x, removal in 5.x, `temp_override` replacement
- `use-foreach-set-for-bulk-data` -- per-element Python loops over mesh data versus `foreach_set` and `foreach_get`

The 1 new template:

- `headless-batch-script-template` -- argparse after `--`, mesh iteration, modifier apply via temp_override, glTF export, explicit exit codes

The 7 new snippets:

- `principled-bsdf-material.py`
- `driver-with-custom-function.py`
- `app-handler-registration.py`
- `shader-node-group.py` (cross-version `interface` vs `inputs`/`outputs`)
- `foreach-get-vertices.py`
- `version-branch-skeleton.py`
- `usd-export-evaluation-mode.py`

Audit pass on v0.1.0 content: standards-version markers bumped from `1.9.1` to `1.9.4` across all skills, rules, AGENTS.md, CLAUDE.md, and ROADMAP.md. Verified the `bpy_extras.anim_utils.action_ensure_channelbag_for_slot` import path against the current Blender 5.1 API reference and removed the stale "verify before production" caveat in `slotted-actions-animation/SKILL.md`.

## AI asset pipeline track

Provider-agnostic GLB-in / engine-ready-out. This repo does not generate meshes.

- **Post-generation cleanup skills.** Import and unit-scale normalization, transform apply and origin, poly-budget decimate, LOD chain, collision mesh. Phase 1 shipped in v0.54.0 as `ai-mesh-cleanup`, four snippets, two rules.
- **High-to-low normal bake.** **Delivered.** Skill `bake-high-to-low`, snippets `setup_bake_target_image.py` / `bake_normal_high_to_low.py` / `save_baked_image.py`, witness `examples/bake-normal-high-to-low/`. Cycles CPU cage bake; statistical gates, not byte-identity. UV transfer and atlas packing remain a later phase. Template integration remains a later phase.
- **Engine export presets.** **Delivered.** Unity, Godot and Unreal glTF are one spec-compliant export (+Y up, meters; Unreal converts to cm on import, corrected in #346), and Unreal FBX carries `axis_forward`/`axis_up` plus `global_scale`. Skill `engine-export-presets`, three snippets, rule `use-correct-axis-rna-per-exporter`, witness `examples/export-preset-axis/`. Draco remains opt-in via `gltf_draco_export.py`.
- **`ai-asset-pipeline-template/`.** **Delivered.** Third template. Headless: GLB path in; LOD set, convex or box collider, engine-preset export; explicit CI exit codes. Pattern: `templates/headless-batch-script-template/`.
- **Live-session agent bridge.** Research spike, not a committed deliverable. MCP server or socket listener so an agent can execute against a running Blender instance instead of blind `--background` scripts. Built on `templates/extension-addon-template/`. Needs its own design pass. Unpinned.

## Candidate pool (next content)

Not committed; open subjects only. Remove a subject when it ships (CLAUDE.md § Example-Run Process); what shipped, and when, is in the CHANGELOG and git history.

- Library rolling ladder (hooked top rollers riding a round rail, raked stiles, treads, floor wheels) as a game-prop showcase piece — the unbuilt half of the item above: a hook riding a round rail is a curved-on-curved contact that neither the trolley's flat backrests nor the yoke's hung ring exercise
- Ox cart tongue or plough beam that hitches to the yoke's ring as a game-prop showcase piece — a hitch is a ring-on-hook contact the yoke's hung ring only tests against a fixed bar
- Mooring bollard with a coiled rope as a game-prop showcase piece — rope turns laid as stacked helices around the barrel: each turn resting on the one below (not interpenetrating, not floating), measured turn-to-turn off the mesh
- Tiered stone fountain as a game-prop showcase piece — concentric basins on a column: every basin coaxial, each upper basin's lip overhanging the one below by a stated band so the overflow line lands inside the next basin
- Cannon on a wooden field carriage as a game-prop showcase piece — trunnions seated in the carriage's cap-square cradles: trunnion axis coaxial with both cradles and wheels resting on the ground at the axle's computed height
- Spinning wheel as a game-prop showcase piece — a drive band running from the wheel groove to the whorl: band path tangent to both pulleys within a band (a belt-on-pulley contact), treadle linkage reaching the crank
- Hanging tavern sign as a game-prop showcase piece — sign board hung from a wall bracket by chain: each link threaded through its neighbour without interpenetration and the board hanging plumb under the bracket hooks
- Tiered skep beehive on a stand as a game-prop showcase piece — coiled straw courses as stacked tori: each course seated on the one below, the dome closing on its axis
- Rowboat with oars in oarlocks as a game-prop showcase piece — oar shafts passing through the oarlock horns with clearance inside a band, hull resting on its keel line on a flat deck/floor
- Weathervane as a game-prop showcase piece — arrow and cardinal arms on a spindle: the arrow's pivot bore coaxial with the spindle and the arrow statically balanced (centroid on the pivot axis within a band)
- Showcase pieces above this line are category `village`. Candidates for the other categories (`showcase/README.md` § Categories):
  - **Sports:** skateboard
  - **Nature:** (all candidates shipped)
  - **Household:** laundry basket
  - **Vehicles:** sci-fi supply crate
- `persistent` app-handler witness — handlers registered without `@bpy.app.handlers.persistent` are dropped by `wm.read_homefile`/file load while persistent ones survive; assert the registered-handler set before and after a reload (silent loss AI code hits)
- Link vs append witness — `bpy.data.libraries.load(link=True)` yields a linked, non-editable datablock (`library` set, `is_editable` False) while append yields a local copy; write a temp .blend with `bpy.data.libraries.write`, then assert both paths
- Orphan purge witness — `bpy.data.orphans_purge(do_recursive=...)` removes exactly the zero-user datablocks computed independently beforehand, and `bpy.data.batch_remove` removes a given set in one call (counts closed-form)
- `mathutils.bvhtree` witness — `BVHTree.FromObject` on evaluated geometry: `find_nearest` distances and `overlap` pairs match closed forms on a known arrangement
- Curves datablock witness — the modern `bpy.types.Curves` hair API (`add_curves`, `position` attribute, `curve_offset_data`) vs legacy particle hair: point and curve counts closed-form, every root on the emitter surface
- Non-Color normal-map witness — an image used as a normal map must be `colorspace_settings.name = 'Non-Color'`; a baked/sampled value round-trips only then, and sRGB shifts it by the transfer curve (a silent shading error AI code ships)
- MANIFOLD Boolean solver witness — the 4.5+ `'MANIFOLD'` solver against EXACT on the same closed-form operands: identical volumes with fewer faces (10 vs 14 on the fully coplanar union), plus its documented refusal of non-manifold input operands (result empty or unchanged) as the falsifier
- Lattice `use_outside` / outside-vertex witness — verts outside a KEY_LINEAR lattice's volume: assert the documented clamp or extrapolation closed form, and `use_outside` (deform only the outer points) against an interior-only control move
- FBX unit-scale witness — `export_scene.fbx` with `apply_unit_scale` / `apply_scale_options` changes exported coordinates by the closed-form ×100 cm factor; re-import restores metres only on the matching option
- Collection-instance witness — `instance_type = 'COLLECTION'` instances appear only in `depsgraph.object_instances` (never in `scene.objects`); instance world matrices match the closed-form offsets
- Asset-marking witness — `ID.asset_mark()`, `asset_data.tags` and catalog UUIDs written to `blender_assets.cats.txt`, re-read from a saved library file (check-only if no legible still)
- **Flagship showcase: working clock-tower movement** — a tower clock with a visible gear train (great wheel, intermediate pinions, escape wheel, anchor and pendulum, dial motion works driving hour and minute hands): every meshing pair on its computed centre distance (pitch radii sum) with teeth interleaved not interpenetrating, train ratio hour:minute exactly 1:12 recomputed from tooth counts off the mesh, pendulum bob hanging plumb; `--wrong-ratio` / `--gear-clash` falsifiers
- **Flagship showcase: counterweight trebuchet** — A-frame, throwing arm on an axle, hinged counterweight box, sling and pouch, release pin: axle bore coaxial in both uprights, arm pivot on the axle, counterweight hanging plumb from its hinge, sling length within a band of the arm's short-side ratio, all four skids on the ground
- **Flagship showcase: steam locomotive (narrow-gauge)** — boiler barrel, smokebox, cab, drivers linked by coupling and connecting rods, valve gear: every driver on the rail at the axle's computed height, coupling-rod length equal to axle spacing so the rods stay parallel (a four-bar invariant measured off the mesh), crankpins at equal quartering angle
- **Flagship showcase: windmill with sail stocks and brake wheel** — tower cap, four lattice sails on a windshaft, brake wheel meshing the wallower: sails at exact 90° about the shaft axis, shaft tilt as a stated constant, brake-wheel/wallower centre distance from pitch radii
- **Flagship showcase: fairground carousel** — canopy, centre pole, crank rods, 12 horses on twisted brass poles in two rings: exact radial and angular spacing per ring, every pole plumb and passing through a horse's saddle bore, platform concentric with the canopy
- **Flagship showcase: pirate sloop** — lofted hull from stations, deck planking, mast, boom, gaff, shrouds and ratlines to chainplates, cannon ports: hull mirror-symmetric to the keel plane, every shroud terminating on its chainplate and masthead within a band, ratlines horizontal and evenly spaced
- **Flagship showcase: full chess set on a board** — 32 lathe-turned pieces (king to pawn, two woods) on an inlaid board: every piece centred on its square's computed centre, base seated on the board, lathe profiles revolved exactly (radii match profile closed form), 64 squares alternating by (file + rank) parity
- **Flagship showcase: modular dungeon kit** — floor, wall, corner, arch, stair and pillar tiles on a 2 m grid composed into a room: every open-edge boundary vert on the grid, zero gap/overlap at every joint, stair riser × count equal to one storey height, per-tile budgets plus a composed-room budget
- **Flagship example: GN procedural building generator** — one node tree with floor count, bay count and roof type as modifier inputs driving storeys, windows (instanced), cornices and a pitched or flat roof: window instance count = floors × bays × faces closed-form, storey heights exact, three buildings from the same tree side by side
- **Flagship example: GN road along a curve** — a Bezier path swept into a road with kerbs, lane markings and lamp posts instanced at equal arc-length spacing aligned to the tangent: post count = floor(length / spacing) + 1, every post perpendicular to the curve tangent within a band
- **Flagship example: L-system tree via GN repeat zone** — branching generated by a Repeat Zone: branch/leaf counts closed-form in the iteration depth, each child branch attached to its parent's tip, total height the closed-form series sum
- **Flagship example: UDIM texture set** — `Image.tiles.new` for 1001–1004, a UV layout spanning four tiles, per-tile bake/paint writes: tile numbers map to UV offsets exactly, each tile's pixels land only in its tile, `<UDIM>` filepath round-trips through save and reload
- **Flagship example: channel-packed ORM bake** — Cycles-bake AO, roughness and metallic of a prop into R/G/B of one Non-Color image: each channel matches its independently baked single-channel reference within a stated tolerance, and sRGB tagging is the falsifier
- **Flagship example: Cryptomatte ID witness** — a multi-object scene rendered with Cryptomatte passes to multilayer EXR: decoded object IDs (MurmurHash3 of the names) cover exactly each object's coverage mask, re-read with the stdlib-only EXR reader
- **Flagship example: walk cycle with planted feet** — slotted-action walk cycle on a leg rig with IK and NLA strip blending: planted-foot world position constant during each contact phase (foot slide below a band), stride length × cycles equals root travel, 4.5 vs 5.x channelbag paths
- Simulation-zone cache interpolation witness — frames between two cached simulation frames read as a linear interpolation of the endpoints (measured: steps 1.27 at frame 4 between cached 1 and 12), not a simulated state; assert the interpolant closed form and that a bake removes it (found authoring `gn-sim-fountain`)
- Operator PASS_THROUGH trap snippet — an operator whose poll fails headless (`simulation_nodes_cache_calculate_to_frame`) logs "Invalid operator call" and returns `{'PASS_THROUGH'}` without raising; check the returned set, never assume a non-raising `bpy.ops` call ran (found authoring `gn-sim-fountain`)
- Simulation-zone substeps witness — a Repeat Zone inside the Simulation Zone splitting Delta Time into k substeps: explicit Euler error shrinks exactly by 1/k against the closed-form arc, the exact update is invariant in k

- Tighten inverted smoke canaries: assert the expected `[FAIL]` marker text (`skipped on ... should run` / `missing post-exit sidecar`) alongside wrapper exit 1, so a canary that dies for the wrong reason does not satisfy the gate
- Overlapping / mirrored UV islands as a *shipped* pathology (not lightmap `--falsify`): SAT hits matching a constructed overlap, then glTF TEXCOORD survival. Deferred — `lightmap-uv-channel` already owns the zero-overlap gate.
- Vendor CC0 asset fixtures (Kenney, Quaternius, ambientCG only — no aggregators) as `.glb` not `.blend`, with per-fixture provenance records mirroring the Free-Game-Dev-Assets frontmatter schema. Permitted only where the assertion is an invariant over the fixture rather than a measurement of it. Deferred pending a decision on repo weight and CI fetch policy.
- Falsification flags on shipped examples (Phases 6–8 `--skip-delete` / `--unpair-*` / `--bypass`, Phase 9 `--silent-handler` / `--wrong-text`, Phase 10 `--no-dissolve` / `--identity` / `--no-duplicate`) were proven local-Windows only — chat and `.scratch`, not CI history. Decide later whether a cron should exercise them or whether flags in the scripts are sufficient record.
- `modal-operators` skill -- `invoke` returning `RUNNING_MODAL`, the `modal()` event handler, modal cancellation patterns
- `usd-pipelines` skill -- USD export options, `evaluation_mode`, instancing, the USD vs glTF tradeoffs
- `mathutils-patterns` skill -- `mathutils.Vector`, `Matrix`, `Quaternion`, common transforms, the `@` operator
- Additional snippets for asset library scripting, EXR baking, multi-file extensions
- UV-handle lifetime snippet: re-fetch attribute/UV layers by name after any CustomData-reallocating call (`calc_tangents`, `VertexGroup.add`, modifier edits) — held handles dangle silently on 4.5, survive by luck on 5.1 (found authoring `triangulate-tangents`; **confirmed harder authoring `lightmap-uv-channel`: iterating a held `MeshUVLoopLayer.data` after edit-mode UV ops segfaults 4.5.11 headless, EXCEPTION_ACCESS_VIOLATION 5/5, survives on 5.1.2**)
- UV atlas **utilization** witness — coverage/wasted-texel closed forms for a packed lightmap atlas (the non-overlap, unit-square, margin, and active/active_render contracts shipped in `lightmap-uv-channel`; utilization is the remaining unbuilt slice of the old "UV atlas pack" candidate)
- Falsy `bpy_prop_collection` trap snippet: an empty collection is falsy, so `editor.strips or editor.sequences` silently falls through to the legacy accessor on an empty timeline — always branch on `hasattr`; likely generalizes across the API (found authoring `vse-cut-list`)
- Camera DOF + focus_distance witness: `cam.dof.use_dof`, focus plane vs defocus variance on high-freq cards (Stage deviation — depth needs background content)
- Volumetric scatter optical-depth witness: Volume Scatter density → Beer–Lambert transmittance along a known path (Cycles; Stage deviation)
- Freestyle SVG / line-set witness: Freestyle line set on a silhouette (full render pass; prefer Line Art first)
- Chess-piece lathe witness: a turned piece (rook/pawn) via Screw modifier or bmesh spin from an authored profile — evaluated verts == profile × steps (minus pole merges), ring radii match the profile closed form, axis of revolution exact
- Dice-pair per-face witness: material/attribute assignment driven by face normal direction, opposite-faces-sum-to-7 as an independently computed invariant, pip placement from a closed-form lattice
- Bicycle-wheel radial witness: spokes via radial Array with object offset — exact angular spacing, spoke count, hub/rim concentricity, every evaluated spoke endpoint on its computed rim coordinate


## Asset sheets committed before 2026-07-25 are not comparable

The neutral asset-sheet harness sized its camera from the subject's bounding
box **diagonal**, which cropped tall subjects and shrank wide ones, so panels
in one sheet were at different effective scales. It now solves the required
distance from the real field of view on both axes. Sheets committed before
this fix (`modular-kit-snap`, `lightmap-uv-channel`) show mis-scaled panels
and must not be cited as evidence for or against an asset; re-render them if
that comparison is ever needed.

## Asset-quality survey worklist (measured 2026-07-24, `gallery_asset_quality` floors)

Full-gallery floor survey after the gate landed (`feat/asset-quality-gate`).
26 of the 42 examples that existed on 2026-07-24 passed all floors (historical; the gallery has grown since). The 14 below-floor entries, with
measured numbers — every one is a **contract-vehicle or display subject**
(testcard TV, VSE monitors, text bars, swatch/display rigs, single honest
primitives), not a game asset meant for reuse, so none is a remodeling
mandate; the floors exist to catch future asset-type examples at authoring
time. Two non-mesh subjects (curve-bevel-arc, grease-pencil-rosette) are
not measurable by the floors (curve/GP data, no mesh hero). Re-survey after
any example remodel.

- naming (default datablock names): gltf-skin-roundtrip (3 parts), gn-sdf-remesh (`Torus`), turntable (`Suzanne`)
- materials (multi-part, single material): armature-bend (3 parts/1 mat — vertex-color weight bands are the honest display), degenerate-bevel-weld (2/1), driver-wave (16/1, also edge90 1.0)
- edge90 (raw right angles, 1.0): depsgraph-export (also naming + materials), image-pixels-testcard, png-exr-alpha, text-version-stamp, vse-cut-list; vse-gamma-cross at 0.92
- reference: gallery best-modeled measure collision-hull-proxy 0.044, custom-normals-shade 0.288, vertex-weight-limit 0.150, lod-decimate-chain 0.019; calibration details in `docs/VISUAL-STYLE.md` § Asset quality

## Future (uncommitted)

- Asset library and asset browser scripting skill
- Cycles vs EEVEE Next render API skill
- Geometry Nodes 5.x feature parity (volumes, fields)
- Animation rigging from Python (constraints, drivers across bones)
