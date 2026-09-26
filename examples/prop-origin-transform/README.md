# Prop Origin Transform

A runnable example that builds a street utility pedestal with a flanged
conduit elbow and proves the **origin / scale-apply / MPI** contract a
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
  (0.298 m measured); setting `matrix_parent_inverse` restores world
  location (err 0).

**What each check catches on failure:** skipping scale apply leaves
`(1.15, 0.92, 1.08)` (exit 5); skipping the origin bake leaves
`min.z = -0.58` (exit 6); skipping MPI leaves the accessory 0.298 m off
(exit 8).

**Version witness:** identical numbers on Blender 5.2.1 LTS, 5.1.2 and
4.5.11 LTS.

**The asset.** The pedestal is one mesh with five materials: a precast concrete footing,
a galvanised base plate with anchor nuts, a green cabinet on a black kick
skirt, a hipped lid, a door with hinges, a T-handle and a hazard plate, louvred
side vents, a conduit boss on the +X face and a sleeve in the pad. It is
authored the way an import often arrives: origin at the geometric centre and
coordinates divided by a non-uniform object scale. The bake lands it on
exactly the designed shape. The accessory is a flanged PVC conduit elbow
with bolt heads, a strap clamp and a coupling that drops into the sleeve.

**The render.** Two baked pedestals stand on a sidewalk slab. On the left the elbow is
parented with MPI and stays bolted to its boss, seated in the sleeve. On the
right, bare `child.parent = parent` applies the pedestal's transform a
second time. The elbow is thrown 0.65 m, past the slab edge and into the
air, and a glowing cyan outline (a Wireframe modifier on a copy)
marks the seat it left. The slab raises both origins 0.20 m, so the doubled
translation lifts the elbow instead of sliding it along the floor. A
pivot ring on the floor is centred on each pedestal's origin, with red
notches on its X axis and green notches on Y. The origin is under the base,
so the ring frames it. There are no text labels: the ghost and the stranded
elbow carry the proof. The check's closed forms are unchanged.

## Run

```bash
blender --background --python prop_origin_transform.py --
blender --background --python prop_origin_transform.py -- --skip-mpi
blender --background --python prop_origin_transform.py -- --output origin.png
blender --background --python prop_origin_transform.py -- --output origin.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Stale `matrix_world` contract broken |
| 4 | World bbox moved across bake |
| 5 | Scale after bake is not (1,1,1) |
| 6 | Origin not at local base center |
| 7 | Bare parenting did not jump |
| 8 | MPI did not restore world location (`--skip-mpi` lands here) |
| 9 | `--output` produced no file |
| 10 | Gallery framing violation |
| 11 | Gallery asset-quality violation (render path only) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--skip-mpi`.

