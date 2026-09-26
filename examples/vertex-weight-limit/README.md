# Vertex Weight Limit

A runnable example that rigs a six-axis-style industrial robot arm — bolted
floor plinth and turret drum with a finned rear drive pack, clevis cheeks
and servo drums at the shoulder and elbow, a tapered box-section upper arm
and forearm, a gas-spring balancer across the shoulder, a wrist fork and a
two-jaw gripper — as **one skinned mesh**, then enforces the game-engine
**maximum of four bone influences per vertex** through the data API,
following [`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md)
and building on the linear-blend-skinning precedent of
[`armature-bend`](../armature-bend/).

Every rigid part (armor, motors, cheeks, piston, gripper) is weighted 1.0 to
one bone. The two cable runs along the arm's back are the flex parts: they
hand over smoothly from bone to bone across each joint and carry the tail an
auto-weighting pass leaves behind — a small, distance-ranked spill onto all
five bones. That tail is the five-influence authoring the limit prunes.

**Pipeline arc:** modeling/LOD in [`lod-decimate-chain`](../lod-decimate-chain/),
weighting here, export in [`gltf-export-roundtrip`](../gltf-export-roundtrip/).

**What it witnesses:** the skinning constraint every game engine enforces and
AI-generated rigging code most often violates silently.

- **The limit is a data-API operation, not a context operator.** Instead of
  `bpy.ops.object.vertex_group_limit_total`, the example reads each vertex's
  groups, keeps the top four by weight, `VertexGroup.remove`s the rest, and
  renormalizes the survivors. Dropping without renormalizing leaves sums
  short of one — a mesh that shrinks toward the origin under load (the
  check's measured failure, 2.647e-03 off unit sum).
- **The armature modifier is still exactly linear blend skinning** after the
  limit: every depsgraph-evaluated vertex equals
  `Σ wᵢ · (pose.matrix @ bone.matrix_local.inverted()) @ rest`, with the
  weights **read back from the mesh's own deform layer** (`v.groups`) — the
  weights on the mesh are the contract, not the weights you meant to write.
  Measured `lbs_err = 1.2e-06`.
- **Pruning must not damage the pose.** Evaluated positions before and after
  the limit are held within 0.05 (measured 4.2e-03 over 3108 limited
  vertices), the plinth stays exactly pinned (Root is unposed), and the
  pre-limit authoring really carries five influences on the cables —
  otherwise the witness would be vacuous.

The vertex-group API (`v.groups`, `VertexGroup.add`/`remove`) is stable between
Blender 4.5 LTS and 5.2 — the example runs identically on 4.5, 5.1 and 5.2,
which is itself the version witness (measured values match to the digit).

## What the render shows

The render path paints the **post-limit weights** onto the arm as a
`BoneBlend` colour attribute — `Σ wᵢ · colourᵢ` per vertex, read back from
`v.groups` after the prune — and the cables, side hatches and trim bands
display it through a matte Attribute-node material. Each rigid segment
therefore shows its bone's flat colour (blue turret, teal upper arm, violet
forearm, magenta wrist, lime gripper), and the cables grade from colour to
colour exactly where the skin weights blend across each joint, while the
posed arm shows those weights deforming it.

**Numeric-only contract** (docs/VISUAL-STYLE.md § The render is the proof):
the four-influence cap itself has no visual signature. The pruned fifth
weight is the small spill (at most 0.0027 on any vertex), so a five-influence
arm deforms and paints indistinguishably — the prune preserves the pose by
design, and that is what check 3 asserts. The render depicts the subject and
where its weights blend; the cap is witnessed by the numbers above and by the
`--skip-limit` falsifier.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python vertex_weight_limit.py --

# Falsifier: skip the 4-influence prune. Must exit non-zero.
blender --background --python vertex_weight_limit.py -- --skip-limit

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python vertex_weight_limit.py -- --output arm.png
blender --background --python vertex_weight_limit.py -- --output arm.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper; it is also the missing-render
code. `11` is the shared asset-quality helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Pre-limit max influences ≠ 5 |
| 4 | Vertex over the 4-influence cap (`--skip-limit` lands here) |
| 5 | Limit changed nothing |
| 6 | Weight sums off 1.0 after renormalize |
| 7 | Pose damaged by pruning, or evaluated vert count changed |
| 8 | Evaluated mesh off LBS over limited weights |
| 9 | Root-weighted mount moved |
| 10 | Gallery framing violation; also `--output` produced no file |
| 11 | Asset-quality floor violation (`--output` only) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--skip-limit`.

