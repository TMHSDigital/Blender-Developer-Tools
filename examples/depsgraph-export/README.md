# Depsgraph-Evaluated Export

A runnable example that proves **modifiers actually ship in exports** and demonstrates the
[`depsgraph-and-evaluated-data`](../../skills/depsgraph-and-evaluated-data/SKILL.md) lifetime
contract. It builds a cube with a SUBSURF modifier, measures the evaluated mesh via
`evaluated_get().to_mesh()` (paired with `to_mesh_clear()`), exports through `wm.obj_export`,
and asserts the exported vertex count equals the **evaluated** (modifier-applied) count and is
strictly greater than the base mesh.

**What it witnesses:** the `evaluated_get` → `to_mesh` → `to_mesh_clear` contract, and that
`wm.obj_export` writes the depsgraph-evaluated geometry (so modifiers are baked into the
export) rather than the unmodified base mesh.

## Run

```bash
# Cheap correctness check (writes an OBJ to a temp path, asserts the counts) — the CI check:
blender --background --python depsgraph_export.py --

# Write the exported OBJ to a specific path:
blender --background --python depsgraph_export.py -- --output remeshed.obj
```

It exits non-zero on failure (modifier not applied, or exported count ≠ evaluated count). The
`blender-smoke` workflow runs this check on Blender 4.5 LTS and 5.1: base 8 → evaluated/exported
98 vertices with a 2-level SUBSURF.
