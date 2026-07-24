<!-- standards-version: 1.10.0 -->

# Roadmap

**Current:** v0.41.0

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
| 5.2 LTS sweep, modal operators, USD | — | — | — | — | Upcoming |
| Stable | — | — | — | — | Upcoming |

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

## Candidate pool (next content)

Not committed; target list for the next content version. (v0.3.0 shipped the smoke-gated `examples/` track.)

- ~~Fleet Pages facelift + examples support~~ **RESOLVED differently (2026-07-03)**: the meta-repo migration was dropped — the fleet template only scaffolds new tools, and each tool's site evolves independently after that. This repo vendored the site build into `scripts/site/`, redesigned landing + gallery as the Blender-viewport system (see `docs/gallery/DESIGN_NOTES.md`), added the examples grid, nav link, and full hero stats locally. `scripts/build_gallery.py` and `examples/gallery.json` are now permanent, not a prototype awaiting lift-and-shift.
- `modal-operators` skill -- `invoke` returning `RUNNING_MODAL`, the `modal()` event handler, modal cancellation patterns
- `usd-pipelines` skill -- USD export options, `evaluation_mode`, instancing, the USD vs glTF tradeoffs
- `mathutils-patterns` skill -- `mathutils.Vector`, `Matrix`, `Quaternion`, common transforms, the `@` operator
- Blender 5.2 LTS sweep (after the 5.2 LTS release in mid-2026)
- Refresh the `slotted-actions-animation` skill against any 5.2 changes
- Bump `blender_version_min` in the templates if 5.2 APIs are used
- Additional snippets for asset library scripting, EXR baking, multi-file extensions
- Gallery coverage follow-ups from the GPv3 review: light-linking (`grease-pencil-rosette`, `armature-bend`, `text-version-stamp`, `image-pixels-testcard`, and `vse-cut-list` shipped first)
- ~~UV-layer authoring witness~~ **SHIPPED** as `examples/uv-layer-grid/` — `create_grid(..., calc_uvs=True)` silent no-op without a pre-existing UV layer; closed-form UV fill + explicit assignment fallback; dual-panel render (flat texel (0,0) vs neon checker)
- ~~Image save-format witness~~ **SHIPPED** as `examples/png-exr-alpha/` — float→PNG is RGBA16 and false-unpremultiplies as if associated-alpha (closed-form err 0.98 at RGB 0.02 / a=1/255); OpenEXR preserves float RGBA; byte→PNG is straight RGBA8; `EXR color_mode='RGB'` drops alpha
- ~~Attribute domain witness~~ **SHIPPED** as `examples/attribute-domain-shear/` — POINT vs CORNER semantics on an 8-wedge pinwheel with one shared hub: CORNER authoring exact (hub corners disagree by face, err ≤ 1e-6), naive per-wedge POINT loop shears to the last write at hub + ring verts, measured deviation == palette closed form (0.751031); byte-identical on 4.5.11 and 5.1.2; crisp-vs-smeared dual pinwheel still — companion to `color-attribute-wheel`
- ~~Light-linking collection witness~~ **SHIPPED** as `examples/light-link-studio/` — the API is `obj.light_linking` on the light OBJECT (`ld.light_linking` is an AttributeError on both versions); linked ratio 4.0x at projected-center luminance samples, unlink raises the decoy 244–251% with 0.0% hero drift in the same two-render check; EEVEE Next honors linking too (5.5x on 4.5.11, 5.9x on 5.1.2), Cycles pinned for deterministic samples
- ~~VSE sequences-to-strips witness~~ **SHIPPED** as `examples/vse-cut-list/` — `.sequences` removed on 5.x (4.5 bridges to `.strips`), `new_effect` end kwarg `frame_end=` (4.5) vs `length=` (5.x), `frame_final_*` deprecated in favor of `left_handle`/`right_handle`/`duration`, TRANSFORM effect type removed, GAMMA_CROSS clamps to the source overlap, effect strips consume inputs only when stacked above them, same-scene scene strips render transparent; save/reload round-trip + tiny-render pixel witness
- ~~glTF export round-trip witness~~ **SHIPPED** as `examples/gltf-export-roundtrip/` — `export_yup` bakes `(x,y,z)→(x,z,−y)` into vertex data with no node rotation (probed identical on 4.5.11 and 5.1.2), `export_apply` ships the evaluated mesh (one disk vertex per evaluated loop), TEXCOORD_0 is V-flipped on disk, per-triangle material bindings survive; exporter/importer RNA signatures byte-identical between 4.5.11 and 5.1.2 (guarded against future renames); `Mesh.calc_normals()` removal on 5.x surfaced during authoring
- ~~LOD decimate chain witness~~ **SHIPPED** as `examples/lod-decimate-chain/` — Decimate COLLAPSE evaluated through the depsgraph is non-destructive (obj.data keeps closed-form counts), evaluated tris hit `ratio × base` within 5% (measured 0.0–0.44%), silhouette bbox survives within 1e-3 (measured 7.7e-6); a stacked Decimate halves the effective ratio, an aggressive 0.02 ratio collapses the nose tip — both caught failure modes
- ~~Vertex weight limit witness~~ **SHIPPED** as `examples/vertex-weight-limit/` — the 4-influence engine cap enforced via the data API (`v.groups` + `VertexGroup.remove` + renormalize); unit sums (measured 3e-8), pose preserved (4.9e-3), exact LBS from the mesh's own deform layer (2.7e-7), Root mount pinned
- ~~Triangulate + tangent-space witness~~ **SHIPPED** as `examples/triangulate-tangents/` — `calc_tangents` aborts on any ngon (back cap must be an explicit fan); mikktspace matches the edge/UV-delta formula within welding tolerance on smooth fields (2.3e-6 measured); planar UVs on a cylindrical wall collapse tangents onto normals (dot 0.998); `MeshUVLoopLayer` handle dangles across `calc_tangents()` on 4.5 (471 phantom flips, silent exit 0) while the mikktspace math is byte-identical on 4.5.11 and 5.1.2
- UV-handle lifetime snippet: re-fetch attribute/UV layers by name after any CustomData-reallocating call (`calc_tangents`, `VertexGroup.add`, modifier edits) — held handles dangle silently on 4.5, survive by luck on 5.1 (found authoring `triangulate-tangents`)
- glTF skinned-mesh export witness: follow-up to `gltf-export-roundtrip` + `vertex-weight-limit` — **SHIPPED** as `examples/gltf-skin-roundtrip/` — `skins[0].joints` names every bone, JOINTS_0/WEIGHTS_0 with unit sums (3e-8), weights bit-exact, rest matrices to 2.4e-07, deformation to 4.8e-07; exporter welds duplicate loops (sorted-multiset comparisons mispair — compare by rest-key); unparented skinned meshes make the exporter bind an armature by name
- ~~Degenerate-bevel weld hazard~~ **SHIPPED** as `examples/degenerate-bevel-weld/` — at `offset == min_dim/2` the bevel band collapses to exactly 12 zero-area faces (4 min-axis edges × 3 segments) with 16 coincident verts (4 × (segments+1)) and min_area down 3.2e5×; a stdlib GLB re-parse counts **32 degenerate triangles crossing the export boundary** (MEASURED regression constant) versus 0 for the safe mesh — the loops an engine merge-by-distance welds; byte-identical on 4.5.11 and 5.1.2
- ~~GAMMA_CROSS blend-curve witness~~ **SHIPPED** as `examples/vse-gamma-cross/` — the cross blends in a gamma-0.5 space: `((1-t)·√A + t·√B)²` with `t = (frame − start)/duration`, never 1 inside the effect; mid-cross dips 0.115 below the sRGB lerp from crimson/teal (closed form (0.341, 0.349, 0.463) confirmed per frame); AgX-default sampling poisons the fit (0.146 red-channel error, `view_transform='Standard'` mandatory); deleting a consumed input orphans-and-deletes the effect — follow-up to `vse-cut-list`
- Falsy `bpy_prop_collection` trap snippet: an empty collection is falsy, so `editor.strips or editor.sequences` silently falls through to the legacy accessor on an empty timeline — always branch on `hasattr`; likely generalizes across the API (found authoring `vse-cut-list`)
- ~~Collision compound witness~~ **SHIPPED** as `examples/collision-hull-proxy/` — game-prop collision as a compound of convex pieces, each a `bmesh.ops.convex_hull` of a coarse `sec(π/n)`-inflated cage (containment 4.4e-08, watertight, positive signed volume, Euler 2, per-piece 255-face budget: body 70, caps 60×3, compound 250); a hull of the dense render mesh measures 380 faces — over budget — which is why pipelines hull cages; proud details cost cage rows, concave grooves are free; byte-identical on 4.5.11 and 5.1.2
- ~~Custom-normals / shade-by-angle witness~~ **SHIPPED** as `examples/custom-normals-shade/` — the post-4.1 shading contract: `use_auto_smooth`/`use_custom_normals`/`calc_normals` are AttributeError on BOTH 4.5.11 and 5.1.2; `set_sharp_from_angle` sharp sets match an independent dihedral recompute exactly (188/388 edges, 3 meshes); evaluated normal welds/splits exact (0.0 dev); custom split normals survive depsgraph evaluation within int16 quantization (1.407e-04, not float-exact); **divergence**: the legacy `shade_auto_smooth` operator CANCELS headless on 4.5 ("Asset loading is unfinished", mesh untouched, no exception) while 5.1 FINISHES with the Smooth-by-Angle NODES modifier — the data API is the portable path
- ~~Sky Texture / sun_elevation witness~~ **SHIPPED** as `examples/sky-texture-sun-elevation/` — World `ShaderNodeTexSky` → Background; `sky_type` is `NISHITA` on 4.5 and `MULTIPLE_SCATTERING` on 5.1 (`NISHITA` gone); `dust_density` is 4.5-only (`aerosol_density` on 5.1); zenith EXR rise 8°→55° measured **2.25x** (5.1.2) / **1.50x** (4.5.11), gate ≥ 1.25; dual-elevation gallery diptych
- ~~Grease Pencil Line Art contour witness~~ **SHIPPED** as `examples/gp-lineart-contour/` — GPv3 + `modifiers.new(..., "LINEART")`; `source_object` clear → 0 strokes; contour+crease off → 0; restore recovers **10** strokes / **34** points on 4.5.11 and 5.1.2; `thickness` is 4.5-only (`AttributeError` on 5.1; portable `radius`)
- Camera DOF + focus_distance witness: `cam.dof.use_dof`, focus plane vs defocus variance on high-freq cards (Stage deviation — depth needs background content)
- Volumetric scatter optical-depth witness: Volume Scatter density → Beer–Lambert transmittance along a known path (Cycles; Stage deviation)
- Freestyle SVG / line-set witness: Freestyle line set on a silhouette (full render pass; prefer Line Art first)
- ~~prop-origin-transform witness~~ **SHIPPED** as `examples/prop-origin-transform/` — origin to base center + data-API scale apply + `matrix_parent_inverse` for a bolted accessory; scale `(1,1,1)`, local `min.z==0`, world AABB delta 0, bare jump ~0.43 m, MPI err ~3e-8; stale `matrix_world` until `view_layer.update()`; byte-identical on 4.5.11 and 5.1.2
- ~~Goldberg polyhedron topology witness~~ **SHIPPED** as `examples/soccer-ball-goldberg/` — soccer ball as a truncated icosahedron: bmesh icosphere cut at 1/3 per edge, faces ordered by link-topology walks; closed forms 60/90/32 + Euler 2, census 12×5+20×6, uniform degree 3, edge dev 6.5e-06, planarity 1.9e-06 (independent Newell normal), circumsphere dev 9.0e-06, panels bound by face vertex count (enumeration-order probes exit 13); float32 noise floor ~9e-6 → 3e-5 gates; byte-identical on 4.5.11 and 5.1.2
- ~~Mirror-modifier symmetry witness: half-model completed by Mirror evaluated through the depsgraph~~ **SHIPPED** as `examples/car-mirror-symmetry/` — generic hatchback loft (14 stations × 9-point half-rings); datablock keeps the half (126/231/106, 28 centerline), evaluated is exactly 2n−c (224/434/212), watertight Euler 2, ±X partner dev 0.0; wheels/lamps mirror about origins parked on the plane; probes: merge off → 252 (exit 5), centerline off-plane → 27≠28 (exit 4), axis off → 126 half-car (exit 5), applied → exit 3; byte-identical on 4.5.11 and 5.1.2
- Chess-piece lathe witness: a turned piece (rook/pawn) via Screw modifier or bmesh spin from an authored profile — evaluated verts == profile × steps (minus pole merges), ring radii match the profile closed form, axis of revolution exact
- Dice-pair per-face witness: material/attribute assignment driven by face normal direction, opposite-faces-sum-to-7 as an independently computed invariant, pip placement from a closed-form lattice
- Bicycle-wheel radial witness: spokes via radial Array with object offset — exact angular spacing, spoke count, hub/rim concentricity, every evaluated spoke endpoint on its computed rim coordinate
- ~~mesh-hygiene-audit witness~~ **SHIPPED** as `examples/mesh-hygiene-audit/` — engine-ingest topology checklist on a stepped street electrical pedestal: no ngons, no loose verts, manifold edges (exactly 2 faces), no zero-area faces (`min_area` printed), positive signed volume, Euler `V−E+F==2` (24/44/22, volume 0.989248); byte-identical on 4.5.11 and 5.1.2; dual-panel dirty vs clean still
- UV atlas pack witness — lightmap/unique UV island packing with non-overlap + utilization closed forms (deferred behind hygiene/origin; overlaps `uv-layer-grid` / `triangulate-tangents` / `gltf-export-roundtrip` UV arc)

- ~~Gallery framing recomposition worklist~~ **DRAINED**: all four recomposition cases restaged and gated with `check_framing` — depsgraph-export (0.984x/touch→0.812x; cube+dome recentered, aim-based camera), vertex-weight-limit (touch B→0.867y; more frontal camera, lower aim, base in frame), triangulate-tangents (0.334x→0.833y; 2x-class move-in plus Key/Glint trim that also cleared a pre-existing dome blowout), text-version-stamp (0.663x→0.719x; moved in with aim on the stamp center, dead third gone). The seven marginal cases were camera-nudged in the preceding sweep; deviations documented in #108 (damped-track-aim, wave-displace); sky-texture-sun-elevation is a measurement artifact (world subject — report-only if wired). Remaining: nothing on the framing worklist — future examples inherit the gate at authoring time.

## Future (uncommitted)

- Asset library and asset browser scripting skill
- Cycles vs EEVEE Next render API skill
- Geometry Nodes 5.x feature parity (volumes, fields)
- Animation rigging from Python (constraints, drivers across bones)
