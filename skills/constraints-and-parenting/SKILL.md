---
name: constraints-and-parenting
description: "Parent objects without moving them, aim them with constraints, and author empties as engine attach sockets, all on the data API: child.parent plus matrix_parent_inverse = parent.matrix_world.inverted(), stale matrix_world until view_layer.update(), Object.constraints.new('DAMPED_TRACK') read back through the evaluated depsgraph, right-handed socket bases, and the transform_apply-on-an-Empty-root hazard. Use when a child teleports after `.parent =`, matrix_world reads old values, a script calls bpy.ops.object.constraint_add in a loop, an aim constraint rolls or does nothing, or a spawn system seats modules on SKT_ socket empties with an identity local transform. Targets 5.2 LTS with 4.5 LTS fallback."
standards-version: 1.10.0
---

# Constraints, parenting and attach sockets

## Trigger

Use this skill when the user:

- Parents objects from Python with `child.parent = ...` and the child jumps
- Mentions `matrix_parent_inverse`, `matrix_world`, `matrix_basis`, or `matrix_local`
- Reads `matrix_world` right after editing `location` / `rotation_euler` and gets old numbers
- Adds constraints (`DAMPED_TRACK`, `TRACK_TO`) or calls `bpy.ops.object.constraint_add` in a loop
- Builds named socket empties (`SKT_*`) that a game engine or spawn system attaches modules to
- Freezes a rig with `transform_apply` and the children's local transforms change

## High-level shape

```python
import bpy

def parent_keep_world(child, parent):
    """Parent without moving the child (both already linked to the scene)."""
    bpy.context.view_layer.update()            # parent.matrix_world must be current
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()

def aim_at(ob, target):
    con = ob.constraints.new("DAMPED_TRACK")   # data API, no active object needed
    con.target = target
    con.track_axis = "TRACK_Z"
    return con
```

Read results back from an updated scene: `view_layer.update()` before trusting `matrix_world`, or `ob.evaluated_get(depsgraph).matrix_world` for the constrained pose.

None of the calls in this skill diverge between 4.5 LTS and 5.x: the three examples run the same code on both, and `socket-attach-points` check output is byte-identical on 4.5.11 LTS and 5.1.2. No version branch is needed.

## Parenting: `.parent` alone moves the child

`child.parent = p` keeps the child's *local* matrix and re-reads it in `p`'s space. If the child was placed in world space and `p` has any transform, the child teleports. `parent-inverse-orrery` asserts that the bare-parented probe jumps more than 0.5 units. In `socket-attach-points`, sockets parented without the inverse jumped up to **0.690 m**.

The keep-world idiom stores `p.matrix_world.inverted()` in `matrix_parent_inverse`, so world = `p.matrix_world @ matrix_parent_inverse @ matrix_basis` and starts out as it was. The orrery measures the restored position within 1e-5. Afterwards the child follows the parent rigidly: every planet and the two-level moon land on their closed-form orbit positions after the pivots spin.

Bare `.parent =` is correct when the child's transform is **already authored in parent space**. Examples: chassis parts modeled in chassis-local coordinates, or a module seated on a socket (below).

<!-- smoke: run -->
```python
import bpy, math
from mathutils import Vector

scene = bpy.context.scene
view_layer = bpy.context.view_layer

pivot = bpy.data.objects.new("Pivot", None)          # None data -> EMPTY
pivot.location = (0.0, 0.0, 1.0)
pivot.rotation_euler = (0.0, 0.0, 0.7)
scene.collection.objects.link(pivot)
child = bpy.data.objects.new("Child", None)
child.location = (2.0, 0.0, 0.0)
scene.collection.objects.link(child)
view_layer.update()
w0 = child.matrix_world.translation.copy()

child.parent = pivot                                 # bare: local re-read in pivot space
view_layer.update()
assert (child.matrix_world.translation - w0).length > 0.5

child.matrix_parent_inverse = pivot.matrix_world.inverted()
view_layer.update()
assert (child.matrix_world.translation - w0).length < 1e-5

pivot.rotation_euler.z += 0.5                        # child now orbits with the pivot
view_layer.update()
want = Vector((2.0 * math.cos(0.5), 2.0 * math.sin(0.5), 0.0))
assert (child.matrix_world.translation - want).length < 1e-5

before = child.matrix_world.translation.copy()
child.location.x += 1.0                              # matrix_world is stale here
assert (child.matrix_world.translation - before).length < 1e-6
view_layer.update()
assert (child.matrix_world.translation - before).length > 0.5
```

## `matrix_world` is the last-evaluated matrix

After any transform edit, `matrix_world` keeps its old value until `bpy.context.view_layer.update()`. The orrery asserts both halves. That covers the inverse too: it is computed from `parent.matrix_world`, so update after placing the parent and before taking `.inverted()`. Otherwise you bake a stale matrix into the child.

## Aim constraints: `DAMPED_TRACK` on the data API

Add constraints with `ob.constraints.new("DAMPED_TRACK")`, not `bpy.ops.object.constraint_add`. The operator needs an active object and breaks in headless loops. Damped Track points one local axis at the target without the roll fights Track To is known for. Use `TRACK_TO` with `up_axis` only when roll must be pinned, as the example camera rig does with `track_axis="TRACK_NEGATIVE_Z"` and `up_axis="UP_Y"`.

Check the **evaluated** pose, not the flags. `damped-track-aim` samples `ob.evaluated_get(depsgraph).matrix_world`. Each head's local +Z must point at the target (dot >= 0.998). Its `--mute` falsifier is caught by that aim dot, not by reading back `con.mute`.

<!-- smoke: run -->
```python
import bpy
from mathutils import Vector

scene = bpy.context.scene
target = bpy.data.objects.new("Target", None)
target.location = (0.0, 0.0, 2.0)
scene.collection.objects.link(target)

heads = []
for x, z in ((3.0, 0.5), (-2.0, 3.5), (0.5, -1.0)):
    ob = bpy.data.objects.new(f"Head_{len(heads)}", None)
    ob.location = (x, 1.0, z)
    ob.rotation_euler = (0.0, 0.0, 0.0)              # the constraint alone must aim it
    scene.collection.objects.link(ob)
    con = ob.constraints.new("DAMPED_TRACK")
    con.target = target
    con.track_axis = "TRACK_Z"
    heads.append(ob)

bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
goal = target.evaluated_get(dg).matrix_world.translation
for ob in heads:
    mw = ob.evaluated_get(dg).matrix_world
    lens = (mw.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    assert lens.dot((goal - mw.translation).normalized()) >= 0.998, ob.name
```

## Empties as attach sockets

A socket is a named Empty (`bpy.data.objects.new("SKT_Camera", None)`) parented into the asset. Under the `socket-attach-points` convention, +Z is the outward mount normal and +Y is the module's up reference. +X is `Y x Z`, so the basis is right-handed (`det == +1`). Author the socket in world space, then parent it with the keep-world idiom:

```python
from mathutils import Matrix, Vector

def socket_basis(normal, up=Vector((0, 0, 1)), fwd=Vector((1, 0, 0))):
    z = Vector(normal).normalized()
    ref = fwd if abs(z.dot(up)) > 0.999 else up      # fall back when normal ~ up
    y = (ref - z * ref.dot(z)).normalized()
    x = y.cross(z)                                   # z.cross(y) gives det == -1
    return Matrix((x, y, z)).transposed()

def add_socket(root, name, centre, normal):
    local = socket_basis(normal).to_4x4()
    local.translation = Vector(centre)
    skt = bpy.data.objects.new(name, None)
    skt.empty_display_type = "ARROWS"
    bpy.context.scene.collection.objects.link(skt)
    skt.matrix_world = root.matrix_world @ local
    bpy.context.view_layer.update()
    skt.parent = root
    skt.matrix_parent_inverse = root.matrix_world.inverted()
    return skt

def seat(module, skt):
    module.parent = skt
    module.matrix_parent_inverse = Matrix.Identity(4)
    module.matrix_basis = Matrix.Identity(4)         # lands exactly on the socket
```

The example's measured contract: every socket's evaluated `matrix_world` equals `root.matrix_world @ authored_local` within 1e-6, both at the authored pose and after the root is re-posed. A seated module's origin sits on its socket origin with offset exactly 0.0. That example stops at the Blender side and does not export. For the export side (glTF `export_yup`, FBX axes, unparenting before `transform_apply`), see `engine-export-presets`.

### Hazard: `transform_apply` on an Empty root

An Empty has no data to bake into, so applying loc/rot/scale on the root pushes the transform **down** into the children. All 7/7 socket `matrix_parent_inverse` values reset to identity, and the children take on the root's scale locally (0.35 for an applied 1.35). World matrices survive to float32. Local ones do not, so anything that reads `matrix_local` after an artist freezes the rig gets different numbers. Select **only** the root: a child left selected gets the parent transform applied twice, measured at **2.335 m** of socket drift.

```python
for ob in bpy.context.selected_objects:
    ob.select_set(False)
root.select_set(True)
bpy.context.view_layer.objects.active = root
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
```

## Common AI mistakes

1. **`child.parent = p` with nothing else** for a child placed in world space. The child teleports. Set `matrix_parent_inverse = p.matrix_world.inverted()` too.

2. **Reading `matrix_world` right after a transform edit.** It is stale until `bpy.context.view_layer.update()`.

3. **Taking the inverse from a stale parent matrix.** Update after posing the parent, then call `.inverted()`.

4. **The keep-world idiom on a module meant to seat.** Seating means identity `matrix_parent_inverse` *and* identity `matrix_basis`. Keep-world leaves the module wherever it spawned.

5. **`bpy.ops.object.constraint_add` in a loop.** It needs an active object and fails headless. Use `ob.constraints.new("DAMPED_TRACK")`.

6. **`TRACK_TO` for a pure aim.** It needs an up axis and fights roll. `DAMPED_TRACK` points one axis without that.

7. **Asserting `con.mute` / `con.target` instead of the pose.** A flag read-back cannot see a flipped axis. Check `evaluated_get(depsgraph).matrix_world`.

8. **`x = z.cross(y)` for a socket basis.** It produces a left-handed basis (`det == -1`). Use `x = y.cross(z)`.

9. **`transform_apply` on an Empty root, then trusting local transforms**, or running it with children selected. See the hazard above.

## See also

- Example [`damped-track-aim`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/damped-track-aim): twelve heads aimed by `DAMPED_TRACK`, checked on the evaluated depsgraph.
- Example [`parent-inverse-orrery`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/parent-inverse-orrery): the bare-parent jump, the keep-world fix, stale `matrix_world`, and closed-form orbits through a two-level hierarchy.
- Example [`socket-attach-points`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/socket-attach-points): `SKT_*` socket empties, right-handed bases, module seating, re-pose and `transform_apply` hazards.
- Skill `depsgraph-and-evaluated-data`: `evaluated_get` and the depsgraph lifetime.
- Skill `engine-export-presets`: unparenting and applying transforms before glTF / FBX export.

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`damped-track-aim`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/damped-track-aim): Aim constraints via the data API — Object.constraints.new('DAMPED_TRACK') with target and TRACK_Z, not bpy.ops.object.constraint_add in a headless loop. Falsify: `--mute` (exit 9).
- [`parent-inverse-orrery`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/parent-inverse-orrery): Data-API parenting for a brass orrery — the keep-world idiom (child.parent = pivot; child.matrix_parent_inverse = pivot.matrix_world.inverted()) carrying arms. Falsify: `--skip-mpi` (exit 6).
- [`socket-attach-points`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/socket-attach-points): A survey drone whose named SKT_ empties are the spawn contract: modules parented with an identity local transform seat exactly on their mount pads. Falsify: `--skip-mpi` (exit 3).

<!-- examples:end -->

## References

- `bpy.types.Object` (`parent`, `matrix_parent_inverse`, `matrix_world`, `matrix_basis`, `constraints`): https://docs.blender.org/api/current/bpy.types.Object.html
- `bpy.types.ObjectConstraints` (`new`): https://docs.blender.org/api/current/bpy.types.ObjectConstraints.html
- `bpy.types.DampedTrackConstraint`: https://docs.blender.org/api/current/bpy.types.DampedTrackConstraint.html
- `bpy.types.Depsgraph`: https://docs.blender.org/api/current/bpy.types.Depsgraph.html
- 4.5 LTS `Object`: https://docs.blender.org/api/4.5/bpy.types.Object.html
- 4.5 LTS `ObjectConstraints`: https://docs.blender.org/api/4.5/bpy.types.ObjectConstraints.html
- 4.5 LTS `DampedTrackConstraint`: https://docs.blender.org/api/4.5/bpy.types.DampedTrackConstraint.html
