# Armature Bend

A runnable example that rigs a tapered, segmented tube with a four-bone armature chain —
`edit_bones` construction, name-bound vertex groups with smoothstep blend zones, a posed
curl — and checks the depsgraph-evaluated result against closed-form linear blend
skinning, following [`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md)
and [`depsgraph-and-evaluated-data`](../../skills/depsgraph-and-evaluated-data/SKILL.md).

**What it witnesses:** the three contracts AI-generated rigging code most often gets wrong.

1. `edit_bones` only exists in edit mode — the collection is asserted empty in object
   mode and holding the full chain (heads/tails at closed-form positions) inside
   `mode_set(mode='EDIT')`. Outside edit mode, reads silently return nothing.
2. Vertex groups bind to bones **by name**; a typo deforms nothing without erroring.
   Every group here is named after its bone and the deform proves the binding.
3. The armature modifier is exactly linear blend skinning: for *every* vertex,
   `evaluated == Σ wᵢ · (pose_bone.matrix @ bone.matrix_local.inverted()) @ rest`.
   The check re-implements LBS from the pose matrices and compares the whole
   evaluated mesh (max error ~5e-7). The root ring must stay pinned and the tip must
   deflect — a straight tube is a failure.

The armature API is identical on Blender 4.5 LTS and 5.1 — no version gate needed.
One portability hazard is baked in as a comment: interleaving `color_attributes` writes
with `VertexGroup.add()` dangles the attribute reference when the deform layer is
allocated (hard crash on 4.5, silent luck on 5.1), so the script finishes all weight
writes before creating the color attribute.

The render shows rest → half curl → full curl left to right, with per-bone weight
bands visualized through a `BoneTint` color attribute — the smooth color blends at the
joints are the same weights the LBS check asserts.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python armature_bend.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python armature_bend.py -- --output bend.png
blender --background --python armature_bend.py -- --output bend.png --engine cycles
```

It exits non-zero on failure (edit-bone lifetime violation, LBS deviation, moved root
ring, or an undeformed tip). The `blender-smoke` workflow runs the check on Blender
4.5 LTS and 5.1.
