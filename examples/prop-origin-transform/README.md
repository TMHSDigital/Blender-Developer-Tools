# Prop Origin Transform

A runnable example that builds a street utility pedestal with a bolted
conduit accessory and proves the **origin / scale-apply / MPI** contract a
prop pipeline relies on before engine ingest — following
[`operators`](../../skills/operators/SKILL.md) and the data-API parenting
idiom from [`parent-inverse-orrery`](../parent-inverse-orrery/).

**Pipeline arc neighbors:** MPI + stale `matrix_world` in
[`parent-inverse-orrery`](../parent-inverse-orrery/), export origin
sensitivity in [`gltf-export-roundtrip`](../gltf-export-roundtrip/), collision
bounds in [`collision-hull-proxy`](../collision-hull-proxy/), and mesh hygiene
in [`mesh-hygiene-audit`](../mesh-hygiene-audit/). Origin at the base center
with applied scale is what placement and physics ingest assume.

**Scope:** this witnesses the bpy-level contract a prop pipeline relies on
(post-bake scale exactly `(1,1,1)`, local bbox `min.z == 0`, world bbox
unchanged, MPI so a parented accessory does not teleport). It is not an
engine exporter — it proves the transform properties such an asset must have.

**What it witnesses:**

- **Stale `matrix_world`.** After a location edit, `matrix_world` is unchanged
  until `view_layer.update()` (same half of the orrery contract).
- **Scale apply via data API.** Non-uniform scale baked into verts;
  `obj.scale == (1,1,1)` exactly afterward.
- **Origin at base center.** Local bbox `min.z == 0`, XY centered; world AABB
  delta across the bake is **0** (gate `1e-5`).
- **Bare-parent trap.** Parenting the accessory without MPI jumps it
  (~0.43 m measured); setting `matrix_parent_inverse` restores world location
  (err ~3e-8).

**What each check catches on failure:** skipping scale apply leaves
non-identity scale; skipping origin bake leaves `min.z ≈ -0.756`; skipping
MPI leaves the accessory teleported.

**Version witness:** byte-identical numbers on Blender 4.5.11 LTS and 5.1.2.

The render is a dual panel: left **TRAP** (bare parent — flanged conduit
teleports off a deep shadowed mount socket) vs right **MPI KEEP** (same metal
fitting seated in the socket), with emissive origin markers at each pedestal's
base. Accessory and pedestal stay in one material family so displacement — not
color — carries the proof. Check closed forms are unchanged.

## Run

```bash
blender --background --python prop_origin_transform.py --
blender --background --python prop_origin_transform.py -- --output origin.png
blender --background --python prop_origin_transform.py -- --output origin.png --engine cycles
```

Exits non-zero on failure. The `blender-smoke` workflow runs the check on
Blender 4.5 LTS and 5.1. The `--output` render path additionally measures
framing against the Layer 1 band via `examples/gallery_framing.py` (exit 10
on violation) before writing the still.
