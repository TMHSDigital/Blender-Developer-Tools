# Vertex Weight Limit

A runnable example that rigs a mech arm — bolted pedestal and shoulder
fairing, a shoulder hub and clevis-ended upper arm, the elbow hinge pin inside
a ribbed flex bellows, a long plated forearm, wrist bellows and collar, and a
three-finger gripper — with deliberately rich five-bone weight bumps in the
bellows, then enforces the game-engine
**maximum of four bone influences per vertex** through the data API, following
[`mesh-editing-and-bmesh`](../../skills/mesh-editing-and-bmesh/SKILL.md) and
building on the linear-blend-skinning precedent of
[`armature-bend`](../armature-bend/).

**Pipeline arc:** modeling/LOD in [`lod-decimate-chain`](../lod-decimate-chain/),
weighting here, export in [`gltf-export-roundtrip`](../gltf-export-roundtrip/).

**What it witnesses:** the skinning constraint every game engine enforces and
AI-generated rigging code most often violates silently.

1. **The limit is a data-API operation, not a context operator.** Instead of
   `bpy.ops.object.vertex_group_limit_total`, the example reads each vertex's
   groups, keeps the top four by weight, `VertexGroup.remove`s the rest, and
   renormalizes the survivors. Dropping without renormalizing leaves sums at
   0.986 — a mesh that shrinks toward the origin under load (the check's
   measured failure, 1.438e-02 off unit sum).
2. **The armature modifier is still exactly linear blend skinning** after the
   limit: every depsgraph-evaluated vertex equals
   `Σ wᵢ · (pose.matrix @ bone.matrix_local.inverted()) @ rest`, with the
   weights **read back from the mesh's own deform layer** (`v.groups`) — the
   weights on the mesh are the contract, not the weights you meant to write.
   Measured `lbs_err = 3.0e-07`.
3. **Pruning must not damage the pose.** Evaluated positions before and after
   the limit are held within 0.05 (measured 3.0e-03), the pedestal mount stays
   exactly pinned (Root is unposed), and the pre-limit authoring really carries
   five influences in the boots — otherwise the witness would be vacuous.

The vertex-group API (`v.groups`, `VertexGroup.add`/`remove`) is stable between
Blender 4.5 LTS and 5.1 — the example runs identically on both, which is itself
the version witness (measured values match to the digit).

The render shows the pruned arm mid-pose: the flex bellows carry the teal
accent — the five-influence zones the limit prunes glow at the elbow hinge
and wrist, sealed by the bright ring on the elbow bellows — proof that the
limited weights still deform as authored.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python vertex_weight_limit.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python vertex_weight_limit.py -- --output arm.png
blender --background --python vertex_weight_limit.py -- --output arm.png --engine cycles
```

It exits non-zero on failure (vacuous authoring, a vertex over the cap, broken
weight sums, pose damaged by pruning, LBS drift, or a moved Root mount). The
`blender-smoke` workflow runs the check on Blender 4.5 LTS and 5.1.
