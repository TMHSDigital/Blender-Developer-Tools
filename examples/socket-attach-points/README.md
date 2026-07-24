# Socket Attach Points

A runnable example building the thing a spawn system actually leans on:
**named socket empties parented into an asset**, so a module dropped onto a
socket with an *identity local transform* lands exactly where the artist put
it, oriented the way the naming convention promises. Every clause in that
sentence is a matrix identity, and every one of them drifts silently — a
skipped `matrix_parent_inverse`, a basis built with the cross product the
wrong way round, a transform frozen on the parent after the sockets were
placed.

**The asset, for reuse:** `Drone.Survey`, an 0.86 m span survey quadcopter —
a lofted fuselage with a vented deck and canopy face, four canted booms with
finned motor cans and nav lights, and a two-rail landing gear. Seven mount
pads carry seven sockets, and four interchangeable modules seat on them:

| Socket | Mount normal | Module |
| --- | --- | --- |
| `SKT_Rotor.FL/FR/RL/RR` | 8° canted outward | `Mod.Rotor` (twisted, tapered blades) |
| `SKT_Camera` | belly, −Z | `Mod.CamPod` (gimbal ball + lens) |
| `SKT_Mast` | dorsal, +Z | `Mod.Mast` (antenna, dish, beacon) |
| `SKT_Battery` | rear, tilted down | `Mod.Battery` (cell block + gauge) |

Origin is the skid contact plane centre (`z == 0` is where it rests, `+X` is
forward), transforms are identity by construction, datablocks live under
`Drone.Survey.*` and `SKT_*`, and accents are per-face material slots rather
than extra objects. To use it: instantiate a module, parent it to the socket,
zero the local transform. That is the whole API — and it only works because
the socket matrices hold.

**Socket convention** (encoded in the `SKT_` prefix):

- **+Z** — the outward mount normal, matching the mount pad's own face normal.
- **+Y** — the module's up reference: chassis +Z orthogonalised against the
  socket normal, falling back to chassis +X when the normal is parallel to
  chassis up (the belly and dorsal mounts take that branch).
- **+X** — `Y × Z`, so the basis is right-handed (`det == +1`).

**Pipeline arc neighbours:** pivot and origin discipline in
[`prop-origin-transform`](../prop-origin-transform/), parent-inverse under
animation in [`parent-inverse-orrery`](../parent-inverse-orrery/), tile-grid
boundary contracts in [`modular-kit-snap`](../modular-kit-snap/), collision
packaging in [`collision-hull-proxy`](../collision-hull-proxy/).

**What it witnesses** (all closed form or independently re-derived):

- **Socket matrices.** All **7** evaluated `matrix_world` values equal
  `root.matrix_world @ authored_local` within **1e-6** (measured
  **1.788e-07**); every basis is orthonormal (Gram error **3.576e-07**) and
  right-handed (`det − 1` = **2.980e-07**).
- **Orientation vs geometry.** Each socket's world **+Z** equals the **Newell
  normal** of its mount pad's mount face — computed from raw vertex
  coordinates, and the pad mesh is built by a *quaternion swing from +Z*
  while the socket basis is built by *explicit Gram-Schmidt*, so the two
  derivations are independent (normal deviation **1.794e-07**). The socket
  origin sits on that face's centroid (**6.687e-08**), and the up axis
  matches the documented fallback rule (**1.943e-07**).
- **Seating.** Every module's mount origin coincides with its socket origin
  (offset **exactly 0.0**) with its mount axis on the socket +Z
  (`dot − 1` = **1.735e-07**), and carries a strictly identity local matrix —
  seated by the socket, not nudged into place.
- **Rigid invariance.** Re-posing the chassis root to a second arbitrary
  transform moves every socket to `root.matrix_world @ authored_local`
  (**2.384e-07**) and every module stays on its socket (**0.0**).
- **Transform apply.** Freezing loc/rot/scale on the root leaves every socket's
  *world* matrix put (**2.235e-07**) — see the hazard below for what it does
  to the *local* ones.
- **Reuse hygiene.** 14 chassis parts at identity scale, `Drone.Survey.*` /
  `SKT_*` names, no default datablocks, `min z == 0.00e+00`.

## Hazards found while authoring

- **Applying a transform on an Empty root pushes it down into the children.**
  An Empty has no object data to bake into, so `transform_apply` on the root
  resets **7/7** children's `matrix_parent_inverse` to identity and hands each
  child the root's scale locally (measured **0.35** for an applied 1.35).
  World matrices survive to float32; *local* transforms do not. A spawn system
  that reads `matrix_local`, or an exporter that trusts "transforms are
  applied", reads different numbers after an artist freezes the rig. Both
  halves are asserted, so the behaviour cannot change under us silently.
- **Only the root may be selected during the apply.** A child left selected
  gets the parent transform applied twice — measured **2.335 m** of socket
  drift on this asset.
- **`bm.normal_update()` does not fix winding.** It recomputes normals from
  the existing winding. The lofted fuselage wound its side quads inward and
  rendered as a flat unshaded white panel rather than an obvious hole;
  `bmesh.ops.recalc_face_normals` is what fixes it, and `Part.finish` now
  always calls it.
- **Bevel offsets near half the local edge length collapse.** The skid rails
  at a 5 mm offset on a 9.9 mm octagon edge produced 3 zero-area faces each —
  the collapse [`degenerate-bevel-weld`](../degenerate-bevel-weld/) witnesses.
  2.2 mm is clean. Note that `examples/gallery_asset_quality.py` raises
  `ValueError: zero length vectors have no valid angle` on such a mesh rather
  than reporting it.

**What each check catches on failure** (every one probed, with the measured
error): sockets parented without the parent-inverse — worst jump **0.690128 m**
(exit 3); a left-handed basis from `z.cross(y)` — `det == −1.000000` (exit 3);
a rotor pad built flat instead of canted — **1.395e-01** off the Newell normal
(exit 4); an 11° roll on the basis — **1.917e-01** off the up rule (exit 4); a
module nudged 4 mm off its socket (exit 5); a default `Cube` datablock name
(exit 6); a socket left unparented so it ignores the re-pose — **1.417e+00**
(exit 7); a child selected during the apply — **1.252e+00** to **2.244e+00** of
socket drift (exit 8).

**Version witness:** check output is byte-identical on Blender 4.5.11 LTS and
5.1.2 — same counts, same measured deviations to every printed digit, and the
same framing numbers on the render path.

**Render as proof:** the drone on the dark stage with every module seated, the
orange mount pads reading as the socket signature. The falsification variant
(`--falsify`) parents the sockets without `matrix_parent_inverse`: the pads
are left bare, the rotors and mast vanish from the airframe, and the camera
pod and battery hang in space near the top of frame. A broken matrix is not a
subtle pixel difference here — the asset comes apart.

## Run

```bash
blender --background --python socket_attach_points.py --
blender --background --python socket_attach_points.py -- --output drone.png
blender --background --python socket_attach_points.py -- --falsify adrift.png
blender --background --python socket_attach_points.py -- --probe
```

Exits non-zero on failure. The `blender-smoke` workflow runs the check on
Blender 4.5 LTS and 5.1. The `--output` render path additionally gates framing
via `examples/gallery_framing.py` (fill **0.881x**, margins
**0.066/0.053/0.122/0.106**, no edge touched) and the asset floors via
`examples/gallery_asset_quality.py` (32 materials, `edge90` **0.027**, no
default names). The `--falsify` render is a diagnostic, not a gallery hero, so
it takes a documented framing deviation — its whole point is that the modules
leave the frame.
